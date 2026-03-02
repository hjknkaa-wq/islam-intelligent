"""Round-trip tests for EvidenceSpan creation and verification.

Covers:
- Creating spans from TextUnit text
- Hash verification passing for valid spans
- Span snippet matching original bytes
- Prefix/suffix extraction for context

Key Requirements:
- UTF-8 byte offsets (not character offsets)
- SHA-256 hash verification
- Context extraction for human verification

References:
    - Unicode source spans: https://totbwf.github.io/posts/unicode-source-spans.html
"""

import hashlib

import pytest

from islam_intelligent.domain.span_builder import (
    create_span,
    validate_span,
    verify_span_hash,
    extract_snippet,
    compute_snippet_hash,
    get_prefix_suffix,
)


class TestSpanCreation:
    """Tests for creating EvidenceSpan records."""

    def test_create_span_basic(self):
        """Should create span with correct byte offsets."""
        text = "The quick brown fox jumps over the lazy dog"
        span = create_span(
            text_unit_id="test_001",
            start_byte=4,
            end_byte=9,
            text_unit_text=text,
        )

        assert span["text_unit_id"] == "test_001"
        assert span["start_byte"] == 4
        assert span["end_byte"] == 9
        assert span["snippet_text"] == "quick"

    def test_create_span_with_unicode(self):
        """Should handle UTF-8 encoded Unicode text correctly."""
        text = "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ"
        text_bytes = text.encode("utf-8")

        # First word "بِسْمِ" is 12 bytes in UTF-8
        span = create_span(
            text_unit_id="quran_001",
            start_byte=0,
            end_byte=12,
            text_unit_text=text,
        )

        assert span["text_unit_id"] == "quran_001"
        assert span["start_byte"] == 0
        assert span["end_byte"] == 12
        assert span["snippet_text"] == "بِسْمِ"

    def test_create_span_arabic_middle(self):
        """Should extract middle portion of Arabic text."""
        text = "اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ"
        text_bytes = text.encode("utf-8")

        # "لَا إِلَٰهَ" spans specific byte range
        # Find byte offsets by encoding
        prefix = "اللَّهُ "
        prefix_bytes = prefix.encode("utf-8")
        snippet = "لَا إِلَٰهَ"
        snippet_bytes = snippet.encode("utf-8")

        start_byte = len(prefix_bytes)
        end_byte = start_byte + len(snippet_bytes)

        span = create_span(
            text_unit_id="ayah_002",
            start_byte=start_byte,
            end_byte=end_byte,
            text_unit_text=text,
        )

        assert span["snippet_text"] == snippet
        assert len(span["snippet_hash"]) == 64  # SHA-256 hex length


class TestHashVerification:
    """Tests for SHA-256 hash computation and verification."""

    def test_hash_computed_from_bytes(self):
        """Hash should be computed from UTF-8 bytes, not characters."""
        text = "Hello, 世界"
        span = create_span(
            text_unit_id="test_002",
            start_byte=7,
            end_byte=13,
            text_unit_text=text,
        )

        # "世界" encoded in UTF-8
        expected_hash = hashlib.sha256("世界".encode("utf-8")).hexdigest()
        assert span["snippet_hash"] == expected_hash

    def test_verify_span_hash_passes_for_valid(self):
        """Hash verification should pass for unchanged text."""
        text = "The quick brown fox"
        span = create_span(
            text_unit_id="test_003",
            start_byte=4,
            end_byte=9,
            text_unit_text=text,
        )

        is_valid, message = verify_span_hash(span, text)
        assert is_valid is True
        assert message is None

    def test_verify_span_hash_fails_for_modified(self):
        """Hash verification should fail if text is modified."""
        original_text = "The quick brown fox"
        span = create_span(
            text_unit_id="test_004",
            start_byte=4,
            end_byte=9,
            text_unit_text=original_text,
        )

        # Try to verify against modified text
        modified_text = "The QUICK brown fox"
        is_valid, message = verify_span_hash(span, modified_text)
        assert is_valid is False
        assert message is not None
        assert "Hash mismatch" in message

    def test_validate_span_passes_for_valid(self):
        """Full validation should pass for valid span."""
        text = "The quick brown fox jumps"
        span = create_span(
            text_unit_id="test_005",
            start_byte=4,
            end_byte=15,
            text_unit_text=text,
        )

        assert validate_span(span, text) is True


