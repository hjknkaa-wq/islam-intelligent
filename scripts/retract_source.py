#!/usr/bin/env python3
"""Retract a source_document by inserting a new version row (append-only).

Hard rules:
- Do NOT delete any data.
- Do NOT modify the original source_document row.

Operation:
- Create a new source_document row with a new UUID source_id.
- Set supersedes_source_id to the original source_id.
- Set trust_status='retracted'.
- Set retraction_reason from CLI.
"""

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnusedCallResult=false

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, cast

from sqlalchemy import DateTime, Integer, String, Text, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from islam_intelligent.db import engine as engine_module
from islam_intelligent.domain.models import Base as ProjectBase
from islam_intelligent.domain.models import SourceDocument as ProjectSourceDocument


@dataclass(frozen=True)
class ModelBundle:
    base: type[DeclarativeBase]
    source_document: type[DeclarativeBase]
    uses_project_model: bool


class CompatBase(DeclarativeBase):
    pass


class CompatSourceDocument(CompatBase):
    """Compatibility mapping for canonical source_document fields.

    Used when the project SourceDocument does not expose the required retraction
    columns.
    """

    __tablename__: str = "source_document"

    source_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    work_title: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str | None] = mapped_column(Text, nullable=True)
    edition: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    canonical_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    license_id: Mapped[str] = mapped_column(Text, nullable=False)
    license_url: Mapped[str] = mapped_column(Text, nullable=False)
    rights_holder: Mapped[str | None] = mapped_column(Text, nullable=True)
    attribution_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    content_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_mime: Mapped[str] = mapped_column(
        String(64), nullable=False, default="text/plain"
    )
    content_length_bytes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    storage_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    trust_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="untrusted"
    )
    supersedes_source_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    retraction_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


def _has_required_columns(model: type[object]) -> bool:
    return all(
        hasattr(model, k)
        for k in ("supersedes_source_id", "trust_status", "retraction_reason")
    )


def _choose_model() -> ModelBundle:
    project_model = cast(type[DeclarativeBase], ProjectSourceDocument)
    if _has_required_columns(cast(type[object], project_model)):
        return ModelBundle(
            base=ProjectBase,
            source_document=project_model,
            uses_project_model=True,
        )
    return ModelBundle(
        base=CompatBase, source_document=CompatSourceDocument, uses_project_model=False
    )


def _resolve_db_url(cli_db_url: str | None) -> str:
    if cli_db_url:
        return cli_db_url
    env = (os.getenv("DATABASE_URL") or "").strip()
    if env:
        return env
    return engine_module.DATABASE_URL


def _make_engine(db_url: str) -> Engine:
    if db_url == engine_module.DATABASE_URL:
        return engine_module.engine
    return create_engine(db_url, future=True)


def _make_session_factory(engine: Engine, db_url: str) -> sessionmaker[Session]:
    if db_url == engine_module.DATABASE_URL:
        return engine_module.SessionLocal
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _first_fixture_path(fixtures_dir: Path) -> Path:
    candidates = sorted(fixtures_dir.glob("*_minimal.yaml"))
    if not candidates:
        raise SystemExit(f"No fixtures found in {fixtures_dir}")
    return candidates[0]


def _fixture_source_id_from_yaml(path: Path) -> tuple[str, dict[str, object]]:
    import yaml

    raw_obj = cast(object, yaml.safe_load(path.read_text(encoding="utf-8")))
    data = cast(dict[str, object], raw_obj if isinstance(raw_obj, dict) else {})
    metadata_raw = data.get("metadata")
    metadata = cast(
        dict[str, object], metadata_raw if isinstance(metadata_raw, dict) else {}
    )

    fixture_id_raw = metadata.get("source_id")
    fixture_id = str(fixture_id_raw) if fixture_id_raw is not None else ""
    if not fixture_id:
        raise SystemExit(f"Fixture missing metadata.source_id: {path}")

    # Match scripts/load_fixtures.py deterministic ID generation.
    source_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, fixture_id))
    return source_id, metadata


def _ensure_tables(engine: Engine, base: type[DeclarativeBase]) -> None:
    base.metadata.create_all(bind=engine)


def _get_original(
    db: Session, model: type[DeclarativeBase], source_id: str
) -> DeclarativeBase | None:
    q = db.query(model)
    return q.filter_by(source_id=source_id).first()


def _record_view(doc: object) -> dict[str, object | None]:
    work_title = getattr(doc, "work_title", None)
    if work_title is None:
        work_title = getattr(doc, "title", None)
    created_at = getattr(doc, "created_at", None)
    created_at_iso = (
        created_at.isoformat() if isinstance(created_at, datetime) else None
    )
    return {
        "source_id": getattr(doc, "source_id", None),
        "work_title": work_title,
        "trust_status": getattr(doc, "trust_status", None),
        "supersedes_source_id": getattr(doc, "supersedes_source_id", None),
        "retraction_reason": getattr(doc, "retraction_reason", None),
        "created_at": created_at_iso,
    }


