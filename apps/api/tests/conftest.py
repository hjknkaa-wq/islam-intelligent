"""Pytest fixtures shared across API tests."""

from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false

import os

# Must be set before any islam_intelligent imports so db.engine uses in-memory
# SQLite. This ensures tests are isolated from any file-based database and work
# correctly regardless of the current working directory.
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

import pytest


@pytest.fixture(scope="session", autouse=True)
def _init_test_db():  # type: ignore[no-untyped-def]
    """Create ORM tables in the in-memory test database once per session."""
    from islam_intelligent.db.engine import engine
    from islam_intelligent.domain.models import Base
    # Import all model modules so they are registered with Base.metadata before
    # create_all() is called. Without this, related tables (prov_*, kg_*) would
    # be missing and FK references would fail.
    from islam_intelligent.provenance import models as _prov_models  # noqa: F401
    from islam_intelligent.kg import models as _kg_models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture()
def db_session():  # type: ignore[no-untyped-def]
    """Provide a SQLAlchemy session against the in-memory test DB."""
    from islam_intelligent.db.engine import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
