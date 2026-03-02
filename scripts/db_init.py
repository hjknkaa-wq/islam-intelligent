#!/usr/bin/env python3
"""Initialize database schema from SQL migrations.

SQLite is the default target for local development/tests.
Postgres is supported through DATABASE_URL with --postgres.
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "packages" / "schemas" / "sql"
DEFAULT_SQLITE_PATH = ROOT / ".local" / "dev.db"

POSTGRES_SCHEMES = ("postgres://", "postgresql://", "postgresql+")
SQLITE_SCHEMES = ("sqlite://", "sqlite+pysqlite://")

REQUIRED_TABLES = (
    "source_document",
    "text_unit",
    "evidence_span",
    "kg_entity",
    "kg_edge",
    "kg_edge_evidence",
    "rag_query",
    "rag_retrieval_result",
    "rag_validation",
    "rag_answer",
    "schema_migrations",
)


@dataclass(frozen=True)
class Target:
    kind: str
    db_url: str
    sqlite_path: Path | None


@dataclass(frozen=True)
class CliArgs:
    sqlite: str | None
    postgres: bool


def _parse_args() -> CliArgs:
    parser = argparse.ArgumentParser(
        description="Initialize database from SQL migrations"
    )
    group = parser.add_mutually_exclusive_group()
    _ = group.add_argument(
        "--sqlite",
        type=str,
        default=None,
        help="SQLite database file path (example: ./.local/dev.db)",
    )
    _ = group.add_argument(
        "--postgres",
        action="store_true",
        help="Use Postgres DATABASE_URL from environment",
    )
    parsed = parser.parse_args()
    return CliArgs(
        sqlite=cast(str | None, parsed.sqlite),
        postgres=cast(bool, parsed.postgres),
    )


def _is_postgres_url(url: str) -> bool:
    lowered = url.lower()
    return lowered.startswith(POSTGRES_SCHEMES)


def _is_sqlite_url(url: str) -> bool:
    lowered = url.lower()
    return lowered.startswith(SQLITE_SCHEMES)


def _sqlite_url(db_path: Path) -> str:
    return f"sqlite+pysqlite:///{db_path.as_posix()}"


def _resolve_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


def _extract_sqlite_path_from_url(db_url: str) -> Path | None:
    lowered = db_url.lower()
    if ":memory:" in lowered:
        return None

    prefixes = ("sqlite+pysqlite:///", "sqlite:///")
    for prefix in prefixes:
        if lowered.startswith(prefix):
            raw = db_url[len(prefix) :]
            return Path(raw)
    return None


def _resolve_target(args: CliArgs) -> Target:
    env_db_url = (os.getenv("DATABASE_URL") or "").strip()

    if args.sqlite:
        sqlite_path = _resolve_path(args.sqlite)
        return Target(
            kind="sqlite", db_url=_sqlite_url(sqlite_path), sqlite_path=sqlite_path
        )

    if args.postgres:
        if not env_db_url:
            raise ValueError("--postgres requires DATABASE_URL in environment")
        if not _is_postgres_url(env_db_url):
            raise ValueError("--postgres requires a postgres DATABASE_URL")
        return Target(kind="postgres", db_url=env_db_url, sqlite_path=None)

    if env_db_url:
        if _is_postgres_url(env_db_url):
            return Target(kind="postgres", db_url=env_db_url, sqlite_path=None)
        if _is_sqlite_url(env_db_url):
            sqlite_path = _extract_sqlite_path_from_url(env_db_url)
            return Target(kind="sqlite", db_url=env_db_url, sqlite_path=sqlite_path)
        print("[WARN] Using DATABASE_URL as provided (unrecognized scheme)")
        return Target(kind="other", db_url=env_db_url, sqlite_path=None)

    sqlite_path = DEFAULT_SQLITE_PATH.resolve()
    return Target(
        kind="sqlite", db_url=_sqlite_url(sqlite_path), sqlite_path=sqlite_path
    )


def _ensure_sqlite_file(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    existed_before = db_path.exists()
    with sqlite3.connect(db_path):
        pass
    if existed_before:
        print(f"[OK] SQLite file exists: {db_path}")
    else:
        print(f"[OK] Created SQLite file: {db_path}")


def _load_migrations() -> list[Path]:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        raise FileNotFoundError(f"No SQL migrations found in {MIGRATIONS_DIR}")
    return files


def _strip_sql_comments(sql_text: str) -> str:
    cleaned_lines: list[str] = []
    for line in sql_text.splitlines():
        if "--" in line:
            line = line.split("--", 1)[0]
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def _split_sql_statements(sql_text: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    in_double_quote = False

    i = 0
    while i < len(sql_text):
        char = sql_text[i]

        if char == "'" and not in_double_quote:
            if in_single_quote and i + 1 < len(sql_text) and sql_text[i + 1] == "'":
                current.append(char)
                current.append(sql_text[i + 1])
                i += 2
                continue
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote

        if char == ";" and not in_single_quote and not in_double_quote:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(char)

        i += 1

    trailing = "".join(current).strip()
    if trailing:
        statements.append(trailing)

    return statements


def _tables_in_migration(sql_text: str) -> list[str]:
    pattern = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)",
        re.IGNORECASE,
    )
    names: list[str] = []
    for match in pattern.finditer(sql_text):
        table_name = match.group(1)
        if table_name and table_name != "schema_migrations":
            names.append(table_name)
    return names


def _strip_check_constraints(statement: str) -> str:
    out: list[str] = []
    i = 0
    length = len(statement)

    while i < length:
        is_check = statement[i : i + 5].upper() == "CHECK"
        boundary_ok = i == 0 or not (
            statement[i - 1].isalnum() or statement[i - 1] == "_"
        )

        if is_check and boundary_ok:
            j = i + 5
            while j < length and statement[j].isspace():
                j += 1
            if j < length and statement[j] == "(":
                depth = 0
                k = j
                in_quote = False
                while k < length:
                    ch = statement[k]
                    if ch == "'":
                        if in_quote and k + 1 < length and statement[k + 1] == "'":
                            k += 2
                            continue
                        in_quote = not in_quote
                    elif not in_quote:
                        if ch == "(":
                            depth += 1
                        elif ch == ")":
                            depth -= 1
                            if depth == 0:
                                k += 1
                                break
                    k += 1
                i = k
                continue

        out.append(statement[i])
        i += 1

    return "".join(out)


def _rewrite_types_for_sqlite(statement: str) -> str:
    rewritten = statement
    rewritten = re.sub(
        r"TIMESTAMP\s+WITH\s+TIME\s+ZONE",
        "TEXT",
        rewritten,
        flags=re.IGNORECASE,
    )
    rewritten = re.sub(r"\bJSONB\b", "TEXT", rewritten, flags=re.IGNORECASE)
    rewritten = re.sub(
        r"\bNUMERIC\s*\([^\)]*\)", "REAL", rewritten, flags=re.IGNORECASE
    )
    rewritten = re.sub(r"\bUUID\b", "TEXT", rewritten, flags=re.IGNORECASE)
    rewritten = re.sub(
        r"DEFAULT\s+uuid_generate_v4\s*\(\s*\)",
        "",
        rewritten,
        flags=re.IGNORECASE,
    )
    rewritten = re.sub(
        r"\bNOW\s*\(\s*\)", "CURRENT_TIMESTAMP", rewritten, flags=re.IGNORECASE
    )
    return rewritten


def _convert_create_table_for_sqlite(statement: str) -> str:
    rewritten = statement
    rewritten = re.sub(
        r"^\s*CREATE\s+TABLE\s+(?!IF\s+NOT\s+EXISTS)",
        "CREATE TABLE IF NOT EXISTS ",
        rewritten,
        count=1,
        flags=re.IGNORECASE,
    )
    rewritten = _strip_check_constraints(rewritten)
    rewritten = re.sub(r"(?im)^\s*CONSTRAINT\s+[^\n]*\n?", "", rewritten)
    rewritten = _rewrite_types_for_sqlite(rewritten)
    rewritten = re.sub(r",\s*,", ",", rewritten)
    rewritten = re.sub(r",\s*\)", "\n)", rewritten)
    return rewritten


def _convert_statement_for_sqlite(statement: str) -> str | None:
    stripped = statement.strip()
    upper = stripped.upper()

    if upper.startswith("CREATE EXTENSION"):
        return None
    if upper.startswith("CREATE TYPE"):
        return None
    if upper.startswith("COMMENT ON"):
        return None

    rewritten = stripped

    if upper.startswith("CREATE TABLE"):
        rewritten = _convert_create_table_for_sqlite(rewritten)
    elif upper.startswith("CREATE UNIQUE INDEX"):
        rewritten = re.sub(
            r"^\s*CREATE\s+UNIQUE\s+INDEX\s+(?!IF\s+NOT\s+EXISTS)",
            "CREATE UNIQUE INDEX IF NOT EXISTS ",
            rewritten,
            count=1,
            flags=re.IGNORECASE,
        )
    elif upper.startswith("CREATE INDEX"):
        rewritten = re.sub(
            r"^\s*CREATE\s+INDEX\s+(?!IF\s+NOT\s+EXISTS)",
            "CREATE INDEX IF NOT EXISTS ",
            rewritten,
            count=1,
            flags=re.IGNORECASE,
        )
    elif upper.startswith("CREATE VIEW"):
        rewritten = re.sub(
            r"^\s*CREATE\s+VIEW\s+(?!IF\s+NOT\s+EXISTS)",
            "CREATE VIEW IF NOT EXISTS ",
            rewritten,
            count=1,
            flags=re.IGNORECASE,
        )
    elif upper.startswith("INSERT INTO SCHEMA_MIGRATIONS"):
        rewritten = re.sub(
            r"^\s*INSERT\s+INTO\s+schema_migrations",
            "INSERT OR IGNORE INTO schema_migrations",
            rewritten,
            count=1,
            flags=re.IGNORECASE,
        )

    rewritten = _rewrite_types_for_sqlite(rewritten)
    rewritten = re.sub(r",\s*\)", "\n)", rewritten)
    return rewritten.strip() or None


def _sqlite_script_from_migration(sql_text: str) -> str:
    cleaned = _strip_sql_comments(sql_text)
    statements = _split_sql_statements(cleaned)
    converted: list[str] = []

    for statement in statements:
        migrated = _convert_statement_for_sqlite(statement)
        if migrated:
            converted.append(migrated + ";")

    return "\n\n".join(converted)


def _ensure_schema_migrations_sqlite(conn: sqlite3.Connection) -> None:
    _ = conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            description TEXT
        )
        """
    )


