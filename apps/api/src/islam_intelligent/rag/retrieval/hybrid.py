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
    """
    Map a list of score-bearing entries to normalized scores in the range 0.0–1.0 keyed by `text_unit_id`.
    
    Parameters:
        entries (list[_NormalizedEntry]): List of entries each containing `text_unit_id` and `score`.
    
    Returns:
        dict[str, float]: Mapping from `text_unit_id` to normalized score (float between 0.0 and 1.0). Returns an empty dict for an empty input. If all input scores are identical, each score is clamped to the [0.0, 1.0] range; otherwise scores are linearly scaled so the minimum maps to 0.0 and the maximum maps to 1.0.
    """
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
    """
    Normalize a pair of weights so they form proportional fractions that sum to 1.0.
    
    Both inputs are converted to non-negative floats (negative values become 0.0). If the resulting total is less than or equal to 0.0, the function returns an even split of (0.5, 0.5). Otherwise it returns each weight divided by the total so the two values sum to 1.0.
    
    Parameters:
        lexical_weight (float): Weight for lexical signals; negative values are treated as 0.0.
        vector_weight (float): Weight for vector signals; negative values are treated as 0.0.
    
    Returns:
        tuple[float, float]: Normalized (lexical_fraction, vector_fraction) that sum to 1.0.
    """
    lw = max(0.0, float(lexical_weight))
    vw = max(0.0, float(vector_weight))
    total = lw + vw
    if total <= 0.0:
        return (0.5, 0.5)
    return (lw / total, vw / total)


def search_hybrid(
    query: str, limit: int = 10, lexical_weight: float = 0.7, vector_weight: float = 0.3
) -> list[SearchResult]:
    """
    Perform a hybrid search that combines lexical and vector retrieval results into a single ranked list.
    
    Parameters:
    	query (str): The search query; empty or whitespace-only queries return an empty list.
    	limit (int): Maximum number of results to return; values <= 0 return an empty list.
    	lexical_weight (float): Relative weight for lexical relevance; normalized with `vector_weight` so the two sum to 1.
    	vector_weight (float): Relative weight for vector relevance; normalized with `lexical_weight` so the two sum to 1.
    
    Returns:
    	list[SearchResult]: Combined search results ordered by combined weighted score (highest first), limited to `limit`. If only vector matches are available their snippet is set to "[vector match]". Scores are normalized and combined before sorting.
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
    """
    Perform hybrid searches over multiple expanded variations of a query and merge the results.
    
    Generates up to `num_variations` query variations using `expander` (a default expander is created if `None`), runs a hybrid search for each variation, and merges results by `text_unit_id` keeping the highest score for duplicate entries. The merged results are sorted by score in descending order and truncated to `limit`.
    
    Parameters:
        query (str): The original search query.
        limit (int): Maximum number of results to return.
        lexical_weight (float): Relative weight for lexical scoring; normalized with `vector_weight`.
        vector_weight (float): Relative weight for vector scoring; normalized with `lexical_weight`.
        expander (QueryExpander | None): Optional query expander; if `None`, a default expander is used.
        num_variations (int): Number of query variations to generate from the expander.
    
    Returns:
        list[SearchResult]: Deduplicated list of search results sorted by score (highest first), limited to `limit`. Returns an empty list if `query` is empty or `limit` is not greater than zero.
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
