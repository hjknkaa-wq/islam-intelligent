#!/usr/bin/env python3
"""Ingest hadith corpus from SAFE hadith-api source into SQLite.

This script inserts hadith items into `text_unit` with canonical IDs
(`hadith:{collection}:{numbering_system}:{hadith_number}`), creates
`source_document` records with provenance fields, and supports
checkpoint/resume for long-running ingestion.
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
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / ".local" / "dev.db"
DEFAULT_CHECKPOINT = ROOT / ".local" / "hadith_api_checkpoint.json"
LICENSE_AUDIT_PATH = ROOT / "sources" / "LICENSE_AUDIT.md"

SUPPORTED_COLLECTIONS = {
    "bukhari",
    "muslim",
    "abudawud",
    "tirmidhi",
    "nasai",
    "ibnmajah",
    "malik",
    "ahmad",
}

COLLECTION_NUMBERING_SYSTEM = {
    "bukhari": "sahih",
    "muslim": "sahih",
    "abudawud": "standard",
    "tirmidhi": "standard",
    "nasai": "standard",
    "ibnmajah": "standard",
    "malik": "standard",
    "ahmad": "standard",
}

LANGUAGE_CODE_MAP = {
    "ara": "ar",
    "eng": "en",
    "ind": "id",
    "urd": "ur",
    "tur": "tr",
    "fra": "fr",
    "ben": "bn",
    "tam": "ta",
    "rus": "ru",
}

MAJOR_COLLECTION_ORDER = [
    "bukhari",
    "muslim",
    "abudawud",
    "tirmidhi",
    "nasai",
    "ibnmajah",
    "malik",
    "ahmad",
]


@dataclass(frozen=True)
class CliArgs:
    db_path: Path
    editions: list[str]
    all_supported_arabic: bool
    api_ref: str
    batch_size: int
    timeout_sec: int
    checkpoint_file: Path
    resume: bool


def _parse_args() -> CliArgs:
    parser = argparse.ArgumentParser(
        description="Ingest full hadith corpus from hadith-api into SQLite"
    )
    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
        help=f"SQLite DB path (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--edition",
        action="append",
        default=[],
        help=(
            "Edition identifier (repeatable). Example: --edition ara-bukhari "
            "or --edition ara-bukhari,ara-muslim"
        ),
    )
    parser.add_argument(
        "--all-supported-arabic",
        action="store_true",
        help=(
            "Discover and ingest Arabic editions for supported major collections "
            "(bukhari, muslim, abudawud, tirmidhi, nasai, ibnmajah, malik, ahmad if available)"
        ),
    )
    parser.add_argument(
        "--api-ref",
        default="1",
        help=("hadith-api ref used in jsDelivr URL (tag/branch/commit). Default: 1"),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Commit every N processed hadith items",
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

    parsed = parser.parse_args()
    if parsed.batch_size < 1:
        parser.error("--batch-size must be >= 1")

    db_path = Path(parsed.db_path).expanduser().resolve()
    checkpoint = Path(parsed.checkpoint_file).expanduser().resolve()

    editions = _normalize_edition_args(parsed.edition)
    if not editions and not parsed.all_supported_arabic:
        editions = ["ara-bukhari"]

    return CliArgs(
        db_path=db_path,
        editions=editions,
        all_supported_arabic=parsed.all_supported_arabic,
        api_ref=parsed.api_ref,
        batch_size=parsed.batch_size,
        timeout_sec=parsed.timeout_sec,
        checkpoint_file=checkpoint,
        resume=parsed.resume,
    )


def _normalize_edition_args(raw_editions: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in raw_editions:
        for part in raw.split(","):
            edition = part.strip()
            if not edition:
                continue
            if edition not in seen:
                seen.add(edition)
                normalized.append(edition)
    return normalized


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _build_editions_index_urls(api_ref: str) -> tuple[str, str]:
    min_url = f"https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@{api_ref}/editions.min.json"
    full_url = (
        f"https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@{api_ref}/editions.json"
    )
    return min_url, full_url


def _build_edition_urls(api_ref: str, edition: str) -> tuple[str, str]:
    min_url = f"https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@{api_ref}/editions/{edition}.min.json"
    full_url = f"https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@{api_ref}/editions/{edition}.json"
    return min_url, full_url


def _download_text_with_fallback(
    primary_url: str, fallback_url: str, timeout_sec: int
) -> tuple[str, str]:
    try:
        with urlopen(primary_url, timeout=timeout_sec) as response:  # noqa: S310
            return response.read().decode("utf-8"), primary_url
    except URLError:
        with urlopen(fallback_url, timeout=timeout_sec) as response:  # noqa: S310
            return response.read().decode("utf-8"), fallback_url


def _resolve_collection_from_edition(edition: str) -> str:
    parts = edition.split("-", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid edition format: {edition}")
    collection = parts[1].strip().lower()
    if collection not in SUPPORTED_COLLECTIONS:
        raise ValueError(
            f"Unsupported collection '{collection}' from edition '{edition}'"
        )
    return collection


def _resolve_language_from_edition(edition: str) -> str:
    parts = edition.split("-", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid edition format: {edition}")
    lang_prefix = parts[0].strip().lower()
    if lang_prefix in LANGUAGE_CODE_MAP:
        return LANGUAGE_CODE_MAP[lang_prefix]
    if len(lang_prefix) >= 2 and lang_prefix[:2].isalpha():
        return lang_prefix[:2]
    raise ValueError(f"Cannot derive language code from edition: {edition}")


def _load_checkpoint(checkpoint_file: Path) -> tuple[str, int, str] | None:
    if not checkpoint_file.exists():
        return None
    try:
        payload = json.loads(checkpoint_file.read_text(encoding="utf-8"))
        edition = str(payload["edition"])
        hadith_number = int(payload["last_hadith_number"])
        canonical_id = str(payload["canonical_id"])
        if hadith_number < 1:
            return None
        return edition, hadith_number, canonical_id
    except Exception:
        return None


def _write_checkpoint(
    checkpoint_file: Path, *, edition: str, hadith_number: int, canonical_id: str
) -> None:
    checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_file.write_text(
        json.dumps(
            {
                "edition": edition,
                "last_hadith_number": hadith_number,
                "canonical_id": canonical_id,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _canonical_exists(conn: sqlite3.Connection, canonical_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM text_unit WHERE canonical_id = ?", (canonical_id,)
    ).fetchone()
    return row is not None


def _checkpoint_exists_in_db(conn: sqlite3.Connection, canonical_id: str) -> bool:
    return _canonical_exists(conn, canonical_id)


def _assert_safe_source_policy() -> None:
    if not LICENSE_AUDIT_PATH.exists():
        raise RuntimeError(f"Missing license audit file: {LICENSE_AUDIT_PATH}")

    text = LICENSE_AUDIT_PATH.read_text(encoding="utf-8")
    marker = "#### hadith_api_fawazahmed_v1"
    idx = text.find(marker)
    if idx < 0:
        raise RuntimeError(
            "SAFE source policy missing for hadith_api_fawazahmed_v1 in sources/LICENSE_AUDIT.md"
        )

    window = text[idx : idx + 700]
    if "status: SAFE" not in window:
        raise RuntimeError(
            "hadith_api_fawazahmed_v1 is not marked SAFE in sources/LICENSE_AUDIT.md"
        )


def _ensure_source_document(
    conn: sqlite3.Connection,
    *,
    source_key: str,
    work_title: str,
    language: str,
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
            "hadith_collection",
            work_title,
            "hadith-api contributors",
            language,
            "UNLICENSE",
            "https://raw.githubusercontent.com/fawazahmed0/hadith-api/1/LICENSE",
            "Public domain dedication via The Unlicense",
            (
                "Dataset from fawazahmed0/hadith-api under The Unlicense; "
                "source endpoint pinned by api_ref in ingestion script."
            ),
            content_hash,
            "application/json; charset=utf-8",
            content_length,
            source_url,
            "trusted",
        ),
    )
    return source_id


def _extract_hadith_entries(
    payload: dict[str, object],
    *,
    edition: str,
    collection: str,
    numbering_system: str,
) -> list[tuple[int, str, str, str]]:
    metadata = payload.get("metadata")
    metadata_obj = metadata if isinstance(metadata, dict) else {}
    section_map = metadata_obj.get("section")
    section_obj = section_map if isinstance(section_map, dict) else {}

    hadiths = payload.get("hadiths")
    hadith_list = hadiths if isinstance(hadiths, list) else []

    extracted: list[tuple[int, str, str, str]] = []
    for item in hadith_list:
        if not isinstance(item, dict):
            continue

        raw_number = item.get("hadithnumber")
        if not isinstance(raw_number, (int, str)):
            continue
        try:
            hadith_number = int(raw_number)
        except (TypeError, ValueError):
            continue
        if hadith_number < 1:
            continue

        raw_text = item.get("text")
        if not isinstance(raw_text, str):
            continue
        text = raw_text.strip()
        if not text:
            continue

        canonical_id = f"hadith:{collection}:{numbering_system}:{hadith_number}"

        locator: dict[str, object] = {
            "collection": collection,
            "numbering_system": numbering_system,
            "hadith_number": str(hadith_number),
            "edition": edition,
        }

        reference = item.get("reference")
        reference_obj = reference if isinstance(reference, dict) else {}
        raw_ref_book = reference_obj.get("book")
        raw_ref_hadith = reference_obj.get("hadith")

        if isinstance(raw_ref_book, int) and raw_ref_book > 0:
            locator["chapter_number"] = raw_ref_book
            section_name = section_obj.get(str(raw_ref_book))
            if isinstance(section_name, str) and section_name.strip():
                locator["chapter_name"] = section_name.strip()
        if isinstance(raw_ref_hadith, int) and raw_ref_hadith > 0:
            locator["reference_hadith_number"] = str(raw_ref_hadith)

        grades = item.get("grades")
        if isinstance(grades, list) and grades:
            first_grade = grades[0]
            if isinstance(first_grade, dict):
                raw_grade = first_grade.get("grade")
                if isinstance(raw_grade, str) and raw_grade.strip():
                    locator["grading"] = raw_grade.strip()

        locator_json = json.dumps(locator, ensure_ascii=False)
        extracted.append((hadith_number, canonical_id, text, locator_json))

    extracted.sort(key=lambda entry: entry[0])
    return extracted


def _resolve_all_supported_arabic_editions(api_ref: str, timeout_sec: int) -> list[str]:
    min_url, full_url = _build_editions_index_urls(api_ref)
    body, _ = _download_text_with_fallback(min_url, full_url, timeout_sec)
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("Unexpected editions index payload format")

    available_by_book: dict[str, set[str]] = {}
    for _, book_payload in payload.items():
        if not isinstance(book_payload, dict):
            continue
        collection_entries = book_payload.get("collection")
        if not isinstance(collection_entries, list):
            continue
        for entry in collection_entries:
            if not isinstance(entry, dict):
                continue
            book = entry.get("book")
            edition_name = entry.get("name")
            if not isinstance(book, str) or not isinstance(edition_name, str):
                continue
            available_by_book.setdefault(book, set()).add(edition_name)

    editions: list[str] = []
    for collection in MAJOR_COLLECTION_ORDER:
        if collection not in SUPPORTED_COLLECTIONS:
            continue
        edition_name = f"ara-{collection}"
        if edition_name in available_by_book.get(collection, set()):
            editions.append(edition_name)
    return editions


def _merge_target_editions(args: CliArgs) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()

    for edition in args.editions:
        if edition not in seen:
            seen.add(edition)
            merged.append(edition)

    if args.all_supported_arabic:
        auto = _resolve_all_supported_arabic_editions(args.api_ref, args.timeout_sec)
        for edition in auto:
            if edition not in seen:
                seen.add(edition)
                merged.append(edition)

    if not merged:
        merged.append("ara-bukhari")
    return merged


def ingest_hadith_from_api(args: CliArgs) -> tuple[int, int, int, list[str]]:
    if not args.db_path.exists():
        raise FileNotFoundError(f"Database not found: {args.db_path}")

    _assert_safe_source_policy()
    target_editions = _merge_target_editions(args)

    conn = sqlite3.connect(args.db_path)
    created = 0
    skipped = 0
    processed = 0
    ingested_editions: list[str] = []

    checkpoint = _load_checkpoint(args.checkpoint_file) if args.resume else None
    start_index = 0
    checkpoint_hadith = 0
    if checkpoint is not None:
        checkpoint_edition, hadith_number, canonical_id = checkpoint
        if checkpoint_edition in target_editions and _checkpoint_exists_in_db(
            conn, canonical_id
        ):
            start_index = target_editions.index(checkpoint_edition)
            checkpoint_hadith = hadith_number

    try:
        for edition_index, edition in enumerate(target_editions):
            if edition_index < start_index:
                continue

            collection = _resolve_collection_from_edition(edition)
            numbering_system = COLLECTION_NUMBERING_SYSTEM.get(collection, "standard")
            language = _resolve_language_from_edition(edition)

            min_url, full_url = _build_edition_urls(args.api_ref, edition)
            payload_text, used_url = _download_text_with_fallback(
                min_url, full_url, args.timeout_sec
            )
            payload_obj = json.loads(payload_text)
            if not isinstance(payload_obj, dict):
                raise ValueError(f"Unexpected payload format for edition: {edition}")

            source_key = f"hadith_api_{args.api_ref}_{edition}"
            source_id = _ensure_source_document(
                conn,
                source_key=source_key,
                work_title=f"Hadith API ({edition})",
                language=language,
                source_url=used_url,
                content_hash=_sha256(payload_text),
                content_length=len(payload_text.encode("utf-8")),
            )

            raw_entries = _extract_hadith_entries(
                payload_obj,
                edition=edition,
                collection=collection,
                numbering_system=numbering_system,
            )

            local_checkpoint_hadith = (
                checkpoint_hadith if edition_index == start_index else 0
            )
            for hadith_number, canonical_id, text, locator_json in raw_entries:
                if local_checkpoint_hadith and hadith_number <= local_checkpoint_hadith:
                    if _canonical_exists(conn, canonical_id):
                        continue
                    local_checkpoint_hadith = 0

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
                        "hadith_item",
                        canonical_id,
                        locator_json,
                        text_verbatim,
                        text_hash,
                    ),
                )

                if conn.total_changes > before:
                    created += 1
                else:
                    skipped += 1

                processed += 1
                if processed % args.batch_size == 0:
                    conn.commit()
                    _write_checkpoint(
                        args.checkpoint_file,
                        edition=edition,
                        hadith_number=hadith_number,
                        canonical_id=canonical_id,
                    )

            ingested_editions.append(edition)
            conn.commit()
            if raw_entries:
                last_hadith_number, last_canonical, _, _ = raw_entries[-1]
                _write_checkpoint(
                    args.checkpoint_file,
                    edition=edition,
                    hadith_number=last_hadith_number,
                    canonical_id=last_canonical,
                )
    finally:
        conn.close()

    return created, skipped, processed, ingested_editions


def main() -> int:
    args = _parse_args()
    print("=" * 60)
    print("ISLAM INTELLIGENT - HADITH API INGEST")
    print("=" * 60)
    print(f"Database: {args.db_path}")
    print(f"API ref: {args.api_ref}")
    print(f"Resume: {args.resume}")
    print(f"All supported arabic: {args.all_supported_arabic}")
    if args.editions:
        print(f"Editions: {', '.join(args.editions)}")

    try:
        created, skipped, processed, editions = ingest_hadith_from_api(args)
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    except URLError as exc:
        print(
            f"[ERROR] Network error while fetching hadith-api data: {exc}",
            file=sys.stderr,
        )
        return 2
    except sqlite3.Error as exc:
        print(f"[ERROR] Database error: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"[ERROR] Unexpected failure: {exc}", file=sys.stderr)
        return 4

    editions_text = ", ".join(editions) if editions else "(none)"
    print(
        f"[OK] Ingestion complete. Processed: {processed}, Created: {created}, Skipped: {skipped}"
    )
    print(f"[OK] Editions ingested: {editions_text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