def _sqlite_has_table(conn: sqlite3.Connection, table_name: str) -> bool:
    return (
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        is not None
    )


def _sqlite_has_migration(conn: sqlite3.Connection, version: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            (version,),
        ).fetchone()
        is not None
    )


def _sqlite_record_migration(
    conn: sqlite3.Connection,
    *,
    version: str,
    description: str,
) -> None:
    _ = conn.execute(
        "INSERT OR IGNORE INTO schema_migrations (version, description) VALUES (?, ?)",
        (version, description),
    )


def _all_tables_exist(engine: Engine, table_names: list[str]) -> bool:
    if not table_names:
        return False
    inspector = inspect(engine)
    return all(inspector.has_table(name) for name in table_names)


def _ensure_schema_migrations_engine(engine: Engine) -> None:
    ddl = (
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version TEXT PRIMARY KEY, "
        "applied_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP, "
        "description TEXT"
        ")"
    )
    with engine.begin() as conn:
        _ = conn.exec_driver_sql(ddl)


def _engine_has_migration(engine: Engine, version: str) -> bool:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT 1 FROM schema_migrations WHERE version = :version LIMIT 1"),
            {"version": version},
        ).first()
    return row is not None


def _engine_record_migration(engine: Engine, version: str, description: str) -> None:
    if engine.dialect.name == "sqlite":
        stmt = text(
            "INSERT OR IGNORE INTO schema_migrations (version, description) VALUES (:version, :description)"
        )
    else:
        stmt = text(
            "INSERT INTO schema_migrations (version, description) VALUES (:version, :description) ON CONFLICT (version) DO NOTHING"
        )
    with engine.begin() as conn:
        _ = conn.execute(stmt, {"version": version, "description": description})


