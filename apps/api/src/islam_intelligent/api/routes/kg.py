"""FastAPI routes for the minimal Knowledge Graph (KG)."""

from __future__ import annotations

# pyright: reportCallInDefaultInitializer=false, reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportAttributeAccessIssue=false

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ...kg.entity_manager import (
    create_entity as kg_create_entity,
    get_entity as kg_get_entity,
    list_entities as kg_list_entities,
    search_entities as kg_search_entities,
)
from ...kg.edge_manager import (
    create_edge as kg_create_edge,
    get_edge as kg_get_edge,
    list_edges as kg_list_edges,
)


router = APIRouter(prefix="/kg", tags=["kg"])


class EntityCreate(BaseModel):
    entity_type: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None


class EntityResponse(BaseModel):
    entity_id: str
    entity_type: str
    canonical_name: str
    aliases: list[str]
    description: str | None
    created_at: str | None


@router.post("/entities", response_model=EntityResponse, status_code=201)
async def create_entity(data: EntityCreate) -> EntityResponse:
    try:
        entity_id = kg_create_entity(
            entity_type=data.entity_type,
            canonical_name=data.canonical_name,
            aliases=data.aliases,
            description=data.description,
        )
        return EntityResponse(**kg_get_entity(entity_id))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/entities/{entity_id}", response_model=EntityResponse)
async def get_entity(entity_id: str) -> EntityResponse:
    try:
        return EntityResponse(**kg_get_entity(entity_id))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/entities", response_model=list[EntityResponse])
async def list_entities(
    entity_type: str | None = Query(None, description="Filter by entity type"),
    query: str | None = Query(None, description="Search canonical_name or aliases"),
) -> list[EntityResponse]:
    try:
        if query is not None and query.strip():
            items = kg_search_entities(query)
            if entity_type is not None:
                items = [i for i in items if i.get("entity_type") == entity_type]
        else:
            items = kg_list_entities(entity_type=entity_type)
        return [EntityResponse(**i) for i in items]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class EdgeCreate(BaseModel):
    subject_entity_id: str
    predicate: str
    object_entity_id: str | None = None
    object_literal: str | None = None
    evidence_span_ids: list[str] = Field(..., min_length=1)
    confidence: float = Field(1.0, ge=0.0, le=1.0)


class EdgeResponse(BaseModel):
    edge_id: str
    subject_entity_id: str
    predicate: str
    object_entity_id: str | None
    object_literal: str | None
    evidence_span_ids: list[str]
    confidence: float
    created_at: str | None


@router.post("/edges", response_model=EdgeResponse, status_code=201)
async def create_edge(data: EdgeCreate) -> EdgeResponse:
    try:
        edge_id = kg_create_edge(
            subject_entity_id=data.subject_entity_id,
            predicate=data.predicate,
            object_entity_id=data.object_entity_id,
            object_literal=data.object_literal,
            evidence_span_ids=data.evidence_span_ids,
            confidence=data.confidence,
        )
        return EdgeResponse(**kg_get_edge(edge_id))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/edges/{edge_id}", response_model=EdgeResponse)
async def get_edge(edge_id: str) -> EdgeResponse:
    try:
        return EdgeResponse(**kg_get_edge(edge_id))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/edges", response_model=list[EdgeResponse])
async def list_edges(
    entity_id: str | None = Query(None, description="Filter by subject/object entity"),
    predicate: str | None = Query(None, description="Filter by predicate"),
) -> list[EdgeResponse]:
    items = kg_list_edges(entity_id=entity_id, predicate=predicate)
    return [EdgeResponse(**i) for i in items]
