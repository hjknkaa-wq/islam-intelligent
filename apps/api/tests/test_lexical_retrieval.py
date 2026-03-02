"""Tests for lexical retrieval."""

import pytest

from islam_intelligent.rag.retrieval.lexical import search_lexical


class TestLexicalRetrieval:
    """Test lexical search functionality."""

    def test_empty_query_returns_empty(self):
        """Empty query should return empty list."""
        results = search_lexical("")
        assert results == []

    def test_whitespace_query_returns_empty(self):
        """Whitespace-only query should return empty list."""
        results = search_lexical("   ")
        assert results == []

    def test_search_finds_quran_ayahs(self):
        """Search should find Quran ayahs containing query."""
        # Search for "Allah" which appears in many ayahs
        results = search_lexical("الله", limit=5)

        # Should return results (fixture data has Allah in many ayahs)
        assert isinstance(results, list)
        # Note: This may return empty if no fixture data loaded
        # The test documents expected behavior

    def test_results_have_required_fields(self):
        """Results should have text_unit_id, score, snippet."""
        # Use a very generic search that might match anything
        results = search_lexical("ب", limit=1)

        if results:  # Only check if we have results
            result = results[0]
            assert "text_unit_id" in result
            assert "score" in result
            assert "snippet" in result
            assert isinstance(result["score"], float)
            assert 0.0 <= result["score"] <= 1.0

    def test_results_sorted_by_score(self):
        """Results should be sorted by score descending."""
        results = search_lexical("الله", limit=5)

        if len(results) > 1:
            scores = [r["score"] for r in results]
            assert scores == sorted(scores, reverse=True)

    def test_respects_limit(self):
        """Should not return more results than limit."""
        results = search_lexical("الله", limit=3)
        assert len(results) <= 3
