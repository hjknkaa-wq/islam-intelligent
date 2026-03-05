"""Vector search implementation with HNSW ANN index."""

from __future__ import annotations

import struct
from collections.abc import Sequence
from typing import TypedDict, cast

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from ...db.engine import SessionLocal
from .embeddings import EmbeddingGenerator


class SearchResult(TypedDict):
    text_unit_id: str
    score: float


_EMBEDDING_GENERATOR = EmbeddingGenerator()


def _parse_embedding(raw_embedding: object) -> list[float]:
    """Parse embedding from various formats."""
    if raw_embedding is None:
        return []

    if isinstance(raw_embedding, memoryview):
        raw_embedding = raw_embedding.tobytes()

    if isinstance(raw_embedding, (bytes, bytearray)):
        size = len(raw_embedding) // 4
        if size <= 0:
            return []
        fmt = f"<{size}f"
        try:
            unpacked = struct.unpack(fmt, raw_embedding[: size * 4])
            return list(unpacked)
        except struct.error:
            return []

    return []


def search_vector(query: str, limit: int = 10) -> list[SearchResult]:
    """Search text units by vector similarity using HNSW ANN index.

    Uses pgvector's <=> operator for efficient approximate nearest neighbor
    search instead of loading all embeddings into Python.

    Returns an empty list when embeddings are not configured, unavailable,
    or when database access fails.
    """
    if not query or not query.strip() or limit <= 0:
        return []

    if not is_vector_available():
        return []

    query_embedding = _EMBEDDING_GENERATOR.generate_embedding(query)
    if not query_embedding:
        return []

    db = SessionLocal()
    try:
        # Use HNSW ANN index with <=> operator for efficient search
        # This is O(log N) instead of O(N) compared to loading all embeddings
        stmt = text(
            """
            SELECT text_unit_id, 1 - (embedding <=> :query_embedding) as score
            FROM text_unit
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> :query_embedding
            LIMIT :limit
            """
        )

        # Convert embedding to pgvector format: '[f1,f2,f3,...]'
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        try:
            rows = db.execute(
                stmt, {"query_embedding": embedding_str, "limit": limit}
            ).all()
        except OperationalError:
            # Fallback: HNSW index might not exist, try without ORDER BY
            stmt_fallback = text(
                """
                SELECT text_unit_id, embedding
                FROM text_unit
                WHERE embedding IS NOT NULL
                LIMIT :candidate_limit
                """
            )
            rows = db.execute(stmt_fallback, {"candidate_limit": limit * 50}).all()

            # Manual scoring as fallback
            results: list[SearchResult] = []
            for row in rows:
                text_unit_id = cast(object, row[0])
                embedding_raw = cast(object, row[1])
                embedding = _parse_embedding(embedding_raw)
                if text_unit_id is None or not embedding:
                    continue

                # Simple dot product similarity
                score = sum(a * b for a, b in zip(query_embedding, embedding))
                results.append(
                    SearchResult(
                        text_unit_id=str(text_unit_id),
                        score=round(score, 6),
                    )
                )

            results.sort(key=lambda item: item["score"], reverse=True)
            return results[:limit]

        # Return results directly (already sorted by ANN index)
        return [
            SearchResult(
                text_unit_id=str(row[0]),
                score=round(float(row[1]), 6),
            )
            for row in rows
        ]

    except SQLAlchemyError:
        return []
    finally:
        db.close()


def is_vector_available() -> bool:
    """Check if vector search can generate embeddings."""
    return _EMBEDDING_GENERATOR.is_available()
