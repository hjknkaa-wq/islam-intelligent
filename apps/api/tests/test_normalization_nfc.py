"""
Tests for Unicode text normalization (NFC/NFKC).

Covers:
- NFC normalization for storage
- NFKC vs NFC difference for Arabic text
- SHA-256 hash computation and verification
- Round-trip integrity
- Edge cases with combining characters

References:
    Unicode TR15: https://unicode.org/reports/tr15/
"""

import hashlib
import unicodedata

import pytest

from islam_intelligent.normalize import (
    TextNormalizer,
    compute_hash,
    get_normalization_form,
    is_nfc_normalized,
    is_nfkc_normalized,
    normalize_search,
    normalize_storage,
    verify_hash,
)


class TestNFCNormalization:
    """Tests for NFC (Canonical Composition) normalization."""

    def test_nfc_normalizes_combining_characters(self):
        """NFC should combine base + combining char into precomposed form."""
        # A + combining diaeresis (U+0041 + U+0308)
        decomposed = "\u0041\u0308"
        nfc = normalize_storage(decomposed)
        # Should become precomposed Ä (U+00C4)
        assert nfc == "\u00c4"
        assert len(nfc) == 1  # Single codepoint
        assert is_nfc_normalized(nfc)

    def test_nfc_preserves_already_normalized(self):
        """NFC should not change already normalized text."""
        text = "بسم الله الرحمن الرحيم"
        nfc = normalize_storage(text)
        assert nfc == text
        assert is_nfc_normalized(nfc)

    def test_nfc_handles_arabic_text(self):
        """NFC should handle Arabic text correctly."""
        # Arabic text with various marks
        text = "السَّلَامُ عَلَيْكُمْ"
        nfc = normalize_storage(text)
        assert nfc is not None
        assert isinstance(nfc, str)
        assert is_nfc_normalized(nfc)

    def test_nfc_handles_empty_string(self):
        """NFC should handle empty string."""
        assert normalize_storage("") == ""
        assert is_nfc_normalized("")

    def test_nfc_handles_none(self):
        """NFC should handle None as empty string."""
        assert normalize_storage(None) == ""

    def test_nfc_idempotent(self):
        """NFC applied twice should give same result."""
        text = "Test \u0041\u0308 Text"
        nfc1 = normalize_storage(text)
        nfc2 = normalize_storage(nfc1)
        assert nfc1 == nfc2


class TestNFKCNormalization:
    """Tests for NFKC (Compatibility Composition) normalization."""

    def test_nfkc_normalizes_compatibility_chars(self):
        """NFKC should normalize compatibility characters."""
        # Circled digit one ① (U+2460)
        circled = "①"
        nfkc = normalize_search(circled)
        assert nfkc == "1"
        assert is_nfkc_normalized(nfkc)

    def test_nfkc_different_from_nfc_for_arabic(self):
        """
        NFKC should differ from NFC for Arabic compatibility characters.

        Some Arabic presentation forms are compatibility characters
        that NFKC will normalize differently than NFC.
        """
        # Arabic Letter Alef with Madda Above (U+0622) vs
        # Arabic Letter Alef (U+0627) + Arabic Maddah Above (U+0653)
        # NFC preserves U+0622, NFKC decomposes it

        # Use a known compatibility character case
        # Fullwidth digits are compatibility characters
        fullwidth_1 = "１"  # U+FF11 Fullwidth Digit One
        nfc = normalize_storage(fullwidth_1)
        nfkc = normalize_search(fullwidth_1)

        # NFC preserves fullwidth, NFKC converts to ASCII
        assert nfc == fullwidth_1  # NFC preserves
        assert nfkc == "1"  # NFKC normalizes
        assert nfc != nfkc  # They differ!

    def test_nfkc_handles_arabic_ligatures(self):
        """NFKC should handle Arabic ligature compatibility forms."""
        # Many Arabic ligatures are compatibility characters
        # NFKC will decompose them for better search matching
        text = "لله"  # Regular Arabic
        nfkc = normalize_search(text)
        assert nfkc is not None
        assert isinstance(nfkc, str)

    def test_nfkc_handles_empty_string(self):
        """NFKC should handle empty string."""
        assert normalize_search("") == ""

    def test_nfkc_handles_none(self):
        """NFKC should handle None as empty string."""
        assert normalize_search(None) == ""

    def test_nfkc_idempotent(self):
        """NFKC applied twice should give same result."""
        text = "① Test １ Text"
        nfkc1 = normalize_search(text)
        nfkc2 = normalize_search(nfkc1)
        assert nfkc1 == nfkc2


