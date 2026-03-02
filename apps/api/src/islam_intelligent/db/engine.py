"""Database engine scaffold.

Defaults to an in-memory SQLite database, but can be overridden via DATABASE_URL.
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


_DEFAULT = "sqlite+pysqlite:///./.local/dev.db"
DATABASE_URL = (os.getenv("DATABASE_URL") or _DEFAULT).strip() or _DEFAULT

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Enable SQLite foreign key enforcement
import sqlite3
from sqlalchemy import event


def _fk_pragma_on_connect(dbapi_connection, connection_record):
    # Only apply to SQLite connections
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


event.listen(engine, "connect", _fk_pragma_on_connect)
