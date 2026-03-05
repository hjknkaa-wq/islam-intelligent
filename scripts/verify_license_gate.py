#!/usr/bin/env python3
"""License gate verification script.

Validates that all sources in the database have acceptable licenses
before allowing ingestion of production data.
"""

import sys
import sqlite3
from pathlib import Path
from typing import List, Tuple

# License categories
SAFE_LICENSES = {
    "CC-BY-3.0",
    "CC-BY-4.0",
    "CC0-1.0",
    "UNLICENSE",
    "PD",
    "MIT",
    "Apache-2.0",
    "LGPL-3.0",
    "GPL-3.0",
}

RESTRICTED_LICENSES = {
    "CC-BY-NC-3.0",
    "CC-BY-NC-4.0",
    "CC-BY-ND-3.0",
    "CC-BY-ND-4.0",
    "All-Rights-Reserved",
    "Proprietary",
    "Unknown",
}

REQUIRES_ATTRIBUTION = {
    "CC-BY-3.0",
    "CC-BY-4.0",
    "CC-BY-NC-3.0",
    "CC-BY-NC-4.0",
    "CC-BY-ND-3.0",
    "CC-BY-ND-4.0",
    "ODC-BY",
}


def verify_license_gate(db_path: str = ".local/dev.db") -> Tuple[bool, List[str]]:
    """
    Verify all sources pass license gate.

    Returns:
        (passed, violations)
    """
    violations = []

    if not Path(db_path).exists():
        return False, [f"Database not found: {db_path}"]

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if source_document table exists
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='source_document'
    """)
    if not cursor.fetchone():
        conn.close()
        return False, ["source_document table does not exist"]

    # Check all sources
    cursor.execute("""
        SELECT source_id, work_title, license_id, trust_status
        FROM source_document
        ORDER BY work_title
    """)

    sources = cursor.fetchall()
    conn.close()

    if not sources:
        return False, ["No sources found in database"]

    for source_id, title, license_id, trust_status in sources:
        # Check for unknown licenses
        if license_id not in SAFE_LICENSES and license_id not in RESTRICTED_LICENSES:
            violations.append(
                f"UNKNOWN_LICENSE: {title} ({source_id}) has unrecognized license: {license_id}"
            )

        # Check for restricted licenses
        if license_id in RESTRICTED_LICENSES:
            violations.append(
                f"RESTRICTED_LICENSE: {title} ({source_id}) has restricted license: {license_id}"
            )

        # Check attribution requirement
        if license_id in REQUIRES_ATTRIBUTION:
            # This is just a warning for now, not a violation
            print(f"[INFO] {title} requires attribution per {license_id}")

        # Check trust status
        if trust_status == "retracted":
            violations.append(
                f"RETRACTED_SOURCE: {title} ({source_id}) is retracted and should not be used"
            )

    passed = len(violations) == 0
    return passed, violations


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Verify license gate for all sources")
    parser.add_argument("--db", default=".local/dev.db", help="Path to SQLite database")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on any non-SAFE license (including attribution-required)",
    )

    args = parser.parse_args()

    print("[INFO] Verifying license gate...")
    print(f"   Database: {args.db}")
    print()

    passed, violations = verify_license_gate(args.db)

    if passed:
        print("[OK] License gate PASSED")
        print("   All sources have acceptable licenses")
        sys.exit(0)
    else:
        print("[FAIL] License gate FAILED")
        print(f"   {len(violations)} violation(s) found:")
        for v in violations:
            print(f"   - {v}")
        sys.exit(1)


if __name__ == "__main__":
    main()