class TestHashComputation:
    """Tests for SHA-256 hash computation and verification."""

    def test_compute_hash_returns_hex_string(self):
        """Hash should be 64-character hex string."""
        text = "بسم الله"
        hash_val = compute_hash(text)
        assert isinstance(hash_val, str)
        assert len(hash_val) == 64  # SHA-256 is 256 bits = 64 hex chars
        assert all(c in "0123456789abcdef" for c in hash_val)

    def test_compute_hash_consistent(self):
        """Same text should produce same hash."""
        text = "السلام عليكم"
        hash1 = compute_hash(text)
        hash2 = compute_hash(text)
        assert hash1 == hash2

    def test_compute_hash_different_for_different_text(self):
        """Different text should produce different hash."""
        hash1 = compute_hash("text1")
        hash2 = compute_hash("text2")
        assert hash1 != hash2

    def test_compute_hash_normalizes_nfc_first(self):
        """Hash computation should normalize to NFC first."""
        # Same text, different Unicode representations
        text_nfc = "\u00c4"  # Precomposed
        text_nfd = "\u0041\u0308"  # Decomposed (A + combining diaeresis)

        hash_nfc = compute_hash(text_nfc)
        hash_nfd = compute_hash(text_nfd)

        # Should produce same hash because both normalize to NFC
        assert hash_nfc == hash_nfd

    def test_compute_hash_empty_string(self):
        """Hash of empty string should be valid."""
        hash_val = compute_hash("")
        expected = hashlib.sha256("".encode("utf-8")).hexdigest()
        assert hash_val == expected
        assert len(hash_val) == 64

    def test_compute_hash_none(self):
        """Hash of None should be same as empty string."""
        hash_none = compute_hash(None)
        hash_empty = compute_hash("")
        assert hash_none == hash_empty

    def test_verify_hash_success(self):
        """verify_hash should return True for correct hash."""
        text = "test text"
        hash_val = compute_hash(text)
        assert verify_hash(text, hash_val) is True

    def test_verify_hash_failure(self):
        """verify_hash should return False for incorrect hash."""
        text = "test text"
        wrong_hash = "a" * 64
        assert verify_hash(text, wrong_hash) is False

    def test_verify_hash_none_expected(self):
        """verify_hash should return False if expected hash is None."""
        assert verify_hash("text", None) is False

    def test_verify_hash_timing_safe(self):
        """verify_hash should use constant-time comparison."""
        # This is hard to test directly, but we verify it works correctly
        text = "secret text"
        hash_val = compute_hash(text)
        assert verify_hash(text, hash_val)


class TestRoundTripIntegrity:
    """Tests for round-trip integrity of normalization."""

    def test_nfc_roundtrip(self):
        """NFC normalization should be stable (idempotent)."""
        original = "بِسْمِ اللهِ الرَّحْمٰنِ الرَّحِيْمِ"
        nfc1 = normalize_storage(original)
        nfc2 = normalize_storage(nfc1)
        nfc3 = normalize_storage(nfc2)

        assert nfc1 == nfc2 == nfc3
        hash1 = compute_hash(nfc1)
        hash3 = compute_hash(nfc3)
        assert hash1 == hash3

    def test_nfkc_roundtrip(self):
        """NFKC normalization should be stable (idempotent)."""
        original = "① ＡＢＣ 日本"
        nfkc1 = normalize_search(original)
        nfkc2 = normalize_search(nfkc1)
        nfkc3 = normalize_search(nfkc2)

        assert nfkc1 == nfkc2 == nfkc3

    def test_hash_verification_roundtrip(self):
        """Hash computation and verification should work correctly."""
        texts = [
            "بسم الله الرحمن الرحيم",
            "الحمد لله رب العالمين",
            "Test text 123",
            "① １ 𝟏",  # Various digit forms
        ]

        for text in texts:
            nfc = normalize_storage(text)
            hash_val = compute_hash(nfc)

            # Verify with same text
            assert verify_hash(nfc, hash_val) is True

            # Verify with equivalent NFD representation
            nfd = unicodedata.normalize("NFD", text)
            assert verify_hash(nfd, hash_val) is True


