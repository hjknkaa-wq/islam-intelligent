"""Lexical search for text units.

Simple LIKE-based search for SQLite compatibility.
For production, upgrade to FTS5 or Postgres tsvector.
"""

from typing import TypedDict

from sqlalchemy import func, select

# Import provenance models to ensure all relationships are registered
from ...provenance.models import ProvEntity  # noqa: F401
from ...kg.models import EvidenceSpan, KgEdge, KgEdgeEvidence, KgEntity  # noqa: F401
from ...db.engine import SessionLocal, engine
from ...domain.models import Base, SourceDocument, TextUnit
from ...normalize.normalizer import normalize_search


class SearchResult(TypedDict):
    text_unit_id: str
    score: float
    snippet: str
    canonical_id: str
    source_id: str
    trust_status: str


_tables_initialized = False


def _ensure_tables() -> None:
    global _tables_initialized
    if _tables_initialized:
        return
    Base.metadata.create_all(engine)
    _tables_initialized = True


def search_lexical(query: str, limit: int = 10) -> list[SearchResult]:
    """Search text units using lexical matching.

    Args:
        query: Search query (will be NFKC normalized)
        limit: Maximum results to return

    Returns:
        List of search results with scores
    """
    if not query or not query.strip():
        return []

    _ensure_tables()

    # Normalize query for search
    normalized_query = normalize_search(query)

    db = SessionLocal()
    try:
        # Simple LIKE search - exact match gets higher score
        latest = (
            select(
                SourceDocument.source_id,
                func.max(SourceDocument.version).label("max_version"),
            )
            .group_by(SourceDocument.source_id)
            .subquery()
        )

        stmt = (
            select(TextUnit, SourceDocument.trust_status)
            .join(SourceDocument, SourceDocument.source_id == TextUnit.source_id)
            .join(
                latest,
                (SourceDocument.source_id == latest.c.source_id)
                & (SourceDocument.version == latest.c.max_version),
            )
            .where(TextUnit.text_canonical.contains(normalized_query))
            .limit(limit * 2)
        )

        rows = db.execute(stmt).all()

        # Score and rank results
        scored_results = []
        for unit, trust_status in rows:
            text = unit.text_canonical

            # Calculate score
            if normalized_query == text:
                score = 1.0  # Exact match
            elif normalized_query in text:
                score = 0.7 + (0.3 * len(normalized_query) / len(text))  # Partial match
            else:
                score = 0.5  # Contains match (from SQL)

            # Create snippet (first 100 chars around match)
            idx = text.find(normalized_query)
            if idx >= 0:
                start = max(0, idx - 40)
                end = min(len(text), idx + len(normalized_query) + 40)
                snippet = text[start:end]
                if start > 0:
                    snippet = "..." + snippet
                if end < len(text):
                    snippet = snippet + "..."
            else:
                snippet = text[:100] + ("..." if len(text) > 100 else "")

            scored_results.append(
                SearchResult(
                    text_unit_id=unit.text_unit_id,
                    score=round(score, 3),
                    snippet=snippet,
                    canonical_id=unit.canonical_id,
                    source_id=unit.source_id,
                    trust_status=str(trust_status or "untrusted"),
                )
            )

        # Sort by score descending and limit
        scored_results.sort(key=lambda x: x["score"], reverse=True)
        return scored_results[:limit]

    finally:
        db.close()
