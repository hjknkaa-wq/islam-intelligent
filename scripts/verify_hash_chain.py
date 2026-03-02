#!/usr/bin/env python3
"""Verify tamper-evident provenance hash chain integrity.

Checks:
- Each prov_activity.prev_activity_hash matches the previous activity_hash (ordered by started_at, activity_id)
- Each prov_activity.activity_hash matches sha256(canonical_json(activity_record + input_hashes + output_hashes))

Exit codes:
- 0: chain verified
- 1: tampering / mismatch detected
- 2: configuration / connection / schema error
"""

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import cast

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))


def _sqlite_url(db_path: Path) -> str:
    return f"sqlite+pysqlite:///{db_path.as_posix()}"


def _resolve_db_url(cli_db_url: str | None) -> str:
    if cli_db_url:
        return cli_db_url
    env = (os.getenv("DATABASE_URL") or "").strip()
    if env:
        return env
    return _sqlite_url((ROOT / ".local" / "dev.db").resolve())


def _make_engine(db_url: str) -> Engine:
    return create_engine(db_url, future=True)


def _ensure_sqlite_parent_dir(db_url: str) -> None:
    lowered = db_url.lower()
    if ":memory:" in lowered:
        return
    prefixes = ("sqlite+pysqlite:///", "sqlite:///")
    for prefix in prefixes:
        if lowered.startswith(prefix):
            raw_path = db_url[len(prefix) :]
            path = Path(raw_path)
            if path.parent and not path.parent.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
            return


def _ensure_provenance_tables(engine: Engine) -> tuple[bool, list[str]]:
    from islam_intelligent.domain.models import Base
    from islam_intelligent.provenance import models as prov_models  # noqa: F401

    _ = prov_models
    Base.metadata.create_all(engine)

    required = ["prov_activity", "prov_entity", "prov_generation", "prov_usage"]
    inspector = inspect(engine)
    missing = [t for t in required if not inspector.has_table(t)]
    if missing:
        return False, missing
    return True, []


def _seed_demo_chain(db: Session) -> None:
    """Create a minimal, ephemeral chain for --simulate-tamper on empty DB.

    Runs inside a transaction/savepoint controlled by the caller.
    """

    from islam_intelligent.provenance.recorder import (
        finish_activity,
        record_activity,
        record_generation,
        record_usage,
    )

    a1 = record_activity(db, activity_type="demo.seed", params={"n": 1})
    db.flush()
    record_generation(
        db,
        entity_id="demo:entity:1",
        activity_id=a1.activity_id,
        entity_type="demo",
        label="seed",
        json_data={"v": 1},
    )
    finish_activity(db, a1)
    db.flush()

    a2 = record_activity(db, activity_type="demo.transform", params={"n": 2})
    db.flush()
    record_usage(db, activity_id=a2.activity_id, entity_id="demo:entity:1")
    record_generation(
        db,
        entity_id="demo:entity:2",
        activity_id=a2.activity_id,
        entity_type="demo",
        label="derived",
        json_data={"v": 2},
    )
    finish_activity(db, a2)
    db.flush()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify provenance activity hash chain"
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="Optional override for DATABASE_URL (default: ./.local/dev.db)",
    )
    parser.add_argument(
        "--simulate-tamper",
        action="store_true",
        help="Simulate tampering (should exit 1)",
    )
    args = parser.parse_args()

    db_url = _resolve_db_url(cast(str | None, args.db_url))
    _ensure_sqlite_parent_dir(db_url)
    engine = _make_engine(db_url)

    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
    except Exception as e:
        print(f"ERROR: Failed to connect to database: {e}", file=sys.stderr)
        return 2

    ok, missing = _ensure_provenance_tables(engine)
    if not ok:
        print(
            "ERROR: Missing required provenance table(s): " + ", ".join(missing),
            file=sys.stderr,
        )
        return 2

    SessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    db = SessionLocal()
    try:
        from islam_intelligent.provenance.hash_chain import verify_hash_chain

        if cast(bool, args.simulate_tamper):
            # Ensure there's something to check even on a fresh DB, without persisting it.
            verified, msg = verify_hash_chain(db, simulate_tamper=True)
            if verified:
                # No activities (or all skipped) - seed an ephemeral demo chain.
                with db.begin_nested():
                    _seed_demo_chain(db)
                    verified, msg = verify_hash_chain(db, simulate_tamper=True)
            if verified:
                print("[FAIL] Tamper simulation did not fail")
                return 2
            print(f"[TAMPER] {msg}")
            return 1

        verified, msg = verify_hash_chain(db, simulate_tamper=False)
        if not verified:
            print(f"[FAIL] {msg}", file=sys.stderr)
            return 1

        print("[OK] Hash chain verified")
        return 0
    except Exception as e:
        print(f"ERROR: Verification failed: {e}", file=sys.stderr)
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
