#!/usr/bin/env python3
"""Performance benchmark script for Islam Intelligent RAG system.

This script measures:
1. Query latency (single query response time)
2. Throughput (queries per second)
3. End-to-end pipeline performance
4. Component-level performance breakdown

Usage:
    python scripts/benchmark_performance.py
    python scripts/benchmark_performance.py --iterations 100
    python scripts/benchmark_performance.py --queries "query1" "query2" "query3"
    python scripts/benchmark_performance.py --output results.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""

    name: str
    latency_ms: float
    success: bool
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkStats:
    """Statistics for a benchmark suite."""

    name: str
    iterations: int
    total_time_ms: float
    min_latency_ms: float
    max_latency_ms: float
    mean_latency_ms: float
    median_latency_ms: float
    std_dev_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    success_rate: float
    queries_per_second: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class Colors:
    """ANSI color codes for terminal output."""

    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    RESET = "\033[0m"

    @classmethod
    def disable(cls):
        """
        Clear all ANSI color code attributes on the class so terminal output is plain (no colors).
        """
        cls.GREEN = ""
        cls.RED = ""
        cls.YELLOW = ""
        cls.BLUE = ""
        cls.CYAN = ""
        cls.RESET = ""


class PerformanceBenchmark:
    """Benchmark runner for Islam Intelligent RAG system."""

    def __init__(self, verbose: bool = False, warmup_iterations: int = 3):
        """
        Initialize the PerformanceBenchmark instance with runtime options.
        
        This sets verbosity, the number of warm-up iterations, and initializes empty containers
        for per-run results and aggregate statistics. It also ensures the API source directory
        (apps/api/src) is present on sys.path so the benchmark can import the RAG pipeline.
        
        Parameters:
            verbose (bool): If True, enable detailed logging output.
            warmup_iterations (int): Number of warm-up iterations to perform before running benchmarks.
        """
        self.verbose = verbose
        self.warmup_iterations = warmup_iterations
        self.results: list[BenchmarkResult] = []
        self.stats: list[BenchmarkStats] = []

        # Add API src to path
        api_src = Path(__file__).parent.parent / "apps" / "api" / "src"
        if str(api_src) not in sys.path:
            sys.path.insert(0, str(api_src))

    def log(self, message: str, level: str = "info"):
        """
        Prints a level-prefixed message when verbose mode is enabled.
        
        Parameters:
            message (str): The message to print.
            level (str): One of "info", "success", "error", "warning", or "benchmark" (default "info"); selects the label and color used as a prefix.
        """
        if self.verbose:
            prefix = {
                "info": f"{Colors.BLUE}[INFO]{Colors.RESET}",
                "success": f"{Colors.GREEN}[PASS]{Colors.RESET}",
                "error": f"{Colors.RED}[FAIL]{Colors.RESET}",
                "warning": f"{Colors.YELLOW}[WARN]{Colors.RESET}",
                "benchmark": f"{Colors.CYAN}[BENCH]{Colors.RESET}",
            }.get(level, "[INFO]")
            print(f"{prefix} {message}")

    def warm_up(self):
        """
        Perform a warm-up run to exercise the RAG pipeline before benchmarking.
        
        Instantiates a RAGPipeline and executes a sample query `self.warmup_iterations` times to prime models, caches, and external services. Logs progress for each iteration and prints completion status. If warm-up fails, the error is caught and a warning is printed; the exception is not propagated.
        """
        print(
            f"{Colors.BLUE}Warming up with {self.warmup_iterations} iterations...{Colors.RESET}"
        )

        try:
            from islam_intelligent.rag.pipeline.core import RAGPipeline

            pipeline = RAGPipeline()

            for i in range(self.warmup_iterations):
                _ = pipeline.query("What is prayer?")
                self.log(f"Warm-up iteration {i + 1}/{self.warmup_iterations}")

            print(f"{Colors.GREEN}Warm-up complete{Colors.RESET}\n")
        except Exception as e:
            print(f"{Colors.YELLOW}Warning: Warm-up failed: {e}{Colors.RESET}")

    def benchmark_query_latency(
        self, query: str, iterations: int = 10
    ) -> BenchmarkStats:
        """
        Measure per-iteration latency for a query and compute aggregate statistics.
        
        Runs the provided query against a RAGPipeline for a number of iterations and returns aggregated latency and success metrics.
        
        Parameters:
        	query (str): The query string to execute.
        	iterations (int): Number of times to run the query.
        
        Returns:
        	stats (BenchmarkStats): Aggregated statistics for the benchmark including total time (ms), min/max/mean/median/std_dev/p95/p99 latencies (ms), success_rate (percentage), and queries_per_second.
        """
        print(
            f"{Colors.BLUE}Benchmarking query latency: '{query[:50]}...'{Colors.RESET}"
        )

        try:
            from islam_intelligent.rag.pipeline.core import RAGPipeline

            pipeline = RAGPipeline()
        except Exception as e:
            print(f"{Colors.RED}Failed to initialize pipeline: {e}{Colors.RESET}")
            return BenchmarkStats(
                name="query_latency",
                iterations=0,
                total_time_ms=0,
                min_latency_ms=0,
                max_latency_ms=0,
                mean_latency_ms=0,
                median_latency_ms=0,
                std_dev_ms=0,
                p95_latency_ms=0,
                p99_latency_ms=0,
                success_rate=0,
                queries_per_second=0,
            )

        latencies = []
        successes = 0
        start_total = time.perf_counter()

        for i in range(iterations):
            start = time.perf_counter()
            try:
                result = pipeline.query(query)
                end = time.perf_counter()

                latency_ms = (end - start) * 1000
                latencies.append(latency_ms)
                successes += 1

                self.log(
                    f"Iteration {i + 1}/{iterations}: {latency_ms:.2f}ms", "benchmark"
                )
            except Exception as e:
                end = time.perf_counter()
                latency_ms = (end - start) * 1000
                latencies.append(latency_ms)

                self.log(f"Iteration {i + 1}/{iterations}: FAILED ({e})", "error")

        end_total = time.perf_counter()
        total_time_ms = (end_total - start_total) * 1000

        if not latencies:
            return BenchmarkStats(
                name="query_latency",
                iterations=iterations,
                total_time_ms=total_time_ms,
                min_latency_ms=0,
                max_latency_ms=0,
                mean_latency_ms=0,
                median_latency_ms=0,
                std_dev_ms=0,
                p95_latency_ms=0,
                p99_latency_ms=0,
                success_rate=0,
                queries_per_second=0,
            )

        # Calculate statistics
        latencies_sorted = sorted(latencies)
        mean_latency = statistics.mean(latencies)
        median_latency = statistics.median(latencies)
        std_dev = statistics.stdev(latencies) if len(latencies) > 1 else 0

        p95_index = int(len(latencies_sorted) * 0.95)
        p99_index = int(len(latencies_sorted) * 0.99)
        p95_latency = latencies_sorted[min(p95_index, len(latencies_sorted) - 1)]
        p99_latency = latencies_sorted[min(p99_index, len(latencies_sorted) - 1)]

        success_rate = (successes / iterations) * 100
        qps = iterations / (total_time_ms / 1000) if total_time_ms > 0 else 0

        stats = BenchmarkStats(
            name=f"query_latency_{query[:20].replace(' ', '_')}",
            iterations=iterations,
            total_time_ms=total_time_ms,
            min_latency_ms=min(latencies),
            max_latency_ms=max(latencies),
            mean_latency_ms=mean_latency,
            median_latency_ms=median_latency,
            std_dev_ms=std_dev,
            p95_latency_ms=p95_latency,
            p99_latency_ms=p99_latency,
            success_rate=success_rate,
            queries_per_second=qps,
        )

        self.print_stats(stats)
        return stats

    def benchmark_throughput(self, duration_seconds: int = 10) -> BenchmarkStats:
        """
        Run a duration-limited throughput test against the RAG pipeline.
        
        The function sends rotating sample queries to a newly initialized RAGPipeline for the specified
        duration and collects per-query latencies and success counts. If the pipeline fails to
        initialize or no queries complete, a BenchmarkStats instance with zeroed metrics is returned.
        
        Parameters:
            duration_seconds (int): Number of seconds to run the throughput test.
        
        Returns:
            BenchmarkStats: Aggregated statistics for the test, including total iterations, total time
            in milliseconds, min/max/mean/median latency (ms), standard deviation (ms), 95th and 99th
            percentile latencies (ms), success rate (percentage), and measured queries per second.
        """
        print(
            f"{Colors.BLUE}Benchmarking throughput for {duration_seconds} seconds...{Colors.RESET}"
        )

        try:
            from islam_intelligent.rag.pipeline.core import RAGPipeline

            pipeline = RAGPipeline()
        except Exception as e:
            print(f"{Colors.RED}Failed to initialize pipeline: {e}{Colors.RESET}")
            return BenchmarkStats(
                name="throughput",
                iterations=0,
                total_time_ms=0,
                min_latency_ms=0,
                max_latency_ms=0,
                mean_latency_ms=0,
                median_latency_ms=0,
                std_dev_ms=0,
                p95_latency_ms=0,
                p99_latency_ms=0,
                success_rate=0,
                queries_per_second=0,
            )

        queries = [
            "What is prayer?",
            "How to perform wudu?",
            "What is zakat?",
            "Tell me about fasting",
            "What are the pillars of Islam?",
        ]

        latencies = []
        successes = 0
        iterations = 0
        start_total = time.perf_counter()
        end_time = start_total + duration_seconds

        while time.perf_counter() < end_time:
            query = queries[iterations % len(queries)]
            start = time.perf_counter()
            try:
                _ = pipeline.query(query)
                end = time.perf_counter()
                latencies.append((end - start) * 1000)
                successes += 1
            except Exception as e:
                end = time.perf_counter()
                latencies.append((end - start) * 1000)

            iterations += 1

            if iterations % 10 == 0:
                self.log(f"Completed {iterations} queries...", "benchmark")

        end_total = time.perf_counter()
        total_time_ms = (end_total - start_total) * 1000

        if not latencies:
            return BenchmarkStats(
                name="throughput",
                iterations=iterations,
                total_time_ms=total_time_ms,
                min_latency_ms=0,
                max_latency_ms=0,
                mean_latency_ms=0,
                median_latency_ms=0,
                std_dev_ms=0,
                p95_latency_ms=0,
                p99_latency_ms=0,
                success_rate=0,
                queries_per_second=0,
            )

        mean_latency = statistics.mean(latencies)
        median_latency = statistics.median(latencies)
        std_dev = statistics.stdev(latencies) if len(latencies) > 1 else 0
        latencies_sorted = sorted(latencies)
        p95_index = int(len(latencies_sorted) * 0.95)
        p99_index = int(len(latencies_sorted) * 0.99)
        p95_latency = latencies_sorted[min(p95_index, len(latencies_sorted) - 1)]
        p99_latency = latencies_sorted[min(p99_index, len(latencies_sorted) - 1)]

        success_rate = (successes / iterations) * 100
        qps = iterations / (total_time_ms / 1000) if total_time_ms > 0 else 0

        stats = BenchmarkStats(
            name="throughput",
            iterations=iterations,
            total_time_ms=total_time_ms,
            min_latency_ms=min(latencies),
            max_latency_ms=max(latencies),
            mean_latency_ms=mean_latency,
            median_latency_ms=median_latency,
            std_dev_ms=std_dev,
            p95_latency_ms=p95_latency,
            p99_latency_ms=p99_latency,
            success_rate=success_rate,
            queries_per_second=qps,
        )

        self.print_stats(stats)
        return stats

    def benchmark_component_breakdown(self) -> list[BenchmarkStats]:
        """
        Run benchmarks for individual components (HyDE, query expansion, and cost estimation) and collect their statistics.
        
        Returns:
            list[BenchmarkStats]: A list of BenchmarkStats for HyDE, query expansion, and cost estimation, in that order.
        """
        print(f"\n{Colors.BLUE}=== Component Breakdown ==={Colors.RESET}")

        stats_list = []

        # Benchmark HyDE
        stats_list.append(self._benchmark_hyde())

        # Benchmark Query Expansion
        stats_list.append(self._benchmark_query_expansion())

        # Benchmark Cost Estimation
        stats_list.append(self._benchmark_cost_estimation())

        return stats_list

    def _benchmark_hyde(self) -> BenchmarkStats:
        """
        Run a latency and throughput benchmark for the HyDE query expander using a fixed query.
        
        Performs 10 expansions of a predefined query, measures per-call latencies (milliseconds), and aggregates statistics including min/max/mean/median, standard deviation, p95/p99, success rate, and queries-per-second.
        
        Returns:
            BenchmarkStats: Aggregated statistics for the HyDE component benchmark.
        """
        print(f"{Colors.BLUE}Benchmarking HyDE...{Colors.RESET}")

        try:
            from islam_intelligent.rag.retrieval.hyde import HyDEQueryExpander

            expander = HyDEQueryExpander()
            query = "How do Muslims pray?"

            latencies = []
            for _ in range(10):
                start = time.perf_counter()
                _ = expander.expand(query)
                end = time.perf_counter()
                latencies.append((end - start) * 1000)

            mean_latency = statistics.mean(latencies)

            stats = BenchmarkStats(
                name="component_hyde",
                iterations=10,
                total_time_ms=sum(latencies),
                min_latency_ms=min(latencies),
                max_latency_ms=max(latencies),
                mean_latency_ms=mean_latency,
                median_latency_ms=statistics.median(latencies),
                std_dev_ms=statistics.stdev(latencies) if len(latencies) > 1 else 0,
                p95_latency_ms=sorted(latencies)[int(len(latencies) * 0.95)],
                p99_latency_ms=sorted(latencies)[int(len(latencies) * 0.99)],
                success_rate=100.0,
                queries_per_second=10 / (sum(latencies) / 1000),
            )

            self.print_stats(stats)
            return stats

        except Exception as e:
            print(f"{Colors.RED}HyDE benchmark failed: {e}{Colors.RESET}")
            return BenchmarkStats(
                name="component_hyde",
                iterations=0,
                total_time_ms=0,
                min_latency_ms=0,
                max_latency_ms=0,
                mean_latency_ms=0,
                median_latency_ms=0,
                std_dev_ms=0,
                p95_latency_ms=0,
                p99_latency_ms=0,
                success_rate=0,
                queries_per_second=0,
            )

    def _benchmark_query_expansion(self) -> BenchmarkStats:
        """
        Measure latency and throughput of the QueryExpander component by performing multiple expansions of a sample query.
        
        Performs a fixed number of expansion requests and aggregates latency statistics (min, max, mean, median, standard deviation, p95, p99) and throughput (queries per second). On failure, returns a BenchmarkStats instance with zeroed metrics.
        
        Returns:
            BenchmarkStats: Aggregated statistics for the query expansion benchmark, including latency percentiles, success rate, and queries per second.
        """
        print(f"{Colors.BLUE}Benchmarking Query Expansion...{Colors.RESET}")

        try:
            from islam_intelligent.rag.retrieval.query_expander import QueryExpander

            expander = QueryExpander()
            query = "What is the ruling on fasting?"

            latencies = []
            for _ in range(10):
                start = time.perf_counter()
                _ = expander.expand(query, num_variations=5)
                end = time.perf_counter()
                latencies.append((end - start) * 1000)

            mean_latency = statistics.mean(latencies)

            stats = BenchmarkStats(
                name="component_query_expansion",
                iterations=10,
                total_time_ms=sum(latencies),
                min_latency_ms=min(latencies),
                max_latency_ms=max(latencies),
                mean_latency_ms=mean_latency,
                median_latency_ms=statistics.median(latencies),
                std_dev_ms=statistics.stdev(latencies) if len(latencies) > 1 else 0,
                p95_latency_ms=sorted(latencies)[int(len(latencies) * 0.95)],
                p99_latency_ms=sorted(latencies)[int(len(latencies) * 0.99)],
                success_rate=100.0,
                queries_per_second=10 / (sum(latencies) / 1000),
            )

            self.print_stats(stats)
            return stats

        except Exception as e:
            print(f"{Colors.RED}Query expansion benchmark failed: {e}{Colors.RESET}")
            return BenchmarkStats(
                name="component_query_expansion",
                iterations=0,
                total_time_ms=0,
                min_latency_ms=0,
                max_latency_ms=0,
                mean_latency_ms=0,
                median_latency_ms=0,
                std_dev_ms=0,
                p95_latency_ms=0,
                p99_latency_ms=0,
                success_rate=0,
                queries_per_second=0,
            )

    def _benchmark_cost_estimation(self) -> BenchmarkStats:
        """
        Measure latency and throughput of the CostEstimator component.
        
        Runs multiple cost estimation calls for a fixed query and returns aggregated timing and success metrics.
        
        Returns:
            BenchmarkStats: Aggregated statistics for the cost estimation benchmark, including iterations, total and percentile latencies, standard deviation, success rate, and queries per second.
        """
        print(f"{Colors.BLUE}Benchmarking Cost Estimation...{Colors.RESET}")

        try:
            from islam_intelligent.cost_governance import CostEstimator

            estimator = CostEstimator()
            query = "Explain the five pillars of Islam in detail"

            latencies = []
            for _ in range(10):
                start = time.perf_counter()
                _ = estimator.estimate_query_cost(
                    query=query,
                    embedding_model="text-embedding-3-small",
                    llm_model="gpt-4o-mini",
                )
                end = time.perf_counter()
                latencies.append((end - start) * 1000)

            mean_latency = statistics.mean(latencies)

            stats = BenchmarkStats(
                name="component_cost_estimation",
                iterations=10,
                total_time_ms=sum(latencies),
                min_latency_ms=min(latencies),
                max_latency_ms=max(latencies),
                mean_latency_ms=mean_latency,
                median_latency_ms=statistics.median(latencies),
                std_dev_ms=statistics.stdev(latencies) if len(latencies) > 1 else 0,
                p95_latency_ms=sorted(latencies)[int(len(latencies) * 0.95)],
                p99_latency_ms=sorted(latencies)[int(len(latencies) * 0.99)],
                success_rate=100.0,
                queries_per_second=10 / (sum(latencies) / 1000),
            )

            self.print_stats(stats)
            return stats

        except Exception as e:
            print(f"{Colors.RED}Cost estimation benchmark failed: {e}{Colors.RESET}")
            return BenchmarkStats(
                name="component_cost_estimation",
                iterations=0,
                total_time_ms=0,
                min_latency_ms=0,
                max_latency_ms=0,
                mean_latency_ms=0,
                median_latency_ms=0,
                std_dev_ms=0,
                p95_latency_ms=0,
                p99_latency_ms=0,
                success_rate=0,
                queries_per_second=0,
            )

    def print_stats(self, stats: BenchmarkStats):
        """
        Print formatted performance metrics for a BenchmarkStats instance.
        
        Parameters:
            stats (BenchmarkStats): Aggregated benchmark metrics to display, including
                name, iteration count, total time, latency statistics (min/max/mean/median/std),
                percentiles (p95, p99), success rate, and throughput (queries per second).
        """
        print(f"\n{Colors.CYAN}Results for: {stats.name}{Colors.RESET}")
        print(f"  Iterations:        {stats.iterations}")
        print(f"  Total time:        {stats.total_time_ms:.2f}ms")
        print(f"  Min latency:       {stats.min_latency_ms:.2f}ms")
        print(f"  Max latency:       {stats.max_latency_ms:.2f}ms")
        print(f"  Mean latency:      {stats.mean_latency_ms:.2f}ms")
        print(f"  Median latency:    {stats.median_latency_ms:.2f}ms")
        print(f"  Std dev:           {stats.std_dev_ms:.2f}ms")
        print(f"  P95 latency:       {stats.p95_latency_ms:.2f}ms")
        print(f"  P99 latency:       {stats.p99_latency_ms:.2f}ms")
        print(f"  Success rate:      {stats.success_rate:.1f}%")
        print(f"  Throughput:        {stats.queries_per_second:.2f} QPS")

    def run_benchmarks(
        self,
        queries: list[str] | None = None,
        iterations: int = 10,
        throughput_duration: int = 10,
    ) -> list[BenchmarkStats]:
        """
        Execute the full benchmark suite (warm-up, per-query latency tests, throughput test, and component breakdown) and collect statistics for each run.
        
        Parameters:
            queries (list[str] | None): Specific queries to benchmark; if None a default set of sample queries is used.
            iterations (int): Number of iterations to run for each query latency test.
            throughput_duration (int): Duration in seconds for the throughput benchmark.
        
        Returns:
            list[BenchmarkStats]: A list of BenchmarkStats objects for each executed benchmark.
        
        Side effects:
            Stores the collected list of BenchmarkStats in `self.stats`.
        """
        print(f"\n{Colors.BLUE}{'=' * 60}{Colors.RESET}")
        print(
            f"{Colors.BLUE}=== Islam Intelligent Performance Benchmark ==={Colors.RESET}"
        )
        print(f"{Colors.BLUE}{'=' * 60}{Colors.RESET}")
        print(f"Timestamp: {datetime.now().isoformat()}")
        print(f"Iterations per test: {iterations}")
        print(f"Throughput duration: {throughput_duration}s\n")

        self.warm_up()

        all_stats = []

        # Query latency benchmarks
        if queries is None:
            queries = [
                "What is prayer?",
                "How do I perform wudu?",
                "What are the rulings on zakat?",
            ]

        print(f"\n{Colors.BLUE}=== Query Latency Benchmarks ==={Colors.RESET}")
        for query in queries:
            stats = self.benchmark_query_latency(query, iterations=iterations)
            all_stats.append(stats)

        # Throughput benchmark
        print(f"\n{Colors.BLUE}=== Throughput Benchmark ==={Colors.RESET}")
        throughput_stats = self.benchmark_throughput(
            duration_seconds=throughput_duration
        )
        all_stats.append(throughput_stats)

        # Component breakdown
        component_stats = self.benchmark_component_breakdown()
        all_stats.extend(component_stats)

        self.stats = all_stats
        return all_stats

    def print_summary(self):
        """
        Prints a concise summary of collected benchmark statistics to stdout.
        
        Displays overall statistics (total queries executed, average throughput in QPS, and average latency in milliseconds)
        followed by per-test results. Each test line shows the test name, mean latency (ms), and throughput (QPS).
        Tests with a success rate greater than 90 are marked with a green check; others are marked with a red cross.
        """
        print(f"\n{Colors.BLUE}{'=' * 60}{Colors.RESET}")
        print(f"{Colors.BLUE}=== BENCHMARK SUMMARY ==={Colors.RESET}")
        print(f"{Colors.BLUE}{'=' * 60}{Colors.RESET}")

        total_queries = sum(s.iterations for s in self.stats)
        avg_qps = statistics.mean(
            [s.queries_per_second for s in self.stats if s.queries_per_second > 0]
        )
        avg_latency = statistics.mean(
            [s.mean_latency_ms for s in self.stats if s.mean_latency_ms > 0]
        )

        print(f"\n{Colors.GREEN}Overall Statistics:{Colors.RESET}")
        print(f"  Total queries executed: {total_queries}")
        print(f"  Average throughput:     {avg_qps:.2f} QPS")
        print(f"  Average latency:        {avg_latency:.2f}ms")

        print(f"\n{Colors.CYAN}Per-Test Results:{Colors.RESET}")
        for stats in self.stats:
            status = (
                f"{Colors.GREEN}✓{Colors.RESET}"
                if stats.success_rate > 90
                else f"{Colors.RED}✗{Colors.RESET}"
            )
            print(
                f"  {status} {stats.name}: {stats.mean_latency_ms:.2f}ms mean, {stats.queries_per_second:.2f} QPS"
            )

    def save_results(self, output_path: str):
        """
        Save benchmark results to a JSON file.
        
        The file will contain a top-level object with:
        - `timestamp`: ISO8601 timestamp when the file was written.
        - `summary`: object with `total_tests` (number of recorded BenchmarkStats entries) and `total_queries` (sum of iterations across all entries).
        - `benchmarks`: list of `BenchmarkStats` serialized with `asdict()`.
        
        Parameters:
            output_path (str): Filesystem path where the JSON results file will be written. Parent directories will be created if they do not exist.
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        results = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_tests": len(self.stats),
                "total_queries": sum(s.iterations for s in self.stats),
            },
            "benchmarks": [asdict(s) for s in self.stats],
        }

        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)

        print(f"\n{Colors.GREEN}Results saved to: {output_path}{Colors.RESET}")


