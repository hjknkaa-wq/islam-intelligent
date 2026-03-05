"""Tests for query expansion functionality."""

from __future__ import annotations

import pytest

from islam_intelligent.rag.retrieval.query_expander import (
    QueryExpander,
    QueryExpanderConfig,
    create_default_expander,
)


class TestQueryExpander:
    """Test query expansion functionality."""

    def test_expand_returns_variations(self) -> None:
        """Should return multiple variations of the query."""
        expander = QueryExpander()
        query = "prayer"

        variations = expander.expand(query, num_variations=5)

        assert len(variations) == 5
        assert "prayer" in variations
        assert "Quran verses about prayer" in variations
        assert "Hadith on prayer" in variations
        assert "Islamic perspective on prayer" in variations
        assert "What does Quran say about prayer" in variations

    def test_expand_respects_num_variations(self) -> None:
        """Should return exactly the requested number of variations."""
        expander = QueryExpander()

        assert len(expander.expand("test", num_variations=1)) == 1
        assert len(expander.expand("test", num_variations=3)) == 3
        assert len(expander.expand("test", num_variations=5)) == 5

    def test_expand_returns_original_first(self) -> None:
        """Original query should be first in the list."""
        expander = QueryExpander()

        variations = expander.expand("charity")

        assert variations[0] == "charity"

    def test_expand_strips_whitespace(self) -> None:
        """Should handle queries with leading/trailing whitespace."""
        expander = QueryExpander()

        variations = expander.expand("  fasting  ", num_variations=2)

        assert variations[0] == "fasting"
        assert variations[1] == "Quran verses about fasting"

    def test_expand_raises_on_empty_query(self) -> None:
        """Should raise ValueError for empty queries."""
        expander = QueryExpander()

        with pytest.raises(ValueError, match="Query cannot be empty"):
            expander.expand("")

        with pytest.raises(ValueError, match="Query cannot be empty"):
            expander.expand("   ")

        with pytest.raises(ValueError, match="Query cannot be empty"):
            expander.expand(None)  # type: ignore[arg-type]

    def test_expand_disabled_returns_original(self) -> None:
        """When disabled, should return only original query."""
        config = QueryExpanderConfig(enabled=False)
        expander = QueryExpander(config=config)

        variations = expander.expand("test", num_variations=5)

        assert variations == ["test"]

    def test_deduplicate_removes_duplicates(self) -> None:
        """Should remove duplicate variations."""
        config = QueryExpanderConfig(deduplicate=True)
        expander = QueryExpander(config=config)

        # Create variations that might be similar
        variations = expander.expand("test")

        # Check no duplicates
        assert len(variations) == len(set(v.lower() for v in variations))

    def test_deduplicate_case_insensitive(self) -> None:
        """Deduplication should be case-insensitive."""
        expander = QueryExpander()

        # Manually test deduplication
        result = expander._deduplicate(["Test", "test", "TEST", "Query"])

        assert result == ["Test", "Query"]


class TestQueryExpanderConfig:
    """Test query expander configuration."""

    def test_default_config(self) -> None:
        """Default config should have sensible defaults."""
        config = QueryExpanderConfig()

        assert config.enabled is True
        assert config.num_variations == 5
        assert config.include_original is True
        assert config.deduplicate is True

    def test_custom_config(self) -> None:
        """Should accept custom configuration."""
        config = QueryExpanderConfig(
            enabled=False,
            num_variations=3,
            include_original=False,
            deduplicate=False,
        )

        assert config.enabled is False
        assert config.num_variations == 3
        assert config.include_original is False
        assert config.deduplicate is False


class TestExpandWithSources:
    """Test source-specific query expansion."""

    def test_expand_with_quran_source(self) -> None:
        """Should return only Quran-related variations."""
        expander = QueryExpander()

        variations = expander.expand_with_sources("prayer", source_types=["quran"])

        assert all("quran" in v.lower() or v.lower() == "prayer" for v in variations)

    def test_expand_with_hadith_source(self) -> None:
        """Should return only Hadith-related variations."""
        expander = QueryExpander()

        variations = expander.expand_with_sources("charity", source_types=["hadith"])

        assert all("hadith" in v.lower() for v in variations)

    def test_expand_with_multiple_sources(self) -> None:
        """Should return variations for multiple source types."""
        expander = QueryExpander()

        variations = expander.expand_with_sources(
            "fasting", source_types=["quran", "hadith"]
        )

        assert any("quran" in v.lower() for v in variations)
        assert any("hadith" in v.lower() for v in variations)

    def test_expand_with_fiqh_source(self) -> None:
        """Should return fiqh/scholarly perspective variations."""
        expander = QueryExpander()

        variations = expander.expand_with_sources("zakat", source_types=["fiqh"])

        assert any("perspective" in v.lower() for v in variations)

    def test_expand_with_no_matching_sources(self) -> None:
        """Should return original query when no sources match."""
        expander = QueryExpander()

        variations = expander.expand_with_sources("test", source_types=["unknown"])

        assert variations == ["test"]


class TestCreateDefaultExpander:
    """Test default expander factory function."""

    def test_create_default_expander(self) -> None:
        """Should create properly configured expander."""
        expander = create_default_expander(enabled=True, num_variations=3)

        assert expander.config.enabled is True
        assert expander.config.num_variations == 3
        assert expander.config.deduplicate is True

    def test_create_disabled_expander(self) -> None:
        """Should create disabled expander."""
        expander = create_default_expander(enabled=False)

        variations = expander.expand("test", num_variations=5)

        assert variations == ["test"]


class TestQueryExpanderIntegration:
    """Integration-style tests for query expansion."""

    def test_expand_variations_cover_different_aspects(self) -> None:
        """Variations should cover different Islamic knowledge aspects."""
        expander = QueryExpander()

        variations = expander.expand("marriage", num_variations=5)

        # Should have original
        assert "marriage" in variations

        # Should have Quran-focused
        assert any("quran" in v.lower() for v in variations)

        # Should have Hadith-focused
        assert any("hadith" in v.lower() for v in variations)

        # Should have scholarly perspective
        assert any(
            "perspective" in v.lower() or "islamic" in v.lower() for v in variations
        )

    def test_variations_are_distinct(self) -> None:
        """All variations should be distinct from each other."""
        expander = QueryExpander()

        variations = expander.expand("hajj", num_variations=5)

        # All lowercase variations should be unique
        lower_variations = [v.lower() for v in variations]
        assert len(lower_variations) == len(set(lower_variations))

    def test_complex_query_handling(self) -> None:
        """Should handle multi-word queries correctly."""
        expander = QueryExpander()

        query = "rights of orphans"
        variations = expander.expand(query, num_variations=3)

        assert variations[0] == "rights of orphans"
        assert all(query in v for v in variations)

    def test_arabic_query_handling(self) -> None:
        """Should handle Arabic text correctly."""
        expander = QueryExpander()

        query = "الصلاة"
        variations = expander.expand(query, num_variations=3)

        assert variations[0] == "الصلاة"
        assert all(query in v for v in variations)
