"""Citation verifier should reject fabricated evidence_span_id values."""

from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUntypedBaseClass=false

import sqlite3
from pathlib import Path
from typing import cast

import pytest

from islam_intelligent.rag.pipeline import RAGConfig, RAGPipeline


ROOT = Path(__file__).resolve().parents[3]
DEV_DB_PATH = ROOT / ".local" / "dev.db"


def test_citation_verifier_rejects_fabricated_span_id() -> None:
    if not DEV_DB_PATH.exists():
        pytest.skip("Missing .local/dev.db; run scripts/dev_reset_and_seed.py")

    class FabricatedCitationPipeline(RAGPipeline):
        def retrieve(self, _query: str):  # type: ignore[override]
            return [
                {
                    "evidence_span_id": "es_fabricated_9999",
                    "text_unit_id": "es_fabricated_9999",
                    "score": 0.95,
                    "snippet": "fabricated citation",
                    "canonical_id": "unknown:fabricated",
                    "source_id": "source:fabricated",
                    "trust_status": "trusted",
                }
            ]

    pipeline = FabricatedCitationPipeline(RAGConfig(sufficiency_threshold=0.1))
    result = pipeline.query("fabrication-check")

    assert result["verdict"] == "abstain"
    assert result["abstain_reason"] == "citation_verification_failed"
    assert result["fail_reason"] == "citation_verification_failed"


def test_citation_verifier_directly_rejects_missing_span() -> None:
    if not DEV_DB_PATH.exists():
        pytest.skip("Missing .local/dev.db; run scripts/dev_reset_and_seed.py")

    with sqlite3.connect(str(DEV_DB_PATH)) as conn:
        row = cast(
            tuple[object] | None,
            conn.execute(
                "SELECT 1 FROM evidence_span WHERE evidence_span_id = ?",
                ("es_fabricated_9999",),
            ).fetchone(),
        )
    assert row is None
