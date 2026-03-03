"""Unit tests for citation verification.

These tests are deterministic and operate on a temporary SQLite DB.
"""

from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingParameterType=false

import hashlib
import sqlite3
from pathlib import Path

from islam_intelligent.rag.verify import CitationVerificationResult, CitationVerifier


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _create_schema(conn: sqlite3.Connection) -> None:
    _ = conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS evidence_span (
            evidence_span_id TEXT PRIMARY KEY,
            text_unit_id TEXT,
            start_byte INTEGER,
            end_byte INTEGER,
            snippet_utf8_sha256 TEXT
        );

        CREATE TABLE IF NOT EXISTS text_unit (
            text_unit_id TEXT PRIMARY KEY,
            source_id TEXT,
            text_canonical TEXT
        );

        CREATE TABLE IF NOT EXISTS source_document (
            source_id TEXT PRIMARY KEY
        );
        """
    )
    conn.commit()


def _seed_valid_span(db_path: Path) -> dict[str, str | int]:
    evidence_span_id = "es_1"
    text_unit_id = "tu_1"
    source_id = "src_1"
    text = "abc def ghi"
    text_bytes = text.encode("utf-8")
    start = text_bytes.index(b"def")
    end = start + 3
    expected = _sha256_hex(text_bytes[start:end])

    with sqlite3.connect(str(db_path)) as conn:
        _create_schema(conn)
        _ = conn.execute(
            "INSERT INTO source_document(source_id) VALUES (?)", (source_id,)
        )
        _ = conn.execute(
            "INSERT INTO text_unit(text_unit_id, source_id, text_canonical) VALUES (?,?,?)",
            (text_unit_id, source_id, text),
        )
        _ = conn.execute(
            """
            INSERT INTO evidence_span(
                evidence_span_id, text_unit_id, start_byte, end_byte, snippet_utf8_sha256
            ) VALUES (?,?,?,?,?)
            """,
            (evidence_span_id, text_unit_id, int(start), int(end), expected),
        )
        conn.commit()

    return {
        "evidence_span_id": evidence_span_id,
        "text_unit_id": text_unit_id,
        "source_id": source_id,
        "text": text,
        "start": int(start),
        "end": int(end),
        "expected": expected,
    }


def _verify(
    db_path: Path, evidence_span_ids: list[str] | str
) -> CitationVerificationResult:
    verifier = CitationVerifier(db_path=db_path)
    if isinstance(evidence_span_ids, str):
        ids = [evidence_span_ids]
    else:
        ids = evidence_span_ids
    statements = [
        {
            "text": "stmt",
            "citations": [{"evidence_span_id": esid} for esid in ids],
        }
    ]
    return verifier.verify_citations(statements)


def test_invalid_citation_payload_rejected() -> None:
    db_path = Path("does-not-matter.db")
    verifier = CitationVerifier(db_path=db_path)
    res = verifier.verify_citations([{"text": "x", "citations": {}}])
    assert res.verified is False
    assert res.reason == "invalid_citation_payload"
    assert res.checked_citation_count == 0


def test_invalid_evidence_span_id_rejected_empty_string() -> None:
    db_path = Path("does-not-matter.db")
    verifier = CitationVerifier(db_path=db_path)
    res = verifier.verify_citations(
        [{"text": "x", "citations": [{"evidence_span_id": ""}]}]
    )
    assert res.verified is False
    assert res.reason == "invalid_evidence_span_id"
    assert res.checked_citation_count == 0


def test_invalid_evidence_span_id_rejected_whitespace() -> None:
    db_path = Path("does-not-matter.db")
    verifier = CitationVerifier(db_path=db_path)
    res = verifier.verify_citations(
        [{"text": "x", "citations": [{"evidence_span_id": "   "}]}]
    )
    assert res.verified is False
    assert res.reason == "invalid_evidence_span_id"


def test_no_citations_rejected() -> None:
    db_path = Path("does-not-matter.db")
    verifier = CitationVerifier(db_path=db_path)
    res = verifier.verify_citations([{"text": "x", "citations": []}])
    assert res.verified is False
    assert res.reason == "no_citations"
    assert res.checked_citation_count == 0


def test_citation_db_unavailable_rejected(tmp_path: Path) -> None:
    db_path = tmp_path / "missing.db"
    res = _verify(db_path, "es_1")
    assert res.verified is False
    assert res.reason == "citation_db_unavailable"
    assert res.checked_citation_count == 0


def test_evidence_span_not_found(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    _ = _seed_valid_span(db_path)
    res = _verify(db_path, "es_missing")
    assert res.verified is False
    assert res.reason == "evidence_span_not_found"
    assert res.checked_citation_count == 0


def test_citation_unresolved_when_text_unit_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    with sqlite3.connect(str(db_path)) as conn:
        _create_schema(conn)
        _ = conn.execute(
            "INSERT INTO evidence_span VALUES (?,?,?,?,?)",
            ("es_1", "tu_missing", 0, 1, "0" * 64),
        )
        conn.commit()

    res = _verify(db_path, "es_1")
    assert res.verified is False
    assert res.reason == "citation_unresolved"


def test_invalid_span_offsets_negative_start(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    seed = _seed_valid_span(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        _ = conn.execute(
            "UPDATE evidence_span SET start_byte=? WHERE evidence_span_id=?",
            (-1, seed["evidence_span_id"]),
        )
        conn.commit()

    res = _verify(db_path, str(seed["evidence_span_id"]))
    assert res.verified is False
    assert res.reason == "invalid_span_offsets"


def test_invalid_span_offsets_start_ge_end(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    seed = _seed_valid_span(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        _ = conn.execute(
            "UPDATE evidence_span SET start_byte=?, end_byte=? WHERE evidence_span_id=?",
            (5, 5, seed["evidence_span_id"]),
        )
        conn.commit()

    res = _verify(db_path, str(seed["evidence_span_id"]))
    assert res.verified is False
    assert res.reason == "invalid_span_offsets"


def test_hash_mismatch_detected(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    seed = _seed_valid_span(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        _ = conn.execute(
            "UPDATE evidence_span SET snippet_utf8_sha256=? WHERE evidence_span_id=?",
            ("0" * 64, seed["evidence_span_id"]),
        )
        conn.commit()

    res = _verify(db_path, str(seed["evidence_span_id"]))
    assert res.verified is False
    assert res.reason == "hash_mismatch"
    assert res.checked_citation_count == 0


def test_valid_citation_verifies(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    seed = _seed_valid_span(db_path)
    res = _verify(db_path, str(seed["evidence_span_id"]))
    assert res.verified is True
    assert res.reason is None
    assert res.checked_citation_count == 1


def test_multi_citation_checked_count_reports_prior_success(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    _ = _seed_valid_span(db_path)

    with sqlite3.connect(str(db_path)) as conn:
        _ = conn.execute(
            "INSERT INTO source_document(source_id) VALUES (?)", ("src_2",)
        )
        _ = conn.execute(
            "INSERT INTO text_unit(text_unit_id, source_id, text_canonical) VALUES (?,?,?)",
            ("tu_2", "src_2", "zzz yyy xxx"),
        )
        _ = conn.execute(
            "INSERT INTO evidence_span VALUES (?,?,?,?,?)",
            ("es_2", "tu_2", 0, 3, "0" * 64),
        )
        conn.commit()

    res = _verify(db_path, ["es_1", "es_2"])
    assert res.verified is False
    assert res.reason == "hash_mismatch"
    assert res.checked_citation_count == 1


def test_invalid_citation_payload_counts_prior_parsed_citations(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    _ = _seed_valid_span(db_path)
    verifier = CitationVerifier(db_path=db_path)

    res = verifier.verify_citations(
        [
            {"text": "ok", "citations": [{"evidence_span_id": "es_1"}]},
            {"text": "bad", "citations": {"evidence_span_id": "es_1"}},
        ]
    )
    assert res.verified is False
    assert res.reason == "invalid_citation_payload"
    assert res.checked_citation_count == 1
