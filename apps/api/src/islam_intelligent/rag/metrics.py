"""Metrics tracking for RAG pipeline observability.

This module provides comprehensive metrics collection for the RAG pipeline,
enabling monitoring, debugging, and performance analysis of each stage.

Tracked metrics include:
- Latency per pipeline stage
- Retrieval quality (count, scores, sources)
- Generation metrics (tokens, cost)
- Verification results (citations, faithfulness)
- Pipeline outcomes (answers, abstentions, failures)
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Protocol

from ..db.engine import SessionLocal
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)


@dataclass
class RetrievalMetrics:
    """Metrics from the retrieval stage."""

    query: str
    latency_ms: float
    results_count: int
    trusted_count: int
    untrusted_count: int
    avg_score: float
    max_score: float
    min_score: float
    sources: list[str] = field(default_factory=list)
    hyde_used: bool = False
    query_variations: int = 1
    reranker_used: bool = False


@dataclass
class GenerationMetrics:
    """Metrics from the generation stage."""

    latency_ms: float
    statements_count: int
    citations_count: int
    tokens_prompt: int = 0
    tokens_completion: int = 0
    model_used: str = ""
    cost_usd: float = 0.0


@dataclass
class VerificationMetrics:
    """Metrics from verification stages."""

    citation_verification_latency_ms: float = 0.0
    citation_verified: bool = False
    citation_fail_reason: str | None = None
    faithfulness_latency_ms: float = 0.0
    faithfulness_score: float = 0.0
    faithfulness_verified: bool = False
    unfaithful_statements: list[int] = field(default_factory=list)


@dataclass
class RagasScores:
    """RAGAS-like metrics on a 0..1 scale."""

    faithfulness: float = 0.0
    relevancy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0


@dataclass
class RAGPipelineMetrics:
    """Complete metrics for a RAG pipeline execution."""

    query_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    query: str = ""
    pipeline_start_time: datetime = field(default_factory=_utc_now)
    pipeline_end_time: datetime | None = None
    total_latency_ms: float = 0.0

    # Stage outcomes
    retrieval: RetrievalMetrics | None = None
    generation: GenerationMetrics | None = None
    verification: VerificationMetrics | None = None

    # Final result
    verdict: str = ""  # 'answer', 'abstain', 'error'
    abstain_reason: str | None = None
    error_type: str | None = None

    # Cost tracking
    cost_estimate_usd: float = 0.0
    cost_actual_usd: float = 0.0
    cost_governance_applied: bool = False
    cost_degradation_message: str | None = None
    ragas: RagasScores = field(default_factory=RagasScores)

    def finalize(self) -> None:
        """
        Set the pipeline end time to the current UTC time and compute total_latency_ms.
        
        If pipeline_start_time is present, total_latency_ms is set to the elapsed time
        from pipeline_start_time to the new pipeline_end_time in milliseconds. If
        pipeline_start_time is not set, pipeline_end_time is still recorded and
        total_latency_ms is left unchanged.
        """
        self.pipeline_end_time = _utc_now()
        if self.pipeline_start_time:
            self.total_latency_ms = (
                self.pipeline_end_time - self.pipeline_start_time
            ).total_seconds() * 1000

    def to_dict(self) -> dict[str, object]:
        """
        Serialize the pipeline metrics into a JSON-serializable dictionary.
        
        The returned dictionary contains top-level identifiers and timestamps (ISO 8601 strings or `None`), numeric totals (with `total_latency_ms` rounded to two decimals), flattened scalar fields, and nested stage objects converted to plain dictionaries. Dataclass fields that are `None` are represented as `None`; nested dataclasses are converted via the collector's internal `_dataclass_to_dict` helper.
        
        Returns:
            dict[str, object]: A JSON-serializable mapping of the metrics suitable for storage or transmission.
        """
        return {
            "query_id": self.query_id,
            "query": self.query,
            "pipeline_start_time": self.pipeline_start_time.isoformat()
            if self.pipeline_start_time
            else None,
            "pipeline_end_time": self.pipeline_end_time.isoformat()
            if self.pipeline_end_time
            else None,
            "total_latency_ms": round(self.total_latency_ms, 2),
            "retrieval": self._dataclass_to_dict(self.retrieval),
            "generation": self._dataclass_to_dict(self.generation),
            "verification": self._dataclass_to_dict(self.verification),
            "verdict": self.verdict,
            "abstain_reason": self.abstain_reason,
            "error_type": self.error_type,
            "cost_estimate_usd": self.cost_estimate_usd,
            "cost_actual_usd": self.cost_actual_usd,
            "cost_governance_applied": self.cost_governance_applied,
            "cost_degradation_message": self.cost_degradation_message,
            "ragas": self._dataclass_to_dict(self.ragas),
        }

    def _dataclass_to_dict(self, obj: object | None) -> dict[str, object] | None:
        """
        Convert a dataclass-like object's public attributes into a dictionary.
        
        Parameters:
            obj (object | None): An object with a __dict__ attribute (typically a dataclass instance). If None, no conversion is performed.
        
        Returns:
            dict[str, object] | None: A dictionary of the object's public attributes (keys not starting with "_") to their values, or `None` if `obj` is `None`.
        """
        if obj is None:
            return None
        return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}


class MetricsSink(Protocol):
    """Protocol for metrics persistence sinks."""

    def record_metrics(self, metrics: RAGPipelineMetrics) -> None: """
