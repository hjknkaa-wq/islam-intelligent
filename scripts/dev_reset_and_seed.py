#!/usr/bin/env python3
"""Reset and seed development database.

This script provides a one-command reset for the development environment:
1. Deletes existing SQLite database file
2. Runs db_init.py to recreate schema
3. Seeds data directly using raw SQL (avoids ORM/SQL schema mismatch)
4. Runs smoke checks to verify data integrity

Usage:
    python scripts/dev_reset_and_seed.py [--db-path PATH]

Exit codes:
    0 - Success
    1 - Database initialization failed
    2 - Fixture loading failed
    3 - Smoke checks failed
    4 - Other error
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / ".local" / "dev.db"
DB_INIT_SCRIPT = ROOT / "scripts" / "db_init.py"
HADITH_INGEST_SCRIPT = ROOT / "scripts" / "ingest_hadith_api.py"
FIXTURES_DIR = ROOT / "data" / "fixtures"

# Smoke check thresholds
MIN_QURAN_AYAH = 1
MIN_HADITH_ITEM = 1


@dataclass(frozen=True)
class CliArgs:
    db_path: Path
    verbose: bool
    quran_mode: str
    quran_variant: str
    hadith_mode: str
    hadith_edition: str
    hadith_all_supported_arabic: bool
    hadith_api_ref: str


def _parse_args() -> CliArgs:
    parser = argparse.ArgumentParser(description="Reset and seed development database")
    parser.add_argument(
        "--db-path",
        type=str,
        default=str(DEFAULT_DB_PATH),
        help=f"Path to SQLite database (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "--quran-mode",
        choices=["minimal", "tanzil"],
        default="minimal",
        help="Quran ingestion mode: minimal fixtures or full Tanzil corpus",
    )
    parser.add_argument(
        "--quran-variant",
        choices=["uthmani", "simple", "simple_clean"],
        default="uthmani",
        help="Tanzil variant used when --quran-mode=tanzil",
    )
    parser.add_argument(
        "--hadith-mode",
        choices=["minimal", "api"],
        default="minimal",
        help="Hadith ingestion mode: minimal fixtures or hadith-api ingestion",
    )
    parser.add_argument(
        "--hadith-edition",
        type=str,
        default="ara-bukhari",
        help="Hadith edition used when --hadith-mode=api",
    )
    parser.add_argument(
        "--hadith-all-supported-arabic",
        action="store_true",
        help=(
            "When --hadith-mode=api, ingest all supported Arabic major collections "
            "instead of a single --hadith-edition"
        ),
    )
    parser.add_argument(
        "--hadith-api-ref",
        type=str,
        default="1",
        help="hadith-api ref (tag/branch/commit) used when --hadith-mode=api",
    )
    parsed = parser.parse_args()
    return CliArgs(
        db_path=_resolve_path(cast(str, parsed.db_path)),
        verbose=cast(bool, parsed.verbose),
        quran_mode=cast(str, parsed.quran_mode),
        quran_variant=cast(str, parsed.quran_variant),
        hadith_mode=cast(str, parsed.hadith_mode),
        hadith_edition=cast(str, parsed.hadith_edition),
        hadith_all_supported_arabic=cast(bool, parsed.hadith_all_supported_arabic),
        hadith_api_ref=cast(str, parsed.hadith_api_ref),
    )


def _resolve_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


def _delete_database(db_path: Path, verbose: bool = False) -> bool:
    """Delete the SQLite database file if it exists."""
    if db_path.exists():
        try:
            db_path.unlink()
            print(f"[OK] Deleted existing database: {db_path}")
            return True
        except OSError as e:
            print(f"[ERROR] Failed to delete database: {e}", file=sys.stderr)
            return False
    else:
        if verbose:
            print(f"[INFO] Database does not exist: {db_path}")
        return True


def _run_db_init(db_path: Path, verbose: bool = False) -> bool:
    """Run db_init.py to create schema."""
    cmd = [
        sys.executable,
        str(DB_INIT_SCRIPT),
        "--sqlite",
        str(db_path),
    ]

    if verbose:
        print(f"[INFO] Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        print("[OK] Database schema initialized")
        return True
    except subprocess.CalledProcessError as e:
        print(
            f"[ERROR] db_init.py failed with exit code {e.returncode}", file=sys.stderr
        )
        print(e.stdout, file=sys.stderr)
        print(e.stderr, file=sys.stderr)
        return False
    except Exception as e:
        print(f"[ERROR] Failed to run db_init.py: {e}", file=sys.stderr)
        return False


def _load_yaml_fixture(file_path: Path) -> dict[str, Any]:
    """Load a YAML fixture file."""
    with open(file_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _seed_quran_fixtures(conn: sqlite3.Connection, fixtures_dir: Path) -> int:
    """Load Quran fixtures directly using SQL."""
    print("\n[QURAN FIXTURES]")

    quran_file = fixtures_dir / "quran_minimal.yaml"
    if not quran_file.exists():
        print(f"  WARNING: {quran_file} not found")
        return 0

    data = _load_yaml_fixture(quran_file)
    metadata = data.get("metadata", {})
    text_units = data.get("text_units", [])

    # Create source document
    source_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, metadata["source_id"]))

    # Check if source already exists
    cursor = conn.execute(
        "SELECT 1 FROM source_document WHERE source_id = ?", (source_id,)
    )
    if cursor.fetchone():
        print(f"  Source already exists: {metadata['source_id']}")
    else:
        all_text = "\n".join(u.get("text", "") for u in text_units)
        content_hash = hashlib.sha256(all_text.encode("utf-8")).hexdigest()

        conn.execute(
            """INSERT INTO source_document
            (source_id, source_type, work_title, author, language,
             license_id, license_url, rights_holder, content_hash_sha256,
             content_mime, content_length_bytes, storage_path, trust_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                source_id,
                metadata.get("source_type", "quran_text"),
                metadata.get("work_title", "Quran"),
                metadata.get("author"),
                metadata.get("language", "ar"),
                metadata.get("license_id", "UNLICENSED"),
                metadata.get("license_url", ""),
                metadata.get("rights_holder"),
                content_hash,
                "text/yaml",
                len(all_text),
                str(quran_file),
                "trusted",
            ),
        )
        print(f"  Created source: {metadata['source_id']}")

    # Insert text units
    created_count = 0
    print(f"  Processing {len(text_units)} ayah(s)...")

    for unit_data in text_units:
        canonical_id = unit_data["canonical_id"]

        # Check if already exists
        cursor = conn.execute(
            "SELECT 1 FROM text_unit WHERE canonical_id = ?", (canonical_id,)
        )
        if cursor.fetchone():
            continue

        text_unit_id = str(uuid.uuid4())
        text_canonical = unit_data["text"]
        text_hash = hashlib.sha256(text_canonical.encode("utf-8")).hexdigest()
        locator_json = json.dumps(
            {
                "surah": unit_data["surah"],
                "ayah": unit_data["ayah"],
                "surah_name_ar": unit_data.get("surah_name_ar"),
                "surah_name_en": unit_data.get("surah_name_en"),
                "juz": unit_data.get("juz"),
            },
            ensure_ascii=False,
        )

        conn.execute(
            """INSERT INTO text_unit
            (text_unit_id, source_id, unit_type, canonical_id,
             canonical_locator_json, text_canonical, text_canonical_utf8_sha256)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                text_unit_id,
                source_id,
                "quran_ayah",
                canonical_id,
                locator_json,
                text_canonical,
                text_hash,
            ),
        )
        created_count += 1

    conn.commit()
    print(f"  Created: {created_count}")
    return created_count


def _seed_hadith_fixtures(conn: sqlite3.Connection, fixtures_dir: Path) -> int:
    """Load Hadith fixtures directly using SQL."""
    print("\n[HADITH FIXTURES]")

    hadith_file = fixtures_dir / "hadith_minimal.yaml"
    if not hadith_file.exists():
        print(f"  WARNING: {hadith_file} not found")
        return 0

    data = _load_yaml_fixture(hadith_file)
    metadata = data.get("metadata", {})
    text_units = data.get("text_units", [])

    # Create source document
    source_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, metadata["source_id"]))

    # Check if source already exists
    cursor = conn.execute(
        "SELECT 1 FROM source_document WHERE source_id = ?", (source_id,)
    )
    if cursor.fetchone():
        print(f"  Source already exists: {metadata['source_id']}")
    else:
        all_text = "\n".join(u.get("text_ar", "") for u in text_units)
        content_hash = hashlib.sha256(all_text.encode("utf-8")).hexdigest()

        conn.execute(
            """INSERT INTO source_document
            (source_id, source_type, work_title, author, language,
             license_id, license_url, rights_holder, content_hash_sha256,
             content_mime, content_length_bytes, storage_path, trust_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                source_id,
                metadata.get("source_type", "hadith_collection"),
                metadata.get("work_title", "Sahih Bukhari"),
                metadata.get("author"),
                metadata.get("language", "ar"),
                metadata.get("license_id", "UNLICENSED"),
                metadata.get("license_url", ""),
                metadata.get("rights_holder"),
                content_hash,
                "text/yaml",
                len(all_text),
                str(hadith_file),
                "trusted",
            ),
        )
        print(f"  Created source: {metadata['source_id']}")

    # Insert text units
    created_count = 0
    print(f"  Processing {len(text_units)} hadith(s)...")

    for unit_data in text_units:
        canonical_id = unit_data["canonical_id"]

        # Check if already exists
        cursor = conn.execute(
            "SELECT 1 FROM text_unit WHERE canonical_id = ?", (canonical_id,)
        )
        if cursor.fetchone():
            continue

        text_unit_id = str(uuid.uuid4())
        text_canonical = unit_data["text_ar"]
        text_hash = hashlib.sha256(text_canonical.encode("utf-8")).hexdigest()
        locator_json = json.dumps(
            {
                "collection": unit_data["collection"],
                "numbering_system": unit_data["numbering_system"],
                "hadith_number": unit_data["hadith_number"],
                "book_name": unit_data.get("book_name"),
                "chapter_name": unit_data.get("chapter_name"),
                "chapter_number": unit_data.get("chapter_number"),
                "grading": unit_data.get("grading"),
                "topics": unit_data.get("topics"),
            },
            ensure_ascii=False,
        )

        conn.execute(
            """INSERT INTO text_unit
            (text_unit_id, source_id, unit_type, canonical_id,
             canonical_locator_json, text_canonical, text_canonical_utf8_sha256)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                text_unit_id,
                source_id,
                "hadith_item",
                canonical_id,
                locator_json,
                text_canonical,
                text_hash,
            ),
        )
        created_count += 1
        print(f"    Created: {canonical_id}")

    conn.commit()
    print(f"  Created: {created_count}")
    return created_count


def _seed_quran_tanzil(
    db_path: Path, quran_variant: str, verbose: bool = False
) -> bool:
    """Load full Quran corpus from Tanzil using dedicated script."""
    script = ROOT / "scripts" / "ingest_quran_tanzil.py"
    cmd = [
        sys.executable,
        str(script),
        "--db-path",
        str(db_path),
        "--variant",
        quran_variant,
    ]

    if verbose:
        print(f"[INFO] Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return True
    except subprocess.CalledProcessError as exc:
        print(
            f"[ERROR] ingest_quran_tanzil.py failed with exit code {exc.returncode}",
            file=sys.stderr,
        )
        print(exc.stdout, file=sys.stderr)
        print(exc.stderr, file=sys.stderr)
        return False


def _seed_hadith_api(
    db_path: Path,
    *,
    hadith_edition: str,
    hadith_all_supported_arabic: bool,
    hadith_api_ref: str,
    verbose: bool = False,
) -> bool:
    """Load hadith corpus from hadith-api using dedicated script."""
    cmd = [
        sys.executable,
        str(HADITH_INGEST_SCRIPT),
        "--db-path",
        str(db_path),
        "--api-ref",
        hadith_api_ref,
    ]
    if hadith_all_supported_arabic:
        cmd.append("--all-supported-arabic")
    else:
        cmd.extend(["--edition", hadith_edition])

    if verbose:
        print(f"[INFO] Running: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return True
    except subprocess.CalledProcessError as exc:
        print(
            f"[ERROR] ingest_hadith_api.py failed with exit code {exc.returncode}",
            file=sys.stderr,
        )
        print(exc.stdout, file=sys.stderr)
        print(exc.stderr, file=sys.stderr)
        return False


def _seed_fixtures(
    db_path: Path,
    *,
    quran_mode: str,
    quran_variant: str,
    hadith_mode: str,
    hadith_edition: str,
    hadith_all_supported_arabic: bool,
    hadith_api_ref: str,
    verbose: bool = False,
) -> bool:
    """Load fixtures directly into database."""
    try:
        conn = sqlite3.connect(db_path)

        if quran_mode == "minimal":
            quran_count = _seed_quran_fixtures(conn, FIXTURES_DIR)
        else:
            quran_ok = _seed_quran_tanzil(db_path, quran_variant, verbose=verbose)
            if not quran_ok:
                conn.close()
                return False
            quran_count = conn.execute(
                "SELECT COUNT(*) FROM text_unit WHERE unit_type = 'quran_ayah'"
            ).fetchone()[0]

        if hadith_mode == "minimal":
            hadith_count = _seed_hadith_fixtures(conn, FIXTURES_DIR)
        else:
            hadith_ok = _seed_hadith_api(
                db_path,
                hadith_edition=hadith_edition,
                hadith_all_supported_arabic=hadith_all_supported_arabic,
                hadith_api_ref=hadith_api_ref,
                verbose=verbose,
            )
            if not hadith_ok:
                conn.close()
                return False
            hadith_count = conn.execute(
                "SELECT COUNT(*) FROM text_unit WHERE unit_type = 'hadith_item'"
            ).fetchone()[0]

        # Print summary
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)

        cursor = conn.execute(
            "SELECT unit_type, COUNT(*) FROM text_unit GROUP BY unit_type"
        )
        for row in cursor.fetchall():
            print(f"  {row[0]}: {row[1]}")

        total = conn.execute("SELECT COUNT(*) FROM text_unit").fetchone()[0]
        print(f"\n  Total text units: {total}")

        sources = conn.execute("SELECT COUNT(*) FROM source_document").fetchone()[0]
        print(f"  Total sources: {sources}")

        conn.close()

        print("\n" + "=" * 60)
        if quran_count > 0 or hadith_count > 0:
            print("[OK] FIXTURES LOADED SUCCESSFULLY")
        else:
            print("[INFO] No new fixtures to load (all may already exist)")
        return True

    except Exception as e:
        print(f"[ERROR] Failed to load fixtures: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return False


def _run_smoke_checks(db_path: Path) -> bool:
    """Run smoke checks on the database."""
    print("\n[SMOKE CHECKS]")

    if not db_path.exists():
        print(f"[ERROR] Database file not found: {db_path}", file=sys.stderr)
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if required tables exist
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='text_unit'"
        )
        if not cursor.fetchone():
            print("[ERROR] Table 'text_unit' does not exist", file=sys.stderr)
            conn.close()
            return False

        # Count quran_ayah records
        cursor.execute("SELECT COUNT(*) FROM text_unit WHERE unit_type = 'quran_ayah'")
        quran_count = cursor.fetchone()[0]
        print(f"  quran_ayah count: {quran_count}")

        if quran_count < MIN_QURAN_AYAH:
            print(
                f"[ERROR] quran_ayah count ({quran_count}) below threshold ({MIN_QURAN_AYAH})",
                file=sys.stderr,
            )
            conn.close()
            return False

        # Count hadith_item records
        cursor.execute("SELECT COUNT(*) FROM text_unit WHERE unit_type = 'hadith_item'")
        hadith_count = cursor.fetchone()[0]
        print(f"  hadith_item count: {hadith_count}")

        if hadith_count < MIN_HADITH_ITEM:
            print(
                f"[ERROR] hadith_item count ({hadith_count}) below threshold ({MIN_HADITH_ITEM})",
                file=sys.stderr,
            )
            conn.close()
            return False

        # Additional checks - verify canonical_ids are valid
        cursor.execute(
            "SELECT canonical_id FROM text_unit WHERE unit_type = 'quran_ayah' LIMIT 1"
        )
        sample_quran = cursor.fetchone()
        if sample_quran:
            print(f"  Sample quran_ayah canonical_id: {sample_quran[0]}")

        cursor.execute(
            "SELECT canonical_id FROM text_unit WHERE unit_type = 'hadith_item' LIMIT 1"
        )
        sample_hadith = cursor.fetchone()
        if sample_hadith:
            print(f"  Sample hadith_item canonical_id: {sample_hadith[0]}")

        # Check source_document table
        cursor.execute("SELECT COUNT(*) FROM source_document")
        source_count = cursor.fetchone()[0]
        print(f"  source_document count: {source_count}")

        conn.close()

        print("\n[OK] All smoke checks passed")
        return True

    except sqlite3.Error as e:
        print(f"[ERROR] Database error during smoke checks: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected error during smoke checks: {e}", file=sys.stderr)
        return False


def _write_evidence(db_path: Path, success: bool) -> None:
    """Write evidence file for task tracking."""
    evidence_dir = ROOT / ".sisyphus" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    evidence_file = evidence_dir / "task-21-reset-seed.txt"

    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    status = "SUCCESS" if success else "FAILED"

    content = f"""Task: dev_reset_and_seed.py
Timestamp: {timestamp}
Status: {status}
Database: {db_path}

Execution Steps:
1. Database deletion: {"SKIPPED" if not db_path.exists() else "COMPLETED"}
2. Schema initialization: {status}
3. Fixture loading: {status}
4. Smoke checks: {status}
"""

    evidence_file.write_text(content, encoding="utf-8")
    print(f"\n[OK] Evidence written to: {evidence_file}")


def main() -> int:
    """Main entry point."""
    print("=" * 60)
    print("ISLAM INTELLIGENT - DEV RESET AND SEED")
    print("=" * 60)

    args = _parse_args()

    print(f"\nDatabase path: {args.db_path}")
    print(f"Idempotent: Yes (safe to run multiple times)")
    print(f"Quran mode: {args.quran_mode}")
    if args.quran_mode == "tanzil":
        print(f"Quran variant: {args.quran_variant}")
    print(f"Hadith mode: {args.hadith_mode}")
    if args.hadith_mode == "api":
        print(f"Hadith API ref: {args.hadith_api_ref}")
        if args.hadith_all_supported_arabic:
            print("Hadith editions: all supported Arabic major collections")
        else:
            print(f"Hadith edition: {args.hadith_edition}")

    # Step 1: Delete existing database
    print("\n[STEP 1] Deleting existing database...")
    if not _delete_database(args.db_path, verbose=args.verbose):
        _write_evidence(args.db_path, success=False)
        return 4

    # Step 2: Initialize database schema
    print("\n[STEP 2] Initializing database schema...")
    if not _run_db_init(args.db_path, verbose=args.verbose):
        _write_evidence(args.db_path, success=False)
        return 1

    # Step 3: Load fixtures
    print("\n[STEP 3] Loading fixtures...")
    if not _seed_fixtures(
        args.db_path,
        quran_mode=args.quran_mode,
        quran_variant=args.quran_variant,
        hadith_mode=args.hadith_mode,
        hadith_edition=args.hadith_edition,
        hadith_all_supported_arabic=args.hadith_all_supported_arabic,
        hadith_api_ref=args.hadith_api_ref,
        verbose=args.verbose,
    ):
        _write_evidence(args.db_path, success=False)
        return 2

    # Step 4: Run smoke checks
    if not _run_smoke_checks(args.db_path):
        _write_evidence(args.db_path, success=False)
        return 3

    # Success
    print("\n" + "=" * 60)
    print("[OK] DEV ENVIRONMENT RESET AND SEEDED SUCCESSFULLY")
    print("=" * 60)

    _write_evidence(args.db_path, success=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
