#!/usr/bin/env python3
"""Test script for append-only versioning behavior.

This script verifies that:
1. Creating a source creates the first version
2. Updating a source creates a NEW version (doesn't overwrite)
3. The old version still exists and is accessible
4. The supersedes_source_id link is correctly set
5. Version history is properly maintained

Exit codes:
    0 - All tests passed
    1 - One or more tests failed
    2 - Unexpected error
"""

import sys
from typing import Any

from sqlalchemy.orm import Session

# Add the project to path
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api", "src"))

from islam_intelligent.db.engine import SessionLocal, engine
from islam_intelligent.domain.models import Base, SourceDocument
from islam_intelligent.ingest import source_registry

# Import provenance models to register them on Base
from islam_intelligent.provenance import models as _prov_models
from islam_intelligent.domain.models import Base, SourceDocument
from islam_intelligent.ingest import source_registry


def test_create_source(db: Session) -> tuple[str, dict[str, Any]]:
    """Test creating a source document.

    Returns:
        Tuple of (source_id, test results dict)
    """
    print("TEST 1: Creating source document...")

    content = {
        "text": "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ",
        "translation": "In the name of Allah, the Most Gracious, the Most Merciful",
        "surah": 1,
        "ayah": 1,
    }

    doc = source_registry.create_source_document(
        db=db,
        source_type="quran",
        content=content,
        title="Al-Fatiha",
        author="Allah",
        language="ar",
    )

    # Verify
    assert doc.source_id is not None, "source_id should be generated"
    assert doc.version == 1, "First version should be 1"
    assert doc.source_type == "quran"
    assert doc.title == "Al-Fatiha"
    assert doc.content_sha256 is not None
    assert doc.manifest_sha256 is not None
    assert doc.supersedes_source_id is None, (
        "First version should not supersede anything"
    )
    assert doc.supersedes_version is None

    print(f"  [OK] Created source: {doc.source_id}")
    print(f"  [OK] Version: {doc.version}")
    print(f"  [OK] Content hash: {doc.content_sha256[:16]}...")
    print()

    return doc.source_id, {
        "source_id": doc.source_id,
        "version": doc.version,
        "content_hash": doc.content_sha256,
    }


def test_update_creates_new_version(db: Session, source_id: str) -> dict[str, Any]:
    """Test that update creates a new version."""
    print("TEST 2: Updating source document (should create new version)...")

    # Get original
    original = source_registry.get_source_document(db, source_id)
    assert original is not None, "Original should exist"
    original_version = original.version
    original_hash = original.content_sha256

    # Update
    new_content = {
        "text": "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ",
        "translation": "In the name of God, the Most Gracious, the Most Merciful",
        "surah": 1,
        "ayah": 1,
        "notes": "Updated translation",
    }

    updated = source_registry.update_source(
        db=db,
        source_id=source_id,
        new_data={"content": new_content},
    )

    # Verify
    assert updated is not None, "Update should succeed"
    assert updated.source_id == source_id, "source_id should remain the same"
    assert updated.version == original_version + 1, "Version should increment"
    assert updated.supersedes_source_id == source_id, "Should link to same source_id"
    assert updated.supersedes_version == original_version, (
        "Should link to previous version"
    )
    assert updated.content_sha256 != original_hash, "Content hash should change"

    print(f"  [OK] Created new version: {updated.version}")
    print(
        f"  [OK] Supersedes: {updated.supersedes_source_id} v{updated.supersedes_version}"
    )
    print(f"  [OK] New content hash: {updated.content_sha256[:16]}...")
    print()

    return {
        "new_version": updated.version,
        "new_hash": updated.content_sha256,
        "supersedes_version": updated.supersedes_version,
    }


def test_old_version_preserved(db: Session, source_id: str) -> bool:
    """Test that old version is still accessible."""
    print("TEST 3: Verifying old version still exists...")

    # Get version 1
    v1 = source_registry.get_source_document(db, source_id, version=1)
    assert v1 is not None, "Version 1 should still exist"
    assert v1.version == 1, "Should be version 1"
    assert v1.source_id == source_id

    # Get version 2
    v2 = source_registry.get_source_document(db, source_id, version=2)
    assert v2 is not None, "Version 2 should exist"
    assert v2.version == 2

    # Verify they're different
    assert v1.id != v2.id, "Should have different primary keys"
    assert v1.content_sha256 != v2.content_sha256, (
        "Should have different content hashes"
    )

    print(f"  [OK] Version 1 accessible: id={v1.id}")
    print(f"  [OK] Version 2 accessible: id={v2.id}")
    print(
        f"  [OK] Content differs: {v1.content_sha256[:8]}... vs {v2.content_sha256[:8]}..."
    )
    print()

    return True


