#!/usr/bin/env python3
"""Generate embeddings for all text_units in the database.

This script populates the embedding column for text units that don't have one yet.
It uses the OpenAI embedding API with local caching and batching for efficiency.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import cast

# Add the API src to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api" / "src"))

from islam_intelligent.config import settings
from islam_intelligent.rag.retrieval.embeddings import EmbeddingGenerator


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate embeddings for text_units in the database"
    )
    parser.add_argument(
        "--db-path",
        default=str(Path(__file__).resolve().parents[1] / ".local" / "dev.db"),
        help="Path to SQLite database",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of embeddings to generate per API call",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of text_units to process (0 = all)",
    )
    parser.add_argument(
        "--checkpoint",
        type=int,
        default=100,
        help="Commit to DB every N text_units",
    )
    return parser.parse_args()


def _get_text_units_without_embeddings(
    conn: sqlite3.Connection, limit: int = 0
) -> list[tuple[str, str]]:
    """Get text_unit_id and text_canonical for units without embeddings."""
    cursor = conn.execute(
        """
        SELECT text_unit_id, text_canonical 
        FROM text_unit 
        WHERE embedding IS NULL
        ORDER BY created_at
        """
    )
    rows = cursor.fetchall()
    if limit > 0:
        rows = rows[:limit]
    return cast(list[tuple[str, str]], rows)


def _count_text_units(conn: sqlite3.Connection) -> tuple[int, int]:
    """Return (total, without_embeddings) counts."""
    total = conn.execute("SELECT COUNT(*) FROM text_unit").fetchone()[0]
    without = conn.execute(
        "SELECT COUNT(*) FROM text_unit WHERE embedding IS NULL"
    ).fetchone()[0]
    return cast(int, total), cast(int, without)


def _store_embedding(
    conn: sqlite3.Connection,
    text_unit_id: str,
    embedding: list[float],
    model: str,
) -> None:
    """Store embedding bytes in the database."""
    import struct
    import datetime

    # Convert list of floats to bytes (4 bytes per float)
    embedding_bytes = struct.pack(f"<{len(embedding)}f", *embedding)

    conn.execute(
        """
        UPDATE text_unit 
        SET embedding = ?,
            embedding_model = ?,
            embedding_generated_at = ?
        WHERE text_unit_id = ?
        """,
        (
            embedding_bytes,
            model,
            datetime.datetime.now().isoformat(),
            text_unit_id,
        ),
    )


def main() -> int:
    args = _parse_args()

    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("[ERROR] OPENAI_API_KEY environment variable required", file=sys.stderr)
        print("Set it with: export OPENAI_API_KEY=sk-...", file=sys.stderr)
        return 1

    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"[ERROR] Database not found: {db_path}", file=sys.stderr)
        return 1

    # Initialize embedding generator
    generator = EmbeddingGenerator()
    if not generator.is_available():
        print("[ERROR] Embedding generator not available", file=sys.stderr)
        print(
            "Check that OPENAI_API_KEY is set and openai package is installed",
            file=sys.stderr,
        )
        return 1

    conn = sqlite3.connect(db_path)

    try:
        # Get counts
        total, without_embeddings = _count_text_units(conn)
        print("=" * 60)
        print("ISLAM INTELLIGENT - EMBEDDING GENERATION")
        print("=" * 60)
        print(f"Database: {db_path}")
        print(f"Total text_units: {total}")
        print(f"Without embeddings: {without_embeddings}")
        print(f"Batch size: {args.batch_size}")
        print(f"Model: {settings.embedding_model}")
        print(f"Dimension: {settings.embedding_dimension}")
        print("=" * 60)

        if without_embeddings == 0:
            print("[OK] All text_units already have embeddings")
            return 0

        # Get text units to process
        to_process = _get_text_units_without_embeddings(conn, args.limit)
        print(f"Processing {len(to_process)} text_units...")
        print()

        processed = 0
        generated = 0
        failed = 0
        start_time = time.time()

        # Process in batches
        for i in range(0, len(to_process), args.batch_size):
            batch = to_process[i : i + args.batch_size]
            batch_ids = [row[0] for row in batch]
            batch_texts = [row[1] for row in batch]

            # Generate embeddings for batch
            try:
                embeddings = generator.generate_embeddings(batch_texts)

                # Store in database
                for text_unit_id, embedding in zip(batch_ids, embeddings):
                    if embedding and any(embedding):  # Check not empty/zero
                        _store_embedding(
                            conn, text_unit_id, embedding, settings.embedding_model
                        )
                        generated += 1
                    else:
                        failed += 1

                processed += len(batch)

                # Commit periodically
                if processed % args.checkpoint == 0:
                    conn.commit()
                    elapsed = time.time() - start_time
                    rate = processed / elapsed if elapsed > 0 else 0
                    print(
                        f"  Progress: {processed}/{len(to_process)} "
                        f"({100 * processed / len(to_process):.1f}%) | "
                        f"Rate: {rate:.1f} items/sec | "
                        f"Generated: {generated}, Failed: {failed}"
                    )

            except Exception as e:
                print(f"[WARNING] Batch failed: {e}", file=sys.stderr)
                failed += len(batch)
                processed += len(batch)

        # Final commit
        conn.commit()

        elapsed = time.time() - start_time
        print()
        print("=" * 60)
        print("[OK] Embedding generation complete")
        print(f"Processed: {processed}")
        print(f"Generated: {generated}")
        print(f"Failed: {failed}")
        print(f"Time: {elapsed:.1f}s")
        print(f"Rate: {processed / elapsed:.1f} items/sec" if elapsed > 0 else "N/A")
        print("=" * 60)

    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Saving progress...", file=sys.stderr)
        conn.commit()
        return 130
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
