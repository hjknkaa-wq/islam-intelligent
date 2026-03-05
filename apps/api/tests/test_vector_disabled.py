"""Tests for vector search fallback behavior."""

# pyright: reportMissingImports=false, reportUnknownVariableType=false

from islam_intelligent.rag.retrieval.vector import is_vector_available, search_vector
from islam_intelligent.rag.retrieval.hybrid import search_hybrid


class TestVectorFallback:
    """Test vector search graceful fallback behavior."""

    def test_vector_returns_empty_without_embeddings(self):
        """Vector search should return empty when DB has no embeddings."""
        results = search_vector("test query", limit=10)
        assert results == []

    def test_is_vector_available_returns_true(self):
        """is_vector_available should return True with fallback embeddings."""
        assert is_vector_available() is True

    def test_hybrid_falls_back_gracefully(self):
        """Hybrid should continue working when vector results are empty."""
        results = search_hybrid("ب", limit=5)

        # Should return list (may be empty if no data)
        assert isinstance(results, list)

        # If we have results, they should have required fields
        if results:
            result = results[0]
            assert "text_unit_id" in result
            assert "score" in result
            assert "snippet" in result