def _clone_for_retraction(
    original: object, model: type[DeclarativeBase], reason: str
) -> DeclarativeBase:
    old_source_id = str(getattr(original, "source_id", ""))
    if not old_source_id:
        raise SystemExit("Original row missing source_id")
    new_source_id = str(uuid.uuid4())

    kwargs: dict[str, object] = {
        "source_id": new_source_id,
        "supersedes_source_id": old_source_id,
        "trust_status": "retracted",
        "retraction_reason": reason,
    }

    # Copy canonical fields when present on the active model.
    for field in (
        "source_type",
        "work_title",
        "author",
        "edition",
        "language",
        "canonical_ref",
        "license_id",
        "license_url",
        "rights_holder",
        "attribution_text",
        "retrieved_at",
        "content_hash_sha256",
        "content_mime",
        "content_length_bytes",
        "storage_path",
    ):
        if hasattr(model, field):
            value = getattr(original, field, None)
            if value is not None:
                kwargs[field] = cast(object, value)

    # Support older model shape (title instead of work_title).
    if hasattr(model, "title"):
        title_val = getattr(original, "title", None)
        if title_val is not None:
            kwargs["title"] = cast(object, title_val)

    # Keep version-chain info if present.
    if hasattr(model, "supersedes_version"):
        prior_version = getattr(original, "version", None)
        if prior_version is not None:
            kwargs["supersedes_version"] = cast(object, prior_version)

    return model(**kwargs)  # type: ignore[reportUnknownArgumentType]


def _maybe_insert_fixture_source(
    db: Session,
    model: type[DeclarativeBase],
    fixtures_dir: Path,
    source_id: str,
    metadata: dict[str, object],
) -> None:
    if _get_original(db, model, source_id) is not None:
        return

    fixture_path = _first_fixture_path(fixtures_dir)
    raw = fixture_path.read_bytes()
    content_hash = _sha256_bytes(raw)

    kwargs: dict[str, object] = {}

    def _set(name: str, value: object) -> None:
        if hasattr(model, name):
            kwargs[name] = value

    _set("source_id", source_id)
    _set("source_type", str(metadata.get("source_type") or "other"))
    _set("work_title", str(metadata.get("work_title") or "(fixture)"))
    _set("language", str(metadata.get("language") or "ar"))
    _set("license_id", str(metadata.get("license_id") or "UNKNOWN"))
    _set("license_url", str(metadata.get("license_url") or ""))
    _set("content_hash_sha256", content_hash)
    _set("content_length_bytes", len(raw))
    _set("content_mime", "text/yaml")
    _set("storage_path", str(fixture_path))
    _set("trust_status", "trusted")

    if metadata.get("author") is not None:
        _set("author", str(metadata.get("author")))
    if metadata.get("edition") is not None:
        _set("edition", str(metadata.get("edition")))
    if metadata.get("canonical_ref") is not None:
        _set("canonical_ref", str(metadata.get("canonical_ref")))
    if metadata.get("rights_holder") is not None:
        _set("rights_holder", str(metadata.get("rights_holder")))
    if metadata.get("attribution_text") is not None:
        _set("attribution_text", str(metadata.get("attribution_text")))

    retrieved_at = metadata.get("retrieved_at")
    if retrieved_at is not None and hasattr(model, "retrieved_at"):
        try:
            kwargs["retrieved_at"] = datetime.fromisoformat(str(retrieved_at))
        except Exception:
            kwargs["retrieved_at"] = None

    doc = model(**kwargs)  # type: ignore[reportUnknownArgumentType]
    db.add(doc)
    db.commit()


class _Args(Protocol):
    source_id: str | None
    first_fixture: bool
    reason: str
    db_url: str | None
    fixtures_dir: str


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Retract a source_document (append-only)"
    )
    parser.add_argument("--source-id", help="Source ID (UUID) to retract")
    parser.add_argument(
        "--first-fixture",
        action="store_true",
        help="Retract the first fixture source (sorted *_minimal.yaml)",
    )
    parser.add_argument("--reason", required=True, help="Retraction reason")
    parser.add_argument(
        "--db-url", default=None, help="Optional override for DATABASE_URL"
    )
    parser.add_argument(
        "--fixtures-dir",
        default=str(ROOT / "data" / "fixtures"),
        help="Fixture directory (used with --first-fixture)",
    )

    args = cast(_Args, cast(object, parser.parse_args(argv)))
    if bool(args.source_id) == bool(args.first_fixture):
        raise SystemExit("Provide exactly one of --source-id or --first-fixture")

    bundle = _choose_model()
    if not _has_required_columns(bundle.source_document):
        raise SystemExit(
            "SourceDocument model missing required columns: supersedes_source_id, trust_status, retraction_reason"
        )

    db_url = _resolve_db_url(args.db_url)
    engine = _make_engine(db_url)
    SessionFactory = _make_session_factory(engine, db_url)

    _ensure_tables(engine, bundle.base)

    fixtures_dir = Path(args.fixtures_dir)
    if args.first_fixture:
        fixture_path = _first_fixture_path(fixtures_dir)
        target_source_id, metadata = _fixture_source_id_from_yaml(fixture_path)
    else:
        target_source_id = str(args.source_id)
        metadata = {}

    with SessionFactory() as db:
        if args.first_fixture:
            _maybe_insert_fixture_source(
                db, bundle.source_document, fixtures_dir, target_source_id, metadata
            )

        original = _get_original(db, bundle.source_document, target_source_id)
        if original is None:
            raise SystemExit(f"source_document not found: source_id={target_source_id}")

        new_doc = _clone_for_retraction(
            original, bundle.source_document, str(args.reason)
        )
        db.add(new_doc)
        db.commit()

        old_check = _get_original(
            db, bundle.source_document, str(getattr(original, "source_id", ""))
        )
        new_check = _get_original(
            db, bundle.source_document, str(getattr(new_doc, "source_id", ""))
        )

        print(
            json.dumps(
                {
                    "uses_project_model": bundle.uses_project_model,
                    "old": _record_view(cast(object, old_check)),
                    "new": _record_view(cast(object, new_check)),
                    "old_exists": old_check is not None,
                    "new_exists": new_check is not None,
                },
                indent=2,
                sort_keys=True,
            )
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
