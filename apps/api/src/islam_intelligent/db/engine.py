"""Database engine scaffold.

Defaults to an in-memory SQLite database, but can be overridden via DATABASE_URL.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


_DEFAULT = "sqlite+pysqlite:///./.local/dev.db"
DATABASE_URL = (os.getenv("DATABASE_URL") or _DEFAULT).strip() or _DEFAULT


def _ensure_sqlite_parent_dir(db_url: str) -> None:
    prefix = "sqlite+pysqlite:///"
    if not db_url.startswith(prefix):
        return
    path_str = db_url[len(prefix) :]
    if not path_str or path_str == ":memory:":
        return
    try:
        db_path = Path(path_str)
        parent = db_path.parent
        if str(parent) and parent != Path("."):
            parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        # Fail-safe: if we can't create the directory, let connection fail loudly.
        return


_ensure_sqlite_parent_dir(DATABASE_URL)

# For in-memory SQLite, use StaticPool so all threads share the same connection.
# This is required when the ASGI test client runs in a separate thread (e.g.
# Starlette/FastAPI TestClient) and is the standard FastAPI testing pattern.
_is_memory = ":memory:" in DATABASE_URL
if _is_memory:
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
else:
    engine = create_engine(DATABASE_URL, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Enable SQLite foreign key enforcement
import sqlite3
from sqlalchemy import event


def _fk_pragma_on_connect(dbapi_connection: object, _connection_record: object) -> None:
    # Only apply to SQLite connections
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        try:
            _ = cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


event.listen(engine, "connect", _fk_pragma_on_connect)