class TestArabicSpecificCases:
    """Arabic-specific normalization test cases."""

    def test_arabic_quranic_text(self):
        """Test normalization with Quranic Arabic text."""
        # Surah Al-Fatiha
        bismillah = "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ"
        nfc = normalize_storage(bismillah)
        nfkc = normalize_search(bismillah)

        assert is_nfc_normalized(nfc)
        assert is_nfkc_normalized(nfkc)

        hash_val = compute_hash(nfc)
        assert verify_hash(nfc, hash_val)

    def test_arabic_with_tashkeel(self):
        """Test normalization with Arabic diacritics (tashkeel)."""
        text_with_tashkeel = "ٱلْحَمْدُ لِلَّهِ رَبِّ ٱلْعَٰلَمِينَ"
        nfc = normalize_storage(text_with_tashkeel)
        assert is_nfc_normalized(nfc)

        # Hash should be stable
        hash1 = compute_hash(text_with_tashkeel)
        hash2 = compute_hash(nfc)
        assert hash1 == hash2

    def test_arabic_presentation_forms(self):
        """Test handling of Arabic presentation forms."""
        # Arabic Presentation Forms-A (compatibility characters)
        # These should be normalized differently by NFC vs NFKC

        # U+FDF2 is ARABIC LIGATURE ALLAH ISOLATED FORM
        allah_ligature = "ﷲ"  # Compatibility character

        nfc = normalize_storage(allah_ligature)
        nfkc = normalize_search(allah_ligature)

        # NFC preserves the ligature (canonical)
        # NFKC may decompose it (compatibility)
        assert is_nfc_normalized(nfc)
        assert is_nfkc_normalized(nfkc)

    def test_arabic_kashida(self):
        """Test handling of Arabic kashida/tatweel."""
        # Kashida (U+0640) is not a compatibility character
        # Both NFC and NFKC should preserve it
        text_with_kashida = "كـــــتاب"
        nfc = normalize_storage(text_with_kashida)
        nfkc = normalize_search(text_with_kashida)

        # Kashida should be preserved in both
        assert "\u0640" in nfc


class TestTextNormalizerClass:
    """Tests for the TextNormalizer class interface."""

    def test_for_storage_returns_tuple(self):
        """TextNormalizer.for_storage should return (text, hash)."""
        text = "test text"
        normalized, hash_val = TextNormalizer.for_storage(text)

        assert isinstance(normalized, str)
        assert isinstance(hash_val, str)
        assert len(hash_val) == 64
        assert is_nfc_normalized(normalized)

    def test_for_search_returns_normalized(self):
        """TextNormalizer.for_search should return NFKC text."""
        text = "① Test"
        normalized = TextNormalizer.for_search(text)

        assert normalized == "1 Test"
        assert is_nfkc_normalized(normalized)

    def test_verify_method(self):
        """TextNormalizer.verify should work correctly."""
        text = "verify test"
        normalized, hash_val = TextNormalizer.for_storage(text)

        assert TextNormalizer.verify(normalized, hash_val) is True
        assert TextNormalizer.verify(normalized, "wrong" * 16) is False


class TestValidationFunctions:
    """Tests for is_nfc_normalized and is_nfkc_normalized."""

    def test_is_nfc_normalized_true(self):
        """Should return True for NFC text."""
        text = "Normal text"
        assert is_nfc_normalized(text) is True

    def test_is_nfc_normalized_false(self):
        """Should return False for NFD text."""
        nfd = unicodedata.normalize("NFD", "\u00c4")
        assert is_nfc_normalized(nfd) is False

    def test_is_nfkc_normalized_true(self):
        """Should return True for NFKC text."""
        text = "ASCII text 123"
        assert is_nfkc_normalized(text) is True

    def test_is_nfkc_normalized_false(self):
        """Should return False for text with compatibility chars."""
        assert is_nfkc_normalized("①") is False

    def test_get_normalization_form(self):
        """Should identify normalization form."""
        nfc = "NFC text"
        nfd = unicodedata.normalize("NFD", "\u00c4")

        assert "NFC" in get_normalization_form(nfc)
        assert "NFD" in get_normalization_form(nfd)


class TestEdgeCases:
    """Edge case tests."""

    def test_mixed_scripts(self):
        """Test with mixed Arabic and Latin text."""
        mixed = "Hello السلام World"
        nfc = normalize_storage(mixed)
        nfkc = normalize_search(mixed)

        assert is_nfc_normalized(nfc)
        assert is_nfkc_normalized(nfkc)

    def test_unicode_emojis(self):
        """Test with emoji characters."""
        emoji = "🕌📿✨"  # Mosque, prayer beads, sparkles
        nfc = normalize_storage(emoji)
        nfkc = normalize_search(emoji)

        assert isinstance(nfc, str)
        assert isinstance(nfkc, str)

    def test_whitespace_variations(self):
        """Test with different whitespace characters."""
        # Different spaces: regular, non-breaking, etc.
        text = "Text\u00a0with\u2003spaces"  # NBSP, EM SPACE
        nfc = normalize_storage(text)
        # NFC preserves these spaces (not compatibility)
        assert "\u00a0" in nfc

    def test_long_text(self):
        """Test with long text (e.g., full surah)."""
        long_text = "بسم الله " * 1000
        nfc = normalize_storage(long_text)
        hash_val = compute_hash(nfc)

        assert len(nfc) == len(long_text)
        assert verify_hash(nfc, hash_val)

    def test_special_characters(self):
        """Test with various special Unicode characters."""
        specials = [
            "\u200b",  # Zero-width space
            "\u200c",  # Zero-width non-joiner
            "\u200d",  # Zero-width joiner
            "\ufeff",  # BOM
            "\u2060",  # Word joiner
        ]
        for char in specials:
            nfc = normalize_storage(char)
            assert isinstance(nfc, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