def _apply_sqlite_migration(
    db_path: Path, migration_path: Path, migration_sql: str
) -> bool:
    version = migration_path.stem
    description = f"Applied from {migration_path.relative_to(ROOT).as_posix()}"
    table_names = _tables_in_migration(migration_sql)

    with sqlite3.connect(db_path) as conn:
        _ensure_schema_migrations_sqlite(conn)

        if _sqlite_has_migration(conn, version):
            print(f"[SKIP] Migration {version} already recorded")
            return False

        if table_names and all(_sqlite_has_table(conn, name) for name in table_names):
            print(f"[SKIP] Tables for {version} already exist")
            _sqlite_record_migration(conn, version=version, description=description)
            conn.commit()
            return False

        script = _sqlite_script_from_migration(migration_sql)
        if not script.strip():
            raise RuntimeError(
                f"Migration produced empty SQLite script: {migration_path}"
            )

        print(f"[INFO] Applying migration {version} to SQLite")
        _ = conn.executescript(script)
        _sqlite_record_migration(conn, version=version, description=description)
        conn.commit()
        print(f"[OK] Applied migration {version}")
        return True


def _apply_postgres_migration(
    engine: Engine, migration_path: Path, migration_sql: str
) -> bool:
    version = migration_path.stem
    description = f"Applied from {migration_path.relative_to(ROOT).as_posix()}"
    table_names = _tables_in_migration(migration_sql)

    _ensure_schema_migrations_engine(engine)

    if _engine_has_migration(engine, version):
        print(f"[SKIP] Migration {version} already recorded")
        return False

    if _all_tables_exist(engine, table_names):
        print(f"[SKIP] Tables for {version} already exist")
        _engine_record_migration(engine, version, description)
        return False

    statements = _split_sql_statements(_strip_sql_comments(migration_sql))
    print(f"[INFO] Applying migration {version} to Postgres")
    with engine.begin() as conn:
        for statement in statements:
            _ = conn.exec_driver_sql(statement)

    _engine_record_migration(engine, version, description)
    print(f"[OK] Applied migration {version}")
    return True


