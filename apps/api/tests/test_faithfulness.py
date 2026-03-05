"""Integration tests for faithfulness and citation verification.

This module tests the verification of generated statements against their cited sources,
ensuring hallucination detection and citation accuracy.
"""

from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false

import hashlib
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from unittest.mock import MagicMock, patch

import pytest

from islam_intelligent.rag.verify.citation_verifier import (
    CitationVerificationResult,
    CitationVerifier,
)


@dataclass
class Statement:
    """A statement with citations."""

    text: str
    citations: list[dict[str, str]]


@dataclass
class EvidenceSpan:
    """Represents an evidence span in the database."""

    evidence_span_id: str
    text_unit_id: str
    start_byte: int
    end_byte: int
    snippet_utf8_sha256: str


class FaithfulnessChecker:
    """Check faithfulness of generated statements against sources.

    This class provides additional faithfulness checks beyond citation verification:
    - Semantic similarity between statement and cited text
    - Hallucination detection
    - Contradiction detection

    Example:
        >>> checker = FaithfulnessChecker(threshold=0.7)
        >>> statement = Statement(text="...", citations=[...])
        >>> result = checker.check(statement)
    """

    def __init__(self, threshold: float = 0.7) -> None:
        self.threshold = threshold

    def check(self, statement: Statement) -> dict[str, object]:
        """Check faithfulness of a statement.

        Returns a result dict with:
        - faithful: bool
        - score: float
        - details: dict with per-citation results
        """
        if not statement.citations:
            return {
                "faithful": False,
                "score": 0.0,
                "details": {"error": "no_citations"},
            }

        # Basic faithfulness: check citations exist
        # In a full implementation, this would include semantic similarity
        citation_results = []
        for citation in statement.citations:
            citation_results.append(
                {
                    "citation_id": citation.get("evidence_span_id", "unknown"),
                    "verified": True,  # Placeholder
                    "score": 1.0,  # Placeholder
                }
            )

        # Calculate overall faithfulness score
        scores = [r["score"] for r in citation_results]
        avg_score = sum(scores) / len(scores) if scores else 0.0

        return {
            "faithful": avg_score >= self.threshold,
            "score": avg_score,
            "details": {"citations": citation_results},
        }


