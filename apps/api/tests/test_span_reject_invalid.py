"""Tests for EvidenceSpan validation and rejection of invalid inputs.

Covers:
- Rejecting negative start_byte
- Rejecting end_byte exceeding text length
- Rejecting start_byte >= end_byte
- Rejecting hash mismatches

These tests ensure the span builder properly validates all inputs
and fails gracefully with descriptive error messages.
"""

import pytest

from islam_intelligent.domain.span_builder import (
    create_span,
    validate_span,
    verify_span_hash,
    extract_snippet,
    compute_snippet_hash,
)


class TestRejectNegativeStartByte:
    """Tests for rejecting negative start_byte values."""

    def test_create_span_rejects_negative_start(self):
        """Should reject negative start_byte."""
        with pytest.raises(ValueError) as exc_info:
            create_span(
                text_unit_id="test_001",
                start_byte=-1,
                end_byte=5,
                text_unit_text="Hello World",
            )
        assert "start_byte" in str(exc_info.value).lower()
        assert ">= 0" in str(exc_info.value)

    def test_extract_snippet_rejects_negative_start(self):
        """extract_snippet should reject negative start_byte."""
        with pytest.raises(ValueError) as exc_info:
            extract_snippet("Hello World", -5, 5)
        assert "start_byte" in str(exc_info.value).lower()


class TestRejectEndByteExceedsLength:
    """Tests for rejecting end_byte that exceeds text length."""

    def test_create_span_rejects_end_byte_too_large(self):
        """Should reject end_byte exceeding text length."""
        text = "Hello"  # 5 bytes in UTF-8
        with pytest.raises(ValueError) as exc_info:
            create_span(
                text_unit_id="test_002",
                start_byte=0,
                end_byte=10,
                text_unit_text=text,
            )
        assert "end_byte" in str(exc_info.value).lower()
        assert "exceeds" in str(exc_info.value).lower()

    def test_create_span_rejects_end_byte_at_exact_length_plus_one(self):
        """Should accept end_byte at exact text length but reject beyond."""
        text = "Hello"  # 5 bytes

        # This should work (end_byte == length)
        span = create_span(
            text_unit_id="test_ok",
            start_byte=0,
            end_byte=5,
            text_unit_text=text,
        )
        assert span["snippet_text"] == "Hello"

        # This should fail (end_byte > length)
        with pytest.raises(ValueError):
            create_span(
                text_unit_id="test_fail",
                start_byte=0,
                end_byte=6,
                text_unit_text=text,
            )

    def test_extract_snippet_rejects_end_byte_too_large(self):
        """extract_snippet should reject end_byte exceeding text length."""
        with pytest.raises(ValueError) as exc_info:
            extract_snippet("Hi", 0, 100)
        assert "end_byte" in str(exc_info.value).lower()

    def test_unicode_text_length_check(self):
        """Should correctly calculate byte length for Unicode text."""
        text = "世界"  # Each char is 3 bytes, total 6 bytes

        # end_byte=6 is valid (exact length)
        span = create_span(
            text_unit_id="test_unicode",
            start_byte=0,
            end_byte=6,
            text_unit_text=text,
        )
        assert span["snippet_text"] == "世界"

        # end_byte=7 is invalid
        with pytest.raises(ValueError) as exc_info:
            create_span(
                text_unit_id="test_unicode_fail",
                start_byte=0,
                end_byte=7,
                text_unit_text=text,
            )
        assert "7" in str(exc_info.value)
        assert "6" in str(exc_info.value)  # Length shown


class TestRejectInvalidByteRange:
    """Tests for rejecting start_byte >= end_byte."""

    def test_create_span_rejects_start_equals_end(self):
        """Should reject start_byte equal to end_byte."""
        with pytest.raises(ValueError) as exc_info:
            create_span(
                text_unit_id="test_003",
                start_byte=5,
                end_byte=5,
                text_unit_text="Hello World",
            )
        assert "start_byte" in str(exc_info.value).lower()
        assert "end_byte" in str(exc_info.value).lower()

    def test_create_span_rejects_start_greater_than_end(self):
        """Should reject start_byte greater than end_byte."""
        with pytest.raises(ValueError) as exc_info:
            create_span(
                text_unit_id="test_004",
                start_byte=10,
                end_byte=5,
                text_unit_text="Hello World",
            )
        assert "start_byte" in str(exc_info.value).lower()
        assert "end_byte" in str(exc_info.value).lower()

    def test_extract_snippet_rejects_invalid_range(self):
        """extract_snippet should reject invalid byte ranges."""
        with pytest.raises(ValueError) as exc_info:
            extract_snippet("Hello", 3, 3)  # Equal
        assert "<" in str(exc_info.value)  # Should mention less than

        with pytest.raises(ValueError):
            extract_snippet("Hello", 4, 2)  # Reversed


