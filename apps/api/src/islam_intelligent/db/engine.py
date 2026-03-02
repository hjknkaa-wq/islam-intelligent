"""Database engine scaffold.

Defaults to an in-memory SQLite database, but can be overridden via DATABASE_URL.
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


_DEFAULT = "sqlite+pysqlite:///:memory:"
DATABASE_URL = (os.getenv("DATABASE_URL") or _DEFAULT).strip() or _DEFAULT

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
