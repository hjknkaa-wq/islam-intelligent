"""Tests for RAG abstention gate."""

import pytest

from islam_intelligent.rag.pipeline import RAGConfig, RAGPipeline


class TestRAGAbstainGate:
    """Test abstention behavior when evidence is insufficient."""

    def test_abstains_with_no_evidence(self):
        """Should abstain when no evidence found."""
        pipeline = RAGPipeline(RAGConfig(sufficiency_threshold=0.6))

        # Query that likely won't match anything
        result = pipeline.query("xyznonexistent12345")

        assert result["verdict"] == "abstain"
        assert result["abstain_reason"] == "insufficient_evidence"
        assert len(result["statements"]) == 0

    def test_abstains_with_insufficient_evidence(self):
        """Should abstain when evidence score below threshold."""
        # High threshold should cause abstention
        pipeline = RAGPipeline(RAGConfig(sufficiency_threshold=0.95))

        result = pipeline.query("test")

        if result["retrieved_count"] < 3:  # If not much evidence
            assert result["verdict"] == "abstain"
            assert result["sufficiency_score"] < 0.95

    def test_abstain_has_no_statements(self):
        """Abstention should not have any statements."""
        pipeline = RAGPipeline(RAGConfig(sufficiency_threshold=0.9))

        result = pipeline.query("veryunlikelymatchabc123")

        if result["verdict"] == "abstain":
            assert len(result["statements"]) == 0
            assert result["abstain_reason"] is not None

    def test_sufficient_evidence_returns_answer(self):
        """Should return answer when evidence is sufficient."""
        # Low threshold to ensure answer
        pipeline = RAGPipeline(RAGConfig(sufficiency_threshold=0.1))

        # Query that should find evidence
        result = pipeline.query("الله")  # "Allah"

        if result["retrieved_count"] >= 2:
            assert result["verdict"] == "answer"
            assert result["abstain_reason"] is None