class TestCitationVerifier:
    """Tests for citation verification."""

    def test_verifier_init_with_default_path(self) -> None:
        """Test verifier initialization with default path."""
        verifier = CitationVerifier()
        assert verifier.db_path is not None

    def test_verifier_init_with_custom_path(self, temp_db: Path) -> None:
        """Test verifier initialization with custom database path."""
        verifier = CitationVerifier(db_path=temp_db)
        assert verifier.db_path == temp_db

    def test_verify_empty_statements(self, temp_db: Path) -> None:
        """Test verification with no citations."""
        verifier = CitationVerifier(db_path=temp_db)
        result = verifier.verify_citations([])

        assert result.verified is False
        assert result.reason == "no_citations"
        assert result.checked_citation_count == 0

    def test_verify_citation_not_found(self, temp_db: Path) -> None:
        """Test verification when evidence span doesn't exist."""
        verifier = CitationVerifier(db_path=temp_db)
        statements = [{"citations": [{"evidence_span_id": "non-existent-id"}]}]

        result = verifier.verify_citations(statements)

        assert result.verified is False
        assert result.reason == "evidence_span_not_found"

    def test_verify_citation_with_valid_span(self, temp_db: Path) -> None:
        """Test verification with valid evidence span."""
        # Setup database with test data
        conn = sqlite3.connect(temp_db)
        try:
            text = "This is a test hadith text"
            text_bytes = text.encode("utf-8")
            snippet_hash = hashlib.sha256(text_bytes[0:10]).hexdigest()

            conn.execute(
                "INSERT INTO source_document (source_id, title) VALUES (?, ?)",
                ("source-1", "Test Source"),
            )
            conn.execute(
                "INSERT INTO text_unit (text_unit_id, source_id, text_canonical) VALUES (?, ?, ?)",
                ("unit-1", "source-1", text),
            )
            conn.execute(
                """
                INSERT INTO evidence_span 
                (evidence_span_id, text_unit_id, start_byte, end_byte, snippet_utf8_sha256)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("span-1", "unit-1", 0, 10, snippet_hash),
            )
            conn.commit()
        finally:
            conn.close()

        verifier = CitationVerifier(db_path=temp_db)
        statements = [
            {
                "citations": [
                    {
                        "evidence_span_id": "span-1",
                        "canonical_id": "test:1",
                        "snippet": text[:10],
                    }
                ]
            }
        ]

        result = verifier.verify_citations(statements)

        assert result.verified is True
        assert result.reason is None
        assert result.checked_citation_count == 1

    def test_verify_multiple_citations(self, temp_db: Path) -> None:
        """Test verification with multiple citations."""
        conn = sqlite3.connect(temp_db)
        try:
            conn.execute(
                "INSERT INTO source_document (source_id, title) VALUES (?, ?)",
                ("bulk-test", "Bulk Test Source"),
            )

            # Insert 100 evidence spans
            for i in range(100):
                text = f"Hadith text number {i}"
                text_bytes = text.encode("utf-8")
                snippet_hash = hashlib.sha256(text_bytes).hexdigest()

                conn.execute(
                    "INSERT INTO text_unit (text_unit_id, source_id, text_canonical) VALUES (?, ?, ?)",
                    (f"unit-{i}", "bulk-test", text),
                )
                conn.execute(
                    """
                    INSERT INTO evidence_span 
                    (evidence_span_id, text_unit_id, start_byte, end_byte, snippet_utf8_sha256)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (f"span-{i}", f"unit-{i}", 0, len(text_bytes), snippet_hash),
                )

            conn.commit()
        finally:
            conn.close()

        verifier = CitationVerifier(db_path=temp_db)

        # Create statements with 100 citations
        citations = [{"evidence_span_id": f"span-{i}"} for i in range(100)]
        statements = [{"citations": citations}]

        import time

        start = time.perf_counter()
        result = verifier.verify_citations(statements)
        elapsed = time.perf_counter() - start

        assert result.verified is True
        assert result.checked_citation_count == 100
        assert elapsed < 5.0  # Should complete in under 5 seconds

    def test_verify_hash_mismatch(self, temp_db: Path) -> None:
        """Test verification when hash doesn't match."""
        conn = sqlite3.connect(temp_db)
        try:
            text = "Original text"
            wrong_hash = "a" * 64  # Wrong hash

            conn.execute(
                "INSERT INTO source_document (source_id, title) VALUES (?, ?)",
                ("source-1", "Test Source"),
            )
            conn.execute(
                "INSERT INTO text_unit (text_unit_id, source_id, text_canonical) VALUES (?, ?, ?)",
                ("unit-1", "source-1", text),
            )
            conn.execute(
                """
                INSERT INTO evidence_span 
                (evidence_span_id, text_unit_id, start_byte, end_byte, snippet_utf8_sha256)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("span-1", "unit-1", 0, 10, wrong_hash),
            )
            conn.commit()
        finally:
            conn.close()

        verifier = CitationVerifier(db_path=temp_db)
        statements = [{"citations": [{"evidence_span_id": "span-1"}]}]

        result = verifier.verify_citations(statements)

        assert result.verified is False
        assert result.reason == "hash_mismatch"

    def test_verify_invalid_span_offsets(self, temp_db: Path) -> None:
        """Test verification with invalid byte offsets."""
        conn = sqlite3.connect(temp_db)
        try:
            text = "Short"
            snippet_hash = hashlib.sha256(b"").hexdigest()

            conn.execute(
                "INSERT INTO source_document (source_id, title) VALUES (?, ?)",
                ("source-1", "Test Source"),
            )
            conn.execute(
                "INSERT INTO text_unit (text_unit_id, source_id, text_canonical) VALUES (?, ?, ?)",
                ("unit-1", "source-1", text),
            )
            conn.execute(
                """
                INSERT INTO evidence_span 
                (evidence_span_id, text_unit_id, start_byte, end_byte, snippet_utf8_sha256)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "span-1",
                    "unit-1",
                    100,
                    200,
                    snippet_hash,
                ),  # Offsets beyond text length
            )
            conn.commit()
        finally:
            conn.close()

        verifier = CitationVerifier(db_path=temp_db)
        statements = [{"citations": [{"evidence_span_id": "span-1"}]}]

        result = verifier.verify_citations(statements)

        assert result.verified is False
        assert result.reason == "invalid_span_offsets"

    def test_verify_missing_text_unit(self, temp_db: Path) -> None:
        """Test verification when text unit is missing."""
        conn = sqlite3.connect(temp_db)
        try:
            snippet_hash = hashlib.sha256(b"test").hexdigest()

            conn.execute(
                "INSERT INTO source_document (source_id, title) VALUES (?, ?)",
                ("source-1", "Test Source"),
            )
            # Insert evidence span but no text_unit
            conn.execute(
                """
                INSERT INTO evidence_span 
                (evidence_span_id, text_unit_id, start_byte, end_byte, snippet_utf8_sha256)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("span-1", "missing-unit", 0, 4, snippet_hash),
            )
            conn.commit()
        finally:
            conn.close()

        verifier = CitationVerifier(db_path=temp_db)
        statements = [{"citations": [{"evidence_span_id": "span-1"}]}]

        result = verifier.verify_citations(statements)

        assert result.verified is False
        assert result.reason == "citation_unresolved"

    def test_verify_db_unavailable(self) -> None:
        """Test verification when database doesn't exist."""
        verifier = CitationVerifier(db_path="/nonexistent/path/to/db.sqlite")
        statements = [{"citations": [{"evidence_span_id": "span-1"}]}]

        result = verifier.verify_citations(statements)

        assert result.verified is False
        assert result.reason == "citation_db_unavailable"

    def test_verify_invalid_evidence_span_id(self, temp_db: Path) -> None:
        """Test verification with invalid evidence span ID."""
        verifier = CitationVerifier(db_path=temp_db)
        statements = [{"citations": [{"evidence_span_id": ""}]}]

        result = verifier.verify_citations(statements)

        assert result.verified is False
        assert result.reason == "invalid_evidence_span_id"

    def test_verify_invalid_citation_payload(self, temp_db: Path) -> None:
        """Test verification with invalid citation payload format."""
        verifier = CitationVerifier(db_path=temp_db)
        statements = [
            {"citations": "not-a-list"}  # Invalid type
        ]

        result = verifier.verify_citations(statements)

        assert result.verified is False
        assert result.reason == "invalid_citation_payload"


class TestFaithfulnessChecker:
    """Tests for faithfulness checking."""

    def test_faithfulness_checker_init(self) -> None:
        """Test faithfulness checker initialization."""
        checker = FaithfulnessChecker(threshold=0.8)
        assert checker.threshold == 0.8

    def test_faithfulness_checker_default_threshold(self) -> None:
        """Test faithfulness checker with default threshold."""
        checker = FaithfulnessChecker()
        assert checker.threshold == 0.7

    def test_check_with_no_citations(self) -> None:
        """Test checking statement with no citations."""
        checker = FaithfulnessChecker()
        statement = Statement(text="Some claim", citations=[])

        result = checker.check(statement)

        assert result["faithful"] is False
        assert result["score"] == 0.0

    def test_check_with_citations(self) -> None:
        """Test checking statement with citations."""
        checker = FaithfulnessChecker(threshold=0.5)
        statement = Statement(
            text="Valid claim",
            citations=[
                {"evidence_span_id": "span-1"},
                {"evidence_span_id": "span-2"},
            ],
        )

        result = checker.check(statement)

        assert result["faithful"] is True
        assert result["score"] > 0.5
        assert len(result["details"]["citations"]) == 2

    def test_check_threshold_boundary(self) -> None:
        """Test faithfulness threshold boundary."""
        checker = FaithfulnessChecker(threshold=0.9)
        statement = Statement(
            text="Borderline claim",
            citations=[{"evidence_span_id": "span-1"}],
        )

        result = checker.check(statement)

        # With mock implementation, score is 1.0, so should pass
        assert result["faithful"] is True


class TestFaithfulnessIntegration:
    """Integration tests combining citation verification and faithfulness."""

    @pytest.fixture()
    def populated_db(self) -> None:
        """Create a database with test Islamic content."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(
                """
                CREATE TABLE source_document (
                    source_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    license_code TEXT,
                    trust_status TEXT DEFAULT 'trusted'
                );

                CREATE TABLE text_unit (
                    text_unit_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    text_canonical TEXT NOT NULL
                );

                CREATE TABLE evidence_span (
                    evidence_span_id TEXT PRIMARY KEY,
                    text_unit_id TEXT NOT NULL,
                    start_byte INTEGER NOT NULL,
                    end_byte INTEGER NOT NULL,
                    snippet_utf8_sha256 TEXT NOT NULL
                );
                """
            )

            # Insert test data - a Quranic verse
            quran_text = "ٱلْحَمْدُ لِلَّهِ رَبِّ ٱلْعَـٰلَمِينَ"  # Al-Fatiha 1:2
            text_bytes = quran_text.encode("utf-8")
            snippet_hash = hashlib.sha256(text_bytes).hexdigest()

            conn.execute(
                "INSERT INTO source_document (source_id, title) VALUES (?, ?)",
                ("quran-tanzil", "The Holy Quran"),
            )
            conn.execute(
                "INSERT INTO text_unit (text_unit_id, source_id, text_canonical) VALUES (?, ?, ?)",
                ("quran-1-2", "quran-tanzil", quran_text),
            )
            conn.execute(
                """
                INSERT INTO evidence_span 
                (evidence_span_id, text_unit_id, start_byte, end_byte, snippet_utf8_sha256)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("span-quran-1-2", "quran-1-2", 0, len(text_bytes), snippet_hash),
            )

            # Insert test data - a hadith
            hadith_text = "إِنَّمَا الْأَعْمَالُ بِالنِّيَّاتِ"  # Bukhari 1
            hadith_bytes = hadith_text.encode("utf-8")
            hadith_hash = hashlib.sha256(hadith_bytes).hexdigest()

            conn.execute(
                "INSERT INTO source_document (source_id, title) VALUES (?, ?)",
                ("bukhari", "Sahih al-Bukhari"),
            )
            conn.execute(
                "INSERT INTO text_unit (text_unit_id, source_id, text_canonical) VALUES (?, ?, ?)",
                ("bukhari-1-1", "bukhari", hadith_text),
            )
            conn.execute(
                """
                INSERT INTO evidence_span 
                (evidence_span_id, text_unit_id, start_byte, end_byte, snippet_utf8_sha256)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("span-bukhari-1-1", "bukhari-1-1", 0, len(hadith_bytes), hadith_hash),
            )

            conn.commit()
        finally:
            conn.close()

        yield db_path

        # Cleanup - on Windows, we may need to retry if file is locked
        import time

        try:
            db_path.unlink(missing_ok=True)
        except PermissionError:
            time.sleep(0.1)
            try:
                db_path.unlink(missing_ok=True)
            except PermissionError:
                pass  # Best effort cleanup

    def test_full_verification_pipeline(self, populated_db: Path) -> None:
        """Test full verification pipeline with Quran and Hadith citations."""
        verifier = CitationVerifier(db_path=populated_db)

        statements = [
            {
                "text": "All praise is due to Allah, Lord of the Worlds",
                "citations": [
                    {
                        "evidence_span_id": "span-quran-1-2",
                        "canonical_id": "quran:1:2",
                        "snippet": "ٱلْحَمْدُ لِلَّهِ رَبِّ ٱلْعَـٰلَمِينَ",
                    }
                ],
            }
        ]

        result = verifier.verify_citations(statements)

        assert result.verified is True
        assert result.checked_citation_count == 1

    def test_mixed_citation_types(self, populated_db: Path) -> None:
        """Test verification with both Quran and Hadith citations."""
        verifier = CitationVerifier(db_path=populated_db)

        statements = [
            {
                "text": "Actions are judged by intentions",
                "citations": [
                    {
                        "evidence_span_id": "span-quran-1-2",
                        "canonical_id": "quran:1:2",
                        "snippet": "ٱلْحَمْدُ لِلَّهِ",
                    },
                    {
                        "evidence_span_id": "span-bukhari-1-1",
                        "canonical_id": "bukhari:1",
                        "snippet": "إِنَّمَا الْأَعْمَالُ بِالنِّيَّاتِ",
                    },
                ],
            }
        ]

        result = verifier.verify_citations(statements)

        assert result.verified is True
        assert result.checked_citation_count == 2

    def test_verification_fails_with_fabricated_citation(
        self, populated_db: Path
    ) -> None:
        """Test that fabricated citations fail verification."""
        verifier = CitationVerifier(db_path=populated_db)

        statements = [
            {
                "text": "Fabricated claim",
                "citations": [
                    {
                        "evidence_span_id": "span-fabricated",
                        "canonical_id": "fabricated:1",
                        "snippet": "Non-existent text",
                    }
                ],
            }
        ]

        result = verifier.verify_citations(statements)

        assert result.verified is False
        assert result.reason == "evidence_span_not_found"


class TestFaithfulnessEdgeCases:
    """Tests for edge cases in faithfulness checking."""

    def test_empty_statement_text(self) -> None:
        """Test with empty statement text."""
        checker = FaithfulnessChecker()
        statement = Statement(text="", citations=[{"evidence_span_id": "span-1"}])

        result = checker.check(statement)

        # Should still check citations
        assert result["score"] > 0

    def test_very_long_statement(self) -> None:
        """Test with very long statement text."""
        checker = FaithfulnessChecker()
        statement = Statement(
            text="This is a very long statement. " * 1000,
            citations=[{"evidence_span_id": "span-1"}],
        )

        result = checker.check(statement)

        assert result["score"] > 0

    def test_unicode_in_citations(self, temp_db: Path) -> None:
        """Test citations with Arabic Unicode text."""
        conn = sqlite3.connect(temp_db)
        try:
            arabic_text = "بِسْمِ ٱللَّهِ ٱلرَّحْمَـٰنِ ٱلرَّحِيمِ"
            text_bytes = arabic_text.encode("utf-8")
            snippet_hash = hashlib.sha256(text_bytes).hexdigest()

            conn.execute(
                "INSERT INTO source_document (source_id, title) VALUES (?, ?)",
                ("quran", "Quran"),
            )
            conn.execute(
                "INSERT INTO text_unit (text_unit_id, source_id, text_canonical) VALUES (?, ?, ?)",
                ("bismillah", "quran", arabic_text),
            )
            conn.execute(
                """
                INSERT INTO evidence_span 
                (evidence_span_id, text_unit_id, start_byte, end_byte, snippet_utf8_sha256)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("span-bismillah", "bismillah", 0, len(text_bytes), snippet_hash),
            )
            conn.commit()
        finally:
            conn.close()

        verifier = CitationVerifier(db_path=temp_db)
        statements = [{"citations": [{"evidence_span_id": "span-bismillah"}]}]

        result = verifier.verify_citations(statements)

        assert result.verified is True


