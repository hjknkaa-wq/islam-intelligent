"""Tests for RAG abstention gates.

These tests are deterministic and do not require a seeded dev DB.
"""

from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUntypedBaseClass=false

from dataclasses import dataclass

import pytest

from islam_intelligent.rag.pipeline import RAGConfig, RAGPipeline
from islam_intelligent.rag.verify import CitationVerificationResult


@dataclass(frozen=True)
class _StubCitationVerifier:
    verified: bool
    reason: str | None = None

    def verify_citations(self, statements):  # type: ignore[no-untyped-def]
        checked = 0
        if isinstance(statements, list):
            for s in statements:
                if isinstance(s, dict) and isinstance(s.get("citations"), list):
                    checked += len(s.get("citations") or [])
        return CitationVerificationResult(
            verified=self.verified,
            reason=self.reason,
            checked_citation_count=checked,
        )


def _trusted_result(
    evidence_span_id: str,
    *,
    score: float,
    canonical_id: str = "quran:1:1",
    snippet: str = "sample snippet",
) -> dict[str, object]:
    return {
        "evidence_span_id": evidence_span_id,
        "text_unit_id": evidence_span_id,
        "score": score,
        "snippet": snippet,
        "canonical_id": canonical_id,
        "source_id": "source:trusted",
        "trust_status": "trusted",
    }


