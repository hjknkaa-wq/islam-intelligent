#!/usr/bin/env python3
"""Toggle source_document.trust_status for a given source.

Primary mode is --first-fixture, which derives the source_id from the first
fixture YAML in data/fixtures/ using the same deterministic UUIDv5 scheme as
scripts/load_fixtures.py.
"""

from __future__ import annotations

import argparse
import sqlite3
import uuid
from pathlib import Path
from typing import Protocol, cast


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / ".local" / "dev.db"
DEFAULT_FIXTURES_DIR = ROOT / "data" / "fixtures"


def _parse_bool(raw: str) -> bool:
    v = raw.strip().lower()
    if v in ("true", "1", "yes", "y", "t"):
        return True
    if v in ("false", "0", "no", "n", "f"):
        return False
    raise argparse.ArgumentTypeError("--trusted must be true/false")


def _first_fixture_path(fixtures_dir: Path) -> Path:
    candidates = sorted(fixtures_dir.glob("*_minimal.yaml"))
    if not candidates:
        candidates = sorted(fixtures_dir.glob("*.yaml"))
    if not candidates:
        raise SystemExit(f"No YAML fixtures found in: {fixtures_dir}")
    return candidates[0]


def _fixture_id_from_yaml(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore[import-untyped]

        raw_obj = cast(object, yaml.safe_load(text))
        if isinstance(raw_obj, dict):
            data = cast(dict[str, object], raw_obj)
            meta_raw = data.get("metadata")
            meta = cast(
                dict[str, object], meta_raw if isinstance(meta_raw, dict) else {}
            )
            fixture_id_raw = meta.get("source_id")
            fixture_id = (
                str(fixture_id_raw).strip() if fixture_id_raw is not None else ""
            )
            if fixture_id:
                return fixture_id
    except ModuleNotFoundError:
        pass

    # Fallback parser (best-effort) to avoid hard dependency on PyYAML.
    in_metadata = False
    meta_indent: int | None = None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue

        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()

        if stripped == "metadata:" or stripped.startswith("metadata: "):
            in_metadata = True
            meta_indent = indent
            continue

        if in_metadata:
            if meta_indent is not None and indent <= meta_indent:
                in_metadata = False
                meta_indent = None
                continue

            if stripped.startswith("source_id:"):
                _, _, rhs = stripped.partition(":")
                value = rhs.strip().strip('"').strip("'")
                if value:
                    return value

    raise SystemExit(f"Fixture missing metadata.source_id: {path}")


def _deterministic_source_id(fixture_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, fixture_id))


def _get_trust_status(conn: sqlite3.Connection, source_id: str) -> str | None:
    cur = conn.cursor()
    _ = cur.execute(
        "SELECT trust_status FROM source_document WHERE source_id = ?", (source_id,)
    )
    row = cast(tuple[object, ...] | None, cur.fetchone())
    if row is None:
        return None
    return str(row[0])


def _update_trust_status(
    conn: sqlite3.Connection, source_id: str, trust_status: str
) -> int:
    cur = conn.cursor()
    _ = cur.execute(
        "UPDATE source_document SET trust_status = ? WHERE source_id = ?",
        (trust_status, source_id),
    )
    return int(cur.rowcount or 0)


class _Args(Protocol):
    first_fixture: bool
    trusted: str
    db_path: str
    fixtures_dir: str


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Toggle a source_document trust status"
    )
    _ = parser.add_argument(
        "--first-fixture",
        action="store_true",
        help="Use the first fixture source (sorted *_minimal.yaml in data/fixtures)",
    )
    _ = parser.add_argument(
        "--trusted",
        nargs="?",
        const="true",
        required=True,
        help="Set trust to true/false (also supports bare --trusted for true)",
    )
    _ = parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
        help="SQLite DB path (default: .local/dev.db)",
    )
    _ = parser.add_argument(
        "--fixtures-dir",
        default=str(DEFAULT_FIXTURES_DIR),
        help="Fixtures directory used with --first-fixture",
    )
    args = cast(_Args, cast(object, parser.parse_args(argv)))

    if not args.first_fixture:
        raise SystemExit("This CLI currently requires --first-fixture")

    fixtures_dir = Path(args.fixtures_dir)
    fixture_path = _first_fixture_path(fixtures_dir)
    fixture_id = _fixture_id_from_yaml(fixture_path)
    source_id = _deterministic_source_id(fixture_id)
    trusted = _parse_bool(str(args.trusted))
    desired = "trusted" if trusted else "untrusted"

    db_path = Path(args.db_path)
    if not db_path.is_absolute():
        db_path = (ROOT / db_path).resolve()
    if not db_path.exists():
        raise SystemExit(f"DB file not found: {db_path}")

    with sqlite3.connect(str(db_path)) as conn:
        before = _get_trust_status(conn, source_id)
        if before is None:
            msg = (
                "source_document not found for fixture source. "
                + f"source_id={source_id} fixture={fixture_path} "
                + "(did you run scripts/db_init.py and scripts/load_fixtures.py?)"
            )
            raise SystemExit(msg)

        updated = _update_trust_status(conn, source_id, desired)
        after = _get_trust_status(conn, source_id)

    print(f"fixture: {fixture_path}")
    print(f"fixture_id: {fixture_id}")
    print(f"source_id: {source_id}")
    print(f"updated_rows: {updated}")
    print(f"trust_status: {before} -> {after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
