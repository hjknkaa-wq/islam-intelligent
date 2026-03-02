"""Tests for TextUnit builder module.

Covers:
- Quran ayah creation with proper canonical ID format
- Hadith item creation with numbering system
- NFC normalization applied to all text
- SHA-256 hash computation and verification
- Canonical ID validation

References:
    - Canonical ID schema: docs/canonical_ids.md
    - Unicode TR15: https://unicode.org/reports/tr15/
"""

import hashlib
import unicodedata

import pytest

from islam_intelligent.ingest.text_unit_builder import (
    build_text_unit,
    create_hadith_item,
    create_quran_ayah,
    validate_canonical_id,
)


class TestQuranAyahCreation:
    """Tests for Quran ayah text_unit creation."""

    def test_quran_ayah_basic_creation(self):
        """Should create Quran ayah with correct canonical ID."""
        unit = create_quran_ayah(
            source_id="src_quran_test",
            surah=1,
            ayah=1,
            text="بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ",
        )

        assert unit["unit_type"] == "quran_ayah"
        assert unit["canonical_id"] == "quran:1:1"
        assert unit["source_id"] == "src_quran_test"
        assert "text_unit_id" in unit
        assert len(unit["text_unit_id"]) == 36  # UUID length

    def test_quran_ayah_locator_structure(self):
        """Should include surah and ayah in locator JSON."""
        unit = create_quran_ayah(
            source_id="src_test",
            surah=2,
            ayah=255,
            text="اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ",
            surah_name_ar="البقرة",
            surah_name_en="Al-Baqarah",
            juz=3,
        )

        locator = unit["canonical_locator_json"]
        assert locator["surah"] == 2
        assert locator["ayah"] == 255
        assert locator["surah_name_ar"] == "البقرة"
        assert locator["surah_name_en"] == "Al-Baqarah"
        assert locator["juz"] == 3

    def test_quran_ayah_last_surah(self):
        """Should handle last surah (Al-Nas, 114)."""
        unit = create_quran_ayah(
            source_id="src_test",
            surah=114,
            ayah=6,
            text="مِنَ الْجِنَّةِ وَالنَّاسِ",
        )

        assert unit["canonical_id"] == "quran:114:6"

    def test_quran_ayah_with_translation(self):
        """Should include translation in metadata."""
        unit = create_quran_ayah(
            source_id="src_test",
            surah=1,
            ayah=1,
            text="بِسْمِ اللَّهِ",
            translation="In the name of Allah",
        )

        assert unit["metadata"]["translation_en"] == "In the name of Allah"


class TestHadithItemCreation:
    """Tests for Hadith text_unit creation."""

    def test_hadith_item_basic_creation(self):
        """Should create Hadith item with correct canonical ID."""
        unit = create_hadith_item(
            source_id="src_hadith_test",
            collection="bukhari",
            numbering_system="sahih",
            hadith_number="1",
            text_ar="إِنَّمَا الأَعْمَالُ بِالنِّيَّاتِ",
        )

        assert unit["unit_type"] == "hadith_item"
        assert unit["canonical_id"] == "hadith:bukhari:sahih:1"
        assert unit["source_id"] == "src_hadith_test"

    def test_hadith_item_locator_structure(self):
        """Should include collection and numbering info in locator."""
        unit = create_hadith_item(
            source_id="src_test",
            collection="muslim",
            numbering_system="reference",
            hadith_number="45",
            text_ar="حَدِيثٌ تَجْرِيبِيٌّ",
            book_name="Book of Prayer",
            chapter_number=2,
            grading="sahih",
        )

        locator = unit["canonical_locator_json"]
        assert locator["collection"] == "muslim"
        assert locator["numbering_system"] == "reference"
        assert locator["hadith_number"] == "45"
        assert locator["book_name"] == "Book of Prayer"
        assert locator["chapter_number"] == 2
        assert locator["grading"] == "sahih"

    def test_hadith_item_with_english_text(self):
        """Should include English translation in metadata."""
        unit = create_hadith_item(
            source_id="src_test",
            collection="bukhari",
            numbering_system="sahih",
            hadith_number="1",
            text_ar="إِنَّمَا الأَعْمَالُ بِالنِّيَّاتِ",
            text_en="Actions are judged by intentions",
        )

        assert unit["metadata"]["text_en"] == "Actions are judged by intentions"

    def test_hadith_item_with_narrators(self):
        """Should include narrator chain in metadata."""
        narrators = ["عُمَرُ", "النَّبِيِّ صلى الله عليه وسلم"]
        unit = create_hadith_item(
            source_id="src_test",
            collection="bukhari",
            numbering_system="sahih",
            hadith_number="1",
            text_ar="نَصُّ الْحَدِيثِ",
            narrator_chain=narrators,
        )

        assert unit["metadata"]["narrator_chain"] == narrators

    def test_hadith_item_with_topics(self):
        """Should include topic tags in metadata."""
        topics = ["intention", "sincerity", "migration"]
        unit = create_hadith_item(
            source_id="src_test",
            collection="bukhari",
            numbering_system="sahih",
            hadith_number="1",
            text_ar="نَصُّ الْحَدِيثِ",
            topics=topics,
        )

        assert unit["metadata"]["topics"] == topics


