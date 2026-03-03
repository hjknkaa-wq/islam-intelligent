"""Pytest fixtures shared across API tests."""

from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false

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
