"""Database engine scaffold.

Defaults to a local SQLite database, but can be overridden via DATABASE_URL.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.exc import NoSuchModuleError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


_DEFAULT = "sqlite+pysqlite:///./.local/dev.db"
DATABASE_URL = (os.getenv("DATABASE_URL") or _DEFAULT).strip() or _DEFAULT
POOL_SIZE = 20
MAX_OVERFLOW = 30


def _ensure_sqlite_parent_dir(db_url: str) -> None:
    sqlite_prefixes = ("sqlite+pysqlite:///", "sqlite+aiosqlite:///")
    prefix = next((p for p in sqlite_prefixes if db_url.startswith(p)), "")
    if not prefix:
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


def _is_sqlite_in_memory(db_url: str) -> bool:
    lowered = db_url.lower()
    return lowered.startswith("sqlite") and ":memory:" in lowered

def _engine_kwargs(db_url: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"future": True}
    if _is_sqlite_in_memory(db_url):
        # Share one in-memory SQLite connection across threads/process contexts.
        kwargs["connect_args"] = {"check_same_thread": False}
        kwargs["poolclass"] = StaticPool
    else:
        kwargs["pool_size"] = POOL_SIZE
        kwargs["max_overflow"] = MAX_OVERFLOW
    return kwargs


def _to_async_database_url(db_url: str) -> str:
    if db_url.startswith("sqlite+pysqlite://"):
        return db_url.replace("sqlite+pysqlite://", "sqlite+aiosqlite://", 1)
    if db_url.startswith("sqlite://"):
        return db_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    if db_url.startswith("postgresql+psycopg2://"):
        return db_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if db_url.startswith("postgresql://"):
        return db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return db_url


def _fk_pragma_on_connect(dbapi_connection: object, _connection_record: object) -> None:
    # Only apply to SQLite connections
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        try:
            _ = cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


_ensure_sqlite_parent_dir(DATABASE_URL)
ASYNC_DATABASE_URL = _to_async_database_url(DATABASE_URL)
_ensure_sqlite_parent_dir(ASYNC_DATABASE_URL)

engine = create_engine(DATABASE_URL, **_engine_kwargs(DATABASE_URL))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

event.listen(engine, "connect", _fk_pragma_on_connect)

async_engine: AsyncEngine | None
AsyncSessionLocal: async_sessionmaker[AsyncSession] | None
try:
    async_engine = create_async_engine(
        ASYNC_DATABASE_URL,
        **_engine_kwargs(ASYNC_DATABASE_URL),
    )
    AsyncSessionLocal = async_sessionmaker(
        bind=async_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    event.listen(async_engine.sync_engine, "connect", _fk_pragma_on_connect)
except (ModuleNotFoundError, NoSuchModuleError):
    async_engine = None
    AsyncSessionLocal = None


async def get_async_session() -> AsyncIterator[AsyncSession]:
    if AsyncSessionLocal is None:
        raise RuntimeError("Async database session is not available")
    async with AsyncSessionLocal() as session:
        yield session
