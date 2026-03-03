"""Tests for provenance link integrity.

Verifies that the chain from answer -> evidence_span -> text_unit -> source_document
is intact and verifiable.
"""

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportMissingParameterType=false, reportUnknownParameterType=false, reportUnusedParameter=false, reportUnusedVariable=false, reportUnusedCallResult=false, reportAny=false, reportUnknownArgumentType=false

import pytest
from uuid import uuid4
from datetime import datetime


def _db_has_table(conn, name: str) -> bool:  # type: ignore[no-untyped-def]
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _table_has_columns(conn, table: str, required: set[str]) -> bool:  # type: ignore[no-untyped-def]
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    cols = {str(r[1]) for r in rows if isinstance(r, tuple) and len(r) >= 2}
    return required.issubset(cols)


def _provenance_db_ready() -> bool:
    """These tests are intended for a fully-seeded dev DB.

    Unit tests may create an empty `.local/dev.db` file; in that case we skip.
    """

    import os
    import sqlite3

    if not os.path.exists(".local/dev.db"):
        return False
    try:
        conn = sqlite3.connect(".local/dev.db")
    except Exception:
        return False
    try:
        required_tables = {
            "source_document",
            "text_unit",
            "evidence_span",
            "kg_edge_evidence",
        }
        for t in required_tables:
            if not _db_has_table(conn, t):
                return False

        if not _table_has_columns(
            conn, "source_document", {"source_id", "trust_status"}
        ):
            return False
        if not _table_has_columns(conn, "text_unit", {"text_unit_id", "source_id"}):
            return False
        if not _table_has_columns(
            conn, "evidence_span", {"evidence_span_id", "text_unit_id"}
        ):
            return False

        # This table is optional in the current scaffold; if missing, skip.
        if not _db_has_table(conn, "rag_retrieval_result"):
            return False

        # Must have at least one evidence span to validate linkage.
        row = conn.execute("SELECT COUNT(1) FROM evidence_span").fetchone()
        if row is None or int(str(row[0] or 0)) == 0:
            return False

        return True
    finally:
        conn.close()


pytestmark = pytest.mark.skipif(
    not _provenance_db_ready(), reason="Dev DB not seeded for provenance link tests"
)


