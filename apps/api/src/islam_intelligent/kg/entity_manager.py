"""Entity manager for the minimal Knowledge Graph (KG).

Public functions intentionally match the requested MVP signatures.
"""

from __future__ import annotations

import json
from typing import TypedDict, cast

from sqlalchemy import select

from ..db.engine import SessionLocal, engine
from ..domain.models import Base

from .models import KgEntity


_tables_initialized = False

_DEFAULT_ALIASES: list[str] = []


class EntityDict(TypedDict):
    entity_id: str
    entity_type: str
    canonical_name: str
    aliases: list[str]
    description: str | None
    created_at: str | None


def _ensure_tables() -> None:
    global _tables_initialized
    if _tables_initialized:
        return

    # Ensure provenance tables are registered in metadata.
    from ..provenance import models as _prov_models

    _ = _prov_models
    Base.metadata.create_all(engine)
    _tables_initialized = True


def create_entity(
    entity_type: str,
    canonical_name: str,
    aliases: list[str] = _DEFAULT_ALIASES,
    description: str | None = None,
) -> str:
    _ensure_tables()

    aliases_list = list(aliases or [])
    aliases_json = json.dumps(aliases_list, ensure_ascii=False)

    db = SessionLocal()
    try:
        existing = db.execute(
            select(KgEntity).where(
                KgEntity.entity_type == entity_type,
                KgEntity.canonical_name == canonical_name,
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ValueError("entity already exists for (entity_type, canonical_name)")

        ent = KgEntity(
            entity_type=entity_type,
            canonical_name=canonical_name,
            aliases_json=aliases_json,
            description=description,
        )
        db.add(ent)
        db.commit()
        db.refresh(ent)
        return ent.entity_id
    finally:
        db.close()


def _to_entity_dict(ent: KgEntity) -> EntityDict:
    try:
        raw_aliases_obj = cast(object, json.loads(ent.aliases_json or "[]"))
    except json.JSONDecodeError:
        raw_aliases_obj = []

    raw_aliases_list: list[object] = (
        cast(list[object], raw_aliases_obj) if isinstance(raw_aliases_obj, list) else []
    )

    aliases: list[str] = []
    for a in raw_aliases_list:
        if isinstance(a, str):
            aliases.append(a)

    return {
        "entity_id": ent.entity_id,
        "entity_type": ent.entity_type,
        "canonical_name": ent.canonical_name,
        "aliases": aliases,
        "description": ent.description,
        "created_at": ent.created_at.isoformat()
        if getattr(ent, "created_at", None)
        else None,
    }


def get_entity(entity_id: str) -> EntityDict:
    _ensure_tables()

    db = SessionLocal()
    try:
        ent = db.get(KgEntity, entity_id)
        if ent is None:
            raise KeyError(f"entity {entity_id} not found")
        return _to_entity_dict(ent)
    finally:
        db.close()


def list_entities(entity_type: str | None = None) -> list[EntityDict]:
    _ensure_tables()

    db = SessionLocal()
    try:
        stmt = select(KgEntity)
        if entity_type is not None:
            stmt = stmt.where(KgEntity.entity_type == entity_type)
        ents = list(db.execute(stmt).scalars().all())
        return [_to_entity_dict(e) for e in ents]
    finally:
        db.close()


def search_entities(query: str) -> list[EntityDict]:
    _ensure_tables()
    q = (query or "").strip().lower()
    if not q:
        return []

    db = SessionLocal()
    try:
        ents = list(db.execute(select(KgEntity)).scalars().all())
        out: list[EntityDict] = []
        for ent in ents:
            if (ent.canonical_name or "").lower().find(q) != -1:
                out.append(_to_entity_dict(ent))
                continue

            try:
                raw_aliases_obj = cast(object, json.loads(ent.aliases_json or "[]"))
            except json.JSONDecodeError:
                raw_aliases_obj = []

            raw_aliases_list: list[object] = (
                cast(list[object], raw_aliases_obj)
                if isinstance(raw_aliases_obj, list)
                else []
            )

            aliases: list[str] = []
            for a in raw_aliases_list:
                if isinstance(a, str):
                    aliases.append(a)

            if any(a.lower().find(q) != -1 for a in aliases):
                out.append(_to_entity_dict(ent))

        return out
    finally:
        db.close()
