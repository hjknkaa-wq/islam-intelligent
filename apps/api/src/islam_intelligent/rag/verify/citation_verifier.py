"""Verify citations against persisted evidence spans."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from collections.abc import Mapping, Sequence


@dataclass(frozen=True)
class CitationVerificationResult:
    """Result object for citation verification."""

    verified: bool
    reason: str | None
    checked_citation_count: int


def _default_dev_db_path() -> Path:
    repo_root = Path(__file__).resolve().parents[6]
    return repo_root / ".local" / "dev.db"


class CitationVerifier:
    """Verifies that citations are resolvable and cryptographically consistent."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path: Path = (
            Path(db_path) if db_path is not None else _default_dev_db_path()
        )

    def verify_citations(
        self, statements: Sequence[Mapping[str, object]]
    ) -> CitationVerificationResult:
        """Verify all citations in statement payloads.

        Checks for every citation:
        1) evidence_span_id exists
        2) span resolves to text_unit + source_document
        3) hash(UTF-8 bytes slice) == snippet_utf8_sha256
        """
        citations: list[str] = []
        for statement in statements:
            raw_citations = statement.get("citations", [])
            if not isinstance(raw_citations, list):
                return CitationVerificationResult(
                    verified=False,
                    reason="invalid_citation_payload",
                    checked_citation_count=len(citations),
                )
            raw_citations_typed = cast(list[Mapping[str, object]], raw_citations)
            for citation in raw_citations_typed:
                evidence_span_id = citation.get("evidence_span_id")
                if (
                    not isinstance(evidence_span_id, str)
                    or not evidence_span_id.strip()
                ):
                    return CitationVerificationResult(
                        verified=False,
                        reason="invalid_evidence_span_id",
                        checked_citation_count=len(citations),
                    )
                citations.append(evidence_span_id)

        if not citations:
            return CitationVerificationResult(
                verified=False,
                reason="no_citations",
                checked_citation_count=0,
            )

        if not self.db_path.exists():
            return CitationVerificationResult(
                verified=False,
                reason="citation_db_unavailable",
                checked_citation_count=0,
            )

        with sqlite3.connect(str(self.db_path)) as conn:
            for idx, evidence_span_id in enumerate(citations, start=1):
                verification = self._verify_single_citation(conn, evidence_span_id)
                if verification is not None:
                    return CitationVerificationResult(
                        verified=False,
                        reason=verification,
                        checked_citation_count=idx - 1,
                    )

        return CitationVerificationResult(
            verified=True,
            reason=None,
            checked_citation_count=len(citations),
        )

    def _verify_single_citation(
        self, conn: sqlite3.Connection, evidence_span_id: str
    ) -> str | None:
        row = cast(
            tuple[object, object, object, object, object, object] | None,
            conn.execute(
                """
            SELECT
                es.start_byte,
                es.end_byte,
                es.snippet_utf8_sha256,
                tu.text_canonical,
                tu.text_unit_id,
                sd.source_id
            FROM evidence_span es
            LEFT JOIN text_unit tu ON tu.text_unit_id = es.text_unit_id
            LEFT JOIN source_document sd ON sd.source_id = tu.source_id
            WHERE es.evidence_span_id = ?
            """,
                (evidence_span_id,),
            ).fetchone(),
        )

        if row is None:
            return "evidence_span_not_found"

        start_byte, end_byte, expected_hash, text_canonical, text_unit_id, source_id = (
            row
        )

        if text_unit_id is None or source_id is None or text_canonical is None:
            return "citation_unresolved"

        if not isinstance(start_byte, int) or not isinstance(end_byte, int):
            return "invalid_span_offsets"

        text_bytes = str(text_canonical).encode("utf-8")
        if start_byte < 0 or end_byte > len(text_bytes) or start_byte >= end_byte:
            return "invalid_span_offsets"

        observed_hash = hashlib.sha256(text_bytes[start_byte:end_byte]).hexdigest()
        if observed_hash != str(expected_hash):
            return "hash_mismatch"

        return None