Persist a RAGPipelineMetrics snapshot to the configured database sink.

Parameters:
    metrics (RAGPipelineMetrics): The metrics object to persist; nested dataclasses will be serialized into JSON blobs and timestamps formatted as ISO strings.

Notes:
    - Inserts a row into the `rag_metrics_log` table containing serialized retrieval, generation, verification, ragas fields and top-level metric columns.
    - Commits the transaction on success; on SQLAlchemyError the session is rolled back and the error is logged (the exception is not propagated).
"""
...


class DatabaseMetricsSink:
    """Persist metrics to the database."""

    def __init__(self, session_factory=SessionLocal) -> None:
        """
        Initialize the DatabaseMetricsSink with a session factory.
        
        Parameters:
            session_factory: A callable or sessionmaker that produces SQLAlchemy Session instances used to persist metrics. Defaults to `SessionLocal`.
        """
        self._session_factory = session_factory

    def record_metrics(self, metrics: RAGPipelineMetrics) -> None:
        """
        Persist a RAGPipelineMetrics snapshot into the database.
        
        Parameters:
            metrics (RAGPipelineMetrics): Finalized pipeline metrics to store; a new row will be inserted into the `rag_metrics_log` table.
        
        Notes:
            On success the change is committed; on failure the transaction is rolled back and the session is closed.
        """
        session = self._session_factory()
        try:
            snapshot = metrics.to_dict()
            _ = session.execute(
                text(
                    """
                    INSERT INTO rag_metrics_log (
                        metrics_id,
                        query_id,
                        query_text,
                        pipeline_start_time,
                        pipeline_end_time,
                        total_latency_ms,
                        retrieval_metrics,
                        generation_metrics,
                        verification_metrics,
                        ragas_faithfulness,
                        ragas_relevancy,
                        ragas_precision,
                        ragas_recall,
                        verdict,
                        abstain_reason,
                        error_type,
                        cost_estimate_usd,
                        cost_actual_usd,
                        cost_governance_applied,
                        created_at
                    ) VALUES (
                        :metrics_id,
                        :query_id,
                        :query_text,
                        :pipeline_start_time,
                        :pipeline_end_time,
                        :total_latency_ms,
                        :retrieval_metrics,
                        :generation_metrics,
                        :verification_metrics,
                        :ragas_faithfulness,
                        :ragas_relevancy,
                        :ragas_precision,
                        :ragas_recall,
                        :verdict,
                        :abstain_reason,
                        :error_type,
                        :cost_estimate_usd,
                        :cost_actual_usd,
                        :cost_governance_applied,
                        :created_at
                    )
                    """
                ),
                {
                    "metrics_id": str(uuid.uuid4()),
                    "query_id": metrics.query_id,
                    "query_text": metrics.query[:1000],
                    "pipeline_start_time": metrics.pipeline_start_time,
                    "pipeline_end_time": metrics.pipeline_end_time,
                    "total_latency_ms": metrics.total_latency_ms,
                    "retrieval_metrics": json.dumps(
                        snapshot.get("retrieval", {}), default=str
                    ),
                    "generation_metrics": json.dumps(
                        snapshot.get("generation", {}), default=str
                    ),
                    "verification_metrics": json.dumps(
                        snapshot.get("verification", {}), default=str
                    ),
                    "ragas_faithfulness": metrics.ragas.faithfulness,
                    "ragas_relevancy": metrics.ragas.relevancy,
                    "ragas_precision": metrics.ragas.precision,
                    "ragas_recall": metrics.ragas.recall,
                    "verdict": metrics.verdict,
                    "abstain_reason": metrics.abstain_reason,
                    "error_type": metrics.error_type,
                    "cost_estimate_usd": metrics.cost_estimate_usd,
                    "cost_actual_usd": metrics.cost_actual_usd,
                    "cost_governance_applied": metrics.cost_governance_applied,
                    "created_at": _utc_now(),
                },
            )
            session.commit()
            logger.debug(f"Recorded metrics for query {metrics.query_id}")
        except SQLAlchemyError:
            session.rollback()
            logger.exception("Failed to persist metrics")
        finally:
            session.close()


class LoggingMetricsSink:
    """Log metrics for debugging and development."""

    def record_metrics(self, metrics: RAGPipelineMetrics) -> None:
        """
        Log a concise, human-readable summary of the provided RAGPipelineMetrics to the module logger at INFO level.
        
        Parameters:
            metrics (RAGPipelineMetrics): The pipeline metrics to summarize and log; the log includes query_id, a truncated query, verdict, total latency in milliseconds, and actual cost.
        """
        logger.info(
            f"RAG Pipeline Metrics [{metrics.query_id}]: "
            f"query='{metrics.query[:50]}...' "
            f"verdict={metrics.verdict} "
            f"latency={metrics.total_latency_ms:.1f}ms "
            f"cost=${metrics.cost_actual_usd:.6f}"
        )


class MetricsCollector:
    """Collect and track metrics throughout the RAG pipeline.

    This class provides a context manager and helper methods to track
    metrics at each stage of the RAG pipeline, from retrieval through
    verification to final output.

    Example:
        >>> collector = MetricsCollector()
        >>> with collector.track_retrieval(query) as retrieval_ctx:
        ...     results = retrieve(query)
        ...     retrieval_ctx.record_results(results)
        >>> metrics = collector.get_metrics()
    """

    metrics: RAGPipelineMetrics
    _sinks: list[MetricsSink]
    _stage_timers: dict[str, float]

    def __init__(
        self,
        query: str = "",
        sinks: Sequence[MetricsSink] | None = None,
        enable_db_sink: bool = True,
    ) -> None:
        """
        Constructs a MetricsCollector configured for a single pipeline run.
        
        By default the collector uses a LoggingMetricsSink; if `enable_db_sink` is true it will also attempt to add a DatabaseMetricsSink. A custom sequence of sinks can be provided to replace the defaults.
        
        Parameters:
            query (str): The user query associated with this metrics run.
            sinks (Sequence[MetricsSink] | None): Optional custom sinks to record metrics. If provided, these replace the default sinks.
            enable_db_sink (bool): When true and `sinks` is not provided, attempts to initialize and add a DatabaseMetricsSink; failures are logged and ignored.
        """
        self.metrics = RAGPipelineMetrics(query=query)
        self._stage_timers = {}

        if sinks is not None:
            self._sinks = list(sinks)
        else:
            self._sinks = [LoggingMetricsSink()]
            if enable_db_sink:
                try:
                    self._sinks.append(DatabaseMetricsSink())
                except Exception:
                    logger.warning("Failed to initialize database metrics sink")

    def start_stage(self, stage: str) -> None:
        """
        Begin timing for the named pipeline stage.
        
        Parameters:
            stage (str): Identifier for the pipeline stage to time. If a timer for the same stage already exists, it is replaced with a new start time.
        """
        self._stage_timers[stage] = time.perf_counter()

    def end_stage(self, stage: str) -> float:
        """
        Stop timing a named pipeline stage and compute its elapsed latency.
        
        Parameters:
            stage (str): The name of the pipeline stage to end timing for.
        
        Returns:
            float: Elapsed time in milliseconds for the stage; `0.0` if the stage was not being timed.
        """
        if stage not in self._stage_timers:
            return 0.0
        elapsed = (time.perf_counter() - self._stage_timers[stage]) * 1000
        del self._stage_timers[stage]
        return elapsed

    def record_retrieval(
        self,
        results: Sequence[Mapping[str, object]],
        latency_ms: float,
        hyde_used: bool = False,
        query_variations: int = 1,
        reranker_used: bool = False,
    ) -> None:
        """
        Record metrics produced by the retrieval stage into the collector's metrics.
        
        Parameters:
            results (Sequence[Mapping[str, object]]): Retrieved items where each mapping may include keys
                "trust_status" (str), "score" (int|float|bool), and "source_id" (any). Boolean scores are ignored.
            latency_ms (float): Elapsed time of the retrieval stage in milliseconds.
            hyde_used (bool): Whether HyDE-style augmentation was used.
            query_variations (int): Number of query variations executed.
            reranker_used (bool): Whether a reranker was applied to retrieval results.
        """
        results_list = list(results)

        # Count trusted vs untrusted
        trusted_count = sum(
            1
            for r in results_list
            if str(r.get("trust_status", "")).lower() == "trusted"
        )

        # Calculate score statistics
        scores: list[float] = []
        for result in results_list:
            score_raw = result.get("score")
            if isinstance(score_raw, bool):
                continue
            if isinstance(score_raw, int):
                scores.append(float(score_raw))
            elif isinstance(score_raw, float):
                scores.append(score_raw)

        # Collect source IDs
        sources = list(
            {str(r.get("source_id", "")) for r in results_list if r.get("source_id")}
        )

        self.metrics.retrieval = RetrievalMetrics(
            query=self.metrics.query,
            latency_ms=latency_ms,
            results_count=len(results_list),
            trusted_count=trusted_count,
            untrusted_count=len(results_list) - trusted_count,
            avg_score=sum(scores) / len(scores) if scores else 0.0,
            max_score=max(scores) if scores else 0.0,
            min_score=min(scores) if scores else 0.0,
            sources=sources,
            hyde_used=hyde_used,
            query_variations=query_variations,
            reranker_used=reranker_used,
        )

    def record_generation(
        self,
        statements: Sequence[Mapping[str, object]],
        latency_ms: float,
        tokens_prompt: int = 0,
        tokens_completion: int = 0,
        model_used: str = "",
        cost_usd: float = 0.0,
    ) -> None:
        """
        Record generation-stage metrics on the collector's RAGPipelineMetrics instance.
        
        Parameters:
            statements (Sequence[Mapping[str, object]]): Generated statements; each statement may include a `citations` key whose value is a list of citation entries used to count citations.
            latency_ms (float): Latency of the generation stage in milliseconds.
            tokens_prompt (int): Number of prompt tokens consumed.
            tokens_completion (int): Number of completion tokens produced.
            model_used (str): Identifier of the model used to generate the statements.
            cost_usd (float): Monetary cost incurred for the generation stage in USD.
        """
        statements_list = list(statements)

        # Count citations
        citations_count = 0
        for stmt in statements_list:
            citations = stmt.get("citations", [])
            if isinstance(citations, list):
                citations_count += len(citations)

        self.metrics.generation = GenerationMetrics(
            latency_ms=latency_ms,
            statements_count=len(statements_list),
            citations_count=citations_count,
            tokens_prompt=tokens_prompt,
            tokens_completion=tokens_completion,
            model_used=model_used,
            cost_usd=cost_usd,
        )

    def record_verification(
        self,
        citation_verified: bool = False,
        citation_fail_reason: str | None = None,
        faithfulness_score: float = 0.0,
        faithfulness_verified: bool = False,
        unfaithful_statements: Sequence[int] | None = None,
    ) -> None:
        """
        Store verification metrics describing citation checks and faithfulness evaluation.
        
        Parameters:
            citation_verified (bool): `True` if citations were verified successfully, `False` otherwise.
            citation_fail_reason (str | None): Short reason for citation verification failure, or `None` if not applicable.
            faithfulness_score (float): Faithfulness score on a 0.0–1.0 scale.
            faithfulness_verified (bool): `True` if the overall faithfulness check passed, `False` otherwise.
            unfaithful_statements (Sequence[int] | None): Indices of statements found unfaithful; empty or `None` if none.
        """
        self.metrics.verification = VerificationMetrics(
            citation_verified=citation_verified,
            citation_fail_reason=citation_fail_reason,
            faithfulness_score=faithfulness_score,
            faithfulness_verified=faithfulness_verified,
            unfaithful_statements=list(unfaithful_statements or []),
        )

    def record_verdict(
        self,
        verdict: str,
        abstain_reason: str | None = None,
        error_type: str | None = None,
    ) -> None:
        """
        Set the pipeline's final verdict and optional explanatory fields.
        
        Parameters:
        	verdict (str): Final decision for the pipeline run (e.g., a verdict label).
        	abstain_reason (str | None): Human-readable reason when the pipeline abstains from a definitive verdict.
        	error_type (str | None): Optional classification or code identifying an error that influenced the verdict.
        """
        self.metrics.verdict = verdict
        self.metrics.abstain_reason = abstain_reason
        self.metrics.error_type = error_type

    def record_cost(
        self,
        estimate_usd: float = 0.0,
        actual_usd: float = 0.0,
        governance_applied: bool = False,
        degradation_message: str | None = None,
    ) -> None:
        """
        Record cost-related values on the collector's metrics.
        
        Parameters:
            estimate_usd (float): Estimated cost in USD for the pipeline run.
            actual_usd (float): Actual incurred cost in USD for the pipeline run.
            governance_applied (bool): Whether governance (cost-limiting or adjustment) was applied.
            degradation_message (str | None): Optional human-readable message describing any quality degradation or trade-off applied due to cost governance.
        """
        self.metrics.cost_estimate_usd = estimate_usd
        self.metrics.cost_actual_usd = actual_usd
        self.metrics.cost_governance_applied = governance_applied
        self.metrics.cost_degradation_message = degradation_message

    def record_ragas(
        self,
        *,
        faithfulness: float,
        relevancy: float,
        precision: float,
        recall: float,
    ) -> None:
        """
        Record RAGAS scores on the current metrics.
        
        Each provided score is clamped to the range 0.0–1.0 and stored on the collector's `metrics.ragas`.
        """
        self.metrics.ragas = RagasScores(
            faithfulness=max(0.0, min(1.0, float(faithfulness))),
            relevancy=max(0.0, min(1.0, float(relevancy))),
            precision=max(0.0, min(1.0, float(precision))),
            recall=max(0.0, min(1.0, float(recall))),
        )

    def finalize_and_record(self) -> RAGPipelineMetrics:
        """
        Finalize the current metrics and dispatch them to all configured sinks.
        
        This finalizes pipeline timings (sets the end time and computes total latency), then attempts to record the finalized metrics with each configured sink; failures from individual sinks are logged and do not stop the process.
        
        Returns:
            RAGPipelineMetrics: The finalized metrics object with pipeline end time set and total latency computed.
        """
        self.metrics.finalize()

        for sink in self._sinks:
            try:
                sink.record_metrics(self.metrics)
            except Exception as exc:
                logger.warning(f"Failed to record metrics to sink: {exc}")

        return self.metrics

    def get_metrics(self) -> RAGPipelineMetrics:
        """
        Get the current RAGPipelineMetrics instance without finalizing it.
        
        Returns:
            RAGPipelineMetrics: The live metrics object representing the current pipeline state.
        """
        return self.metrics


class MetricsContext:
    """Context manager for timing a pipeline stage."""

    def __init__(
        self,
        collector: MetricsCollector,
        stage: str,
        record_func: Callable[[float], None] | None = None,
    ) -> None:
        """
        Initialize a MetricsContext for timing a pipeline stage.
        
        Parameters:
            collector (MetricsCollector): The collector that tracks and stores stage timings.
            stage (str): Name of the pipeline stage being timed.
            record_func (Callable[[float], None] | None): Optional callback invoked with the measured latency in milliseconds when the context exits.
        
        Attributes:
            latency_ms (float): Initialized to 0.0; will hold the measured latency in milliseconds after the context exits.
        """
        self.collector = collector
        self.stage = stage
        self.record_func = record_func
        self.latency_ms: float = 0.0

    def __enter__(self) -> "MetricsContext":
        """
        Start timing the configured pipeline stage and return this context manager.
        
        Returns:
            MetricsContext: the context manager instance with stage timing started.
        """
        self.collector.start_stage(self.stage)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """
        Stop timing the context's stage, record the elapsed milliseconds in `self.latency_ms`, and if a `record_func` was provided, invoke it with the measured latency.
        
        Parameters:
            exc_type (type[BaseException] | None): Exception type if raised inside the with-block, otherwise None.
            exc_val (BaseException | None): Exception instance if raised inside the with-block, otherwise None.
            exc_tb (object | None): Traceback object if an exception was raised, otherwise None.
        
        Notes:
            This method does not suppress exceptions raised within the with-block.
        """
        self.latency_ms = self.collector.end_stage(self.stage)
        if self.record_func:
            self.record_func(self.latency_ms)


def create_metrics_collector(
    query: str = "",
    enable_db_sink: bool = True,
) -> MetricsCollector:
    """Factory function to create a metrics collector.

    Args:
        query: The user query being processed
        enable_db_sink: Whether to enable database persistence

    Returns:
        Configured MetricsCollector instance
    """
    return MetricsCollector(query=query, enable_db_sink=enable_db_sink)


__all__ = [
    "MetricsCollector",
    "MetricsContext",
    "RAGPipelineMetrics",
    "RetrievalMetrics",
    "GenerationMetrics",
    "VerificationMetrics",
    "RagasScores",
    "DatabaseMetricsSink",
    "LoggingMetricsSink",
    "create_metrics_collector",
]
