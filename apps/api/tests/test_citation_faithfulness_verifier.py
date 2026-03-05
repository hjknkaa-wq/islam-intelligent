"""Unit tests for citation faithfulness verification."""

from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

import hashlib
import sqlite3
from pathlib import Path

import pytest

from islam_intelligent.rag.verify.citation_verifier import CitationVerifier
from islam_intelligent.rag.verify.faithfulness import CitationFaithfulnessVerifier


def _create_schema(conn: sqlite3.Connection) -> None:
    """
    Create the SQLite schema used in tests for source documents, text units, and evidence spans.
    
    This ensures the following tables exist with their primary keys and key columns:
    - source_document: source_id (PRIMARY KEY)
    - text_unit: text_unit_id (PRIMARY KEY), source_id, text_canonical
    - evidence_span: evidence_span_id (PRIMARY KEY), text_unit_id, start_byte, end_byte, snippet_utf8_sha256
    
    Parameters:
        conn (sqlite3.Connection): Open SQLite connection on which the schema will be created and committed.
    """
    _ = conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS source_document (
            source_id TEXT PRIMARY KEY
        );

        CREATE TABLE IF NOT EXISTS text_unit (
            text_unit_id TEXT PRIMARY KEY,
            source_id TEXT,
            text_canonical TEXT
        );

        CREATE TABLE IF NOT EXISTS evidence_span (
            evidence_span_id TEXT PRIMARY KEY,
            text_unit_id TEXT,
            start_byte INTEGER,
            end_byte INTEGER,
            snippet_utf8_sha256 TEXT
        );
        """
    )
    conn.commit()


def _seed_span(db_path: Path, *, evidence_span_id: str, text: str) -> None:
    """
    Insert a source_document, text_unit, and evidence_span row into the SQLite database at db_path for use in tests.
    
    Seeds the database with a source and text unit derived from the provided evidence_span_id, creates an evidence_span covering the full UTF-8 byte range of text, and stores the SHA-256 hex digest of the UTF-8 bytes in the snippet_utf8_sha256 column. The changes are committed to the database.
    
    Parameters:
        db_path (Path): Filesystem path to the SQLite database file to modify.
        evidence_span_id (str): Identifier to use for the evidence_span (also used to derive text_unit and source IDs).
        text (str): Text content of the span; its UTF-8 byte length determines start/end byte values and is hashed for snippet_utf8_sha256.
    """
    text_unit_id = f"tu_{evidence_span_id}"
    source_id = f"src_{evidence_span_id}"
    text_bytes = text.encode("utf-8")
    span_hash = hashlib.sha256(text_bytes).hexdigest()

    with sqlite3.connect(str(db_path)) as conn:
        _create_schema(conn)
        _ = conn.execute(
            "INSERT INTO source_document(source_id) VALUES (?)",
            (source_id,),
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
            (evidence_span_id, text_unit_id, 0, len(text_bytes), span_hash),
        )
        conn.commit()


def test_faithfulness_checker_scores_each_claim_against_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    checker = CitationFaithfulnessVerifier(api_key=None)

    statements = [
        {
            "text": "Allah is Most Merciful",
            "citations": [
                {
                    "evidence_span_id": "es_1",
                    "snippet": "Allah is Most Merciful and Forgiving.",
                }
            ],
        },
        {
            "text": "The moon is made of cheese",
            "citations": [
                {
                    "evidence_span_id": "es_2",
                    "snippet": "Prayer is established five times daily.",
                }
            ],
        },
    ]
    retrieved = [
        {
            "evidence_span_id": "es_1",
            "snippet": "Allah is Most Merciful and Forgiving.",
        },
        {
            "evidence_span_id": "es_2",
            "snippet": "Prayer is established five times daily.",
        },
    ]

    result = checker.evaluate(statements, retrieved)

    assert result.judge == "heuristic"
    assert result.claims_checked == 2
    assert 0.0 <= result.overall_score <= 10.0
    assert result.per_claim[0].supported is True
    assert result.per_claim[1].supported is False
    assert result.unsupported_claim_count == 1


def test_faithfulness_checker_uses_retrieved_context_when_citation_snippet_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    checker = CitationFaithfulnessVerifier(api_key=None)

    statements = [
        {
            "text": "Prayer is established five times daily",
            "citations": [{"evidence_span_id": "es_1", "snippet": ""}],
        }
    ]
    retrieved = [
        {
            "evidence_span_id": "es_1",
            "snippet": "Prayer is established five times daily in Islam.",
        }
    ]

    result = checker.evaluate(statements, retrieved)

    assert result.claims_checked == 1
    assert result.per_claim[0].supported is True
    assert result.per_claim[0].score >= 7.0


def test_citation_verifier_abstains_when_faithfulness_below_threshold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verifies that CitationVerifier abstains when the citation faithfulness score is below the configured threshold.
    
    Seeds a temporary SQLite evidence span, constructs a CitationVerifier with faithfulness_threshold=7.0 and action "abstain", supplies a statement whose citation snippet does not fully match the seeded span, runs verification, and asserts that verification is rejected with reason "low_faithfulness", that faithfulness was flagged, and that a numeric faithfulness_score is present and less than 7.0.
    """
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    db_path = tmp_path / "faithfulness.sqlite"
    _seed_span(
        db_path, evidence_span_id="es_1", text="Prayer is established five times daily"
    )

    verifier = CitationVerifier(
        db_path=db_path,
        faithfulness_threshold=7.0,
        faithfulness_action="abstain",
        faithfulness_verifier=CitationFaithfulnessVerifier(api_key=None),
    )
    statements = [
        {
            "text": "The moon is made of cheese",
            "citations": [
                {"evidence_span_id": "es_1", "snippet": "Prayer is established"}
            ],
        }
    ]
    retrieved = [{"evidence_span_id": "es_1", "snippet": "Prayer is established"}]

    result = verifier.verify_citations(statements, retrieved)

    assert result.verified is False
    assert result.reason == "low_faithfulness"
    assert result.faithfulness_flagged is True
    assert result.faithfulness_score is not None
    assert result.faithfulness_score < 7.0


