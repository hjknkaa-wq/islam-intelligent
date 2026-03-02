"""Tests for RAG citation requirements."""

import pytest

from islam_intelligent.rag.pipeline import RAGConfig, RAGPipeline


class TestRAGCitationRequired:
    """Test that RAG outputs require citations."""

    def test_answer_has_citations(self):
        """Generated answer must include citations."""
        pipeline = RAGPipeline(RAGConfig(sufficiency_threshold=0.3))

        # Use a query that should find evidence (general religious term)
        result = pipeline.query("الله")  # "Allah" in Arabic

        if result["verdict"] == "answer":
            # Must have statements
            assert len(result["statements"]) > 0

            # Each statement must have citations
            for stmt in result["statements"]:
                assert "citations" in stmt
                assert len(stmt["citations"]) > 0

                # Each citation must have required fields
                for citation in stmt["citations"]:
                    assert "evidence_span_id" in citation
                    assert "canonical_id" in citation

    def test_no_statements_without_citations(self):
        """No statement should exist without citations."""
        pipeline = RAGPipeline(RAGConfig(sufficiency_threshold=0.3))

        result = pipeline.query("محمد")  # "Muhammad" in Arabic

        if result["verdict"] == "answer":
            for stmt in result["statements"]:
                assert stmt.get("citations"), "Statement without citations found"
