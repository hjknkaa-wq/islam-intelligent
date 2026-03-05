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
    """Provide a SQLAlchemy session against the local SQLite dev DB.

    Some integration tests depend on a DB existing, even if they use sqlite3
    directly. This fixture ensures tables are created and the session is closed.
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
    """Create a temporary database with required schema for citation verification tests."""
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