def test_citation_verifier_flags_when_configured_to_flag_low_faithfulness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    db_path = tmp_path / "faithfulness.sqlite"
    _seed_span(
        db_path, evidence_span_id="es_1", text="Prayer is established five times daily"
    )

    verifier = CitationVerifier(
        db_path=db_path,
        faithfulness_threshold=7.0,
        faithfulness_action="flag",
        faithfulness_verifier=CitationFaithfulnessVerifier(api_key=None),
    )
    statements = [
        {
            "text": "The moon is made of cheese",
            "citations": [
                {"evidence_span_id": "es_1", "snippet": "Prayer is established"}
            ],
        }
    ]
    retrieved = [{"evidence_span_id": "es_1", "snippet": "Prayer is established"}]

    result = verifier.verify_citations(statements, retrieved)

    assert result.verified is True
    assert result.reason is None
    assert result.faithfulness_flagged is True
    assert result.faithfulness_score is not None
    assert result.faithfulness_score < 7.0


def test_citation_verifier_passes_when_faithfulness_meets_threshold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verifies that CitationVerifier accepts citations when faithfulness meets or exceeds the threshold.
    
    Seeds a evidence span in a temporary SQLite database, constructs a CitationVerifier configured to abstain on low faithfulness with a threshold of 7.0, and asserts that a statement whose cited snippet exactly matches the seeded span is verified, not flagged, and receives a faithfulness score >= 7.0.
    
    Parameters:
        tmp_path (Path): Temporary filesystem path fixture.
        monkeypatch (pytest.MonkeyPatch): Fixture used to modify environment variables for the test.
    """
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    db_path = tmp_path / "faithfulness.sqlite"
    _seed_span(
        db_path, evidence_span_id="es_1", text="Prayer is established five times daily"
    )

    verifier = CitationVerifier(
        db_path=db_path,
        faithfulness_threshold=7.0,
        faithfulness_action="abstain",
        faithfulness_verifier=CitationFaithfulnessVerifier(api_key=None),
    )
    statements = [
        {
            "text": "Prayer is established five times daily",
            "citations": [
                {
                    "evidence_span_id": "es_1",
                    "snippet": "Prayer is established five times daily",
                }
            ],
        }
    ]
    retrieved = [
        {
            "evidence_span_id": "es_1",
            "snippet": "Prayer is established five times daily",
        }
    ]

    result = verifier.verify_citations(statements, retrieved)

    assert result.verified is True
    assert result.reason is None
    assert result.faithfulness_flagged is False
    assert result.faithfulness_score is not None
    assert result.faithfulness_score >= 7.0