def test_version_chain(db: Session, source_id: str) -> bool:
    """Test version chain via supersedes links."""
    print("TEST 4: Verifying version chain...")

    # Get all versions
    versions = source_registry.get_version_history(db, source_id)
    assert len(versions) == 2, f"Should have 2 versions, got {len(versions)}"

    # Check chain
    v1 = versions[0]
    v2 = versions[1]

    assert v1.version == 1
    assert v2.version == 2
    assert v2.supersedes_source_id == source_id
    assert v2.supersedes_version == 1

    print(f"  [OK] Version chain: v1 -> v2")
    print(f"    v1: id={v1.id}, version={v1.version}")
    print(
        f"    v2: id={v2.id}, version={v2.version}, supersedes v{v2.supersedes_version}"
    )
    print()

    return True


def test_list_returns_latest_only(db: Session, source_id: str) -> bool:
    """Test that list_sources returns only latest version by default."""
    print("TEST 5: Verifying list_sources returns latest version...")

    sources = source_registry.list_sources(db, latest_only=True)
    source_ids = [s.source_id for s in sources]

    # Should have our source
    assert source_id in source_ids, f"Source {source_id} should be in list"

    # Should only have one entry per source
    our_sources = [s for s in sources if s.source_id == source_id]
    assert len(our_sources) == 1, f"Should have exactly 1 entry, got {len(our_sources)}"

    # Should be version 2 (latest)
    assert our_sources[0].version == 2, "Should be version 2"

    print(f"  [OK] List contains source (1 entry)")
    print(f"  [OK] Entry is latest version: v{our_sources[0].version}")
    print()

    return True


def test_multiple_updates(db: Session, source_id: str) -> bool:
    """Test multiple updates create proper chain."""
    print("TEST 6: Testing multiple updates...")

    # Create version 3
    content_v3 = {"text": "v3 content", "version": 3}
    v3 = source_registry.update_source(
        db=db,
        source_id=source_id,
        new_data={"content": content_v3},
    )

    assert v3.version == 3
    assert v3.supersedes_version == 2

    # Verify all 3 versions exist
    all_versions = source_registry.get_version_history(db, source_id)
    assert len(all_versions) == 3, f"Should have 3 versions, got {len(all_versions)}"

    # Verify versions are sequential
    for i, v in enumerate(all_versions, 1):
        assert v.version == i, f"Version {i} should have version number {i}"

    print(f"  [OK] Created version 3")
    print(f"  [OK] Total versions: {len(all_versions)}")
    print(f"  [OK] Chain: v1 -> v2 -> v3")
    print()

    return True


def run_tests() -> int:
    """Run all tests."""
    print("=" * 60)
    print("APPEND-ONLY VERSIONING TEST SUITE")
    print("=" * 60)
    print()

    # Create tables
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"Error creating database tables: {e}", file=sys.stderr)
        return 2

    db = SessionLocal()
    test_source_id = None

    try:
        # Run tests
        test_source_id, create_results = test_create_source(db)
        update_results = test_update_creates_new_version(db, test_source_id)

        assert test_old_version_preserved(db, test_source_id)
        assert test_version_chain(db, test_source_id)
        assert test_list_returns_latest_only(db, test_source_id)
        assert test_multiple_updates(db, test_source_id)

        print("=" * 60)
        print("ALL TESTS PASSED [OK]")
        print("=" * 60)
        print()
        print("Summary:")
        print(f"  Source ID: {test_source_id}")
        print(f"  Versions created: 3")
        print(f"  Append-only behavior: VERIFIED")
        print()

        return 0

    except AssertionError as e:
        print()
        print("=" * 60)
        print(f"TEST FAILED: {e}")
        print("=" * 60)
        return 1

    except Exception as e:
        print()
        print("=" * 60)
        print(f"UNEXPECTED ERROR: {e}")
        print("=" * 60)
        import traceback

        traceback.print_exc()
        return 2

    finally:
        # Cleanup
        if test_source_id:
            try:
                db.query(SourceDocument).filter(
                    SourceDocument.source_id == test_source_id
                ).delete()
                db.commit()
                print(f"Cleaned up test data for {test_source_id}")
            except Exception:
                pass
        db.close()


if __name__ == "__main__":
    sys.exit(run_tests())