class TestRAGAbstainGate:
    def test_insufficient_evidence_abstains_when_retrieval_empty(self) -> None:
        class EmptyRetrievePipeline(RAGPipeline):
            def retrieve(self, _query: str):  # type: ignore[override]
                return []

        pipeline = EmptyRetrievePipeline(RAGConfig(sufficiency_threshold=0.6))
        result = pipeline.query("anything")

        assert result["verdict"] == "abstain"
        assert result["abstain_reason"] == "insufficient_evidence"
        assert result["fail_reason"] == "insufficient_evidence"
        assert result["retrieved_count"] == 0
        assert result["sufficiency_score"] == 0.0
        assert result["statements"] == []

    def test_insufficient_evidence_abstains_when_below_threshold(self) -> None:
        class LowEvidencePipeline(RAGPipeline):
            def retrieve(self, _query: str):  # type: ignore[override]
                return [_trusted_result("es_low_1", score=0.1)]

        pipeline = LowEvidencePipeline(RAGConfig(sufficiency_threshold=0.6))
        result = pipeline.query("low")

        assert result["verdict"] == "abstain"
        assert result["abstain_reason"] == "insufficient_evidence"
        assert result["retrieved_count"] == 1
        assert result["sufficiency_score"] == pytest.approx(0.3)

    def test_untrusted_sources_abstains_when_all_results_untrusted(self) -> None:
        class UntrustedOnlyPipeline(RAGPipeline):
            def retrieve(self, _query: str):  # type: ignore[override]
                return [
                    {
                        "evidence_span_id": "es_u_1",
                        "text_unit_id": "es_u_1",
                        "score": 0.99,
                        "snippet": "untrusted",
                        "canonical_id": "quran:1:1",
                        "source_id": "source:untrusted",
                        "trust_status": "untrusted",
                    },
                    {
                        "evidence_span_id": "es_u_2",
                        "text_unit_id": "es_u_2",
                        "score": 0.99,
                        "snippet": "missing trust_status is fail-safe dropped",
                        "canonical_id": "quran:1:2",
                        "source_id": "source:unknown",
                        # trust_status omitted intentionally
                    },
                ]

        pipeline = UntrustedOnlyPipeline(RAGConfig(sufficiency_threshold=0.1))
        result = pipeline.query("untrusted")

        assert result["verdict"] == "abstain"
        assert result["abstain_reason"] == "untrusted_sources"
        assert result["fail_reason"] == "untrusted_sources"
        assert result["retrieved_count"] == 0
        assert result["sufficiency_score"] == 0.0

    def test_untrusted_sources_not_triggered_when_no_results(self) -> None:
        class EmptyRetrievePipeline(RAGPipeline):
            def retrieve(self, _query: str):  # type: ignore[override]
                return []

        pipeline = EmptyRetrievePipeline(RAGConfig(sufficiency_threshold=0.1))
        result = pipeline.query("none")

        assert result["verdict"] == "abstain"
        assert result["abstain_reason"] == "insufficient_evidence"

    def test_verification_failed_when_generator_returns_no_statements(self) -> None:
        class BadGeneratorPipeline(RAGPipeline):
            def retrieve(self, _query: str):  # type: ignore[override]
                return [
                    _trusted_result("es_ok_1", score=0.9),
                    _trusted_result("es_ok_2", score=0.2),
                ]

            def _mock_generate(self, _query: str, _retrieved):  # type: ignore[override]
                return []

        pipeline = BadGeneratorPipeline(
            RAGConfig(sufficiency_threshold=0.1),
            citation_verifier=_StubCitationVerifier(verified=True),
        )
        result = pipeline.query("bad")

        assert result["verdict"] == "abstain"
        assert result["abstain_reason"] == "verification_failed"
        assert result["fail_reason"] == "verification_failed"

    def test_verification_failed_when_statement_has_no_citations(self) -> None:
        class NoCitationPipeline(RAGPipeline):
            def retrieve(self, _query: str):  # type: ignore[override]
                return [
                    _trusted_result("es_ok_1", score=0.9),
                    _trusted_result("es_ok_2", score=0.2),
                ]

            def _mock_generate(self, _query: str, _retrieved):  # type: ignore[override]
                return [{"text": "no citations", "citations": []}]

        pipeline = NoCitationPipeline(
            RAGConfig(sufficiency_threshold=0.1),
            citation_verifier=_StubCitationVerifier(verified=True),
        )
        result = pipeline.query("no-citations")

        assert result["verdict"] == "abstain"
        assert result["abstain_reason"] == "verification_failed"
        assert result["fail_reason"] == "verification_failed"

    def test_verification_failed_when_citation_does_not_resolve_to_retrieved(
        self,
    ) -> None:
        class NonResolvingCitationPipeline(RAGPipeline):
            def retrieve(self, _query: str):  # type: ignore[override]
                return [
                    _trusted_result("es_ok_1", score=0.9),
                    _trusted_result("es_ok_2", score=0.2),
                ]

            def _mock_generate(self, _query: str, _retrieved):  # type: ignore[override]
                return [
                    {
                        "text": "citation not in retrieved",
                        "citations": [
                            {
                                "evidence_span_id": "es_missing",
                                "canonical_id": "quran:1:1",
                                "snippet": "x",
                            }
                        ],
                    }
                ]

        pipeline = NonResolvingCitationPipeline(
            RAGConfig(sufficiency_threshold=0.1),
            citation_verifier=_StubCitationVerifier(verified=True),
        )
        result = pipeline.query("non-resolving")

        assert result["verdict"] == "abstain"
        assert result["abstain_reason"] == "verification_failed"

    def test_citation_verification_failed_when_verifier_rejects(self) -> None:
        class RejectingVerifierPipeline(RAGPipeline):
            def retrieve(self, _query: str):  # type: ignore[override]
                return [
                    _trusted_result("es_ok_1", score=0.9),
                    _trusted_result("es_ok_2", score=0.2),
                ]

            def _mock_generate(self, _query: str, retrieved):  # type: ignore[override]
                # Resolve to retrieved evidence_span_ids so _verify_statements passes.
                return [
                    {
                        "text": "has citations",
                        "citations": [
                            {
                                "evidence_span_id": str(
                                    retrieved[0]["evidence_span_id"]
                                ),
                                "canonical_id": "quran:1:1",
                                "snippet": "ok",
                            }
                        ],
                    }
                ]

        pipeline = RejectingVerifierPipeline(
            RAGConfig(sufficiency_threshold=0.1),
            citation_verifier=_StubCitationVerifier(
                verified=False, reason="hash_mismatch"
            ),
        )
        result = pipeline.query("reject")

        assert result["verdict"] == "abstain"
        assert result["abstain_reason"] == "citation_verification_failed"
        assert result["fail_reason"] == "citation_verification_failed"

    def test_answer_when_all_gates_pass(self) -> None:
        class OkPipeline(RAGPipeline):
            def retrieve(self, _query: str):  # type: ignore[override]
                return [
                    _trusted_result("es_ok_1", score=0.9),
                    _trusted_result("es_ok_2", score=0.2),
                ]

        pipeline = OkPipeline(
            RAGConfig(sufficiency_threshold=0.1),
            citation_verifier=_StubCitationVerifier(verified=True),
        )
        result = pipeline.query("ok")

        assert result["verdict"] == "answer"
        assert result["abstain_reason"] is None
        assert result["fail_reason"] is None
        assert result["retrieved_count"] == 2
        assert isinstance(result["statements"], list)
        assert len(result["statements"]) >= 1

    def test_filter_trusted_is_fail_safe(self) -> None:
        pipeline = RAGPipeline(RAGConfig())
        raw = [
            {"text_unit_id": "es1", "trust_status": "Trusted"},
            {"text_unit_id": "es2", "trust_status": "TRUSTED"},
            {"text_unit_id": "es3", "trust_status": "untrusted"},
            {"text_unit_id": "es4", "trust_status": None},
            {"text_unit_id": "es5"},
        ]
        trusted = pipeline._filter_trusted(raw)
        assert [r["text_unit_id"] for r in trusted] == ["es1", "es2"]

    def test_query_counts_only_trusted_results(self) -> None:
        class MixedTrustPipeline(RAGPipeline):
            def retrieve(self, _query: str):  # type: ignore[override]
                return [
                    _trusted_result("es_t_1", score=0.9),
                    {
                        "text_unit_id": "es_u_1",
                        "score": 0.99,
                        "snippet": "untrusted",
                        "canonical_id": "quran:1:3",
                        "source_id": "source:untrusted",
                        "trust_status": "untrusted",
                    },
                    _trusted_result("es_t_2", score=0.2),
                ]

        pipeline = MixedTrustPipeline(
            RAGConfig(sufficiency_threshold=0.1),
            citation_verifier=_StubCitationVerifier(verified=True),
        )
        result = pipeline.query("mixed")
        assert result["verdict"] == "answer"
        assert result["retrieved_count"] == 2
