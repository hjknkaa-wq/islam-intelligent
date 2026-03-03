#!/usr/bin/env python3
"""Load Quran and Hadith fixtures into database.

Database seeding utility - direct DB access is OK for initial data loading.

This script:
1. Creates source documents for Quran and Hadith collections
2. Creates text_unit records for each ayah and hadith
3. Uses NFC normalization and SHA-256 hashing for integrity
4. Validates canonical IDs before insertion

Usage:
    python scripts/load_fixtures.py [--fixtures-dir DIR] [--db-path PATH]

Exit codes:
    0 - Success
    1 - Validation errors
    2 - Database errors
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

import yaml

# Add apps/api/src to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "apps" / "api" / "src"))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from islam_intelligent.db.engine import engine as default_engine
from islam_intelligent.domain.models import Base, SourceDocument, TextUnit
from islam_intelligent.ingest.text_unit_builder import (
    create_quran_ayah,
    create_hadith_item,
    validate_canonical_id,
)

# Global engine reference (can be overridden)
engine = default_engine


def init_database():
    """Initialize database tables."""
    # Import provenance models to register them with Base
    from islam_intelligent.provenance import models as prov_models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    print("[OK] Database tables initialized")


def compute_sha256(text: str) -> str:
    """Compute SHA-256 hash of text."""
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_yaml_fixture(file_path: Path) -> dict:
    """Load a YAML fixture file."""
    with open(file_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def create_source_doc_from_fixture(
    db: Session, fixture_data: dict, fixture_path: Path
) -> SourceDocument:
    """Create a SourceDocument from fixture metadata."""
    metadata = fixture_data.get("metadata", {})

    # Generate deterministic source_id
    source_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, metadata["source_id"]))

    # Check if source already exists
    existing = (
        db.query(SourceDocument).filter(SourceDocument.source_id == source_id).first()
    )

    if existing:
        print(f"  Source already exists: {metadata['source_id']}")
        return existing

    # Compute content hash from all text units
    text_units = fixture_data.get("text_units", [])
    all_text = "\n".join(u.get("text", u.get("text_ar", "")) for u in text_units)
    content_hash = compute_sha256(all_text)

    # Build attribution text
    attribution_parts = [
        f"Source: {metadata.get('work_title', 'Unknown')}",
        f"License: {metadata.get('license_id', 'Unknown')}",
    ]
    if metadata.get("rights_holder"):
        attribution_parts.append(f"Rights: {metadata['rights_holder']}")

    # Create source document
    source_doc = SourceDocument(
        source_id=source_id,
        source_type=metadata.get("source_type", "unknown"),
        title=metadata.get("work_title"),
        author=metadata.get("author"),
        language=metadata.get("language", "ar"),
        content_json=json.dumps(fixture_data, ensure_ascii=False),
        content_sha256=content_hash,
        manifest_sha256="",  # Will be computed
    )

    # Compute manifest hash
    manifest = {
        "source_id": source_doc.source_id,
        "version": source_doc.version,
        "source_type": source_doc.source_type,
        "title": source_doc.title,
        "author": source_doc.author,
        "language": source_doc.language,
        "content_sha256": source_doc.content_sha256,
    }
    source_doc.manifest_sha256 = compute_sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    )

    db.add(source_doc)
    db.commit()
    db.refresh(source_doc)

    print(f"  Created source: {metadata['source_id']}")
    return source_doc


def load_quran_fixtures(db: Session, fixtures_dir: Path) -> int:
    """Load Quran fixtures into database.

    Returns:
        Number of text units created
    """
    print("\n[QURAN FIXTURES]")

    quran_file = fixtures_dir / "quran_minimal.yaml"
    if not quran_file.exists():
        print(f"  WARNING: {quran_file} not found")
        return 0

    data = load_yaml_fixture(quran_file)
    source_doc = create_source_doc_from_fixture(db, data, quran_file)

    text_units = data.get("text_units", [])
    created_count = 0
    skipped_count = 0

    print(f"  Processing {len(text_units)} ayah(s)...")

    for unit_data in text_units:
        canonical_id = unit_data["canonical_id"]

        # Validate canonical ID
        is_valid, error = validate_canonical_id(canonical_id)
        if not is_valid:
            print(f"  ERROR: Invalid ID {canonical_id}: {error}")
            continue

        # Check if already exists
        existing = (
            db.query(TextUnit).filter(TextUnit.canonical_id == canonical_id).first()
        )
        if existing:
            skipped_count += 1
            continue

        # Create text unit using builder
        text_unit = create_quran_ayah(
            source_id=source_doc.source_id,
            surah=unit_data["surah"],
            ayah=unit_data["ayah"],
            text=unit_data["text"],
            surah_name_ar=unit_data.get("surah_name_ar"),
            surah_name_en=unit_data.get("surah_name_en"),
            juz=unit_data.get("juz"),
        )

        # Insert into database
        db_unit = TextUnit(
            text_unit_id=text_unit["text_unit_id"],
            source_id=text_unit["source_id"],
            unit_type=text_unit["unit_type"],
            canonical_id=text_unit["canonical_id"],
            canonical_locator_json=json.dumps(
                text_unit["canonical_locator_json"], ensure_ascii=False
            ),
            text_canonical=text_unit["text_canonical"],
            text_canonical_utf8_sha256=text_unit["text_canonical_utf8_sha256"],
        )

        db.add(db_unit)
        created_count += 1

        if created_count % 10 == 0:
            print(f"    Progress: {created_count} created...")

    db.commit()
    print(f"  Created: {created_count}, Skipped: {skipped_count}")
    return created_count


def load_hadith_fixtures(db: Session, fixtures_dir: Path) -> int:
    """Load Hadith fixtures into database.

    Returns:
        Number of text units created
    """
    print("\n[HADITH FIXTURES]")

    hadith_file = fixtures_dir / "hadith_minimal.yaml"
    if not hadith_file.exists():
        print(f"  WARNING: {hadith_file} not found")
        return 0

    data = load_yaml_fixture(hadith_file)
    source_doc = create_source_doc_from_fixture(db, data, hadith_file)

    text_units = data.get("text_units", [])
    created_count = 0
    skipped_count = 0

    print(f"  Processing {len(text_units)} hadith(s)...")

    for unit_data in text_units:
        canonical_id = unit_data["canonical_id"]

        # Validate canonical ID
        is_valid, error = validate_canonical_id(canonical_id)
        if not is_valid:
            print(f"  ERROR: Invalid ID {canonical_id}: {error}")
            continue

        # Check if already exists
        existing = (
            db.query(TextUnit).filter(TextUnit.canonical_id == canonical_id).first()
        )
        if existing:
            skipped_count += 1
            continue

        # Create text unit using builder
        text_unit = create_hadith_item(
            source_id=source_doc.source_id,
            collection=unit_data["collection"],
            numbering_system=unit_data["numbering_system"],
            hadith_number=unit_data["hadith_number"],
            text_ar=unit_data["text_ar"],
            text_en=unit_data.get("text_en"),
            book_name=unit_data.get("book_name"),
            chapter_name=unit_data.get("chapter_name"),
            chapter_number=unit_data.get("chapter_number"),
            grading=unit_data.get("grading"),
            topics=unit_data.get("topics"),
        )

        # Insert into database
        db_unit = TextUnit(
            text_unit_id=text_unit["text_unit_id"],
            source_id=text_unit["source_id"],
            unit_type=text_unit["unit_type"],
            canonical_id=text_unit["canonical_id"],
            canonical_locator_json=json.dumps(
                text_unit["canonical_locator_json"], ensure_ascii=False
            ),
            text_canonical=text_unit["text_canonical"],
            text_canonical_utf8_sha256=text_unit["text_canonical_utf8_sha256"],
        )

        db.add(db_unit)
        created_count += 1

        print(f"    Created: {canonical_id}")

    db.commit()
    print(f"  Created: {created_count}, Skipped: {skipped_count}")
    return created_count


def print_summary(db: Session):
    """Print summary of loaded data."""
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    # Count by unit type
    results = db.query(TextUnit.unit_type).distinct().all()
    for (unit_type,) in results:
        count = db.query(TextUnit).filter(TextUnit.unit_type == unit_type).count()
        print(f"  {unit_type}: {count}")

    total = db.query(TextUnit).count()
    print(f"\n  Total text units: {total}")

    # Count sources
    source_count = db.query(SourceDocument).count()
    print(f"  Total sources: {source_count}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Load Quran and Hadith fixtures into database"
    )
    parser.add_argument(
        "--fixtures-dir",
        type=Path,
        default=Path(__file__).parent.parent / "data" / "fixtures",
        help="Directory containing fixture YAML files",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Path to SQLite database file (overrides default engine)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("ISLAM INTELLIGENT - FIXTURE LOADER")
    print("=" * 60)

    # Override engine if db-path is provided
    global engine
    skip_init = False
    if args.db_path:
        db_path = Path(args.db_path).resolve()
        db_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
        engine = create_engine(db_url, future=True)
        print(f"[INFO] Using database: {db_path}")
        skip_init = True  # Schema already created by db_init.py

    # Initialize database (skip if using external db_path)
    if not skip_init:
        try:
            init_database()
        except Exception as e:
            print(f"ERROR: Failed to initialize database: {e}")
            return 2
    # Create a new Session with the current engine
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    if args.db_path:
        db_path = Path(args.db_path).resolve()
        db_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
        engine = create_engine(db_url, future=True)
        print(f"[INFO] Using database: {db_path}")

    # Initialize database
    try:
        init_database()
    except Exception as e:
        print(f"ERROR: Failed to initialize database: {e}")
        return 2

    # Create a new Session with the current engine
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    # Load fixtures
    db = Session()
    try:
        quran_count = load_quran_fixtures(db, args.fixtures_dir)
        hadith_count = load_hadith_fixtures(db, args.fixtures_dir)

        print_summary(db)

        print("\n" + "=" * 60)
        if quran_count > 0 or hadith_count > 0:
            print("[OK] FIXTURES LOADED SUCCESSFULLY")
            return 0
        else:
            print("[INFO] No new fixtures to load (all may already exist)")
            return 0

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback

        traceback.print_exc()
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
