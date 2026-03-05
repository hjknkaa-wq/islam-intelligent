"""Query expansion for multi-query retrieval.

This module implements query variation generation to improve retrieval recall
by covering different aspects of the original query.
"""

from dataclasses import dataclass, field
from typing import Protocol


class QueryExpanderProtocol(Protocol):
    """Protocol for query expanders."""

    def expand(self, query: str, num_variations: int = 5) -> list[str]:
        """Generate query variations from original query."""
        ...


@dataclass
class QueryExpanderConfig:
    """Configuration for query expansion.

    Attributes:
        enabled: Whether query expansion is enabled
        num_variations: Number of variations to generate (3-5 recommended)
        include_original: Whether to include original query in results
        deduplicate: Whether to deduplicate similar variations
    """

    enabled: bool = True
    num_variations: int = 5
    include_original: bool = True
    deduplicate: bool = True


@dataclass
class QueryExpander:
    """Generate query variations for multi-query retrieval.

    Creates variations covering different Islamic knowledge aspects:
    - Original query
    - Quran-specific variations
    - Hadith-specific variations
    - Fiqh/scholarly perspective variations

    Example:
        >>> expander = QueryExpander()
        >>> expander.expand("prayer", num_variations=5)
        ['prayer',
         'Quran verses about prayer',
         'Hadith on prayer',
         'Islamic perspective on prayer',
         'What does Quran say about prayer']
    """

    config: QueryExpanderConfig = field(default_factory=QueryExpanderConfig)

    # Templates for query variations
    # Order matters: original first, then most specific to most general
    _TEMPLATES: list[str] = field(
        default_factory=lambda: [
            "{query}",  # Original (handled specially)
            "Quran verses about {query}",
            "Hadith on {query}",
            "Islamic perspective on {query}",
            "What does Quran say about {query}",
        ]
    )

    def expand(self, query: str, num_variations: int | None = None) -> list[str]:
        """Generate query variations from original query.

        Args:
            query: Original user query
            num_variations: Number of variations to generate.
                          If None, uses config.num_variations.

        Returns:
            List of query variations. If expansion is disabled,
            returns only the original query.

        Raises:
            ValueError: If query is empty or None
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty or None")

        if not self.config.enabled:
            return [query.strip()]

        target_count = (
            num_variations if num_variations is not None else self.config.num_variations
        )
        target_count = max(1, min(target_count, len(self._TEMPLATES)))

        variations: list[str] = []

        # Generate variations using templates
        for template in self._TEMPLATES[:target_count]:
            variation = template.format(query=query.strip())
            variations.append(variation)

        # Remove duplicates while preserving order
        if self.config.deduplicate:
            variations = self._deduplicate(variations)

        return variations

    def _deduplicate(self, variations: list[str]) -> list[str]:
        """Remove duplicate variations preserving order.

        Uses case-insensitive comparison for deduplication.
        """
        seen: set[str] = set()
        result: list[str] = []

        for v in variations:
            normalized = v.lower().strip()
            if normalized not in seen:
                seen.add(normalized)
                result.append(v)

        return result

    def expand_with_sources(
        self, query: str, source_types: list[str] | None = None
    ) -> list[str]:
        """Generate variations targeting specific source types.

        Args:
            query: Original user query
            source_types: List of source types to target.
                         Options: "quran", "hadith", "fiqh", "general"

        Returns:
            List of query variations filtered by source type relevance
        """
        if not source_types:
            return self.expand(query)

        all_variations = self.expand(query, num_variations=len(self._TEMPLATES))
        filtered: list[str] = []

        source_set = {s.lower() for s in source_types}

        for variation in all_variations:
            lower_var = variation.lower()

            if "quran" in lower_var and "quran" in source_set:
                filtered.append(variation)
            elif "hadith" in lower_var and "hadith" in source_set:
                filtered.append(variation)
            elif "islamic perspective" in lower_var and "fiqh" in source_set:
                filtered.append(variation)
            elif variation.lower() == query.lower().strip() and "general" in source_set:
                filtered.append(variation)

        return filtered if filtered else [query.strip()]


def create_default_expander(
    enabled: bool = True, num_variations: int = 5
) -> QueryExpander:
    """Factory function to create a default query expander.

    Args:
        enabled: Whether expansion is enabled
        num_variations: Number of variations to generate

    Returns:
        Configured QueryExpander instance
    """
    config = QueryExpanderConfig(
        enabled=enabled,
        num_variations=num_variations,
        include_original=True,
        deduplicate=True,
    )
    return QueryExpander(config=config)
