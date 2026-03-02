"""
Unicode text normalization module for Islamic Knowledge Intelligence Platform.

This module provides utilities for normalizing Unicode text according to
Unicode TR15 specifications:
- NFC (Canonical Composition) for storage
- NFKC (Compatibility Composition) for search indexing

Key Functions:
    normalize_storage: Normalize text to NFC for storage
    normalize_search: Normalize text to NFKC for search indexing
    compute_hash: Compute SHA-256 hash of normalized text
    verify_hash: Verify text integrity against hash

Classes:
    TextNormalizer: High-level interface for normalization workflows

Usage:
    from islam_intelligent.normalize import normalize_storage, compute_hash

    text = "بِسْمِ اللهِ الرَّحْمٰنِ الرَّحِيْمِ"
    nfc_text = normalize_storage(text)
    hash_val = compute_hash(nfc_text)

Design Principles:
    1. Storage uses NFC - preserves canonical equivalence
    2. Search uses NFKC - handles compatibility characters
    3. Never store NFKC as source-of-truth
    4. All storage text must have SHA-256 hash for integrity

References:
    Unicode TR15: https://unicode.org/reports/tr15/
"""

from .normalizer import (
    TextNormalizer,
    compute_hash,
    get_normalization_form,
    is_nfc_normalized,
    is_nfkc_normalized,
    normalize_search,
    normalize_storage,
    verify_hash,
)

__all__ = [
    # Core normalization functions
    "normalize_storage",
    "normalize_search",
    # Hash functions
    "compute_hash",
    "verify_hash",
    # Validation functions
    "is_nfc_normalized",
    "is_nfkc_normalized",
    "get_normalization_form",
    # Class interface
    "TextNormalizer",
]

__version__ = "1.0.0"
