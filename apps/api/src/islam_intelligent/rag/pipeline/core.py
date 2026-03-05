"""RAG Pipeline: retrieve -> validate -> answer (with abstention).

This module implements the core evidence-first RAG flow:
1. Retrieve candidate evidence spans (with HyDE + query expansion)
2. Rerank results using cross-encoder
3. Validate sufficiency (gate)
4. Apply cost governance
5. Generate answer with citations OR abstain
6. Verify faithfulness and citations
7. Track metrics throughout
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from importlib import import_module
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, TypedDict, cast

from ...config import settings
from ...cost_governance import (
    BudgetManager,
    CostEstimate,
    CostGovernanceService,
    ModelRouter,
    SQLCostRepository,
)
from ..generator import LLMGenerator
from ..metrics import MetricsCollector, create_metrics_collector
from ..rerank import CrossEncoderReranker, RerankerConfig, create_reranker
from ..retrieval.hybrid import search_hybrid, search_hybrid_multi_query
from ..retrieval.hyde import HyDEQueryExpander, create_hyde_expander
from ..retrieval.query_expander import QueryExpander, QueryExpanderConfig
from ..verify import CitationVerifier
from ..verify.faithfulness import (
    CitationFaithfulnessVerifier,
    FaithfulnessResult,
)

logger = logging.getLogger(__name__)


class Citation(TypedDict):
    evidence_span_id: str
    canonical_id: str
    snippet: str


class Statement(TypedDict):
    text: str
    citations: list[Citation]


class AnswerContract(TypedDict):
    verdict: str  # "answer" or "abstain"
    statements: list[Statement]
    abstain_reason: str | None
    fail_reason: str | None
    retrieved_count: int
    sufficiency_score: float
    # New fields for enhanced tracking
    faithfulness_score: float | None
    cost_usd: float | None
    degradation_message: str | None
    metrics: dict[str, object] | None


class GeneratorProtocol(Protocol):
    def generate(
        self, query: str, evidence: list[dict[str, object]], min_citations: int = 1
    ) -> list[dict[str, object]]: ...


@dataclass
class RAGConfig:
    """Configuration for RAG pipeline."""

    sufficiency_threshold: float = 0.6
    max_retrieval: int = 10
    min_citations_per_statement: int = 1
    enable_llm: bool = False
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.2
    llm_seed: int = 42
    llm_base_url: str = ""

    # Query expansion settings
    enable_query_expansion: bool = False
    query_expansion_variations: int = 5

    # HyDE settings
    enable_hyde: bool = False
    hyde_max_tokens: int = 150
    hyde_temperature: float = 0.3

    # Cross-encoder reranker settings
    enable_reranker: bool = True
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    reranker_top_k: int = 10

    # Faithfulness verification settings
    enable_faithfulness: bool = True
    faithfulness_threshold: float = 7.0
    faithfulness_method: str = "auto"

    # Cost governance settings
    enable_cost_governance: bool = True
    daily_budget_usd: float = 10.0
    weekly_budget_usd: float = 50.0

    # Metrics settings
    enable_metrics: bool = True
    enable_metrics_db: bool = True


class RAGPipeline:
    """Evidence-first RAG pipeline with abstention and comprehensive features."""

    def __init__(
        self,
        config: RAGConfig | None = None,
        citation_verifier: CitationVerifier | None = None,
        generator: GeneratorProtocol | None = None,
        query_expander: QueryExpander | None = None,
        hyde_expander: HyDEQueryExpander | None = None,
        reranker: CrossEncoderReranker | None = None,
        faithfulness_verifier: CitationFaithfulnessVerifier | None = None,
        cost_governance: CostGovernanceService | None = None,
    ):
        self.config: RAGConfig = config or RAGConfig()
        self._citation_verifier: CitationVerifier = (
            citation_verifier or CitationVerifier()
        )
        self._generator: GeneratorProtocol = generator or LLMGenerator(
            model=self.config.llm_model,
            temperature=self.config.llm_temperature,
            seed=self.config.llm_seed,
            base_url=self.config.llm_base_url,
        )

        # Initialize query expander
        if query_expander is not None:
            self._query_expander = query_expander
        else:
            expander_config = QueryExpanderConfig(
                enabled=self.config.enable_query_expansion,
                num_variations=self.config.query_expansion_variations,
            )
            self._query_expander = QueryExpander(config=expander_config)

        # Initialize HyDE expander
        if hyde_expander is not None:
            self._hyde_expander = hyde_expander
        else:
            self._hyde_expander = create_hyde_expander(
                enabled=self.config.enable_hyde,
                max_tokens=self.config.hyde_max_tokens,
                temperature=self.config.hyde_temperature,
            )

        # Initialize reranker
        if reranker is not None:
            self._reranker = reranker
        else:
            reranker_config = RerankerConfig(
                enabled=self.config.enable_reranker,
                model=self.config.reranker_model,
                top_k=self.config.reranker_top_k,
            )
            self._reranker = CrossEncoderReranker(config=reranker_config)

        # Initialize faithfulness verifier
        if faithfulness_verifier is not None:
            self._faithfulness_verifier = faithfulness_verifier
        else:
            self._faithfulness_verifier = CitationFaithfulnessVerifier()
        self._faithfulness_enabled = self.config.enable_faithfulness

        # Initialize cost governance
        if cost_governance is not None:
            self._cost_governance = cost_governance
        elif self.config.enable_cost_governance:
            try:
                budget_manager = BudgetManager(
                    daily_budget=self.config.daily_budget_usd,
                    weekly_budget=self.config.weekly_budget_usd,
                    repository=SQLCostRepository(),
                )
                self._cost_governance = CostGovernanceService(
                    budget_manager=budget_manager,
                    embedding_model=settings.embedding_model,
                )
            except Exception as exc:
                logger.warning(f"Failed to initialize cost governance: {exc}")
                self._cost_governance = None
        else:
            self._cost_governance = None

    def retrieve(
        self, query: str
    ) -> tuple[Sequence[Mapping[str, object]], dict[str, object]]:
        """Retrieve candidate evidence spans using multi-query and HyDE if enabled.

        Returns:
            Tuple of (retrieved results, metadata dict)
        """
        metadata: dict[str, object] = {
            "hyde_used": False,
            "query_variations": 1,
        }

        # Try HyDE first if enabled
        if self.config.enable_hyde and self._hyde_expander.is_available():
            try:
                hyde_query = self._hyde_expander.expand(query)
                if hyde_query != query:
                    # Use hypothetical document for retrieval
                    query = hyde_query
                    metadata["hyde_used"] = True
                    metadata["hypothetical_answer"] = hyde_query[
                        :200
                    ]  # Truncate for metadata
            except Exception as exc:
                logger.debug(f"HyDE expansion failed: {exc}")

        # Use multi-query expansion if enabled
        if self.config.enable_query_expansion:
            results = search_hybrid_multi_query(
                query,
                limit=self.config.max_retrieval,
                expander=self._query_expander,
                num_variations=self.config.query_expansion_variations,
            )
            metadata["query_variations"] = self.config.query_expansion_variations
        else:
            results = search_hybrid(query, limit=self.config.max_retrieval)

        return results, metadata

    def rerank(
        self, query: str, results: Sequence[Mapping[str, object]]
    ) -> list[dict[str, object]]:
        """Rerank results using cross-encoder if enabled.

        Returns:
            Reranked results or original results if reranker unavailable
        """
        if not self.config.enable_reranker:
            return [dict(r) for r in results]

        if not self._reranker.is_available():
            logger.debug("Reranker not available, skipping reranking")
            return [dict(r) for r in results]

        try:
            reranked = self._reranker.rerank(
                query, [dict(r) for r in results], top_k=self.config.reranker_top_k
            )
            return [r.to_dict() for r in reranked]
        except Exception as exc:
            logger.warning(f"Reranking failed: {exc}")
            return [dict(r) for r in results]

    def _filter_trusted(
        self, retrieved: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        """Filter retrieval results to trusted-only sources.

        Fail-safe behavior: items without explicit trust_status='trusted' are dropped.
        """
        trusted: list[dict[str, object]] = []
        for r in retrieved:
            status = str(r.get("trust_status", "untrusted")).lower()
            if status == "trusted":
                trusted.append(r)
        return trusted

    def validate_sufficiency(
        self, retrieved: list[dict[str, object]]
    ) -> tuple[bool, float]:
        """Validate if retrieved evidence is sufficient.

        Returns:
            (is_sufficient, sufficiency_score)
        """
        if not retrieved:
            return False, 0.0

        def _coerce_score(value: object) -> float:
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value)
                except ValueError:
                    return 0.0
            return 0.0

        # Simple sufficiency: at least 2 results with decent scores
        high_confidence = sum(
            1 for r in retrieved if _coerce_score(r.get("score", 0.0)) > 0.5
        )

        if len(retrieved) >= 2 and high_confidence >= 1:
            score = min(1.0, 0.4 + (0.3 * len(retrieved)) + (0.3 * high_confidence))
            return score >= self.config.sufficiency_threshold, score
        elif len(retrieved) >= 1:
            score = 0.3 * len(retrieved)
            return score >= self.config.sufficiency_threshold, score
        else:
            return False, 0.0

    def apply_cost_governance(
        self, query: str
    ) -> tuple[bool, CostEstimate | None, str | None]:
        """Apply cost governance to determine if query should proceed.

        Returns:
            Tuple of (should_proceed, cost_estimate, degradation_message)
        """
        if not self.config.enable_cost_governance or self._cost_governance is None:
            return True, None, None

        try:
            plan = self._cost_governance.plan_query(query=query)

            if not plan.allowed:
                return False, plan.estimate, plan.degradation_message

            return True, plan.estimate, plan.degradation_message

        except Exception as exc:
            logger.warning(f"Cost governance check failed: {exc}")
            # Fail open - allow query to proceed
            return True, None, None

    def verify_faithfulness(
        self,
        statements: list[Statement],
        retrieved: list[dict[str, object]],
    ) -> FaithfulnessResult:
        """Verify that statements are faithful to retrieved evidence."""
        if not self._faithfulness_enabled:
            # Return a passing result when disabled
            return FaithfulnessResult(
                overall_score=10.0,  # Max score on 0-10 scale
                claims_checked=len(statements),
                unsupported_claim_count=0,
                per_claim=(),
                judge="disabled",
            )

        try:
            return self._faithfulness_verifier.evaluate(statements, retrieved)
        except Exception as exc:
            logger.warning(f"Faithfulness verification failed: {exc}")
            # Fail open - assume faithful on error
            return FaithfulnessResult(
                overall_score=10.0,
                claims_checked=len(statements),
                unsupported_claim_count=0,
                per_claim=(),
                judge="error_fallback",
            )

    def generate_answer(
        self, query: str, retrieved: list[dict[str, object]] | None = None
    ) -> AnswerContract:
        """Generate answer or abstain based on evidence with full feature integration.

        Args:
            query: The user query
            retrieved: Optional pre-retrieved evidence. If None, will retrieve using
                      the pipeline's retrieval configuration.
        """
        # Initialize metrics collector
        metrics_collector = create_metrics_collector(
            query=query,
            enable_db_sink=self.config.enable_metrics and self.config.enable_metrics_db,
        )

        def _record_ragas_scores(
            statement_rows: Sequence[Mapping[str, object]],
            retrieved_rows: Sequence[Mapping[str, object]],
            faithfulness: float | None = None,
        ) -> None:
            observability_metrics = import_module(
                "islam_intelligent.observability.metrics"
            )
            ragas_scores = observability_metrics.compute_ragas_metrics(
                query=query,
                statements=statement_rows,
                retrieved=retrieved_rows,
                faithfulness_score=faithfulness,
            )
            metrics_collector.record_ragas(
                faithfulness=ragas_scores.faithfulness,
                relevancy=ragas_scores.relevancy,
                precision=ragas_scores.precision,
                recall=ragas_scores.recall,
            )

        # Step 1: Retrieve (or use provided retrieved evidence)
        if retrieved:
            # Use provided evidence (backward compatibility)
            raw_retrieved_list = [dict(r) for r in retrieved]
            retrieval_metadata = {"hyde_used": False, "query_variations": 1}
            metrics_collector.record_retrieval(
                results=raw_retrieved_list,
                latency_ms=0.0,
                hyde_used=False,
                query_variations=1,
                reranker_used=False,
            )
        else:
            metrics_collector.start_stage("retrieval")
            retrieve_result = self.retrieve(query)
            if (
                isinstance(retrieve_result, tuple)
                and len(retrieve_result) == 2
                and isinstance(retrieve_result[1], Mapping)
            ):
                raw_retrieved_obj = retrieve_result[0]
                retrieval_metadata = dict(
                    cast(Mapping[str, object], retrieve_result[1])
                )
            else:
                raw_retrieved_obj = retrieve_result
                retrieval_metadata = {"hyde_used": False, "query_variations": 1}

            raw_retrieved_seq = cast(Sequence[Mapping[str, object]], raw_retrieved_obj)
            raw_retrieved_list = [dict(r) for r in raw_retrieved_seq]
            retrieval_latency = metrics_collector.end_stage("retrieval")
            metrics_collector.record_retrieval(
                results=raw_retrieved_list,
                latency_ms=retrieval_latency,
                hyde_used=bool(retrieval_metadata.get("hyde_used")),
                query_variations=int(
                    str(retrieval_metadata.get("query_variations", 1))
                ),
                reranker_used=False,  # Will update after reranking
            )

        # Step 2: Rerank if enabled
        metrics_collector.start_stage("reranking")
        reranked = self.rerank(query, raw_retrieved_list)
        reranking_latency = metrics_collector.end_stage("reranking")

        # Update metrics with reranker info
        if self.config.enable_reranker and self._reranker.is_available():
            if metrics_collector.metrics.retrieval:
                metrics_collector.metrics.retrieval.reranker_used = True
                metrics_collector.metrics.retrieval.latency_ms += reranking_latency

        # Step 3: Filter trusted sources
        trusted_retrieved = self._filter_trusted(reranked)

        if raw_retrieved_list and not trusted_retrieved:
            _record_ragas_scores(statement_rows=[], retrieved_rows=trusted_retrieved)
            metrics_collector.record_verdict(
                verdict="abstain", abstain_reason="untrusted_sources"
            )
            metrics_collector.finalize_and_record()
            return AnswerContract(
                verdict="abstain",
                statements=[],
                abstain_reason="untrusted_sources",
                fail_reason="untrusted_sources",
                retrieved_count=0,
                sufficiency_score=0.0,
                faithfulness_score=None,
                cost_usd=None,
                degradation_message=None,
                metrics=metrics_collector.get_metrics().to_dict(),
            )
        # Step 4: Validate sufficiency
        is_sufficient, sufficiency_score = self.validate_sufficiency(trusted_retrieved)

        if not is_sufficient:
            _record_ragas_scores(statement_rows=[], retrieved_rows=trusted_retrieved)
            metrics_collector.record_verdict(
                verdict="abstain", abstain_reason="insufficient_evidence"
            )
            metrics_collector.finalize_and_record()
            return AnswerContract(
                verdict="abstain",
                statements=[],
                abstain_reason="insufficient_evidence",
                fail_reason="insufficient_evidence",
                retrieved_count=len(trusted_retrieved),
                sufficiency_score=sufficiency_score,
                faithfulness_score=None,
                cost_usd=None,
                degradation_message=None,
                metrics=metrics_collector.get_metrics().to_dict(),
            )

        # Step 5: Apply cost governance
        should_proceed, cost_estimate, degradation_message = self.apply_cost_governance(
            query
        )

        if not should_proceed:
            metrics_collector.record_cost(
                estimate_usd=cost_estimate.total_cost_usd if cost_estimate else 0.0,
                governance_applied=True,
                degradation_message=degradation_message,
            )
            _record_ragas_scores(statement_rows=[], retrieved_rows=trusted_retrieved)
            metrics_collector.record_verdict(
                verdict="abstain", abstain_reason="budget_exceeded"
            )
            metrics_collector.finalize_and_record()
            return AnswerContract(
                verdict="abstain",
                statements=[],
                abstain_reason="budget_exceeded",
                fail_reason="budget_exceeded",
                retrieved_count=len(trusted_retrieved),
                sufficiency_score=sufficiency_score,
                faithfulness_score=None,
                cost_usd=cost_estimate.total_cost_usd if cost_estimate else 0.0,
                degradation_message=degradation_message,
                metrics=metrics_collector.get_metrics().to_dict(),
            )

        metrics_collector.record_cost(
            estimate_usd=cost_estimate.total_cost_usd if cost_estimate else 0.0,
            governance_applied=self.config.enable_cost_governance,
            degradation_message=degradation_message,
        )

        # Step 6: Generate
        metrics_collector.start_stage("generation")
        statements = self._generate_statements(query, trusted_retrieved)
        generation_latency = metrics_collector.end_stage("generation")

        # Estimate generation cost if not available from cost governance
        actual_cost = 0.0
        if cost_estimate:
            actual_cost = cost_estimate.total_cost_usd

        metrics_collector.record_generation(
            statements=statements,
            latency_ms=generation_latency,
            model_used=self.config.llm_model if self.config.enable_llm else "mock",
            cost_usd=actual_cost,
        )

        # Step 7: Post-generation verification
        metrics_collector.start_stage("verification")

        # 7a: Basic statement verification
        if not self._verify_statements(statements, trusted_retrieved):
            metrics_collector.record_verification(
                citation_verified=False,
                citation_fail_reason="statement_verification_failed",
            )
            _record_ragas_scores(
                statement_rows=statements, retrieved_rows=trusted_retrieved
            )
            metrics_collector.record_verdict(
                verdict="abstain", abstain_reason="verification_failed"
            )
            metrics_collector.finalize_and_record()
            return AnswerContract(
                verdict="abstain",
                statements=[],
                abstain_reason="verification_failed",
                fail_reason="verification_failed",
                retrieved_count=len(trusted_retrieved),
                sufficiency_score=sufficiency_score,
                faithfulness_score=None,
                cost_usd=actual_cost,
                degradation_message=degradation_message,
                metrics=metrics_collector.get_metrics().to_dict(),
            )

        # 7b: Citation verification
        try:
            citation_verification = self._citation_verifier.verify_citations(
                statements,
                trusted_retrieved,
            )
        except TypeError:
            # Backward compatibility for test doubles using legacy signature.
            citation_verification = self._citation_verifier.verify_citations(statements)
        if not citation_verification.verified:
            metrics_collector.record_verification(
                citation_verified=False,
                citation_fail_reason=citation_verification.reason,
            )
            _record_ragas_scores(
                statement_rows=statements, retrieved_rows=trusted_retrieved
            )
            metrics_collector.record_verdict(
                verdict="abstain", abstain_reason="citation_verification_failed"
            )
            metrics_collector.finalize_and_record()
            return AnswerContract(
                verdict="abstain",
                statements=[],
                abstain_reason="citation_verification_failed",
                fail_reason="citation_verification_failed",
                retrieved_count=len(trusted_retrieved),
                sufficiency_score=sufficiency_score,
                faithfulness_score=None,
                cost_usd=actual_cost,
                degradation_message=degradation_message,
                metrics=metrics_collector.get_metrics().to_dict(),
            )

        # 7c: Faithfulness verification
        faithfulness_result = self.verify_faithfulness(statements, trusted_retrieved)
        faithfulness_score = faithfulness_result.overall_score

        # Determine if faithful based on both threshold and unsupported claims
        is_faithful = (
            faithfulness_result.overall_score >= self.config.faithfulness_threshold
            and faithfulness_result.unsupported_claim_count == 0
        )
        unfaithful_indices = [
            claim.claim_index - 1  # Convert to 0-based index
            for claim in faithfulness_result.per_claim
            if not claim.supported
        ]

        _ = metrics_collector.end_stage("verification")

        metrics_collector.record_verification(
            citation_verified=True,
            faithfulness_score=faithfulness_score,
            faithfulness_verified=is_faithful,
            unfaithful_statements=unfaithful_indices,
        )

        _record_ragas_scores(
            statement_rows=statements,
            retrieved_rows=trusted_retrieved,
            faithfulness=faithfulness_score,
        )

        if not is_faithful:
            metrics_collector.record_verdict(
                verdict="abstain", abstain_reason="faithfulness_check_failed"
            )
            metrics_collector.finalize_and_record()
            return AnswerContract(
                verdict="abstain",
                statements=[],
                abstain_reason="faithfulness_check_failed",
                fail_reason="faithfulness_check_failed",
                retrieved_count=len(trusted_retrieved),
                sufficiency_score=sufficiency_score,
                faithfulness_score=faithfulness_score,
                cost_usd=actual_cost,
                degradation_message=degradation_message,
                metrics=metrics_collector.get_metrics().to_dict(),
            )

        # Success - return answer with all metrics
        metrics_collector.record_verdict(verdict="answer")
        metrics_collector.finalize_and_record()

        return AnswerContract(
            verdict="answer",
            statements=statements,
            abstain_reason=None,
            fail_reason=None,
            retrieved_count=len(trusted_retrieved),
            sufficiency_score=sufficiency_score,
            faithfulness_score=faithfulness_score,
            cost_usd=actual_cost,
            degradation_message=degradation_message,
            metrics=metrics_collector.get_metrics().to_dict(),
        )

    def _generate_statements(
        self, query: str, retrieved: list[dict[str, object]]
    ) -> list[Statement]:
        """Generate statements using LLM when enabled, otherwise use mock.

        LLM path is optional and fail-safe. Any generation error falls back to
        deterministic mock generation so existing behavior remains stable.
        """
        if not self.config.enable_llm:
            return self._mock_generate(query, retrieved)

        try:
            raw_statements = self._generator.generate(
                query,
                retrieved,
                min_citations=self.config.min_citations_per_statement,
            )
            statements: list[Statement] = []
            for item in raw_statements:
                text = str(item.get("text", "")).strip()
                citations_raw = item.get("citations", [])
                citations: list[Citation] = []
                if isinstance(citations_raw, list):
                    for citation in citations_raw:
                        if not isinstance(citation, dict):
                            continue
                        citations.append(
                            Citation(
                                evidence_span_id=str(
                                    citation.get("evidence_span_id", "")
                                ),
                                canonical_id=str(
                                    citation.get("canonical_id", "unknown")
                                ),
                                snippet=str(citation.get("snippet", "")),
                            )
                        )
                if text:
                    statements.append(Statement(text=text, citations=citations))
            if statements:
                return statements
        except Exception:
            # Fail-safe fallback preserves deterministic behavior.
            pass

        return self._mock_generate(query, retrieved)

    def _mock_generate(
        self, _query: str, retrieved: list[dict[str, object]]
    ) -> list[Statement]:
        """Mock generator - creates statements from evidence.

        In production, this would be an LLM call.
        """
        # Create a simple statement citing the top evidence
        if not retrieved:
            return []

        citations: list[Citation] = []
        for r in retrieved[:3]:  # Top 3 citations
            snippet = str(r.get("snippet", ""))
            citations.append(
                Citation(
                    evidence_span_id=str(
                        r.get("evidence_span_id", r.get("text_unit_id", ""))
                    ),
                    canonical_id=str(r.get("canonical_id", "unknown")),
                    snippet=snippet[:100] + "..." if len(snippet) > 100 else snippet,
                )
            )

        return [
            Statement(
                text=f"Based on the evidence, here is information about the query.",
                citations=citations,
            )
        ]

    def _verify_statements(
        self, statements: list[Statement], retrieved: list[dict[str, object]]
    ) -> bool:
        """Post-generation verification.

        Checks:
        - Every statement has citations
        - Every citation resolves to retrieved evidence
        """
        if not statements:
            return False

        retrieved_ids = {
            str(r.get("evidence_span_id", r.get("text_unit_id", ""))) for r in retrieved
        }

        for stmt in statements:
            # Must have citations
            if not stmt.get("citations"):
                return False

            # Each citation must resolve
            for citation in stmt["citations"]:
                if citation["evidence_span_id"] not in retrieved_ids:
                    return False

        return True

    async def aretrieve(
        self, query: str
    ) -> tuple[Sequence[Mapping[str, object]], dict[str, object]]:
        """Asynchronous retrieval wrapper for non-blocking endpoints."""
        return await asyncio.to_thread(self.retrieve, query)

    async def arerank(
        self, query: str, results: Sequence[Mapping[str, object]]
    ) -> list[dict[str, object]]:
        """Asynchronous reranking wrapper for non-blocking endpoints."""
        return await asyncio.to_thread(self.rerank, query, results)

    async def agenerate_answer(
        self, query: str, retrieved: list[dict[str, object]] | None = None
    ) -> AnswerContract:
        """Run the synchronous pipeline off the event loop.

        This keeps async API endpoints responsive while retrieval and optional
        LLM generation execute in a worker thread.
        """
        return await asyncio.to_thread(self.generate_answer, query, retrieved)

    async def aquery(self, query: str) -> AnswerContract:
        """Asynchronous entry point for full RAG query execution."""
        return await self.agenerate_answer(query, None)

    def query(self, query: str) -> AnswerContract:
        """Full RAG query pipeline with all features integrated."""
        return self.generate_answer(query, None)


__all__ = [
    "RAGPipeline",
    "RAGConfig",
    "AnswerContract",
    "Citation",
    "Statement",
]
