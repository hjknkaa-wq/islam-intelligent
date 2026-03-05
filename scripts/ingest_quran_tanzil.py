#!/usr/bin/env python3
"""Ingest full Quran text from SAFE Tanzil source into SQLite.

This script preserves Tanzil text verbatim and inserts Quran ayat into
`text_unit` with canonical IDs (`quran:{surah}:{ayah}`). It is idempotent and
supports checkpoint/resume for long-running ingestion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / ".local" / "dev.db"
DEFAULT_CHECKPOINT = ROOT / ".local" / "quran_tanzil_checkpoint.json"

TANZIL_VARIANTS = {
    "uthmani": {
        "source_key": "tanzil_quran_text_uthmani",
        "quran_type": "uthmani",
        "work_title": "Tanzil Quran Text (Uthmani)",
    },
    "simple": {
        "source_key": "tanzil_quran_text_simple",
        "quran_type": "simple",
        "work_title": "Tanzil Quran Text (Simple)",
    },
    "simple_clean": {
        "source_key": "tanzil_quran_text_simple_clean",
        "quran_type": "simple-clean",
        "work_title": "Tanzil Quran Text (Simple Clean)",
    },
}


@dataclass(frozen=True)
class CliArgs:
    db_path: Path
    variant: str
    batch_size: int
    timeout_sec: int
    checkpoint_file: Path
    resume: bool


def _parse_args() -> CliArgs:
    parser = argparse.ArgumentParser(
        description="Ingest full Quran corpus from Tanzil into SQLite"
    )
    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
        help=f"SQLite DB path (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--variant",
        choices=sorted(TANZIL_VARIANTS.keys()),
        default="uthmani",
        help="Tanzil text variant",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Commit every N processed ayat",
    )
    parser.add_argument(
        "--timeout-sec",
        type=int,
        default=60,
        help="HTTP timeout in seconds",
    )
    parser.add_argument(
        "--checkpoint-file",
        default=str(DEFAULT_CHECKPOINT),
        help=f"Checkpoint file path (default: {DEFAULT_CHECKPOINT})",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from checkpoint (if present)",
    )
    args = parser.parse_args()

    db_path = Path(args.db_path).expanduser().resolve()
    checkpoint = Path(args.checkpoint_file).expanduser().resolve()
    return CliArgs(
        db_path=db_path,
        variant=args.variant,
        batch_size=args.batch_size,
        timeout_sec=args.timeout_sec,
        checkpoint_file=checkpoint,
        resume=args.resume,
    )


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _build_tanzil_url(quran_type: str) -> str:
    params = {
        "quranType": quran_type,
        "outType": "txt-2",
        "agree": "true",
        "marks": "true",
        "sajdah": "true",
        "tatweel": "true",
    }
    return "https://tanzil.net/pub/download/index.php?" + urlencode(params)


def _download_tanzil_text(url: str, timeout_sec: int) -> str:
    with urlopen(url, timeout=timeout_sec) as response:  # noqa: S310
        payload = response.read()
    return payload.decode("utf-8")


def _parse_tanzil_line(raw_line: str) -> tuple[int, int, str] | None:
    line = raw_line.strip()
    if not line or line.startswith("#"):
        return None

    parts = line.split("|", 2)
    if len(parts) != 3:
        return None

    try:
        surah = int(parts[0])
        ayah = int(parts[1])
    except ValueError:
        return None

    text = parts[2]
    if not text:
        return None

    return surah, ayah, text


def _load_checkpoint(checkpoint_file: Path) -> tuple[int, int] | None:
    if not checkpoint_file.exists():
        return None
    try:
        payload = json.loads(checkpoint_file.read_text(encoding="utf-8"))
        surah = int(payload["last_surah"])
        ayah = int(payload["last_ayah"])
        return surah, ayah
    except Exception:
        return None


def _write_checkpoint(checkpoint_file: Path, surah: int, ayah: int) -> None:
    checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_file.write_text(
        json.dumps({"last_surah": surah, "last_ayah": ayah}, indent=2),
        encoding="utf-8",
    )


def _checkpoint_exists_in_db(
    conn: sqlite3.Connection, checkpoint: tuple[int, int] | None
) -> bool:
    if checkpoint is None:
        return False
    canonical_id = f"quran:{checkpoint[0]}:{checkpoint[1]}"
    row = conn.execute(
        "SELECT 1 FROM text_unit WHERE canonical_id = ?", (canonical_id,)
    ).fetchone()
    return row is not None


def _canonical_exists(conn: sqlite3.Connection, canonical_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM text_unit WHERE canonical_id = ?", (canonical_id,)
    ).fetchone()
    return row is not None


def _ensure_source_document(
    conn: sqlite3.Connection,
    *,
    source_key: str,
    work_title: str,
    source_url: str,
    content_hash: str,
    content_length: int,
) -> str:
    source_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, source_key))
    existing = conn.execute(
        "SELECT 1 FROM source_document WHERE source_id = ?", (source_id,)
    ).fetchone()
    if existing:
        return source_id

    conn.execute(
        """INSERT INTO source_document
        (source_id, source_type, work_title, author, language,
         license_id, license_url, rights_holder, attribution_text,
         content_hash_sha256, content_mime, content_length_bytes,
         storage_path, trust_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            source_id,
            "quran_text",
            work_title,
            "Tanzil Project",
            "ar",
            "CC-BY-3.0",
            "https://tanzil.net/docs/text_license",
            "Tanzil Project",
            (
                "Tanzil Quran Text Copyright (C) 2007-2021 Tanzil Project; "
                "verbatim distribution only; source: https://tanzil.net"
            ),
            content_hash,
            "text/plain; charset=utf-8",
            content_length,
            source_url,
            "trusted",
        ),
    )
    return source_id


