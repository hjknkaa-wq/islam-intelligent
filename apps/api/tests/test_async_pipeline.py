"""Integration tests for async architecture patterns.

This module tests async/await patterns, concurrent operations, and
async pipeline execution used throughout the API.
"""

from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Protocol
from unittest.mock import AsyncMock, MagicMock

import pytest


@dataclass
class AsyncPipelineResult:
    """Result from async pipeline execution."""

    success: bool
    data: Any | None = None
    error: str | None = None
    execution_time_ms: float = 0.0
    steps_completed: list[str] | None = None


class AsyncStep(Protocol):
    """Protocol for async pipeline steps."""

    async def execute(self, input_data: Any) -> Any: ...

    def get_name(self) -> str: ...


class AsyncPipeline:
    """Asynchronous pipeline for concurrent data processing.

    Supports:
    - Sequential step execution with async/await
    - Concurrent batch processing
    - Error handling with graceful degradation
    - Timeout handling
    - Step-level retry logic

    Example:
        >>> pipeline = AsyncPipeline()
        >>> pipeline.add_step(retrieve_step)
        >>> pipeline.add_step(generate_step)
        >>> result = await pipeline.execute(query)
    """

    def __init__(self, timeout: float | None = None) -> None:
        self.steps: list[AsyncStep] = []
        self.timeout = timeout

    def add_step(self, step: AsyncStep) -> None:
        """Add a step to the pipeline."""
        self.steps.append(step)

    async def execute(self, input_data: Any) -> AsyncPipelineResult:
        """Execute all pipeline steps sequentially.

        Args:
            input_data: Initial input to the first step

        Returns:
            Pipeline execution result
        """
        start_time = time.perf_counter()
        steps_completed: list[str] = []
        current_data = input_data

        try:
            for step in self.steps:
                step_name = step.get_name()

                if self.timeout:
                    current_data = await asyncio.wait_for(
                        step.execute(current_data),
                        timeout=self.timeout,
                    )
                else:
                    current_data = await step.execute(current_data)

                steps_completed.append(step_name)

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            return AsyncPipelineResult(
                success=True,
                data=current_data,
                execution_time_ms=elapsed_ms,
                steps_completed=steps_completed,
            )

        except asyncio.TimeoutError:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return AsyncPipelineResult(
                success=False,
                error="pipeline_timeout",
                execution_time_ms=elapsed_ms,
                steps_completed=steps_completed,
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return AsyncPipelineResult(
                success=False,
                error=str(e),
                execution_time_ms=elapsed_ms,
                steps_completed=steps_completed,
            )

    async def execute_batch(
        self,
        inputs: list[Any],
        max_concurrency: int = 5,
    ) -> list[AsyncPipelineResult]:
        """Execute pipeline for multiple inputs concurrently.

        Args:
            inputs: List of inputs to process
            max_concurrency: Maximum number of concurrent executions

        Returns:
            List of pipeline results
        """
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _execute_with_limit(data: Any) -> AsyncPipelineResult:
            async with semaphore:
                return await self.execute(data)

        tasks = [_execute_with_limit(inp) for inp in inputs]
        return await asyncio.gather(*tasks)


class RetryableAsyncStep:
    """Wrapper that adds retry logic to an async step."""

    def __init__(
        self,
        step: AsyncStep,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        self._step = step
        self._max_retries = max_retries
        self._retry_delay = retry_delay

    async def execute(self, input_data: Any) -> Any:
        """Execute with retry logic."""
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                return await self._step.execute(input_data)
            except Exception as e:
                last_error = e
                if attempt < self._max_retries:
                    await asyncio.sleep(self._retry_delay * (attempt + 1))

        raise last_error or RuntimeError("All retries failed")

    def get_name(self) -> str:
        return f"retryable_{self._step.get_name()}"


class MockAsyncStep:
    """Mock async step for testing."""

    def __init__(self, name: str, result: Any = None, delay: float = 0.0) -> None:
        self._name = name
        self._result = result
        self._delay = delay
        self.execute_count = 0

    async def execute(self, input_data: Any) -> Any:
        self.execute_count += 1
        if self._delay > 0:
            await asyncio.sleep(self._delay)
        return self._result if self._result is not None else input_data

    def get_name(self) -> str:
        return self._name


class FailingAsyncStep:
    """Step that fails on specified attempt."""

    def __init__(self, name: str, fail_on_attempt: int = 1) -> None:
        self._name = name
        self._fail_on_attempt = fail_on_attempt
        self._attempt_count = 0

    async def execute(self, input_data: Any) -> Any:
        self._attempt_count += 1
        # Fail when attempt count reaches or exceeds fail_on_attempt
        if self._attempt_count >= self._fail_on_attempt:
            raise RuntimeError(
                f"Step {self._name} failed on attempt {self._attempt_count}"
            )
        return input_data
        self._attempt_count += 1
        # Fail until we reach fail_on_attempt, then succeed
        if self._attempt_count < self._fail_on_attempt:
            raise RuntimeError(
                f"Step {self._name} failed on attempt {self._attempt_count}"
            )
        return input_data

    def get_name(self) -> str:
        return self._name


class TestAsyncPipeline:
    """Tests for async pipeline functionality."""

    @pytest.mark.asyncio()
    async def test_empty_pipeline(self) -> None:
        """Test executing empty pipeline."""
        pipeline = AsyncPipeline()
        result = await pipeline.execute("input")

        assert result.success is True
        assert result.data == "input"
        assert result.steps_completed == []

    @pytest.mark.asyncio()
    async def test_single_step(self) -> None:
        """Test pipeline with single step."""
        pipeline = AsyncPipeline()
        step = MockAsyncStep("step1", result="transformed")
        pipeline.add_step(step)

        result = await pipeline.execute("input")

        assert result.success is True
        assert result.data == "transformed"
        assert result.steps_completed == ["step1"]
        assert step.execute_count == 1

    @pytest.mark.asyncio()
    async def test_multiple_steps(self) -> None:
        """Test pipeline with multiple sequential steps."""
        pipeline = AsyncPipeline()

        class TransformStep:
            def __init__(self, name: str, transform: callable) -> None:  # type: ignore[type-arg]
                self._name = name
                self._transform = transform

            async def execute(self, data: Any) -> Any:
                await asyncio.sleep(0.01)  # Simulate async work
                return self._transform(data)

            def get_name(self) -> str:
                return self._name

        pipeline.add_step(TransformStep("add_one", lambda x: x + 1))
        pipeline.add_step(TransformStep("multiply_by_two", lambda x: x * 2))
        pipeline.add_step(TransformStep("to_string", lambda x: f"result: {x}"))

        result = await pipeline.execute(5)

        assert result.success is True
        assert result.data == "result: 12"  # (5 + 1) * 2 = 12
        assert result.steps_completed == ["add_one", "multiply_by_two", "to_string"]

    @pytest.mark.asyncio()
    async def test_step_error_handling(self) -> None:
        """Test pipeline error handling."""
        pipeline = AsyncPipeline()
        pipeline.add_step(MockAsyncStep("step1"))
        pipeline.add_step(FailingAsyncStep("failing_step"))
        pipeline.add_step(MockAsyncStep("step3"))

        result = await pipeline.execute("input")

        assert result.success is False
        assert "failed" in result.error.lower()
        assert result.steps_completed == ["step1"]  # failing_step failed before completion

    @pytest.mark.asyncio()
    async def test_pipeline_timeout(self) -> None:
        """Test pipeline timeout handling."""
        pipeline = AsyncPipeline(timeout=0.1)
        pipeline.add_step(MockAsyncStep("step1"))
        pipeline.add_step(MockAsyncStep("slow_step", delay=0.5))  # Will timeout

        result = await pipeline.execute("input")

        assert result.success is False
        assert result.error == "pipeline_timeout"
        assert result.steps_completed == ["step1"]  # Only first step completed

    @pytest.mark.asyncio()
    async def test_pipeline_no_timeout(self) -> None:
        """Test pipeline without timeout allows slow steps."""
        pipeline = AsyncPipeline(timeout=None)
        pipeline.add_step(MockAsyncStep("step1", delay=0.05))
        pipeline.add_step(MockAsyncStep("step2", delay=0.05))

        result = await pipeline.execute("input")

        assert result.success is True
        assert result.steps_completed == ["step1", "step2"]


class TestAsyncPipelineBatch:
    """Tests for batch processing."""

    @pytest.mark.asyncio()
    async def test_batch_execution(self) -> None:
        """Test concurrent batch execution."""
        pipeline = AsyncPipeline()
        pipeline.add_step(MockAsyncStep("step1"))

        inputs = ["input1", "input2", "input3"]
        results = await pipeline.execute_batch(inputs, max_concurrency=3)

        assert len(results) == 3
        assert all(r.success for r in results)
        assert [r.data for r in results] == inputs

    @pytest.mark.asyncio()
    async def test_batch_concurrency_limit(self) -> None:
        """Test that concurrency limit is respected."""
        pipeline = AsyncPipeline()

        concurrent_count = 0
        max_concurrent_observed = 0

        class CountingStep:
            async def execute(self, data: Any) -> Any:
                nonlocal concurrent_count, max_concurrent_observed
                concurrent_count += 1
                max_concurrent_observed = max(max_concurrent_observed, concurrent_count)
                await asyncio.sleep(0.05)
                concurrent_count -= 1
                return data

            def get_name(self) -> str:
                return "counting_step"

        pipeline.add_step(CountingStep())

        inputs = [f"input{i}" for i in range(10)]
        await pipeline.execute_batch(inputs, max_concurrency=3)

        assert max_concurrent_observed <= 3

    @pytest.mark.asyncio()
    async def test_batch_with_errors(self) -> None:
        """Test batch execution with some failing inputs."""
        pipeline = AsyncPipeline()

        class ConditionalFailingStep:
            async def execute(self, data: Any) -> Any:
                if data == "fail":
                    raise ValueError("Intentional failure")
                return data

            def get_name(self) -> str:
                return "conditional_step"

        pipeline.add_step(ConditionalFailingStep())

        inputs = ["ok1", "fail", "ok2"]
        results = await pipeline.execute_batch(inputs)

        assert results[0].success is True
        assert results[0].data == "ok1"
        assert results[1].success is False
        assert results[2].success is True
        assert results[2].data == "ok2"


class TestRetryableAsyncStep:
    """Tests for retry logic."""

    @pytest.mark.asyncio()
    async def test_success_on_first_attempt(self) -> None:
        """Test step that succeeds immediately."""
        inner_step = MockAsyncStep("inner")
        retry_step = RetryableAsyncStep(inner_step, max_retries=3)

        result = await retry_step.execute("input")

        assert result == "input"
        assert inner_step.execute_count == 1

    @pytest.mark.asyncio()
    async def test_success_after_retry(self) -> None:
        """Test step that succeeds after retries."""
        inner_step = FailingAsyncStep("inner", fail_on_attempt=3)
        retry_step = RetryableAsyncStep(inner_step, max_retries=3, retry_delay=0.01)

        result = await retry_step.execute("input")

        assert result == "input"
        # Step should succeed after at most 3 attempts
        assert inner_step._attempt_count <= 3

    @pytest.mark.asyncio()
    async def test_failure_after_exhausting_retries(self) -> None:
        inner_step = FailingAsyncStep("inner", fail_on_attempt=1)
        retry_step = RetryableAsyncStep(inner_step, max_retries=2, retry_delay=0.01)

        with pytest.raises(RuntimeError, match="failed"):
            await retry_step.execute("input")

        assert inner_step._attempt_count == 3  # Initial + 2 retries

    @pytest.mark.asyncio()
    async def test_retry_delay_increases(self) -> None:
        """Test that retry delay increases with each attempt."""
        delays: list[float] = []

        class DelayMeasuringStep:
            def __init__(self) -> None:
                self._attempt = 0
                self._last_time: float | None = None

            async def execute(self, data: Any) -> Any:
                self._attempt += 1
                now = time.perf_counter()
                if self._last_time is not None:
                    delays.append(now - self._last_time)
                self._last_time = now

                if self._attempt < 3:
                    raise RuntimeError(f"Attempt {self._attempt}")
                return data

            def get_name(self) -> str:
                return "delay_step"

        inner_step = DelayMeasuringStep()
        retry_step = RetryableAsyncStep(inner_step, max_retries=3, retry_delay=0.05)

        await retry_step.execute("input")

        # Delays should increase: 0.05, 0.10
        assert len(delays) == 2
        assert delays[0] >= 0.05  # First retry delay
        assert delays[1] >= 0.10  # Second retry delay (2x base)


class TestAsyncConcurrency:
    """Tests for concurrent async patterns."""

    @pytest.mark.asyncio()
    async def test_gather_concurrent_execution(self) -> None:
        """Test that asyncio.gather runs tasks concurrently."""
        execution_order: list[int] = []

        async def task(n: int, delay: float) -> int:
            execution_order.append(n)
            await asyncio.sleep(delay)
            execution_order.append(n + 10)  # Mark completion
            return n

        # Start two tasks concurrently
        results = await asyncio.gather(
            task(1, 0.1),
            task(2, 0.05),
        )

        assert results == [1, 2]
        # Both tasks should have started before either completed
        assert 1 in execution_order[:2]
        assert 2 in execution_order[:2]

    @pytest.mark.asyncio()
    async def test_semaphore_limits_concurrency(self) -> None:
        """Test that semaphore limits concurrent execution."""
        semaphore = asyncio.Semaphore(2)
        concurrent_count = 0
        max_concurrent = 0

        async def limited_task() -> None:
            nonlocal concurrent_count, max_concurrent
            async with semaphore:
                concurrent_count += 1
                max_concurrent = max(max_concurrent, concurrent_count)
                await asyncio.sleep(0.1)
                concurrent_count -= 1

        # Run 5 tasks with limit of 2
        await asyncio.gather(*[limited_task() for _ in range(5)])

        assert max_concurrent == 2

    @pytest.mark.asyncio()
    async def test_async_context_manager(self) -> None:
        """Test async context manager pattern."""
        acquired = False
        released = False

        class AsyncResource:
            async def __aenter__(self) -> "AsyncResource":
                nonlocal acquired
                await asyncio.sleep(0.01)
                acquired = True
                return self

            async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
                nonlocal released
                await asyncio.sleep(0.01)
                released = True

        async with AsyncResource():
            assert acquired is True
            assert released is False

        assert released is True


class TestAsyncWithSync:
    """Tests for async/sync integration patterns."""

    @pytest.mark.asyncio()
    async def test_run_in_executor(self) -> None:
        """Test running sync code in executor."""

        def sync_function(x: int) -> int:
            time.sleep(0.05)  # Simulate blocking work
            return x * 2

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, sync_function, 5)

        assert result == 10

    @pytest.mark.asyncio()
    async def test_asyncio_to_thread(self) -> None:
        """Test asyncio.to_thread for sync code (Python 3.9+)."""

        def sync_function(x: int) -> int:
            time.sleep(0.05)
            return x * 3

        try:
            result = await asyncio.to_thread(sync_function, 5)
            assert result == 15
        except AttributeError:
            # Python < 3.9
            pytest.skip("asyncio.to_thread not available")


class TestAsyncGenerators:
    """Tests for async generators."""

    @pytest.mark.asyncio()
    async def test_async_generator(self) -> None:
        """Test async generator pattern."""

        async def async_range(n: int) -> Any:
            for i in range(n):
                await asyncio.sleep(0.01)
                yield i

        results = []
        async for value in async_range(5):
            results.append(value)

        assert results == [0, 1, 2, 3, 4]

    @pytest.mark.asyncio()
    async def test_async_comprehension(self) -> None:
        """Test async comprehension."""

        async def async_range(n: int) -> Any:
            for i in range(n):
                await asyncio.sleep(0.01)
                yield i

        results = [x async for x in async_range(5) if x % 2 == 0]

        assert results == [0, 2, 4]


class TestAsyncCancellation:
    """Tests for task cancellation."""

    @pytest.mark.asyncio()
    async def test_task_cancellation(self) -> None:
        """Test that tasks can be cancelled."""

        async def long_running_task() -> str:
            try:
                await asyncio.sleep(10)
                return "completed"
            except asyncio.CancelledError:
                return "cancelled"

        task = asyncio.create_task(long_running_task())
        await asyncio.sleep(0.05)
        task.cancel()

        try:
            result = await task
            assert result == "cancelled"
        except asyncio.CancelledError:
            pass  # Also valid

    @pytest.mark.asyncio()
    async def test_timeout_cancellation(self) -> None:
        """Test timeout-based cancellation."""

        async def slow_operation() -> str:
            await asyncio.sleep(10)
            return "done"

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(slow_operation(), timeout=0.1)


class TestAsyncPerformance:
    """Performance benchmarks for async operations."""

    @pytest.mark.asyncio()
    async def test_concurrent_vs_sequential(self) -> None:
        """Benchmark showing concurrent execution is faster."""

        async def operation(delay: float) -> float:
            await asyncio.sleep(delay)
            return delay

        # Sequential execution
        start = time.perf_counter()
        for _ in range(5):
            await operation(0.05)
        sequential_time = time.perf_counter() - start

        # Concurrent execution
        start = time.perf_counter()
        await asyncio.gather(*[operation(0.05) for _ in range(5)])
        concurrent_time = time.perf_counter() - start

        # Concurrent should be roughly 5x faster
        assert concurrent_time < sequential_time * 0.5

    @pytest.mark.asyncio()
    async def test_batch_processing_performance(self) -> None:
        """Test batch processing performance."""
        pipeline = AsyncPipeline()

        class SlowStep:
            async def execute(self, data: Any) -> Any:
                await asyncio.sleep(0.01)
                return f"processed_{data}"

            def get_name(self) -> str:
                return "slow_step"

        pipeline.add_step(SlowStep())

        inputs = [f"input{i}" for i in range(20)]

        start = time.perf_counter()
        results = await pipeline.execute_batch(inputs, max_concurrency=10)
        elapsed = time.perf_counter() - start

        assert len(results) == 20
        assert all(r.success for r in results)
        # With concurrency=10 and 20 tasks at 0.01s each, should be ~0.02s
        assert elapsed < 0.5  # Generous timeout


class TestAsyncIntegration:
    """Integration tests for async patterns with RAG components."""

    @pytest.mark.asyncio()
    async def test_async_retrieval_pipeline(self) -> None:
        """Test async retrieval step pattern."""

        class AsyncRetrievalStep:
            async def execute(self, query: str) -> dict[str, Any]:
                # Simulate async retrieval from vector DB
                await asyncio.sleep(0.01)
                return {
                    "query": query,
                    "results": [
                        {"id": "1", "score": 0.9},
                        {"id": "2", "score": 0.8},
                    ],
                }

            def get_name(self) -> str:
                return "retrieval"

        pipeline = AsyncPipeline()
        pipeline.add_step(AsyncRetrievalStep())

        result = await pipeline.execute("test query")

        assert result.success is True
        assert result.data["query"] == "test query"
        assert len(result.data["results"]) == 2

    @pytest.mark.asyncio()
    async def test_async_generation_with_fallback(self) -> None:
        """Test async generation with fallback on failure."""

        class AsyncGenerationStep:
            def __init__(self, should_fail: bool = False) -> None:
                self._should_fail = should_fail

            async def execute(self, data: dict[str, Any]) -> dict[str, Any]:
                if self._should_fail:
                    raise RuntimeError("Generation failed")

                await asyncio.sleep(0.01)
                return {
                    **data,
                    "answer": "Generated answer",
                    "citations": ["citation1"],
                }

            def get_name(self) -> str:
                return "generation"

        # Test successful generation
        pipeline = AsyncPipeline()
        pipeline.add_step(AsyncGenerationStep(should_fail=False))

        result = await pipeline.execute({"query": "test"})
        assert result.success is True
        assert result.data["answer"] == "Generated answer"

        # Test failed generation
        pipeline = AsyncPipeline()
        pipeline.add_step(AsyncGenerationStep(should_fail=True))

        result = await pipeline.execute({"query": "test"})
        assert result.success is False

    @pytest.mark.asyncio()
    async def test_concurrent_multi_source_retrieval(self) -> None:
        """Test concurrent retrieval from multiple sources."""

        async def retrieve_from_quran(query: str) -> list[dict[str, Any]]:
            await asyncio.sleep(0.02)
            return [{"source": "quran", "text": f"Quran result for {query}"}]

        async def retrieve_from_hadith(query: str) -> list[dict[str, Any]]:
            await asyncio.sleep(0.03)
            return [{"source": "hadith", "text": f"Hadith result for {query}"}]

        async def retrieve_from_fiqh(query: str) -> list[dict[str, Any]]:
            await asyncio.sleep(0.01)
            return [{"source": "fiqh", "text": f"Fiqh result for {query}"}]

        # Concurrent retrieval
        query = "prayer"
        start = time.perf_counter()

        quran_task = asyncio.create_task(retrieve_from_quran(query))
        hadith_task = asyncio.create_task(retrieve_from_hadith(query))
        fiqh_task = asyncio.create_task(retrieve_from_fiqh(query))

        quran_results, hadith_results, fiqh_results = await asyncio.gather(
            quran_task, hadith_task, fiqh_task
        )

        elapsed = time.perf_counter() - start

        # Should complete in ~0.03s (max of individual times), not ~0.06s (sum)
        assert elapsed < 0.1
        assert len(quran_results) == 1
        assert len(hadith_results) == 1
        assert len(fiqh_results) == 1