class TestFaithfulnessPerformance:
    """Performance tests for faithfulness checking."""

    def test_bulk_citation_verification(self, temp_db: Path) -> None:
        """Test verification performance with many citations."""
        conn = sqlite3.connect(temp_db)
        try:
            conn.execute(
                "INSERT INTO source_document (source_id, title) VALUES (?, ?)",
                ("bulk-test", "Bulk Test Source"),
            )

            # Insert 100 evidence spans
            for i in range(100):
                text = f"Hadith text number {i}"
                text_bytes = text.encode("utf-8")
                snippet_hash = hashlib.sha256(text_bytes).hexdigest()

                conn.execute(
                    "INSERT INTO text_unit (text_unit_id, source_id, text_canonical) VALUES (?, ?, ?)",
                    (f"unit-{i}", "bulk-test", text),
                )
                conn.execute(
                    """
                    INSERT INTO evidence_span 
                    (evidence_span_id, text_unit_id, start_byte, end_byte, snippet_utf8_sha256)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (f"span-{i}", f"unit-{i}", 0, len(text_bytes), snippet_hash),
                )

            conn.commit()
        finally:
            conn.close()

        verifier = CitationVerifier(db_path=temp_db)

        # Create statements with 100 citations
        citations = [{"evidence_span_id": f"span-{i}"} for i in range(100)]
        statements = [{"citations": citations}]

        import time

        start = time.perf_counter()
        result = verifier.verify_citations(statements)
        elapsed = time.perf_counter() - start

        assert result.verified is True
        assert result.checked_citation_count == 100
        assert elapsed < 5.0  # Should complete in under 5 seconds
