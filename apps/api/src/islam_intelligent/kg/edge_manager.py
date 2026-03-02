"""Edge manager for the minimal Knowledge Graph (KG).

MVP rules:
- Every edge must have >= 1 evidence_span_id
- Every evidence_span_id must exist
"""

from __future__ import annotations

from typing import TypedDict, cast

from sqlalchemy import or_, select

from ..db.engine import SessionLocal, engine
from ..domain.models import Base
from .models import EvidenceSpan, KgEdge, KgEdgeEvidence, KgEntity


_tables_initialized = False

_DEFAULT_EVIDENCE_SPAN_IDS: list[str] = []


class EdgeDict(TypedDict):
    edge_id: str
    subject_entity_id: str
    predicate: str
    object_entity_id: str | None
    object_literal: str | None
    evidence_span_ids: list[str]
    confidence: float
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


def _to_edge_dict(edge: KgEdge, evidence_span_ids: list[str]) -> EdgeDict:
    return {
        "edge_id": edge.edge_id,
        "subject_entity_id": edge.subject_entity_id,
        "predicate": edge.predicate,
        "object_entity_id": edge.object_entity_id,
        "object_literal": edge.object_literal,
        "evidence_span_ids": list(evidence_span_ids),
        "confidence": float(edge.confidence_score),
        "created_at": edge.created_at.isoformat()
        if getattr(edge, "created_at", None)
        else None,
    }


def create_edge(
    subject_entity_id: str,
    predicate: str,
    object_entity_id: str | None = None,
    object_literal: str | None = None,
    evidence_span_ids: list[str] = _DEFAULT_EVIDENCE_SPAN_IDS,
    confidence: float = 1.0,
) -> str:
    _ensure_tables()

    if len(evidence_span_ids) == 0:
        raise ValueError("evidence_span_ids must be a non-empty list")

    unique_evidence_span_ids: list[str] = []
    seen: set[str] = set()
    for es_id in evidence_span_ids:
        if not es_id.strip():
            raise ValueError("evidence_span_ids must contain non-empty strings")
        if es_id in seen:
            continue
        seen.add(es_id)
        unique_evidence_span_ids.append(es_id)

    if (object_entity_id is None) == (object_literal is None):
        raise ValueError(
            "edge must have exactly one of object_entity_id or object_literal"
        )

    if not (0.0 <= float(confidence) <= 1.0):
        raise ValueError("confidence must be between 0.0 and 1.0")

    db = SessionLocal()
    try:
        if db.get(KgEntity, subject_entity_id) is None:
            raise ValueError(f"subject_entity_id {subject_entity_id} not found")
        if object_entity_id is not None and db.get(KgEntity, object_entity_id) is None:
            raise ValueError(f"object_entity_id {object_entity_id} not found")

        existing_ids = set(
            db.execute(
                select(EvidenceSpan.evidence_span_id).where(
                    EvidenceSpan.evidence_span_id.in_(unique_evidence_span_ids)
                )
            )
            .scalars()
            .all()
        )
        missing = [
            es_id for es_id in unique_evidence_span_ids if es_id not in existing_ids
        ]
        if missing:
            raise ValueError(f"evidence spans not found: {missing}")

        edge = KgEdge(
            subject_entity_id=subject_entity_id,
            predicate=predicate,
            object_entity_id=object_entity_id,
            object_literal=object_literal,
            confidence_score=float(confidence),
        )
        db.add(edge)
        db.commit()
        db.refresh(edge)

        for es_id in unique_evidence_span_ids:
            db.add(KgEdgeEvidence(edge_id=edge.edge_id, evidence_span_id=es_id))
        db.commit()

        return edge.edge_id
    finally:
        db.close()


def get_edge(edge_id: str) -> EdgeDict:
    _ensure_tables()

    db = SessionLocal()
    try:
        edge = db.get(KgEdge, edge_id)
        if edge is None:
            raise KeyError(f"edge {edge_id} not found")

        evidence_span_ids = list(
            db.execute(
                select(KgEdgeEvidence.evidence_span_id).where(
                    KgEdgeEvidence.edge_id == edge_id
                )
            )
            .scalars()
            .all()
        )
        return _to_edge_dict(edge, evidence_span_ids)
    finally:
        db.close()


def list_edges(
    entity_id: str | None = None, predicate: str | None = None
) -> list[EdgeDict]:
    _ensure_tables()

    db = SessionLocal()
    try:
        stmt = select(KgEdge)
        if predicate is not None:
            stmt = stmt.where(KgEdge.predicate == predicate)
        if entity_id is not None:
            stmt = stmt.where(
                or_(
                    KgEdge.subject_entity_id == entity_id,
                    KgEdge.object_entity_id == entity_id,
                )
            )

        edges = list(db.execute(stmt).scalars().all())
        if not edges:
            return []

        edge_ids = [e.edge_id for e in edges]
        ee_rows = cast(
            list[tuple[str, str]],
            db.execute(
                select(KgEdgeEvidence.edge_id, KgEdgeEvidence.evidence_span_id).where(
                    KgEdgeEvidence.edge_id.in_(edge_ids)
                )
            ).all(),
        )
        evidence_map: dict[str, list[str]] = {eid: [] for eid in edge_ids}
        for eid, esid in ee_rows:
            evidence_map[eid].append(esid)

        return [_to_edge_dict(e, evidence_map.get(e.edge_id, [])) for e in edges]
    finally:
        db.close()
