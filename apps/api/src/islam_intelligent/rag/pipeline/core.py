"""RAG Pipeline: retrieve -> validate -> answer (with abstention).

This module implements the core evidence-first RAG flow:
1. Retrieve candidate evidence spans
2. Validate sufficiency (gate)
3. Generate answer with citations OR abstain
4. Verify post-generation
"""

from dataclasses import dataclass
from collections.abc import Mapping, Sequence
from typing import Protocol, TypedDict

from ..generator import LLMGenerator
from ..retrieval.hybrid import search_hybrid
from ..verify import CitationVerifier


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


class RAGPipeline:
    """Evidence-first RAG pipeline with abstention."""

    def __init__(
        self,
        config: RAGConfig | None = None,
        citation_verifier: CitationVerifier | None = None,
        generator: GeneratorProtocol | None = None,
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

    def retrieve(self, query: str) -> Sequence[Mapping[str, object]]:
        """Retrieve candidate evidence spans."""
        return search_hybrid(query, limit=self.config.max_retrieval)

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

    def generate_answer(
        self, query: str, retrieved: list[dict[str, object]]
    ) -> AnswerContract:
        """Generate answer or abstain based on evidence."""
        # Step 1: Retrieve (already done)

        # Step 2: Validate sufficiency
        is_sufficient, sufficiency_score = self.validate_sufficiency(retrieved)

        if not is_sufficient:
            # ABSTAIN - don't call generator
            return AnswerContract(
                verdict="abstain",
                statements=[],
                abstain_reason="insufficient_evidence",
                fail_reason="insufficient_evidence",
                retrieved_count=len(retrieved),
                sufficiency_score=sufficiency_score,
            )

        # Step 3: Generate
        statements = self._generate_statements(query, retrieved)

        # Step 4: Post-generation verification
        if not self._verify_statements(statements, retrieved):
            return AnswerContract(
                verdict="abstain",
                statements=[],
                abstain_reason="verification_failed",
                fail_reason="verification_failed",
                retrieved_count=len(retrieved),
                sufficiency_score=sufficiency_score,
            )

        citation_verification = self._citation_verifier.verify_citations(statements)
        if not citation_verification.verified:
            return AnswerContract(
                verdict="abstain",
                statements=[],
                abstain_reason="citation_verification_failed",
                fail_reason="citation_verification_failed",
                retrieved_count=len(retrieved),
                sufficiency_score=sufficiency_score,
            )

        return AnswerContract(
            verdict="answer",
            statements=statements,
            abstain_reason=None,
            fail_reason=None,
            retrieved_count=len(retrieved),
            sufficiency_score=sufficiency_score,
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

    def query(self, query: str) -> AnswerContract:
        """Full RAG query pipeline."""
        raw_retrieved = [dict(r) for r in self.retrieve(query)]
        trusted_retrieved = self._filter_trusted(raw_retrieved)

        if raw_retrieved and not trusted_retrieved:
            return AnswerContract(
                verdict="abstain",
                statements=[],
                abstain_reason="untrusted_sources",
                fail_reason="untrusted_sources",
                retrieved_count=0,
                sufficiency_score=0.0,
            )

        return self.generate_answer(query, trusted_retrieved)