class TestRejectHashMismatch:
    """Tests for detecting and rejecting hash mismatches."""

    def test_validate_span_detects_modified_text(self):
        """validate_span should return False if text is modified."""
        original_text = "The quick brown fox"
        span = create_span(
            text_unit_id="test_005",
            start_byte=4,
            end_byte=9,
            text_unit_text=original_text,
        )

        # Verify against modified text
        modified_text = "The QUICK brown fox"
        assert validate_span(span, modified_text) is False

    def test_validate_span_detects_truncated_text(self):
        """validate_span should return False if text is truncated."""
        original_text = "The quick brown fox jumps"
        span = create_span(
            text_unit_id="test_006",
            start_byte=10,
            end_byte=19,
            text_unit_text=original_text,
        )

        # Verify against truncated text
        truncated_text = "The quick"
        assert validate_span(span, truncated_text) is False

    def test_verify_span_hash_reports_mismatch(self):
        """verify_span_hash should report hash mismatch details."""
        original_text = "Original text content"
        span = create_span(
            text_unit_id="test_007",
            start_byte=0,
            end_byte=8,
            text_unit_text=original_text,
        )

        is_valid, message = verify_span_hash(span, "Modified content")
        assert is_valid is False
        assert message is not None
        assert "Hash mismatch" in message

    def test_validate_span_with_corrupt_span_dict(self):
        """validate_span should handle corrupt span dictionaries."""
        # Missing required fields
        corrupt_span = {
            "start_byte": 0,
            "end_byte": 5,
        }  # Missing snippet_text, snippet_hash

        result = validate_span(corrupt_span, "Some text")
        assert result is False

    def test_validate_span_with_empty_span(self):
        """validate_span should handle empty span dictionary."""
        result = validate_span({}, "Some text")
        assert result is False


class TestInvalidByteOffsetsInMiddleOfMultiByteChar:
    """Tests for byte offsets that split multi-byte UTF-8 characters."""

    def test_create_span_may_accept_mid_char_boundary(self):
        """Byte offsets in middle of multi-byte char will cause decode error."""
        text = "日本語"  # Each char is 3 bytes

        # Offset 1 is in the middle of first character
        # This will cause a decode error when trying to extract
        with pytest.raises(UnicodeDecodeError):
            create_span(
                text_unit_id="test_mid",
                start_byte=1,
                end_byte=3,
                text_unit_text=text,
            )

    def test_validate_span_handles_decode_error(self):
        """validate_span should return False on decode errors."""
        # Create a valid span first
        text = "日本語"
        span = create_span(
            text_unit_id="test_decode",
            start_byte=0,
            end_byte=3,
            text_unit_text=text,
        )

        # Tamper with start_byte to point to middle of multi-byte char
        span["start_byte"] = 1

        # Should return False (not raise)
        result = validate_span(span, text)
        assert result is False


class TestBoundaryConditions:
    """Tests for boundary conditions and edge cases."""

    def test_empty_string_rejected(self):
        """Should handle empty string appropriately."""
        # start_byte=0, end_byte=0 is invalid (start >= end)
        with pytest.raises(ValueError):
            create_span(
                text_unit_id="test_empty",
                start_byte=0,
                end_byte=0,
                text_unit_text="",
            )

    def test_single_character_span(self):
        """Should allow single character spans."""
        text = "A"
        span = create_span(
            text_unit_id="test_single",
            start_byte=0,
            end_byte=1,
            text_unit_text=text,
        )
        assert span["snippet_text"] == "A"

    def test_whole_text_span(self):
        """Should allow span covering entire text."""
        text = "Complete text"
        text_bytes = text.encode("utf-8")
        span = create_span(
            text_unit_id="test_whole",
            start_byte=0,
            end_byte=len(text_bytes),
            text_unit_text=text,
        )
        assert span["snippet_text"] == text

    def test_span_at_exact_byte_boundary(self):
        """Should handle spans at exact byte boundaries."""
        text = "ABC日本語"  # ABC = 3 bytes, each kanji = 3 bytes

        # Span just the ASCII portion
        span1 = create_span(
            text_unit_id="test_ascii",
            start_byte=0,
            end_byte=3,
            text_unit_text=text,
        )
        assert span1["snippet_text"] == "ABC"

        # Span just the kanji portion
        span2 = create_span(
            text_unit_id="test_kanji",
            start_byte=3,
            end_byte=12,
            text_unit_text=text,
        )
        assert span2["snippet_text"] == "日本語"


class TestErrorMessageQuality:
    """Tests for quality and helpfulness of error messages."""

    def test_error_includes_actual_values(self):
        """Error messages should include actual invalid values."""
        with pytest.raises(ValueError) as exc_info:
            create_span(
                text_unit_id="test",
                start_byte=-5,
                end_byte=10,
                text_unit_text="Hello",
            )
        error_msg = str(exc_info.value)
        assert "-5" in error_msg  # Actual value shown

    def test_error_includes_text_length(self):
        """Error for exceeding length should show actual text length."""
        text = "Hi"  # 2 bytes
        with pytest.raises(ValueError) as exc_info:
            create_span(
                text_unit_id="test",
                start_byte=0,
                end_byte=100,
                text_unit_text=text,
            )
        error_msg = str(exc_info.value)
        assert "100" in error_msg  # Requested end_byte
        assert "2" in error_msg  # Actual length


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
