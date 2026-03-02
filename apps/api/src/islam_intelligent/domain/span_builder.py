"""EvidenceSpan builder for precise text citation with byte-level integrity.

This module provides utilities for creating EvidenceSpan records that can
cite exact byte ranges within TextUnit documents. Each span includes:
- UTF-8 byte offsets (not character offsets)
- SHA-256 hash of the cited text for integrity verification
- Context prefix/suffix for human verification

Key Design Decisions:
    1. Byte offsets, not character offsets - Unicode characters vary in byte length
    2. Hash verification - every span can be cryptographically verified
    3. Context extraction - prefix/suffix help humans verify the citation

References:
    - Unicode source spans: https://totbwf.github.io/posts/unicode-source-spans.html
    - UTF-8 encoding: https://tools.ietf.org/html/rfc3629
"""

import hashlib
from typing import Optional


def extract_snippet(text: str, start_byte: int, end_byte: int) -> str:
    """Extract text snippet using UTF-8 byte offsets.

    Args:
        text: The source text (NFC normalized)
        start_byte: Starting byte offset (inclusive)
        end_byte: Ending byte offset (exclusive)

    Returns:
        The extracted snippet as a string

    Raises:
        ValueError: If byte offsets are invalid

    Example:
        >>> text = "Hello, 世界"  # '世' is 3 bytes in UTF-8
        >>> extract_snippet(text, 7, 13)  # Extract "世界"
        '世界'
    """
    text_bytes = text.encode("utf-8")

    if start_byte < 0:
        raise ValueError(f"start_byte must be >= 0, got {start_byte}")
    if end_byte > len(text_bytes):
        raise ValueError(
            f"end_byte ({end_byte}) exceeds text length ({len(text_bytes)})"
        )
    if start_byte >= end_byte:
        raise ValueError(f"start_byte ({start_byte}) must be < end_byte ({end_byte})")

    snippet_bytes = text_bytes[start_byte:end_byte]
    return snippet_bytes.decode("utf-8")


def compute_snippet_hash(snippet: str) -> str:
    """Compute SHA-256 hash of a text snippet.

    The hash is computed from the UTF-8 encoded bytes of the snippet.

    Args:
        snippet: The text snippet to hash

    Returns:
        64-character hexadecimal SHA-256 hash

    Example:
        >>> compute_snippet_hash("Hello")
        '185f8db32271fe25f561a6fc938b2e264306ec304eda518007d1764826381969'
    """
    snippet_bytes = snippet.encode("utf-8")
    return hashlib.sha256(snippet_bytes).hexdigest()


def get_prefix_suffix(
    text: str, start_byte: int, end_byte: int, context: int = 50
) -> tuple[str, str]:
    """Extract prefix and suffix context around a span.

    Args:
        text: The source text
        start_byte: Starting byte offset of the span
        end_byte: Ending byte offset of the span
        context: Number of bytes to include before/after (default: 50)

    Returns:
        Tuple of (prefix, suffix) strings

    Example:
        >>> text = "The quick brown fox jumps over the lazy dog"
        >>> get_prefix_suffix(text, 10, 19)  # "brown fox"
        ('The quick ', ' jumps over the lazy dog')
    """
    text_bytes = text.encode("utf-8")

    # Calculate byte ranges for prefix and suffix
    prefix_start = max(0, start_byte - context)
    prefix_end = start_byte
    suffix_start = end_byte
    suffix_end = min(len(text_bytes), end_byte + context)

    # Extract bytes and decode
    prefix_bytes = text_bytes[prefix_start:prefix_end]
    suffix_bytes = text_bytes[suffix_start:suffix_end]

    # Handle decode errors gracefully (truncated multi-byte sequences)
    prefix = prefix_bytes.decode("utf-8", errors="ignore")
    suffix = suffix_bytes.decode("utf-8", errors="ignore")

    return prefix, suffix


