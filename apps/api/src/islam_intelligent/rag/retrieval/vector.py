"""Vector search placeholder.

Returns empty list if embeddings not configured.
"""

from typing import TypedDict


class SearchResult(TypedDict):
    text_unit_id: str
    score: float


def search_vector(query: str, limit: int = 10) -> list[SearchResult]:
    """Search using vector embeddings.

    Currently returns empty list as embeddings are not configured.
    Future: implement actual vector search using pgvector or similar.

    Args:
        query: Search query
        limit: Maximum results to return

    Returns:
        Empty list (placeholder)
    """
    # Placeholder - vector search disabled
    return []


def is_vector_available() -> bool:
    """Check if vector search is available."""
    return False
