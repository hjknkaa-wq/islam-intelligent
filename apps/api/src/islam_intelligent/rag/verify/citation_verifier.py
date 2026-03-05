"""Verify citations against persisted evidence spans."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from collections.abc import Mapping, Sequence
from ...db.engine import DATABASE_URL

from .faithfulness import CitationFaithfulnessVerifier, FaithfulnessResult


@dataclass(frozen=True)
class CitationVerificationResult:
    """Result object for citation verification."""

    verified: bool
    reason: str | None
    checked_citation_count: int
    faithfulness_score: float | None = None
    faithfulness_threshold: float | None = None
    faithfulness_flagged: bool = False
    unsupported_claim_count: int = 0


def _default_dev_db_path() -> Path:
    """
    Determine the filesystem path for the development SQLite database used by the verifier.
    
    If the engine's DATABASE_URL points to a local sqlite+pysqlite:/// path, returns that path as a Path. Otherwise returns the repository root's ".local/dev.db" fallback.
    
    Returns:
        Path: Filesystem path to the development SQLite database file.
    """
    db_url = DATABASE_URL
    if db_url.startswith("sqlite+pysqlite:///"):
        path_str = db_url[len("sqlite+pysqlite:///") :]
        if path_str:
            return Path(path_str)
    # Fallback to default path
    repo_root = Path(__file__).resolve().parents[6]
    return repo_root / ".local" / "dev.db"


class CitationVerifier:
    """Verifies that citations are resolvable and cryptographically consistent."""

    db_path: Path
    faithfulness_threshold: float
    faithfulness_action: str
    _faithfulness_verifier: CitationFaithfulnessVerifier

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        faithfulness_threshold: float = 0.0,
        faithfulness_action: str = "abstain",
        faithfulness_verifier: CitationFaithfulnessVerifier | None = None,
    ):
        """
        Initialize a CitationVerifier with database path and optional faithfulness configuration.
        
        Parameters:
            db_path (str | Path | None): Path to the SQLite citation database. If None, a default development DB path is used.
            faithfulness_threshold (float): Minimum overall faithfulness score required to consider faithfulness checks passing; coerced to a non-negative float.
            faithfulness_action (str): Action when faithfulness is below threshold; normalized to either "abstain" or "flag" (defaults to "abstain").
            faithfulness_verifier (CitationFaithfulnessVerifier | None): Optional custom verifier used to evaluate faithfulness; a default verifier is created when not provided.
        
        """
        self.db_path: Path = (
            Path(db_path) if db_path is not None else _default_dev_db_path()
        )
        self.faithfulness_threshold = _coerce_non_negative_float(faithfulness_threshold)
        clean_action = str(faithfulness_action).strip().lower()
        self.faithfulness_action = (
            clean_action if clean_action in {"abstain", "flag"} else "abstain"
        )
        self._faithfulness_verifier = (
            faithfulness_verifier or CitationFaithfulnessVerifier()
        )

    def verify_citations(
        self,
        statements: Sequence[Mapping[str, object]],
        retrieved_context: Sequence[Mapping[str, object]] | None = None,
    ) -> CitationVerificationResult:
        """
        Verify that all citations in the provided statements resolve to persisted evidence spans and, if configured, that the statements meet the configured faithfulness threshold.
        
        Parameters:
            statements (Sequence[Mapping[str, object]]): Sequence of statement payloads. Each statement may include a "citations" list of mappings where each citation must include a non-empty string "evidence_span_id".
            retrieved_context (Sequence[Mapping[str, object]] | None): Optional retrieved context used by the faithfulness verifier to evaluate claim support.
        
        Returns:
            CitationVerificationResult: Outcome of the verification. `verified` is `True` when every citation resolves, the stored snippet hash matches the text slice, and (when a positive faithfulness threshold is configured) the overall faithfulness score meets the threshold. If verification fails, `reason` contains a machine-friendly error code such as "invalid_citation_payload", "invalid_evidence_span_id", "no_citations", "citation_db_unavailable", "evidence_span_not_found", "citation_unresolved", "invalid_span_offsets", "hash_mismatch", or "low_faithfulness". When a faithfulness check runs, the result includes `faithfulness_score`, `faithfulness_threshold`, `faithfulness_flagged`, and `unsupported_claim_count` as applicable.
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

        faithfulness_result = self._verify_faithfulness(statements, retrieved_context)
        if (
            faithfulness_result is not None
            and faithfulness_result.overall_score < self.faithfulness_threshold
        ):
            if self.faithfulness_action == "abstain":
                return CitationVerificationResult(
                    verified=False,
                    reason="low_faithfulness",
                    checked_citation_count=len(citations),
                    faithfulness_score=faithfulness_result.overall_score,
                    faithfulness_threshold=self.faithfulness_threshold,
                    faithfulness_flagged=True,
                    unsupported_claim_count=faithfulness_result.unsupported_claim_count,
                )

            return CitationVerificationResult(
                verified=True,
                reason=None,
                checked_citation_count=len(citations),
                faithfulness_score=faithfulness_result.overall_score,
                faithfulness_threshold=self.faithfulness_threshold,
                faithfulness_flagged=True,
                unsupported_claim_count=faithfulness_result.unsupported_claim_count,
            )

        return CitationVerificationResult(
            verified=True,
            reason=None,
            checked_citation_count=len(citations),
            faithfulness_score=(
                faithfulness_result.overall_score
                if faithfulness_result is not None
                else None
            ),
            faithfulness_threshold=(
                self.faithfulness_threshold
                if self.faithfulness_threshold > 0.0
                else None
            ),
            unsupported_claim_count=(
                faithfulness_result.unsupported_claim_count
                if faithfulness_result is not None
                else 0
            ),
        )

    def _verify_single_citation(
        self, conn: sqlite3.Connection, evidence_span_id: str
    ) -> str | None:
        """
        Validate that a single evidence span citation exists, resolves to a concrete text unit and source, has valid byte offsets, and matches the stored snippet hash.
        
        Parameters:
            conn (sqlite3.Connection): Open SQLite connection used to query evidence_span, text_unit, and source_document.
            evidence_span_id (str): Identifier of the evidence_span to validate.
        
        Returns:
            str | None: An error code describing why the citation is invalid, or `None` if the citation is valid.
                Possible error codes:
                - "evidence_span_not_found": no evidence_span row exists for the given id.
                - "citation_unresolved": the evidence span does not reference a concrete text unit, source, or canonical text.
                - "invalid_span_offsets": span start/end are not integers, out of bounds, or start is not less than end.
                - "hash_mismatch": the extracted span bytes do not match the stored snippet hash.
        """
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

    def _verify_faithfulness(
        self,
        statements: Sequence[Mapping[str, object]],
        retrieved_context: Sequence[Mapping[str, object]] | None,
    ) -> FaithfulnessResult | None:
        """
        Evaluate the faithfulness of provided statements using the retrieved context when a positive faithfulness threshold is configured.
        
        Parameters:
            statements (Sequence[Mapping[str, object]]): Statements to assess for faithfulness.
            retrieved_context (Sequence[Mapping[str, object]] | None): Optional retrieved documents or context to inform the assessment.
        
        Returns:
            FaithfulnessResult | None: A faithfulness evaluation result when the verifier is enabled (faithfulness_threshold > 0.0); `None` if the threshold is zero or negative.
        """
        if self.faithfulness_threshold <= 0.0:
            return None
        return self._faithfulness_verifier.evaluate(statements, retrieved_context)


def _coerce_non_negative_float(value: object) -> float:
    """
    Coerces a value into a non-negative float.
    
    Converts integers, floats, or numeric strings to a float greater than or equal to 0.0. For non-numeric strings or other types, returns 0.0.
    
    Parameters:
        value (object): The value to coerce.
    
    Returns:
        float: The coerced non-negative float (>= 0.0).
    """
    if isinstance(value, (int, float)):
        return max(0.0, float(value))
    if isinstance(value, str):
        try:
            return max(0.0, float(value))
        except ValueError:
            return 0.0
    return 0.0
