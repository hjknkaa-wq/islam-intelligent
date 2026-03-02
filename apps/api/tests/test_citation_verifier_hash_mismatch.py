"""Citation verifier must abstain when span hash integrity fails."""

from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUntypedBaseClass=false, reportUnusedCallResult=false

import sqlite3
from pathlib import Path
from typing import cast

import pytest

from islam_intelligent.rag.pipeline import RAGConfig, RAGPipeline


ROOT = Path(__file__).resolve().parents[3]
DEV_DB_PATH = ROOT / ".local" / "dev.db"


def _get_one_span() -> tuple[str, str, str, str, str, str, str] | None:
    with sqlite3.connect(str(DEV_DB_PATH)) as conn:
        row = cast(
            tuple[object, object, object, object, object, object, object] | None,
            conn.execute(
                """
                SELECT
                    es.evidence_span_id,
                    tu.text_unit_id,
                    tu.canonical_id,
                    tu.text_canonical,
                    es.snippet_utf8_sha256,
                    sd.source_id,
                    sd.trust_status
                FROM evidence_span es
                JOIN text_unit tu ON tu.text_unit_id = es.text_unit_id
                JOIN source_document sd ON sd.source_id = tu.source_id
                LIMIT 1
                """
            ).fetchone(),
        )

    if row is None:
        return None

    return (
        str(row[0]),
        str(row[1]),
        str(row[2]),
        str(row[3]),
        str(row[4]),
        str(row[5]),
        str(row[6]),
    )


def test_citation_verifier_hash_mismatch_forces_abstain() -> None:
    if not DEV_DB_PATH.exists():
        pytest.skip("Missing .local/dev.db; run scripts/dev_reset_and_seed.py")

    span = _get_one_span()
    if span is None:
        pytest.skip("No evidence_span rows in .local/dev.db")

    (
        evidence_span_id,
        text_unit_id,
        canonical_id,
        text_canonical,
        original_hash,
        source_id,
        original_trust_status,
    ) = span

    class HashMismatchPipeline(RAGPipeline):
        def retrieve(self, _query: str):  # type: ignore[override]
            return [
                {
                    "evidence_span_id": evidence_span_id,
                    "text_unit_id": text_unit_id,
                    "score": 0.95,
                    "snippet": text_canonical[:120],
                    "canonical_id": canonical_id,
                    "source_id": "trusted-source",
                    "trust_status": "trusted",
                }
            ]

    with sqlite3.connect(str(DEV_DB_PATH)) as conn:
        _ = conn.execute(
            "UPDATE source_document SET trust_status = ? WHERE source_id = ?",
            ("trusted", source_id),
        )
        conn.execute(
            "UPDATE evidence_span SET snippet_utf8_sha256 = ? WHERE evidence_span_id = ?",
            ("0" * 64, evidence_span_id),
        )
        conn.commit()

    pipeline = HashMismatchPipeline(RAGConfig(sufficiency_threshold=0.1))
    try:
        result = pipeline.query("hash-mismatch-check")
    finally:
        with sqlite3.connect(str(DEV_DB_PATH)) as conn:
            conn.execute(
                "UPDATE evidence_span SET snippet_utf8_sha256 = ? WHERE evidence_span_id = ?",
                (original_hash, evidence_span_id),
            )
            _ = conn.execute(
                "UPDATE source_document SET trust_status = ? WHERE source_id = ?",
                (original_trust_status, source_id),
            )
            conn.commit()

    assert result["verdict"] == "abstain"
    assert result["abstain_reason"] == "citation_verification_failed"
    assert result["fail_reason"] == "citation_verification_failed"
