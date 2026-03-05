"""Hybrid search combining lexical and vector results."""

from typing import NotRequired, Required, TypedDict, cast

from .lexical import search_lexical
from .query_expander import QueryExpander
from .vector import is_vector_available, search_vector


class SearchResult(TypedDict):
    text_unit_id: Required[str]
    score: Required[float]
    snippet: Required[str]
    canonical_id: NotRequired[str]
    source_id: NotRequired[str]
    trust_status: NotRequired[str]


class _NormalizedEntry(TypedDict):
    text_unit_id: str
    score: float


class _CombinedEntry(TypedDict):
    text_unit_id: str
    snippet: str
    lexical_score: float
    lexical_norm: float
    vector_score: float
    vector_norm: float
    canonical_id: str
    source_id: str
    trust_status: str


def _normalize_scores(entries: list[_NormalizedEntry]) -> dict[str, float]:
    """Normalize result scores into [0.0, 1.0] by text_unit_id."""
    if not entries:
        return {}

    values = [item["score"] for item in entries]
    min_score = min(values)
    max_score = max(values)

    if max_score == min_score:
        return {
            item["text_unit_id"]: max(0.0, min(1.0, item["score"])) for item in entries
        }

    spread = max_score - min_score
    return {
        item["text_unit_id"]: (item["score"] - min_score) / spread for item in entries
    }


def _resolve_weights(
    lexical_weight: float, vector_weight: float
) -> tuple[float, float]:
    """Normalize weight pair so final weights always sum to 1."""
    lw = max(0.0, float(lexical_weight))
    vw = max(0.0, float(vector_weight))
    total = lw + vw
    if total <= 0.0:
        return (0.5, 0.5)
    return (lw / total, vw / total)


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

    if limit <= 0:
        return []

    lexical_weight, vector_weight = _resolve_weights(lexical_weight, vector_weight)

    # Get lexical results
    lexical_results: list[SearchResult] = cast(
        list[SearchResult], search_lexical(query, limit=limit * 2)
    )

    # Get vector results if available
    if is_vector_available():
        vector_results = search_vector(query, limit=limit * 2)
    else:
        vector_results = []

    # Graceful single-source fallbacks
    if not lexical_results and not vector_results:
        return []

    if not vector_results:
        return lexical_results[:limit]

    if not lexical_results:
        vector_only: list[SearchResult] = []
        for result in vector_results[:limit]:
            vector_only.append(
                {
                    "text_unit_id": result["text_unit_id"],
                    "score": round(result["score"] * vector_weight, 3),
                    "snippet": "[vector match]",
                }
            )
        return vector_only

    # Combine results from both retrieval methods
    combined: dict[str, _CombinedEntry] = {}

    lexical_entries: list[_NormalizedEntry] = [
        {"text_unit_id": item["text_unit_id"], "score": item["score"]}
        for item in lexical_results
    ]
    vector_entries: list[_NormalizedEntry] = [
        {"text_unit_id": item["text_unit_id"], "score": item["score"]}
        for item in vector_results
    ]
    lexical_norm = _normalize_scores(lexical_entries)
    vector_norm = _normalize_scores(vector_entries)

    # Add lexical scores
    for result in lexical_results:
        tid = result["text_unit_id"]
        entry: _CombinedEntry = {
            "text_unit_id": tid,
            "snippet": result["snippet"],
            "lexical_score": result["score"],
            "lexical_norm": lexical_norm.get(tid, 0.0),
            "vector_score": 0.0,
            "vector_norm": 0.0,
            "canonical_id": result.get("canonical_id") or "",
            "source_id": result.get("source_id") or "",
            "trust_status": result.get("trust_status") or "",
        }
        combined[tid] = entry

    # Add vector scores
    for result in vector_results:
        tid = result["text_unit_id"]
        if tid in combined:
            combined[tid]["vector_score"] = result["score"]
            combined[tid]["vector_norm"] = vector_norm.get(tid, 0.0)
        else:
            vector_entry: _CombinedEntry = {
                "text_unit_id": tid,
                "snippet": "",  # Vector doesn't provide snippet
                "lexical_score": 0.0,
                "lexical_norm": 0.0,
                "vector_score": result["score"],
                "vector_norm": vector_norm.get(tid, 0.0),
                "canonical_id": "",
                "source_id": "",
                "trust_status": "",
            }
            combined[tid] = vector_entry

    # Calculate weighted normalized scores
    final_results: list[SearchResult] = []
    for item in combined.values():
        weighted_score = (
            item["lexical_norm"] * lexical_weight + item["vector_norm"] * vector_weight
        )
        out: SearchResult = {
            "text_unit_id": item["text_unit_id"],
            "score": round(weighted_score, 3),
            "snippet": item["snippet"] or "[vector match]",
        }
        canonical_id = item["canonical_id"]
        source_id = item["source_id"]
        trust_status = item["trust_status"]
        if canonical_id:
            out["canonical_id"] = canonical_id
        if source_id:
            out["source_id"] = source_id
        if trust_status:
            out["trust_status"] = trust_status
        final_results.append(out)

    # Sort by score and limit
    final_results.sort(key=lambda result: result["score"], reverse=True)
    return final_results[:limit]


def search_hybrid_multi_query(
    query: str,
    limit: int = 10,
    lexical_weight: float = 0.7,
    vector_weight: float = 0.3,
    expander: QueryExpander | None = None,
    num_variations: int = 5,
) -> list[SearchResult]:
    """Multi-query hybrid search with query expansion.

    Generates multiple query variations and performs hybrid search for each,
    then deduplicates and merges results.

    Args:
        query: Original search query
        limit: Maximum results to return
        lexical_weight: Weight for lexical scores (0.0-1.0)
        vector_weight: Weight for vector scores (0.0-1.0)
        expander: QueryExpander instance (creates default if None)
        num_variations: Number of query variations to generate

    Returns:
        Deduplicated and ranked search results from all query variations
    """
    if not query or not query.strip():
        return []

    if limit <= 0:
        return []

    # Initialize expander if not provided
    if expander is None:
        from .query_expander import create_default_expander

        expander = create_default_expander()

    # Generate query variations
    variations = expander.expand(query, num_variations=num_variations)

    if not variations:
        # Fallback to single query search
        return search_hybrid(
            query,
            limit=limit,
            lexical_weight=lexical_weight,
            vector_weight=vector_weight,
        )

    # If expansion is disabled, just do single search
    if len(variations) == 1 and variations[0] == query.strip():
        return search_hybrid(
            query,
            limit=limit,
            lexical_weight=lexical_weight,
            vector_weight=vector_weight,
        )

    # Search for each variation and collect results
    all_results: dict[str, SearchResult] = {}

    for variation in variations:
        variation_results = search_hybrid(
            variation,
            limit=limit * 2,
            lexical_weight=lexical_weight,
            vector_weight=vector_weight,
        )

        # Merge results, keeping highest score for duplicates
        for result in variation_results:
            tid = result["text_unit_id"]
            if tid in all_results:
                # Keep the higher score
                if result["score"] > all_results[tid]["score"]:
                    all_results[tid] = result
            else:
                all_results[tid] = result

    # Convert to list and sort by score
    final_results = list(all_results.values())
    final_results.sort(key=lambda r: r["score"], reverse=True)

    return final_results[:limit]