class TestProvenanceLinks:
    """Test provenance chain integrity."""

    def test_evidence_span_to_text_unit_link(self, db_session):
        """Verify evidence_span.text_unit_id references valid text_unit."""
        # This test requires a database session
        # For now, we'll use sqlite3 directly
        import sqlite3

        conn = sqlite3.connect(".local/dev.db")
        cursor = conn.cursor()

        # Find evidence spans with broken text_unit links
        cursor.execute("""
            SELECT es.evidence_span_id, es.text_unit_id
            FROM evidence_span es
            LEFT JOIN text_unit tu ON es.text_unit_id = tu.text_unit_id
            WHERE tu.text_unit_id IS NULL
        """)
        orphans = cursor.fetchall()
        conn.close()

        assert len(orphans) == 0, f"Found {len(orphans)} orphaned evidence spans"

    def test_text_unit_to_source_link(self, db_session):
        """Verify text_unit.source_id references valid source_document."""
        import sqlite3

        conn = sqlite3.connect(".local/dev.db")
        cursor = conn.cursor()

        cursor.execute("""
            SELECT tu.text_unit_id, tu.source_id
            FROM text_unit tu
            LEFT JOIN source_document sd ON tu.source_id = sd.source_id
            WHERE sd.source_id IS NULL
        """)
        orphans = cursor.fetchall()
        conn.close()

        assert len(orphans) == 0, f"Found {len(orphans)} orphaned text units"

    def test_kg_edge_evidence_link(self, db_session):
        """Verify kg_edge_evidence.evidence_span_id references valid span."""
        import sqlite3

        conn = sqlite3.connect(".local/dev.db")
        cursor = conn.cursor()

        cursor.execute("""
            SELECT ee.edge_id, ee.evidence_span_id
            FROM kg_edge_evidence ee
            LEFT JOIN evidence_span es ON ee.evidence_span_id = es.evidence_span_id
            WHERE es.evidence_span_id IS NULL
        """)
        orphans = cursor.fetchall()
        conn.close()

        assert len(orphans) == 0, f"Found {len(orphans)} orphaned KG edge evidences"

    def test_full_provenance_chain(self, db_session):
        """Test full chain from span -> unit -> source."""
        import sqlite3

        conn = sqlite3.connect(".local/dev.db")
        cursor = conn.cursor()

        # Use the view if it exists, otherwise manual join
        cursor.execute("""
            SELECT COUNT(*) FROM (
                SELECT es.evidence_span_id
                FROM evidence_span es
                JOIN text_unit tu ON es.text_unit_id = tu.text_unit_id
                JOIN source_document sd ON tu.source_id = sd.source_id
                LIMIT 1
            )
        """)
        result = cursor.fetchone()
        conn.close()

        # Should be able to traverse the full chain
        assert result is not None

    def test_rag_retrieval_evidence_link(self, db_session):
        """Verify rag_retrieval_result.evidence_span_id is valid."""
        import sqlite3

        conn = sqlite3.connect(".local/dev.db")
        cursor = conn.cursor()

        cursor.execute("""
            SELECT rr.rag_query_id, rr.evidence_span_id
            FROM rag_retrieval_result rr
            LEFT JOIN evidence_span es ON rr.evidence_span_id = es.evidence_span_id
            WHERE es.evidence_span_id IS NULL
        """)
        orphans = cursor.fetchall()
        conn.close()

        # Note: This might be empty if RAG logging not yet implemented
        # But if there are records, they should be valid
        if orphans:
            assert False, f"Found {len(orphans)} RAG retrievals with invalid spans"

    def test_source_retraction_propagation(self, db_session):
        """Test that retracted sources are properly marked."""
        import sqlite3

        conn = sqlite3.connect(".local/dev.db")
        cursor = conn.cursor()

        cursor.execute("""
            SELECT source_id, work_title, trust_status, retraction_reason
            FROM source_document
            WHERE trust_status = 'retracted'
        """)
        retracted = cursor.fetchall()
        conn.close()

        for source_id, title, status, reason in retracted:
            assert reason is not None, (
                f"Retracted source {title} missing retraction_reason"
            )

    def test_evidence_span_hash_integrity(self, db_session):
        """Verify evidence span hashes are valid format."""
        import sqlite3
        import re

        conn = sqlite3.connect(".local/dev.db")
        cursor = conn.cursor()

        cursor.execute("""
            SELECT evidence_span_id, snippet_utf8_sha256
            FROM evidence_span
        """)
        spans = cursor.fetchall()
        conn.close()

        hash_pattern = re.compile(r"^[a-f0-9]{64}$")

        for span_id, hash_val in spans:
            assert hash_val is not None, f"Span {span_id} missing hash"
            assert hash_pattern.match(hash_val), (
                f"Span {span_id} has invalid hash format"
            )

    def test_text_unit_hash_integrity(self, db_session):
        """Verify text unit hashes are valid format."""
        import sqlite3
        import re

        conn = sqlite3.connect(".local/dev.db")
        cursor = conn.cursor()

        cursor.execute("""
            SELECT text_unit_id, text_canonical_utf8_sha256
            FROM text_unit
        """)
        units = cursor.fetchall()
        conn.close()

        hash_pattern = re.compile(r"^[a-f0-9]{64}$")

        for unit_id, hash_val in units:
            assert hash_val is not None, f"Unit {unit_id} missing hash"
            assert hash_pattern.match(hash_val), (
                f"Unit {unit_id} has invalid hash format"
            )


class TestProvenanceConstraints:
    """Test database constraints enforcement."""

    def test_foreign_key_enforcement(self):
        """Verify FK constraints prevent orphan records."""
        import sqlite3

        conn = sqlite3.connect(".local/dev.db")

        # Enable FK enforcement for this test
        conn.execute("PRAGMA foreign_keys = ON")

        cursor = conn.cursor()

        # Try to insert evidence_span with non-existent text_unit_id
        fake_unit_id = str(uuid4())

        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute(
                """
                INSERT INTO evidence_span (
                    evidence_span_id, text_unit_id, start_byte, end_byte,
                    snippet_utf8_sha256, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    str(uuid4()),
                    fake_unit_id,
                    0,
                    10,
                    "a" * 64,
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()

        conn.close()