def _run_sanity_checks(engine: Engine) -> None:
    inspector = inspect(engine)

    missing_tables = [name for name in REQUIRED_TABLES if not inspector.has_table(name)]
    if missing_tables:
        joined = ", ".join(missing_tables)
        raise RuntimeError(f"Schema sanity check failed. Missing tables: {joined}")

    required_columns = {
        "source_document": {"source_id", "source_type", "work_title"},
        "text_unit": {"text_unit_id", "source_id", "canonical_id"},
        "schema_migrations": {"version", "applied_at"},
    }

    for table_name, columns in required_columns.items():
        existing = {col["name"] for col in inspector.get_columns(table_name)}
        missing_cols = sorted(columns - existing)
        if missing_cols:
            missing_joined = ", ".join(missing_cols)
            raise RuntimeError(
                f"Schema sanity check failed. Missing columns in {table_name}: {missing_joined}"
            )

    print("[OK] Schema sanity checks passed")


def main() -> int:
    args = _parse_args()

    try:
        target = _resolve_target(args)
        print(f"[INFO] Database target: {target.kind}")

        if target.kind == "sqlite" and target.sqlite_path is not None:
            _ensure_sqlite_file(target.sqlite_path)

        migrations = _load_migrations()
        print(f"[INFO] Found {len(migrations)} migration(s) in {MIGRATIONS_DIR}")

        engine = create_engine(target.db_url, future=True)

        applied_any = False
        for migration_path in migrations:
            migration_sql = migration_path.read_text(encoding="utf-8")

            if target.kind == "sqlite" and target.sqlite_path is not None:
                applied = _apply_sqlite_migration(
                    db_path=target.sqlite_path,
                    migration_path=migration_path,
                    migration_sql=migration_sql,
                )
            else:
                applied = _apply_postgres_migration(
                    engine=engine,
                    migration_path=migration_path,
                    migration_sql=migration_sql,
                )

            applied_any = applied_any or applied

        _run_sanity_checks(engine)

        if applied_any:
            print("[OK] Database initialization complete")
        else:
            print("[OK] Database already initialized")
        return 0
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