def main():
    """
    Parse command-line arguments, run the benchmark suite, print a summary, and optionally save results.
    
    Parses CLI options for iterations, throughput duration, specific queries, output file, verbosity, color disabling, and warm-up iterations; constructs a PerformanceBenchmark with the selected settings, executes the full benchmark suite, prints a summary, and writes results to the provided JSON path if specified.
    """
    parser = argparse.ArgumentParser(
        description="Benchmark Islam Intelligent RAG performance"
    )
    parser.add_argument(
        "--iterations", "-i", type=int, default=10, help="Number of iterations per test"
    )
    parser.add_argument(
        "--duration",
        "-d",
        type=int,
        default=10,
        help="Throughput test duration (seconds)",
    )
    parser.add_argument(
        "--queries", "-q", nargs="+", help="Specific queries to benchmark"
    )
    parser.add_argument("--output", "-o", type=str, help="Output JSON file path")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "--no-color", action="store_true", help="Disable colored output"
    )
    parser.add_argument(
        "--warmup", "-w", type=int, default=3, help="Warm-up iterations"
    )

    args = parser.parse_args()

    if args.no_color:
        Colors.disable()

    benchmark = PerformanceBenchmark(
        verbose=args.verbose,
        warmup_iterations=args.warmup,
    )

    benchmark.run_benchmarks(
        queries=args.queries,
        iterations=args.iterations,
        throughput_duration=args.duration,
    )

    benchmark.print_summary()

    if args.output:
        benchmark.save_results(args.output)


if __name__ == "__main__":
    main()
