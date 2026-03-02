"""
Unicode text normalization for Islamic knowledge base.

NFC (Canonical Decomposition, Canonical Composition) - for storage
NFKC (Compatibility Decomposition, Canonical Composition) - for search indexing

References:
    - Unicode TR15: https://unicode.org/reports/tr15/
    - NFC preserves canonical equivalence
    - NFKC for search to handle compatibility characters

Design principle: Never store NFKC as source-of-truth.
All text_canonical must have SHA-256 hash for integrity.
"""

import hmac
import hashlib
import unicodedata
from typing import Optional
import unicodedata
from typing import Optional


def normalize_storage(text: str) -> str:
    """
    Normalize text for storage using NFC (Canonical Composition).

    NFC is used for storage because it:
    - Preserves canonical equivalence
    - Is the most compact normalized form
    - Maintains visual identity of characters

    Args:
        text: Input text to normalize

    Returns:
        NFC-normalized text

    Example:
        >>> normalize_storage("\u0041\u0308")  # A + combining diaeresis
        'Ä'  # Precomposed form
    """
    if text is None:
        return ""
    return unicodedata.normalize("NFC", text)


def normalize_search(text: str) -> str:
    """
    Normalize text for search indexing using NFKC (Compatibility Composition).

    NFKC is used for search because it:
    - Handles compatibility characters (fullwidth, circled, etc.)
    - Provides better matching for user queries
    - Should NEVER be stored as source-of-truth

    Args:
        text: Input text to normalize

    Returns:
        NFKC-normalized text (for indexing only)

    Example:
        >>> normalize_search("①")  # Circled digit
        '1'  # Compatibility decomposition
    """
    if text is None:
        return ""
    return unicodedata.normalize("NFKC", text)


def compute_hash(text: str) -> str:
    """
    Compute SHA-256 hash of UTF-8 encoded text.

    This provides content-addressable storage and integrity verification.
    Always hash the NFC-normalized text for consistency.

    Args:
        text: Text to hash (should already be NFC-normalized)

    Returns:
        Hex-encoded SHA-256 hash

    Example:
        >>> compute_hash("بسم الله")
        'a3f5c2...'  # 64 character hex string
    """
    if text is None:
        text = ""
    # Always work with NFC for hashing consistency
    normalized = normalize_storage(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def verify_hash(text: str, expected_hash: str) -> bool:
    """
    Verify that text matches the expected SHA-256 hash.

    Args:
        text: Text to verify
        expected_hash: Expected SHA-256 hash (hex string)

    Returns:
        True if hash matches, False otherwise

    Example:
        >>> text = "بسم الله"
        >>> hash_val = compute_hash(text)
        >>> verify_hash(text, hash_val)
        True
    """
    if expected_hash is None:
        return False
    computed = compute_hash(text)
    # Constant-time comparison to prevent timing attacks
    # Constant-time comparison to prevent timing attacks
    return hmac.compare_digest(computed, expected_hash)


def is_nfc_normalized(text: str) -> bool:
    """
    Check if text is already in NFC normalized form.

    Args:
        text: Text to check

    Returns:
        True if text is NFC normalized
    """
    if text is None:
        return True
    return unicodedata.is_normalized("NFC", text)


def is_nfkc_normalized(text: str) -> bool:
    """
    Check if text is already in NFKC normalized form.

    Args:
        text: Text to check

    Returns:
        True if text is NFKC normalized
    """
    if text is None:
        return True
    return unicodedata.is_normalized("NFKC", text)


def get_normalization_form(text: str) -> Optional[str]:
    """
    Determine the normalization form of text.

    Returns:
        'NFC', 'NFKC', 'NFD', 'NFKD', or None if mixed/inconsistent

    Note: Text can be both NFC and NFKC if it contains no
    compatibility characters.
    """
    if text is None:
        return None

    forms = []
    if unicodedata.is_normalized("NFC", text):
        forms.append("NFC")
    if unicodedata.is_normalized("NFKC", text):
        forms.append("NFKC")
    if unicodedata.is_normalized("NFD", text):
        forms.append("NFD")
    if unicodedata.is_normalized("NFKD", text):
        forms.append("NFKD")

    if len(forms) == 1:
        return forms[0]
    elif len(forms) > 1:
        # Multiple forms possible (e.g., ASCII is all forms)
        return "/".join(forms)
    return None


class TextNormalizer:
    """
    High-level normalizer class for managing text normalization workflows.

    Provides a unified interface for storage and search normalization
    with built-in integrity checking.
    """

    @staticmethod
    def for_storage(text: str) -> tuple[str, str]:
        """
        Normalize text for storage and compute hash.

        Returns:
            Tuple of (normalized_text, hash)
        """
        normalized = normalize_storage(text)
        hash_val = compute_hash(normalized)
        return normalized, hash_val

    @staticmethod
    def for_search(text: str) -> str:
        """
        Normalize text for search indexing.

        Returns:
            NFKC-normalized text
        """
        return normalize_search(text)

    @staticmethod
    def verify(normalized_text: str, hash_val: str) -> bool:
        """
        Verify integrity of normalized text.

        Returns:
            True if hash matches
        """
        return verify_hash(normalized_text, hash_val)