def create_span(
    text_unit_id: str,
    start_byte: int,
    end_byte: int,
    text_unit_text: str,
) -> dict:
    """Create an EvidenceSpan record with integrity verification.

    Args:
        text_unit_id: UUID of the parent TextUnit
        start_byte: Starting byte offset (inclusive)
        end_byte: Ending byte offset (exclusive)
        text_unit_text: The full text of the TextUnit for hash computation

    Returns:
        Complete EvidenceSpan record ready for database insertion

    Raises:
        ValueError: If byte offsets are invalid or out of bounds

    Example:
        >>> span = create_span(
        ...     text_unit_id="abc123",
        ...     start_byte=10,
        ...     end_byte=20,
        ...     text_unit_text="The quick brown fox jumps...",
        ... )
        >>> span["snippet_text"]
        'brown fox '
        >>> len(span["snippet_hash"])
        64
    """
    # Extract the snippet using byte offsets
    snippet_text = extract_snippet(text_unit_text, start_byte, end_byte)

    # Compute hash of the snippet
    snippet_hash = compute_snippet_hash(snippet_text)

    # Get context for verification
    prefix, suffix = get_prefix_suffix(text_unit_text, start_byte, end_byte)

    # Build the span record
    span = {
        "text_unit_id": text_unit_id,
        "start_byte": start_byte,
        "end_byte": end_byte,
        "snippet_text": snippet_text,
        "snippet_hash": snippet_hash,
        "prefix": prefix,
        "suffix": suffix,
    }

    return span


def validate_span(span: dict, text_unit_text: str) -> bool:
    """Validate an EvidenceSpan against its source text.

    Verifies:
    1. Byte offsets are within bounds
    2. Extracted snippet matches stored snippet_text
    3. Computed hash matches stored snippet_hash

    Args:
        span: The EvidenceSpan record to validate
        text_unit_text: The full text of the parent TextUnit

    Returns:
        True if span is valid, False otherwise

    Example:
        >>> span = create_span("abc", 0, 5, "Hello World")
        >>> validate_span(span, "Hello World")
        True
        >>> validate_span(span, "Different text")
        False
    """
    try:
        start_byte = span["start_byte"]
        end_byte = span["end_byte"]
        stored_snippet = span["snippet_text"]
        stored_hash = span["snippet_hash"]

        # Verify byte offsets are valid
        text_bytes = text_unit_text.encode("utf-8")
        if start_byte < 0 or end_byte > len(text_bytes) or start_byte >= end_byte:
            return False

        # Extract current snippet and verify it matches
        current_snippet = extract_snippet(text_unit_text, start_byte, end_byte)
        if current_snippet != stored_snippet:
            return False

        # Compute hash and verify it matches
        current_hash = compute_snippet_hash(current_snippet)
        if current_hash != stored_hash:
            return False

        return True

    except (KeyError, ValueError, UnicodeDecodeError):
        return False


def verify_span_hash(span: dict, text_unit_text: str) -> tuple[bool, Optional[str]]:
    """Verify only the hash of a span against source text.

    This is a lighter-weight check than full validation - it only
    recomputes and compares the hash, not the full snippet extraction.

    Args:
        span: The EvidenceSpan record
        text_unit_text: The full text of the parent TextUnit

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if hash matches
        - error_message: None if valid, description of mismatch if invalid

    Example:
        >>> span = create_span("abc", 0, 5, "Hello World")
        >>> verify_span_hash(span, "Hello World")
        (True, None)
        >>> verify_span_hash(span, "Different")
        (False, 'Hash mismatch: stored=... computed=...')
    """
    try:
        start_byte = span["start_byte"]
        end_byte = span["end_byte"]
        stored_hash = span["snippet_hash"]

        # Extract snippet and compute hash
        current_snippet = extract_snippet(text_unit_text, start_byte, end_byte)
        current_hash = compute_snippet_hash(current_snippet)

        if current_hash != stored_hash:
            return (
                False,
                f"Hash mismatch: stored={stored_hash[:16]}..., computed={current_hash[:16]}...",
            )

        return True, None

    except ValueError as e:
        return False, f"Invalid span: {e}"
    except KeyError as e:
        return False, f"Missing field in span: {e}"


# Convenience exports
__all__ = [
    "create_span",
    "validate_span",
    "verify_span_hash",
    "extract_snippet",
    "compute_snippet_hash",
    "get_prefix_suffix",
]
