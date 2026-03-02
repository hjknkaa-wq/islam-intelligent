"""TextUnit builder for Islamic knowledge ingestion.

This module provides factory functions for building text_unit records
ready for database insertion. All text undergoes NFC normalization
and SHA-256 hash computation for integrity verification.

Canonical ID Formats:
- Quran: quran:{surah}:{ayah}
- Hadith: hadith:{collection}:{numbering_system}:{number}

References:
    - Unicode TR15: https://unicode.org/reports/tr15/
    - Canonical ID schema: docs/canonical_ids.md
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from islam_intelligent.normalize import (
    TextNormalizer,
    compute_hash,
    normalize_storage,
)


def build_text_unit(
    source_id: str,
    unit_type: str,
    canonical_id: str,
    text: str,
    locator_json: dict[str, Any],
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Build a complete text_unit record ready for DB insertion.

    This is the core factory function that creates standardized text_unit
    records with proper normalization, hashing, and provenance tracking.

    Args:
        source_id: UUID of the parent source document
        unit_type: Type of unit ('quran_ayah', 'hadith_item', 'tafsir_section', etc.)
        canonical_id: Globally unique canonical identifier (e.g., 'quran:1:1')
        text: Raw text content (will be NFC normalized)
        locator_json: Structured location information (surah/ayah, collection/number, etc.)
        metadata: Optional additional metadata (translations, tags, etc.)

    Returns:
        Complete text_unit record with normalized text and computed hashes

    Example:
        >>> unit = build_text_unit(
        ...     source_id="src_abc123",
        ...     unit_type="quran_ayah",
        ...     canonical_id="quran:1:1",
        ...     text="بِسْمِ اللَّهِ",
        ...     locator_json={"surah": 1, "ayah": 1}
        ... )
        >>> unit["text_canonical"]
        'بِسْمِ اللَّهِ'
        >>> len(unit["text_canonical_utf8_sha256"])
        64
    """
    # Generate deterministic UUID based on canonical_id
    text_unit_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, canonical_id))

    # NFC normalize text for storage
    text_normalized = normalize_storage(text)

    # Compute SHA-256 hash of normalized text
    text_hash = compute_hash(text_normalized)

    # Build complete record
    record = {
        "text_unit_id": text_unit_id,
        "source_id": source_id,
        "unit_type": unit_type,
        "canonical_id": canonical_id,
        "canonical_locator_json": locator_json,
        "text_canonical": text_normalized,
        "text_canonical_utf8_sha256": text_hash,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Add optional metadata if provided
    if metadata:
        record["metadata"] = metadata

    return record


def create_quran_ayah(
    source_id: str,
    surah: int,
    ayah: int,
    text: str,
    surah_name_ar: Optional[str] = None,
    surah_name_en: Optional[str] = None,
    juz: Optional[int] = None,
    page: Optional[int] = None,
    hizb: Optional[int] = None,
    rub: Optional[int] = None,
    translation: Optional[str] = None,
) -> dict[str, Any]:
    """
    Create a Quran ayah text_unit record.

    Canonical ID format: quran:{surah}:{ayah}

    Args:
        source_id: UUID of the parent Quran source document
        surah: Surah number (1-114)
        ayah: Ayah number within surah (1+)
        text: Arabic text of the ayah
        surah_name_ar: Arabic name of the surah
        surah_name_en: English name of the surah
        juz: Juz number (1-30)
        page: Page number in mushaf
        hizb: Hizb number (1-60)
        rub: Rub' al-hizb number (1-240)
        translation: Optional English translation

    Returns:
        Complete text_unit record for Quran ayah

    Example:
        >>> unit = create_quran_ayah(
        ...     source_id="src_quran_tanzil",
        ...     surah=1,
        ...     ayah=1,
        ...     text="بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ",
        ...     surah_name_ar="الفاتحة",
        ...     surah_name_en="Al-Fatiha",
        ...     juz=1,
        ... )
        >>> unit["canonical_id"]
        'quran:1:1'
        >>> unit["unit_type"]
        'quran_ayah'
    """
    # Build canonical ID
    canonical_id = f"quran:{surah}:{ayah}"

    # Build locator JSON with all available location data
    locator_json: dict[str, Any] = {
        "surah": surah,
        "ayah": ayah,
    }

    if surah_name_ar:
        locator_json["surah_name_ar"] = surah_name_ar
    if surah_name_en:
        locator_json["surah_name_en"] = surah_name_en
    if juz is not None:
        locator_json["juz"] = juz
    if page is not None:
        locator_json["page"] = page
    if hizb is not None:
        locator_json["hizb"] = hizb
    if rub is not None:
        locator_json["rub"] = rub

    # Build metadata with optional translation
    metadata: dict[str, Any] = {}
    if translation:
        metadata["translation_en"] = translation

    return build_text_unit(
        source_id=source_id,
        unit_type="quran_ayah",
        canonical_id=canonical_id,
        text=text,
        locator_json=locator_json,
        metadata=metadata if metadata else None,
    )


def create_hadith_item(
    source_id: str,
    collection: str,
    numbering_system: str,
    hadith_number: str,
    text_ar: str,
    text_en: Optional[str] = None,
    book_name: Optional[str] = None,
    chapter_name: Optional[str] = None,
    chapter_number: Optional[int] = None,
    bab_name: Optional[str] = None,
    bab_number: Optional[int] = None,
    narrator_chain: Optional[list[str]] = None,
    grading: Optional[str] = None,
    topics: Optional[list[str]] = None,
) -> dict[str, Any]:
    """
    Create a Hadith text_unit record.

    Canonical ID format: hadith:{collection}:{numbering_system}:{hadith_number}

    Supported collections:
    - bukhari: Sahih al-Bukhari
    - muslim: Sahih Muslim
    - abudawud: Sunan Abu Dawud
    - tirmidhi: Jami' at-Tirmidhi
    - nasai: Sunan an-Nasa'i
    - ibnmajah: Sunan Ibn Majah
    - malik: Muwatta Malik
    - ahmad: Musnad Ahmad

    Numbering systems:
    - sahih: Sahih numbering (e.g., Sahih Bukhari 1)
    - fath: Fath al-Bari numbering
    - irab: Irab numbering
    - inbook: In-book numbering
    - reference: Reference number in collection

    Args:
        source_id: UUID of the parent Hadith source document
        collection: Collection identifier (bukhari, muslim, etc.)
        numbering_system: Numbering system identifier
        hadith_number: Hadith number in the specified system
        text_ar: Arabic text of the hadith
        text_en: Optional English translation
        book_name: Book (kitab) name
        chapter_name: Chapter name
        chapter_number: Chapter number
        bab_name: Bab (section) name
        bab_number: Bab number
        narrator_chain: List of narrators (sanad)
        grading: Hadith grading (sahih, hasan, daif, etc.)
        topics: List of topic tags

    Returns:
        Complete text_unit record for Hadith item

    Example:
        >>> unit = create_hadith_item(
        ...     source_id="src_hadith_bukhari",
        ...     collection="bukhari",
        ...     numbering_system="sahih",
        ...     hadith_number="1",
        ...     text_ar="إِنَّمَا الأَعْمَالُ بِالنِّيَّاتِ...",
        ...     text_en="Actions are judged by intentions...",
        ...     book_name="Book of Revelation",
        ...     grading="sahih",
        ... )
        >>> unit["canonical_id"]
        'hadith:bukhari:sahih:1'
        >>> unit["unit_type"]
        'hadith_item'
    """
    # Build canonical ID
    canonical_id = f"hadith:{collection}:{numbering_system}:{hadith_number}"

    # Primary text is Arabic
    text = text_ar

    # Build locator JSON with all available metadata
    locator_json: dict[str, Any] = {
        "collection": collection,
        "numbering_system": numbering_system,
        "hadith_number": hadith_number,
    }

    if book_name:
        locator_json["book_name"] = book_name
    if chapter_name:
        locator_json["chapter_name"] = chapter_name
    if chapter_number is not None:
        locator_json["chapter_number"] = chapter_number
    if bab_name:
        locator_json["bab_name"] = bab_name
    if bab_number is not None:
        locator_json["bab_number"] = bab_number
    if grading:
        locator_json["grading"] = grading

    # Build metadata
    metadata: dict[str, Any] = {}

    if text_en:
        metadata["text_en"] = text_en
    if narrator_chain:
        metadata["narrator_chain"] = narrator_chain
    if topics:
        metadata["topics"] = topics

    return build_text_unit(
        source_id=source_id,
        unit_type="hadith_item",
        canonical_id=canonical_id,
        text=text,
        locator_json=locator_json,
        metadata=metadata if metadata else None,
    )


def validate_canonical_id(canonical_id: str) -> tuple[bool, Optional[str]]:
    """
    Validate a canonical ID format.

    Args:
        canonical_id: The canonical ID to validate

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if format is valid
        - error_message: None if valid, description of error if invalid
    """
    if not canonical_id:
        return False, "Canonical ID cannot be empty"

    parts = canonical_id.split(":")

    if len(parts) < 3:
        return (
            False,
            f"Invalid format: {canonical_id} (expected at least 3 parts separated by ':')",
        )

    entity_type = parts[0]

    if entity_type == "quran":
        # quran:surah:ayah
        if len(parts) != 3:
            return (
                False,
                f"Invalid Quran ID: {canonical_id} (expected quran:surah:ayah)",
            )
        try:
            surah = int(parts[1])
            ayah = int(parts[2])
            if not (1 <= surah <= 114):
                return False, f"Invalid surah number: {surah} (must be 1-114)"
            if ayah < 1:
                return False, f"Invalid ayah number: {ayah} (must be >= 1)"
        except ValueError:
            return (
                False,
                f"Invalid Quran ID: {canonical_id} (surah and ayah must be integers)",
            )

    elif entity_type == "hadith":
        # hadith:collection:numbering_system:number
        if len(parts) != 4:
            return (
                False,
                f"Invalid Hadith ID: {canonical_id} (expected hadith:collection:numbering_system:number)",
            )
        collection = parts[1]
        numbering_system = parts[2]
        hadith_number = parts[3]

        valid_collections = {
            "bukhari",
            "muslim",
            "abudawud",
            "tirmidhi",
            "nasai",
            "ibnmajah",
            "malik",
            "ahmad",
        }
        if collection not in valid_collections:
            return False, f"Invalid collection: {collection}"

        if not numbering_system:
            return False, "Numbering system cannot be empty"
        if not hadith_number:
            return False, "Hadith number cannot be empty"

    else:
        return False, f"Unknown entity type: {entity_type}"

    return True, None


# Convenience exports
__all__ = [
    "build_text_unit",
    "create_quran_ayah",
    "create_hadith_item",
    "validate_canonical_id",
]