def ingest_quran_from_tanzil(args: CliArgs) -> tuple[int, int]:
    if not args.db_path.exists():
        raise FileNotFoundError(f"Database not found: {args.db_path}")

    variant = TANZIL_VARIANTS[args.variant]
    source_url = _build_tanzil_url(variant["quran_type"])
    raw_text = _download_tanzil_text(source_url, args.timeout_sec)
    source_hash = _sha256(raw_text)

    conn = sqlite3.connect(args.db_path)
    created = 0
    skipped = 0
    processed = 0
    last_seen: tuple[int, int] | None = None

    try:
        checkpoint = _load_checkpoint(args.checkpoint_file) if args.resume else None
        if checkpoint is not None and not _checkpoint_exists_in_db(conn, checkpoint):
            checkpoint = None
        resume_found = checkpoint is None

        source_id = _ensure_source_document(
            conn,
            source_key=variant["source_key"],
            work_title=variant["work_title"],
            source_url=source_url,
            content_hash=source_hash,
            content_length=len(raw_text.encode("utf-8")),
        )

        lines = raw_text.splitlines()
        for raw_line in lines:
            parsed = _parse_tanzil_line(raw_line)
            if parsed is None:
                continue

            surah, ayah, text = parsed
            canonical_id = f"quran:{surah}:{ayah}"

            if checkpoint is not None and not resume_found:
                if not _canonical_exists(conn, canonical_id):
                    resume_found = True
                elif (surah, ayah) == checkpoint:
                    resume_found = True
                    continue
                else:
                    continue

            locator = json.dumps({"surah": surah, "ayah": ayah}, ensure_ascii=False)
            text_unit_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, canonical_id))
            text_verbatim = unicodedata.normalize("NFC", text)
            text_hash = _sha256(text_verbatim)

            before = conn.total_changes
            conn.execute(
                """INSERT OR IGNORE INTO text_unit
                (text_unit_id, source_id, unit_type, canonical_id,
                 canonical_locator_json, text_canonical, text_canonical_utf8_sha256)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    text_unit_id,
                    source_id,
                    "quran_ayah",
                    canonical_id,
                    locator,
                    text_verbatim,
                    text_hash,
                ),
            )
            if conn.total_changes > before:
                created += 1
            else:
                skipped += 1

            processed += 1
            last_seen = (surah, ayah)

            if processed % args.batch_size == 0:
                conn.commit()
                if last_seen is not None:
                    _write_checkpoint(args.checkpoint_file, last_seen[0], last_seen[1])

        conn.commit()
        if last_seen is not None:
            _write_checkpoint(args.checkpoint_file, last_seen[0], last_seen[1])
    finally:
        conn.close()

    return created, skipped


def main() -> int:
    args = _parse_args()
    print("=" * 60)
    print("ISLAM INTELLIGENT - TANZIL QURAN INGEST")
    print("=" * 60)
    print(f"Database: {args.db_path}")
    print(f"Variant: {args.variant}")
    print(f"Resume: {args.resume}")

    try:
        created, skipped = ingest_quran_from_tanzil(args)
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    except URLError as exc:
        print(
            f"[ERROR] Network error while fetching Tanzil data: {exc}", file=sys.stderr
        )
        return 2
    except sqlite3.Error as exc:
        print(f"[ERROR] Database error: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"[ERROR] Unexpected failure: {exc}", file=sys.stderr)
        return 4

    print(f"[OK] Ingestion complete. Created: {created}, Skipped: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