class TestNFCNormalization:
    """Tests for NFC normalization applied to text."""

    def test_quran_text_nfc_normalized(self):
        """Should NFC normalize Quran text."""
        # Text with combining characters (decomposed)
        decomposed = "بِسْمِ \u0627\u0644\u0644\u064e\u0651\u0647ِ"  # Alef + lam + lam + shadda + fatha + heh

        unit = create_quran_ayah(
            source_id="src_test",
            surah=1,
            ayah=1,
            text=decomposed,
        )

        # Should be NFC normalized
        assert unicodedata.is_normalized("NFC", unit["text_canonical"])

    def test_hadith_text_nfc_normalized(self):
        """Should NFC normalize Hadith text."""
        # Text with potential decomposed forms
        decomposed = (
            "إِنَّمَا\u0627\u0644\u0623\u064e\0639\u0652\u0645\u064e\0627\u0644\u064f"
        )

        unit = create_hadith_item(
            source_id="src_test",
            collection="bukhari",
            numbering_system="sahih",
            hadith_number="1",
            text_ar=decomposed,
        )

        assert unicodedata.is_normalized("NFC", unit["text_canonical"])

    def test_nfc_idempotent(self):
        """NFC normalization should be idempotent."""
        text = "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ"

        unit1 = create_quran_ayah(
            source_id="src_test",
            surah=1,
            ayah=1,
            text=text,
        )

        unit2 = create_quran_ayah(
            source_id="src_test",
            surah=1,
            ayah=1,
            text=unit1["text_canonical"],
        )

        # Text should be the same after second normalization
        assert unit1["text_canonical"] == unit2["text_canonical"]
        assert (
            unit1["text_canonical_utf8_sha256"] == unit2["text_canonical_utf8_sha256"]
        )


class TestHashComputation:
    """Tests for SHA-256 hash computation."""

    def test_hash_is_hex_string(self):
        """Hash should be 64-character hex string."""
        unit = create_quran_ayah(
            source_id="src_test",
            surah=1,
            ayah=1,
            text="بِسْمِ اللَّهِ",
        )

        hash_val = unit["text_canonical_utf8_sha256"]
        assert isinstance(hash_val, str)
        assert len(hash_val) == 64
        assert all(c in "0123456789abcdef" for c in hash_val)

    def test_hash_consistent(self):
        """Same text should produce same hash."""
        text = "السَّلَامُ عَلَيْكُمْ"

        unit1 = create_quran_ayah(
            source_id="src_test",
            surah=1,
            ayah=1,
            text=text,
        )

        unit2 = create_quran_ayah(
            source_id="src_test",
            surah=1,
            ayah=1,
            text=text,
        )

        assert (
            unit1["text_canonical_utf8_sha256"] == unit2["text_canonical_utf8_sha256"]
        )

    def test_hash_computed_from_nfc_text(self):
        """Hash should be computed from NFC-normalized text."""
        # Same semantic text, different Unicode representations
        nfc = "\u00c4"  # Precomposed
        nfd = "\u0041\u0308"  # Decomposed (A + combining diaeresis)

        unit_nfc = build_text_unit(
            source_id="src_test",
            unit_type="test",
            canonical_id="test:nfc",
            text=nfc,
            locator_json={},
        )

        unit_nfd = build_text_unit(
            source_id="src_test",
            unit_type="test",
            canonical_id="test:nfd",
            text=nfd,
            locator_json={},
        )

        # Both should produce the same hash after NFC normalization
        assert (
            unit_nfc["text_canonical_utf8_sha256"]
            == unit_nfd["text_canonical_utf8_sha256"]
        )

    def test_hash_verification(self):
        """Should be able to verify computed hash."""
        unit = create_quran_ayah(
            source_id="src_test",
            surah=1,
            ayah=1,
            text="بِسْمِ اللَّهِ",
        )

        text = unit["text_canonical"]
        expected_hash = unit["text_canonical_utf8_sha256"]

        # Recompute hash
        computed_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

        assert computed_hash == expected_hash