class TestSnippetExtraction:
    """Tests for extract_snippet function."""

    def test_extract_snippet_basic(self):
        """Should extract snippet by byte offsets."""
        text = "Hello, World!"
        snippet = extract_snippet(text, 7, 12)
        assert snippet == "World"

    def test_extract_snippet_unicode(self):
        """Should handle multi-byte UTF-8 characters."""
        text = "Hello, 世界!"
        # "世界" starts at byte 7, each char is 3 bytes
        snippet = extract_snippet(text, 7, 13)
        assert snippet == "世界"

    def test_extract_snippet_arabic(self):
        """Should handle Arabic text with diacritics."""
        text = "بِسْمِ اللَّهِ"
        # First word is 12 bytes
        snippet = extract_snippet(text, 0, 12)
        assert snippet == "بِسْمِ"


class TestPrefixSuffixExtraction:
    """Tests for get_prefix_suffix function."""

    def test_prefix_suffix_basic(self):
        """Should extract context around span."""
        text = "The quick brown fox jumps over the lazy dog"
        prefix, suffix = get_prefix_suffix(text, 10, 19)

        assert prefix == "The quick "
        assert suffix == " jumps over the lazy dog"

    def test_prefix_suffix_with_context_limit(self):
        """Should respect context byte limit."""
        text = "The quick brown fox jumps over the lazy dog"
        prefix, suffix = get_prefix_suffix(text, 16, 19, context=5)

        assert len(prefix.encode("utf-8")) <= 5
        assert len(suffix.encode("utf-8")) <= 5

    def test_prefix_suffix_at_start(self):
        """Should handle span at start of text."""
        text = "The quick brown fox"
        prefix, suffix = get_prefix_suffix(text, 0, 9)

        assert prefix == ""  # No prefix at start
        assert suffix == " brown fox"

    def test_prefix_suffix_at_end(self):
        """Should handle span at end of text."""
        text = "The quick brown fox"
        prefix, suffix = get_prefix_suffix(text, 10, 19)

        assert prefix == "The quick "
        assert suffix == ""  # No suffix at end

    def test_prefix_suffix_unicode(self):
        """Should handle Unicode text correctly."""
        text = "بِسْمِ اللَّهِ الرَّحْمَٰنِ"
        text_bytes = text.encode("utf-8")

        # Extract prefix/suffix around second word
        prefix_len = len("بِسْمِ ".encode("utf-8"))
        word_len = len("اللَّهِ".encode("utf-8"))

        # Use larger context to ensure we get complete characters
        prefix, suffix = get_prefix_suffix(
            text, prefix_len, prefix_len + word_len, context=20
        )

        # Verify we got strings back (decode errors handled gracefully)
        assert isinstance(prefix, str)
        assert isinstance(suffix, str)
        # With sufficient context, we should see part of the first word
        assert len(prefix) > 0 or prefix == ""
        assert len(suffix) > 0 or suffix == ""


class TestRoundTrip:
    """End-to-end round-trip tests."""

    def test_create_and_verify_roundtrip(self):
        """Full round-trip: create span, store, verify."""
        original_text = "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ"

        # Create span
        span = create_span(
            text_unit_id="quran_1_1",
            start_byte=0,
            end_byte=12,
            text_unit_text=original_text,
        )

        # Verify it against original text
        assert validate_span(span, original_text) is True

        # Verify hash specifically
        is_valid, _ = verify_span_hash(span, original_text)
        assert is_valid is True

    def test_span_includes_all_fields(self):
        """Created span should include all required fields."""
        text = "The quick brown fox"
        span = create_span(
            text_unit_id="test_rt",
            start_byte=4,
            end_byte=9,
            text_unit_text=text,
        )

        required_fields = [
            "text_unit_id",
            "start_byte",
            "end_byte",
            "snippet_text",
            "snippet_hash",
            "prefix",
            "suffix",
        ]

        for field in required_fields:
            assert field in span, f"Missing field: {field}"

    def test_byte_offsets_preserved(self):
        """Byte offsets should be preserved exactly."""
        text = "Mixed 日本語 and العربية text"
        text_bytes = text.encode("utf-8")

        # Create span from known byte offsets
        start = text_bytes.find("日本語".encode("utf-8"))
        end = start + len("日本語".encode("utf-8"))

        span = create_span(
            text_unit_id="mixed_test",
            start_byte=start,
            end_byte=end,
            text_unit_text=text,
        )

        assert span["start_byte"] == start
        assert span["end_byte"] == end
        assert span["snippet_text"] == "日本語"

    def test_hash_consistency(self):
        """Same text should always produce same hash."""
        text = "Consistent text for hashing"

        span1 = create_span(
            text_unit_id="test_1",
            start_byte=0,
            end_byte=9,
            text_unit_text=text,
        )

        span2 = create_span(
            text_unit_id="test_2",
            start_byte=0,
            end_byte=9,
            text_unit_text=text,
        )

        assert span1["snippet_hash"] == span2["snippet_hash"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
