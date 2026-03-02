"""Ingestion module for source documents and text units."""

from .source_registry import (
    create_source_document,
    get_source_document,
    list_sources,
    update_source,
    generate_manifest,
    verify_manifest,
    get_version_history,
)
from .text_unit_builder import (
    build_text_unit,
    create_quran_ayah,
    create_hadith_item,
    validate_canonical_id,
)

__all__ = [
    # Source registry
    "create_source_document",
    "get_source_document",
    "list_sources",
    "update_source",
    "generate_manifest",
    "verify_manifest",
    "get_version_history",
    # Text unit builder
    "build_text_unit",
    "create_quran_ayah",
    "create_hadith_item",
    "validate_canonical_id",
]