class TestCanonicalIDValidation:
    """Tests for canonical ID validation."""

    def test_valid_quran_id(self):
        """Should validate correct Quran IDs."""
        valid, error = validate_canonical_id("quran:1:1")
        assert valid is True
        assert error is None

        valid, error = validate_canonical_id("quran:114:6")
        assert valid is True

    def test_invalid_quran_surah(self):
        """Should reject invalid surah numbers."""
        valid, error = validate_canonical_id("quran:0:1")
        assert valid is False
        assert "surah" in error.lower()

        valid, error = validate_canonical_id("quran:115:1")
        assert valid is False

    def test_invalid_quran_ayah(self):
        """Should reject invalid ayah numbers."""
        valid, error = validate_canonical_id("quran:1:0")
        assert valid is False
        assert "ayah" in error.lower()

    def test_valid_hadith_id(self):
        """Should validate correct Hadith IDs."""
        valid, error = validate_canonical_id("hadith:bukhari:sahih:1")
        assert valid is True
        assert error is None

        valid, error = validate_canonical_id("hadith:muslim:reference:45")
        assert valid is True

    def test_invalid_hadith_collection(self):
        """Should reject invalid collection names."""
        valid, error = validate_canonical_id("hadith:unknown:sahih:1")
        assert valid is False
        assert "collection" in error.lower()

    def test_malformed_id(self):
        """Should reject malformed IDs."""
        valid, error = validate_canonical_id("")
        assert valid is False

        valid, error = validate_canonical_id("quran:1")
        assert valid is False
        assert "format" in error.lower()

        valid, error = validate_canonical_id("hadith:bukhari:1")
        assert valid is False
        assert "expected" in error.lower()

    def test_unknown_entity_type(self):
        """Should reject unknown entity types."""
        valid, error = validate_canonical_id("unknown:type:1")
        assert valid is False
        assert "unknown" in error.lower()


class TestBuildTextUnit:
    """Tests for the core build_text_unit function."""

    def test_build_text_unit_basic(self):
        """Should build complete text_unit record."""
        unit = build_text_unit(
            source_id="src_test",
            unit_type="custom_type",
            canonical_id="custom:123",
            text="Test text",
            locator_json={"key": "value"},
        )

        assert unit["source_id"] == "src_test"
        assert unit["unit_type"] == "custom_type"
        assert unit["canonical_id"] == "custom:123"
        assert unit["text_canonical"] == "Test text"
        assert unit["canonical_locator_json"] == {"key": "value"}
        assert "text_unit_id" in unit
        assert "text_canonical_utf8_sha256" in unit
        assert "created_at" in unit

    def test_build_text_unit_with_metadata(self):
        """Should include metadata when provided."""
        unit = build_text_unit(
            source_id="src_test",
            unit_type="test",
            canonical_id="test:1",
            text="Text",
            locator_json={},
            metadata={"extra": "data", "number": 42},
        )

        assert unit["metadata"]["extra"] == "data"
        assert unit["metadata"]["number"] == 42

    def test_build_text_unit_deterministic_id(self):
        """Same canonical_id should produce same text_unit_id."""
        unit1 = build_text_unit(
            source_id="src_test",
            unit_type="test",
            canonical_id="test:123",
            text="Text one",
            locator_json={},
        )

        unit2 = build_text_unit(
            source_id="src_test",
            unit_type="test",
            canonical_id="test:123",
            text="Text two",
            locator_json={},
        )

        # Same canonical_id = same UUID
        assert unit1["text_unit_id"] == unit2["text_unit_id"]

    def test_build_text_unit_different_ids(self):
        """Different canonical_ids should produce different UUIDs."""
        unit1 = build_text_unit(
            source_id="src_test",
            unit_type="test",
            canonical_id="test:1",
            text="Text",
            locator_json={},
        )

        unit2 = build_text_unit(
            source_id="src_test",
            unit_type="test",
            canonical_id="test:2",
            text="Text",
            locator_json={},
        )

        # Different canonical_id = different UUID
        assert unit1["text_unit_id"] != unit2["text_unit_id"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
