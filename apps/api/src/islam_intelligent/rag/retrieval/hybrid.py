"""Hybrid search combining lexical and vector results."""

from typing import Any, NotRequired, Required, TypedDict, cast

from .lexical import search_lexical
from .vector import is_vector_available, search_vector


class SearchResult(TypedDict):
    text_unit_id: Required[str]
    score: Required[float]
    snippet: Required[str]
    canonical_id: NotRequired[str]
    source_id: NotRequired[str]
    trust_status: NotRequired[str]


def search_hybrid(
    query: str, limit: int = 10, lexical_weight: float = 0.7, vector_weight: float = 0.3
) -> list[SearchResult]:
    """Search using both lexical and vector methods.

    Args:
        query: Search query
        limit: Maximum results to return
        lexical_weight: Weight for lexical scores (0.0-1.0)
        vector_weight: Weight for vector scores (0.0-1.0)

    Returns:
        Combined and ranked search results
    """
    if not query or not query.strip():
        return []

    # Get lexical results
    lexical_results: list[SearchResult] = cast(
        list[SearchResult], search_lexical(query, limit=limit * 2)
    )

    # Get vector results if available
    if is_vector_available():
        vector_results = search_vector(query, limit=limit * 2)
    else:
        vector_results = []

    # If no vector results, return lexical only
    if not vector_results:
        return lexical_results[:limit]

    # Combine results (weighted average)
    combined: dict[str, dict[str, Any]] = {}

    # Add lexical scores
    for result in lexical_results:
        tid = result["text_unit_id"]
        combined[tid] = {
            "text_unit_id": tid,
            "snippet": result["snippet"],
            "lexical_score": result["score"],
            "vector_score": 0.0,
            "canonical_id": result.get("canonical_id"),
            "source_id": result.get("source_id"),
            "trust_status": result.get("trust_status"),
        }

    # Add vector scores
    for result in vector_results:
        tid = result["text_unit_id"]
        if tid in combined:
            combined[tid]["vector_score"] = result["score"]
        else:
            combined[tid] = {
                "text_unit_id": tid,
                "snippet": "",  # Vector doesn't provide snippet
                "lexical_score": 0.0,
                "vector_score": result["score"],
            }

    # Calculate weighted scores
    final_results = []
    for item in combined.values():
        score = (
            item["lexical_score"] * lexical_weight
            + item["vector_score"] * vector_weight
        )
        out: SearchResult = {
            "text_unit_id": item["text_unit_id"],
            "score": round(score, 3),
            "snippet": item["snippet"] or "[vector match]",
        }
        if isinstance(item.get("canonical_id"), str):
            out["canonical_id"] = item["canonical_id"]
        if isinstance(item.get("source_id"), str):
            out["source_id"] = item["source_id"]
        if isinstance(item.get("trust_status"), str):
            out["trust_status"] = item["trust_status"]
        final_results.append(out)

    # Sort by score and limit
    final_results.sort(key=lambda x: x["score"], reverse=True)
    return final_results[:limit]
