"""Pytest fixtures shared across API tests."""

from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false

import sqlite3
import tempfile
from pathlib import Path
from typing import Generator

import pytest


@pytest.fixture()
def db_session():  # type: ignore[no-untyped-def]
    """
    Provide a SQLAlchemy session connected to the local SQLite development database.
    
    Creates all ORM tables defined on Base if they do not exist and yields an active
    Session for use in tests. The session is closed when the fixture is torn down.
    
    Yields:
        db (Session): Active SQLAlchemy session bound to the development database.
    """

    from islam_intelligent.db.engine import SessionLocal, engine
    from islam_intelligent.domain.models import Base

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def temp_db() -> Generator[Path, None, None]:
    """
    Provide a temporary SQLite database file initialized with the schema required for citation verification tests.
    
    The fixture yields a Path to a temporary .db file that contains the tables: source_document, text_unit, and evidence_span. The temporary file is removed during fixture teardown; removal uses a best-effort retry on PermissionError (to accommodate Windows file locking).
    
    Returns:
        db_path (Path): Path to the temporary SQLite database file.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    conn = sqlite3.connect(db_path)
    try:
        # Create required tables
        conn.executescript(
            """
            CREATE TABLE source_document (
                source_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                license_code TEXT,
                trust_status TEXT DEFAULT 'untrusted'
            );

            CREATE TABLE text_unit (
                text_unit_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                text_canonical TEXT NOT NULL,
                FOREIGN KEY (source_id) REFERENCES source_document(source_id)
            );

            CREATE TABLE evidence_span (
                evidence_span_id TEXT PRIMARY KEY,
                text_unit_id TEXT NOT NULL,
                start_byte INTEGER NOT NULL,
                end_byte INTEGER NOT NULL,
                snippet_utf8_sha256 TEXT NOT NULL,
                FOREIGN KEY (text_unit_id) REFERENCES text_unit(text_unit_id)
            );
            """
        )
        conn.commit()
    finally:
        conn.close()

    yield db_path

    # Cleanup - on Windows, we may need to retry if file is locked
    try:
        db_path.unlink(missing_ok=True)
    except PermissionError:
        import time

        time.sleep(0.1)
        try:
            db_path.unlink(missing_ok=True)
        except PermissionError:
            pass  # Best effort cleanup
