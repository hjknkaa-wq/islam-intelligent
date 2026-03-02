"""Tests for vector search (disabled mode)."""

import pytest

from islam_intelligent.rag.retrieval.vector import is_vector_available, search_vector
from islam_intelligent.rag.retrieval.hybrid import search_hybrid


class TestVectorDisabled:
    """Test vector search when disabled."""

    def test_vector_returns_empty(self):
        """Vector search should return empty when not configured."""
        results = search_vector("test query", limit=10)
        assert results == []

    def test_is_vector_available_returns_false(self):
        """is_vector_available should return False when not configured."""
        assert is_vector_available() is False

    def test_hybrid_falls_back_to_lexical(self):
        """Hybrid should work even when vector is disabled."""
        # This tests that hybrid doesn't crash when vector is unavailable
        results = search_hybrid("ب", limit=5)

        # Should return list (may be empty if no data)
        assert isinstance(results, list)

        # If we have results, they should have required fields
        if results:
            result = results[0]
            assert "text_unit_id" in result
            assert "score" in result
            assert "snippet" in result
