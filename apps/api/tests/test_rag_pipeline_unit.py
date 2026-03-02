"""Unit tests for RAG pipeline (no DB required)."""

import pytest

from islam_intelligent.rag.pipeline.core import RAGConfig, RAGPipeline


class TestRAGPipelineUnit:
    """Unit tests for RAG pipeline logic."""

    def test_sufficiency_calculation_low(self):
        """Test sufficiency score with minimal evidence."""
        pipeline = RAGPipeline()

        # Mock retrieved data
        retrieved = [{"score": 0.3}]
        is_sufficient, score = pipeline.validate_sufficiency(retrieved)

        assert score > 0
        assert score < 0.6  # Low score expected

    def test_sufficiency_calculation_high(self):
        """Test sufficiency score with good evidence."""
        pipeline = RAGPipeline()

        retrieved = [{"score": 0.8}, {"score": 0.7}, {"score": 0.6}]
        is_sufficient, score = pipeline.validate_sufficiency(retrieved)

        assert score >= 0.6
        assert is_sufficient is True

    def test_empty_retrieval_not_sufficient(self):
        """Empty retrieval should not be sufficient."""
        pipeline = RAGPipeline()

        is_sufficient, score = pipeline.validate_sufficiency([])

        assert is_sufficient is False
        assert score == 0.0

    def test_verify_statements_no_citations(self):
        """Statements without citations should fail verification."""
        pipeline = RAGPipeline()

        statements = [{"text": "No citations here", "citations": []}]
        retrieved = [{"text_unit_id": "es_1"}]

        result = pipeline._verify_statements(statements, retrieved)
        assert result is False

    def test_verify_statements_with_valid_citations(self):
        """Statements with valid citations should pass."""
        pipeline = RAGPipeline()

        statements = [
            {"text": "With citations", "citations": [{"evidence_span_id": "es_1"}]}
        ]
        retrieved = [{"text_unit_id": "es_1"}]

        result = pipeline._verify_statements(statements, retrieved)
        assert result is True

    def test_verify_statements_invalid_citation(self):
        """Statements with non-existent citations should fail."""
        pipeline = RAGPipeline()

        statements = [
            {
                "text": "Invalid citation",
                "citations": [{"evidence_span_id": "es_invalid"}],
            }
        ]
        retrieved = [{"text_unit_id": "es_1"}]

        result = pipeline._verify_statements(statements, retrieved)
        assert result is False

    def test_abstain_output_structure(self):
        """Abstain output should have correct structure."""
        pipeline = RAGPipeline()

        # Force abstain with no evidence
        answer = pipeline.generate_answer("test", [])

        assert answer["verdict"] == "abstain"
        assert answer["abstain_reason"] is not None
        assert len(answer["statements"]) == 0
        assert "retrieved_count" in answer
        assert "sufficiency_score" in answer

    def test_answer_output_structure(self):
        """Answer output should have correct structure."""
        pipeline = RAGPipeline(RAGConfig(sufficiency_threshold=0.1))

        # Mock sufficient evidence
        retrieved = [
            {
                "text_unit_id": "es_1",
                "score": 0.8,
                "snippet": "test1",
                "canonical_id": "q:1:1",
            },
            {
                "text_unit_id": "es_2",
                "score": 0.7,
                "snippet": "test2",
                "canonical_id": "q:1:2",
            },
        ]

        answer = pipeline.generate_answer("test", retrieved)

        if answer["verdict"] == "answer":
            assert answer["abstain_reason"] is None
            assert len(answer["statements"]) > 0
            assert answer["sufficiency_score"] >= 0.1
