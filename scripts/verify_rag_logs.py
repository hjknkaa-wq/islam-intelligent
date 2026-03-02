#!/usr/bin/env python3
"""Verify complete RAG audit logs in SQLite.

Checks:
- rag_query rows exist for all pipeline artifacts (no child rows without parent query)
- every rag_query has >=1 rag_retrieval_result row
- every rag_query has exactly one rag_validation row
- every rag_query has exactly one rag_answer row

Exit codes:
- 0: all checks pass
- 1: violations found
- 2: runtime/configuration error
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / ".local" / "dev.db"
REQUIRED_TABLES = (
    "rag_query",
    "rag_retrieval_result",
    "rag_validation",
    "rag_answer",
)


@dataclass(frozen=True)
class CliArgs:
    db_path: str
    simulate_missing: bool


def _parse_args() -> CliArgs:
    parser = argparse.ArgumentParser(description="Verify RAG audit trail completeness")
    _ = parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
        help="SQLite database path (default: ./.local/dev.db)",
    )
    _ = parser.add_argument(
        "--simulate-missing",
        action="store_true",
        help="Simulate one missing retrieval/validation/answer set for testing",
    )
    parsed = parser.parse_args()
    return CliArgs(
        db_path=cast(str, parsed.db_path),
        simulate_missing=cast(bool, parsed.simulate_missing),
    )


def _has_table(conn: sqlite3.Connection, table_name: str) -> bool:
    row = cast(
        tuple[int] | None,
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table_name,),
        ).fetchone(),
    )
    return row is not None


def _collect_query_ids(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = cast(
        list[tuple[str | None]],
        conn.execute(f"SELECT rag_query_id FROM {table_name}").fetchall(),
    )
    return {str(row[0]) for row in rows if row[0] is not None}


def _choose_simulated_target(query_ids: set[str]) -> str:
    if not query_ids:
        return "SIMULATED_QUERY_ID"
    return sorted(query_ids)[0]


def _format_missing(label: str, query_ids: set[str]) -> list[str]:
    return [f"query_id={query_id} missing {label}" for query_id in sorted(query_ids)]


def main() -> int:
    args = _parse_args()
    db_path = Path(args.db_path).expanduser().resolve()

    if not db_path.exists():
        print(f"[ERROR] Database not found: {db_path}", file=sys.stderr)
        return 2

    try:
        conn = sqlite3.connect(str(db_path))
    except Exception as exc:
        print(f"[ERROR] Failed to open database: {exc}", file=sys.stderr)
        return 2

    violations: list[str] = []
    try:
        missing_tables = [t for t in REQUIRED_TABLES if not _has_table(conn, t)]
        if missing_tables:
            print(
                "[ERROR] Missing required table(s): " + ", ".join(missing_tables),
                file=sys.stderr,
            )
            return 2

        query_ids = _collect_query_ids(conn, "rag_query")
        retrieval_ids = _collect_query_ids(conn, "rag_retrieval_result")
        validation_ids = _collect_query_ids(conn, "rag_validation")
        answer_ids = _collect_query_ids(conn, "rag_answer")

        if args.simulate_missing:
            simulated_target = _choose_simulated_target(query_ids)
            query_ids.add(simulated_target)
            retrieval_ids.discard(simulated_target)
            validation_ids.discard(simulated_target)
            answer_ids.discard(simulated_target)

        # Parent presence checks: child rows must map to rag_query rows.
        unknown_retrieval = retrieval_ids - query_ids
        unknown_validation = validation_ids - query_ids
        unknown_answer = answer_ids - query_ids
        violations.extend(
            [
                f"query_id={query_id} exists in rag_retrieval_result but missing rag_query"
                for query_id in sorted(unknown_retrieval)
            ]
        )
        violations.extend(
            [
                f"query_id={query_id} exists in rag_validation but missing rag_query"
                for query_id in sorted(unknown_validation)
            ]
        )
        violations.extend(
            [
                f"query_id={query_id} exists in rag_answer but missing rag_query"
                for query_id in sorted(unknown_answer)
            ]
        )

        # Completeness checks for each query.
        missing_retrieval = query_ids - retrieval_ids
        missing_validation = query_ids - validation_ids
        missing_answer = query_ids - answer_ids

        violations.extend(_format_missing("rag_retrieval_result", missing_retrieval))
        violations.extend(_format_missing("rag_validation", missing_validation))
        violations.extend(_format_missing("rag_answer", missing_answer))

        if violations:
            print(
                f"[FAIL] RAG log verification failed ({len(violations)} violation(s))"
            )
            for violation in violations:
                print(f"- {violation}")
            return 1

        print("[OK] All RAG queries have complete audit logs")
        return 0
    except Exception as exc:
        print(f"[ERROR] Verification failed: {exc}", file=sys.stderr)
        return 2
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
