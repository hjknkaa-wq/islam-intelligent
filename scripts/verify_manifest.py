#!/usr/bin/env python3
"""Verify source document storage paths and content hashes.

This script verifies that each `source_document.storage_path` exists and that
`source_document.content_hash_sha256` matches the canonical content derived
from that storage file.

It is schema-aligned with `packages/schemas/sql/*.sql` (SQLite or Postgres).

Usage:
  python scripts/verify_manifest.py --all --db-path ./.local/dev.db
  python scripts/verify_manifest.py --source-id <uuid> --db-url <db_url>

Exit codes:
  0 - all sources verified
  1 - one or more sources failed verification
  2 - database/configuration error
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml
from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / ".local" / "dev.db"


def _sha256_hex_utf8(text_value: str) -> str:
    return hashlib.sha256(text_value.encode("utf-8")).hexdigest()


def _sqlite_url(db_path: Path) -> str:
    return f"sqlite+pysqlite:///{db_path.as_posix()}"


def _resolve_db_url(db_path: Path, db_url: str | None) -> str:
    if db_url and db_url.strip():
        return db_url.strip()
    return _sqlite_url(db_path)


def _resolve_storage_path(raw: str) -> Path:
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    return p


def _extract_canonical_text_from_yaml(doc: object) -> str:
    if not isinstance(doc, dict):
        return ""
    doc_map = cast(dict[str, object], doc)
    units_obj = doc_map.get("text_units")
    if not isinstance(units_obj, list):
        return ""

    parts: list[str] = []
    units = cast(list[object], units_obj)
    for item_obj in units:
        if not isinstance(item_obj, dict):
            continue
        item = cast(dict[str, object], item_obj)
        v_obj: object | None = item.get("text")
        if not isinstance(v_obj, str) or not v_obj.strip():
            v_obj = item.get("text_ar")
        if not isinstance(v_obj, str) or not v_obj.strip():
            v_obj = item.get("text_canonical")
        if isinstance(v_obj, str) and v_obj:
            parts.append(v_obj)
    return "\n".join(parts)


def _canonical_content_sha256(storage_path: Path) -> tuple[str | None, str | None]:
    """Returns (sha256_hex, error)."""
    try:
        if storage_path.suffix.lower() in {".yaml", ".yml"}:
            raw = storage_path.read_text(encoding="utf-8")
            parsed = cast(object, yaml.safe_load(raw))
            text_value = _extract_canonical_text_from_yaml(parsed)
            if text_value:
                return _sha256_hex_utf8(text_value), None
            # Fall back to hashing the full file if structure is unexpected.
            return _sha256_hex_utf8(raw), None

        raw_text = storage_path.read_text(encoding="utf-8")
        return _sha256_hex_utf8(raw_text), None
    except UnicodeDecodeError:
        try:
            data = storage_path.read_bytes()
            return hashlib.sha256(data).hexdigest(), None
        except Exception as e:
            return None, f"read_bytes_failed:{type(e).__name__}:{e}"
    except Exception as e:
        return None, f"read_failed:{type(e).__name__}:{e}"


@dataclass(frozen=True)
class SourceRow:
    source_id: str
    source_type: str
    storage_path: str
    content_hash_sha256: str


def _fetch_sources(db_url: str, *, source_id: str | None) -> list[SourceRow]:
    engine = create_engine(db_url, future=True)
    stmt = (
        "SELECT source_id, source_type, storage_path, content_hash_sha256 "
        "FROM source_document"
    )
    params: dict[str, object] = {}
    if source_id:
        stmt += " WHERE source_id = :source_id"
        params["source_id"] = source_id

    with engine.connect() as conn:
        rows = conn.execute(text(stmt), params).mappings().all()

    out: list[SourceRow] = []
    for r in rows:
        out.append(
            SourceRow(
                source_id=str(r.get("source_id")),
                source_type=str(r.get("source_type")),
                storage_path=str(r.get("storage_path")),
                content_hash_sha256=str(r.get("content_hash_sha256")),
            )
        )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify source storage + content hashes"
    )
    _ = parser.add_argument("--all", action="store_true", help="Verify all sources")
    _ = parser.add_argument(
        "--source-id", type=str, default=None, help="Verify a single source_id"
    )
    _ = parser.add_argument(
        "--db-path",
        type=str,
        default=str(DEFAULT_DB_PATH),
        help=f"SQLite file path (default: {DEFAULT_DB_PATH})",
    )
    _ = parser.add_argument(
        "--db-url",
        type=str,
        default=None,
        help="Optional SQLAlchemy database URL override",
    )
    args_ns = parser.parse_args(argv)

    verify_all = cast(bool, getattr(args_ns, "all"))
    source_id = cast(str | None, getattr(args_ns, "source_id"))
    db_path_raw = cast(str, getattr(args_ns, "db_path"))
    db_url_raw = cast(str | None, getattr(args_ns, "db_url"))

    if not verify_all and not source_id:
        parser.error("Must specify either --all or --source-id")

    db_path = Path(db_path_raw).expanduser()
    if not db_path.is_absolute():
        db_path = (Path.cwd() / db_path).resolve()
    db_url = _resolve_db_url(db_path, db_url_raw)

    try:
        sources = _fetch_sources(db_url, source_id=source_id)
    except Exception as e:
        print(
            f"ERROR: Failed to query database: {type(e).__name__}: {e}", file=sys.stderr
        )
        return 2

    if not sources:
        print("No sources found in database.")
        return 0

    print(f"Verifying {len(sources)} source(s)...")
    print()

    all_ok = True
    for s in sources:
        errors: list[str] = []
        storage_path = _resolve_storage_path(s.storage_path)
        if not storage_path.exists():
            errors.append(f"missing_storage_path:{storage_path}")
        else:
            computed, err = _canonical_content_sha256(storage_path)
            if err is not None:
                errors.append(err)
            elif computed is None:
                errors.append("hash_compute_failed")
            elif computed != s.content_hash_sha256:
                errors.append(
                    f"content_hash_mismatch expected={s.content_hash_sha256} got={computed}"
                )

        if errors:
            all_ok = False
            print(f"  {s.source_id}: [FAIL] ({s.source_type})")
            for e in errors:
                print(f"    - {e}")
        else:
            print(f"  {s.source_id}: [OK] ({s.source_type})")

    print()
    if all_ok:
        print("All source storage paths and content hashes are valid.")
        return 0
    print("One or more sources failed verification.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
