#!/usr/bin/env python3
"""Validate canonical IDs in fixtures or database.

This script validates that canonical IDs follow the proper format:
- Quran: quran:{surah}:{ayah} where surah is 1-114 and ayah >= 1
- Hadith: hadith:{collection}:{numbering_system}:{number}

Usage:
    python scripts/validate_canonical_ids.py --from-file
    python scripts/validate_canonical_ids.py --from-db

Exit codes:
    0 - All canonical IDs are valid
    1 - Invalid IDs found or validation errors
    2 - Database connection or schema errors
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

import yaml

# Add apps/api/src to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "apps" / "api" / "src"))

from islam_intelligent.ingest.text_unit_builder import validate_canonical_id


def get_fixture_files() -> list[Path]:
    """Get list of fixture YAML files."""
    fixtures_dir = project_root / "data" / "fixtures"
    if not fixtures_dir.exists():
        return []
    return list(fixtures_dir.glob("*.yaml"))


def validate_fixture_file(file_path: Path) -> tuple[list[str], list[str]]:
    """
    Validate all canonical IDs in a fixture file.

    Returns:
        Tuple of (valid_ids, invalid_ids_with_errors)
    """
    valid_ids = []
    invalid_ids = []

    try:
        with open(file_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        print(f"ERROR: Failed to parse {file_path}: {e}")
        return [], [f"FILE_ERROR:{file_path}"]

    if not data or "text_units" not in data:
        print(f"WARNING: No text_units found in {file_path}")
        return [], []

    text_units = data["text_units"]
    for i, unit in enumerate(text_units):
        if "canonical_id" not in unit:
            invalid_ids.append(f"MISSING_ID:unit_{i}")
            continue

        canonical_id = unit["canonical_id"]
        is_valid, error = validate_canonical_id(canonical_id)

        if is_valid:
            valid_ids.append(canonical_id)
        else:
            invalid_ids.append(f"{canonical_id}:{error}")

    return valid_ids, invalid_ids


def validate_from_files() -> int:
    """
    Validate canonical IDs from all fixture files.

    Returns:
        0 if all valid, 1 if any invalid
    """
    print("=" * 60)
    print("VALIDATING CANONICAL IDs FROM FIXTURE FILES")
    print("=" * 60)

    fixture_files = get_fixture_files()

    if not fixture_files:
        print("ERROR: No fixture files found in data/fixtures/")
        return 1

    print(f"\nFound {len(fixture_files)} fixture file(s):")
    for f in fixture_files:
        print(f"  - {f.name}")

    all_valid = []
    all_invalid = []

    for file_path in fixture_files:
        print(f"\nChecking {file_path.name}...")
        valid, invalid = validate_fixture_file(file_path)
        all_valid.extend(valid)
        all_invalid.extend(invalid)

        if invalid:
            print(f"  [FAIL] {len(invalid)} invalid ID(s)")
            for inv in invalid:
                print(f"    - {inv}")
        else:
            print(f"  [OK] All {len(valid)} ID(s) valid")

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Valid IDs:   {len(all_valid)}")
    print(f"Invalid IDs: {len(all_invalid)}")

    if all_invalid:
        print("\n[FAIL] VALIDATION FAILED")
        return 1
    else:
        print("\n[OK] ALL VALID")
        return 0


def validate_from_database() -> int:
    """
    Validate canonical IDs from database text_unit table.

    Returns:
        0 if all valid, 1 if any invalid, 2 on DB error
    """
    print("=" * 60)
    print("VALIDATING CANONICAL IDs FROM DATABASE")
    print("=" * 60)

    try:
        from sqlalchemy import select, text
        from sqlalchemy.orm import Session

        from islam_intelligent.db.engine import SessionLocal
    except ImportError as e:
        print(f"ERROR: Failed to import database modules: {e}")
        return 2

    # Check if text_unit table exists
    try:
        session = SessionLocal()

        # Try to query the text_unit table
        result = session.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='text_unit'"
            )
        )
        if not result.fetchone():
            print("WARNING: text_unit table does not exist in database")
            print("This is expected if fixtures haven't been loaded yet.")
            print("\nRun 'python scripts/load_fixtures.py' to populate the database.")
            return 0  # Not an error, just no data yet

        # Query all canonical IDs
        result = session.execute(
            text("SELECT text_unit_id, canonical_id, unit_type FROM text_unit")
        )
        rows = result.fetchall()

        if not rows:
            print("INFO: No text units found in database")
            return 0

        print(f"\nFound {len(rows)} text unit(s) in database")

        valid_ids = []
        invalid_ids = []

        for row in rows:
            text_unit_id, canonical_id, unit_type = row
            is_valid, error = validate_canonical_id(canonical_id)

            if is_valid:
                valid_ids.append(canonical_id)
            else:
                invalid_ids.append((text_unit_id, canonical_id, error))

        print(f"\nValidating {len(rows)} canonical ID(s)...")

        if invalid_ids:
            print(f"\n[FAIL] {len(invalid_ids)} INVALID ID(s):")
            for text_unit_id, canonical_id, error in invalid_ids:
                print(f"  - {canonical_id} (unit: {text_unit_id})")
                print(f"    Error: {error}")
        else:
            print(f"\n[OK] All {len(valid_ids)} ID(s) valid")

        # Show breakdown by type
        print("\nBreakdown by unit_type:")
        type_counts = {}
        for row in rows:
            unit_type = row[2]
            type_counts[unit_type] = type_counts.get(unit_type, 0) + 1
        for unit_type, count in sorted(type_counts.items()):
            print(f"  - {unit_type}: {count}")

        print("\n" + "=" * 60)
        if invalid_ids:
            print("[FAIL] VALIDATION FAILED")
            return 1
        else:
            print("[OK] ALL VALID")
            return 0

    except Exception as e:
        print(f"ERROR: Database operation failed: {e}")
        return 2


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate canonical IDs in fixtures or database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/validate_canonical_ids.py --from-file
  python scripts/validate_canonical_ids.py --from-db
  python scripts/validate_canonical_ids.py --from-file --from-db
        """,
    )

    parser.add_argument(
        "--from-file",
        action="store_true",
        help="Validate IDs from fixture YAML files",
    )

    parser.add_argument(
        "--from-db",
        action="store_true",
        help="Validate IDs from database text_unit table",
    )

    args = parser.parse_args()

    # If no args specified, default to --from-file
    if not args.from_file and not args.from_db:
        args.from_file = True

    exit_code = 0

    if args.from_file:
        file_exit = validate_from_files()
        exit_code = max(exit_code, file_exit)

    if args.from_db:
        # Add separator if both modes ran
        if args.from_file:
            print("\n" + "=" * 60 + "\n")
        db_exit = validate_from_database()
        exit_code = max(exit_code, db_exit)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
