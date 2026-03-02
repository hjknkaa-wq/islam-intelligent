"""SQLAlchemy models for the minimal Knowledge Graph.

These tables mirror the canonical schema in `packages/schemas/sql/0001_init.sql`.

Note: This repo currently runs against SQLite in-memory for the API scaffold,
so we use portable column types (String/Text/Float) rather than Postgres UUID.
"""

# pyright: reportIncompatibleVariableOverride=false

from __future__ import annotations

import uuid
from datetime import datetime
from typing import ClassVar, final

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..domain.models import Base


@final
class KgEntity(Base):
    __tablename__: ClassVar[str] = "kg_entity"
    __table_args__: ClassVar[tuple[UniqueConstraint]] = (
        UniqueConstraint(
            "entity_type", "canonical_name", name="uq_kg_entity_type_name"
        ),
    )

    entity_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    entity_type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    aliases_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


@final
class EvidenceSpan(Base):
    __tablename__: ClassVar[str] = "evidence_span"

    evidence_span_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    text_unit_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("text_unit.text_unit_id"), nullable=False, index=True
    )
    start_byte: Mapped[int] = mapped_column(Integer, nullable=False)
    end_byte: Mapped[int] = mapped_column(Integer, nullable=False)
    snippet_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    snippet_utf8_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    prefix_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    suffix_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


@final
class KgEdge(Base):
    __tablename__: ClassVar[str] = "kg_edge"

    edge_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    subject_entity_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("kg_entity.entity_id"), nullable=False, index=True
    )
    predicate: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    object_entity_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("kg_entity.entity_id"), nullable=True, index=True
    )
    object_literal: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


@final
class KgEdgeEvidence(Base):
    __tablename__: ClassVar[str] = "kg_edge_evidence"

    edge_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("kg_edge.edge_id"), primary_key=True
    )
    evidence_span_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("evidence_span.evidence_span_id"), primary_key=True
    )
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
