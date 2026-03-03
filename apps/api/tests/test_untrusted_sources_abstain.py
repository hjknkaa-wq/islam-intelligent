"""RAG must abstain when only untrusted evidence exists.

This test operates against the seeded SQLite dev database at `.local/dev.db`.
"""

from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUntypedBaseClass=false, reportUnknownArgumentType=false

import sqlite3
from pathlib import Path
from typing import cast

import pytest

from islam_intelligent.rag.pipeline import RAGConfig, RAGPipeline


ROOT = Path(__file__).resolve().parents[3]
DEV_DB_PATH = ROOT / ".local" / "dev.db"


def _devdb_retrieve(query: str, *, limit: int) -> list[dict[str, object]]:
    like = f"%{query}%"
    with sqlite3.connect(str(DEV_DB_PATH)) as conn:
        cur = conn.cursor()
        _ = cur.execute(
            """
            SELECT
                tu.text_unit_id,
                tu.canonical_id,
                tu.text_canonical,
                sd.source_id,
                sd.trust_status
            FROM text_unit tu
            JOIN source_document sd ON sd.source_id = tu.source_id
            WHERE tu.text_canonical LIKE ? OR tu.canonical_id LIKE ?
            LIMIT ?
            """,
            (like, like, int(limit)),
        )
        rows = cast(
            list[tuple[object, object, object, object, object]],
            cur.fetchall(),
        )

    out: list[dict[str, object]] = []
    for text_unit_id, canonical_id, text_canonical, source_id, trust_status in rows:
        text = str(text_canonical or "")
        out.append(
            {
                "text_unit_id": str(text_unit_id),
                "score": 0.9,
                "snippet": text[:120],
                "canonical_id": str(canonical_id),
                "source_id": str(source_id),
                "trust_status": str(trust_status or "untrusted"),
            }
        )
    return out


def _get_first_hadith_source_id(conn: sqlite3.Connection) -> str:
    row = cast(
        tuple[object, ...] | None,
        conn.execute(
            "SELECT source_id FROM source_document WHERE source_type = 'hadith_collection' LIMIT 1"
        ).fetchone(),
    )
    if row is not None and row[0]:
        return str(row[0])

    row = cast(
        tuple[object, ...] | None,
        conn.execute(
            """
            SELECT DISTINCT tu.source_id
            FROM text_unit tu
            WHERE tu.canonical_id LIKE 'hadith:%'
            LIMIT 1
            """
        ).fetchone(),
    )
    if row is None or not row[0]:
        raise RuntimeError("No hadith source found in dev.db")
    return str(row[0])


def _get_trust_status(conn: sqlite3.Connection, source_id: str) -> str:
    row = cast(
        tuple[object, ...] | None,
        conn.execute(
            "SELECT trust_status FROM source_document WHERE source_id = ?",
            (source_id,),
        ).fetchone(),
    )
    if row is None or not row[0]:
        raise RuntimeError(f"source_document not found: source_id={source_id}")
    return str(row[0])


def _set_trust_status(
    conn: sqlite3.Connection, source_id: str, trust_status: str
) -> None:
    cur = conn.execute(
        "UPDATE source_document SET trust_status = ? WHERE source_id = ?",
        (trust_status, source_id),
    )
    conn.commit()
    if int(cur.rowcount or 0) != 1:
        raise RuntimeError(
            f"Expected to update 1 row, updated {cur.rowcount!r} (source_id={source_id})"
        )


def _is_seeded_for_untrusted_sources_test(conn: sqlite3.Connection) -> bool:
    """Return True if dev.db looks like it was seeded with evidence spans.

    This test is intended to run against a seeded developer DB. Other unit tests may
    create an empty dev.db file (schema-only), which would make this integration test
    fail with false negatives.
    """

    try:
        row = cast(
            tuple[object] | None,
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='text_unit'"
            ).fetchone(),
        )
        if row is None:
            return False
        row = cast(
            tuple[object] | None,
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='evidence_span'"
            ).fetchone(),
        )
        if row is None:
            return False

        # Evidence spans must exist and be resolvable by evidence_span_id==text_unit_id
        span_count = cast(
            tuple[object] | None,
            conn.execute("SELECT COUNT(1) FROM evidence_span").fetchone(),
        )
        if span_count is None or int(str(span_count[0] or 0)) == 0:
            return False
        resolvable = cast(
            tuple[object] | None,
            conn.execute(
                """
                SELECT COUNT(1)
                FROM evidence_span es
                JOIN text_unit tu ON tu.text_unit_id = es.text_unit_id
                WHERE es.evidence_span_id = tu.text_unit_id
                """
            ).fetchone(),
        )
        if resolvable is None or int(str(resolvable[0] or 0)) == 0:
            return False

        # Must contain at least one Bukhari-like hadith canonical_id for the query.
        hadith = cast(
            tuple[object] | None,
            conn.execute(
                "SELECT COUNT(1) FROM text_unit WHERE canonical_id LIKE 'hadith:%' AND canonical_id LIKE '%bukhari%'"
            ).fetchone(),
        )
        if hadith is None or int(str(hadith[0] or 0)) == 0:
            return False

        return True
    except Exception:
        return False


def test_untrusted_sources_abstain_dev_db() -> None:
    if not DEV_DB_PATH.exists():
        pytest.skip("Missing .local/dev.db; run scripts/dev_reset_and_seed.py")

    query = "bukhari"  # ASCII-only query; matches hadith canonical_id values.

    class DevDBPipeline(RAGPipeline):
        def retrieve(self, q: str):  # type: ignore[override]
            return _devdb_retrieve(q, limit=10)

    pipeline = DevDBPipeline(RAGConfig(sufficiency_threshold=0.1))

    with sqlite3.connect(str(DEV_DB_PATH)) as conn:
        if not _is_seeded_for_untrusted_sources_test(conn):
            pytest.skip(
                "dev.db present but not seeded with resolvable evidence spans; run scripts/dev_reset_and_seed.py"
            )
        source_id = _get_first_hadith_source_id(conn)
        original = _get_trust_status(conn, source_id)

        try:
            # Scenario 1: trusted -> should answer
            _set_trust_status(conn, source_id, "trusted")
            trusted_result = pipeline.query(query)
            assert trusted_result["verdict"] == "answer"
            assert trusted_result["fail_reason"] is None

            # Scenario 2: untrusted -> must abstain with untrusted_sources
            _set_trust_status(conn, source_id, "untrusted")
            untrusted_result = pipeline.query(query)
            assert untrusted_result["verdict"] == "abstain"
            assert untrusted_result["abstain_reason"] == "untrusted_sources"
            assert "untrusted" in str(untrusted_result["fail_reason"])
            assert untrusted_result["fail_reason"] == "untrusted_sources"
        finally:
            _set_trust_status(conn, source_id, original)
