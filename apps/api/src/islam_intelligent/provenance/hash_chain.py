"""Tamper-evident SHA-256 hash chain for provenance activities.

Hash definition:
- activity_hash = sha256(json_canonical(activity_record + input_hashes + output_hashes))
- prev_activity_hash links each activity to the previous activity_hash in sequence

Canonical JSON:
- json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=True)
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from .models import ProvActivity, ProvEntity, ProvGeneration, ProvUsage


def _dt_to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat()


def canonical_json(obj: object) -> str:
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def sha256_hex(canonical_payload: str) -> str:
    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


def compute_entity_hash(entity: ProvEntity) -> str:
    json_data_obj: object | None = None
    if entity.json_data:
        try:
            json_data_obj = json.loads(entity.json_data)
        except json.JSONDecodeError:
            json_data_obj = entity.json_data

    payload = {
        "entity_id": entity.entity_id,
        "entity_type": entity.entity_type,
        "label": entity.label,
        "json_data": json_data_obj,
    }
    return sha256_hex(canonical_json(payload))


def activity_record_dict(
    activity: ProvActivity, *, prev_activity_hash: str | None
) -> dict[str, object]:
    return {
        "activity_id": activity.activity_id,
        "activity_type": activity.activity_type,
        "started_at": _dt_to_iso(activity.started_at),
        "ended_at": _dt_to_iso(activity.ended_at),
        "git_sha": activity.git_sha,
        "params_hash": activity.params_hash,
        "prev_activity_hash": prev_activity_hash,
    }


def _unique_sorted_hashes(items: list[str]) -> list[str]:
    out = sorted({h.strip() for h in items if h and h.strip()})
    return out


def get_activity_io_hashes(
    session: Session, activity_id: str
) -> tuple[list[str], list[str]]:
    used_stmt = (
        select(ProvEntity)
        .join(ProvUsage, ProvUsage.entity_id == ProvEntity.entity_id)
        .where(ProvUsage.activity_id == activity_id)
    )
    gen_stmt = (
        select(ProvEntity)
        .join(ProvGeneration, ProvGeneration.entity_id == ProvEntity.entity_id)
        .where(ProvGeneration.activity_id == activity_id)
    )

    used_entities = list(session.execute(used_stmt).scalars().all())
    gen_entities = list(session.execute(gen_stmt).scalars().all())

    input_hashes = _unique_sorted_hashes(
        [compute_entity_hash(e) for e in used_entities]
    )
    output_hashes = _unique_sorted_hashes(
        [compute_entity_hash(e) for e in gen_entities]
    )
    return input_hashes, output_hashes


def compute_activity_hash(
    activity: ProvActivity,
    *,
    input_hashes: list[str],
    output_hashes: list[str],
    prev_activity_hash: str | None,
) -> str:
    payload = {
        "activity_record": activity_record_dict(
            activity, prev_activity_hash=prev_activity_hash
        ),
        "input_hashes": _unique_sorted_hashes(list(input_hashes)),
        "output_hashes": _unique_sorted_hashes(list(output_hashes)),
    }
    return sha256_hex(canonical_json(payload))


def find_prev_activity_hash(session: Session, activity: ProvActivity) -> str | None:
    if activity.started_at is None:
        return None

    cond = or_(
        ProvActivity.started_at < activity.started_at,
        and_(
            ProvActivity.started_at == activity.started_at,
            ProvActivity.activity_id < activity.activity_id,
        ),
    )
    stmt = (
        select(ProvActivity.activity_hash)
        .where(
            ProvActivity.activity_hash.is_not(None),
            ProvActivity.activity_id != activity.activity_id,
            cond,
        )
        .order_by(ProvActivity.started_at.desc(), ProvActivity.activity_id.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def verify_hash_chain(
    session: Session,
    *,
    simulate_tamper: bool = False,
) -> tuple[bool, str]:
    stmt = select(ProvActivity).order_by(
        ProvActivity.started_at.asc(), ProvActivity.activity_id.asc()
    )
    activities = list(session.execute(stmt).scalars().all())

    if not activities:
        return True, "no activities"

    prev: str | None = None
    tamper_index = len(activities) // 2

    for idx, activity in enumerate(activities):
        if activity.activity_hash is None:
            return False, f"missing activity_hash activity_id={activity.activity_id}"

        if activity.prev_activity_hash != prev:
            return (
                False,
                f"prev_activity_hash mismatch activity_id={activity.activity_id} expected={prev} got={activity.prev_activity_hash}",
            )

        input_hashes, output_hashes = get_activity_io_hashes(
            session, activity.activity_id
        )
        expected = compute_activity_hash(
            activity,
            input_hashes=input_hashes,
            output_hashes=output_hashes,
            prev_activity_hash=prev,
        )

        if simulate_tamper and idx == tamper_index:
            expected = ("0" * 64) if expected != ("0" * 64) else ("1" * 64)

        if activity.activity_hash != expected:
            return (
                False,
                f"activity_hash mismatch activity_id={activity.activity_id} expected={expected} got={activity.activity_hash}",
            )

        prev = activity.activity_hash

    return True, "verified"
