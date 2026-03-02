"""W3C PROV-DM inspired provenance models.

This module implements the core PROV-DM (PROV Data Model) entities:
- Entity: A thing in the world
- Activity: Something that occurs over time
- Agent: Something responsible for an activity
- Generation: When an entity was created by an activity
- Usage: When an activity used an entity
- Derivation: When an entity was derived from another
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..domain.models import Base


class ProvEntity(Base):
    """An entity - a physical, digital, conceptual, or other kind of thing.

    In W3C PROV-DM, entities are the primary subjects of provenance records.
    """

    __tablename__: str = "prov_entity"

    entity_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(128), nullable=False)
    label: Mapped[str | None] = mapped_column(String(512), nullable=True)
    json_data: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    generated_by: Mapped[list["ProvGeneration"]] = relationship(
        "ProvGeneration", back_populates="entity", cascade="all, delete-orphan"
    )
    used_in: Mapped[list["ProvUsage"]] = relationship(
        "ProvUsage", back_populates="entity", cascade="all, delete-orphan"
    )
    derived_from: Mapped[list["ProvDerivation"]] = relationship(
        "ProvDerivation",
        foreign_keys="ProvDerivation.derived_entity_id",
        back_populates="derived_entity",
        cascade="all, delete-orphan",
    )
    derived_into: Mapped[list["ProvDerivation"]] = relationship(
        "ProvDerivation",
        foreign_keys="ProvDerivation.source_entity_id",
        back_populates="source_entity",
        cascade="all, delete-orphan",
    )


class ProvActivity(Base):
    """An activity - something that occurs over a period of time.

    Activities are the mechanisms through which entities are generated and used.
    """

    __tablename__: str = "prov_activity"

    activity_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    activity_type: Mapped[str] = mapped_column(String(128), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    git_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    params_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Tamper-evident hash chain
    prev_activity_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    activity_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Relationships
    generated: Mapped[list["ProvGeneration"]] = relationship(
        "ProvGeneration", back_populates="activity", cascade="all, delete-orphan"
    )
    used: Mapped[list["ProvUsage"]] = relationship(
        "ProvUsage", back_populates="activity", cascade="all, delete-orphan"
    )
    derived: Mapped[list["ProvDerivation"]] = relationship(
        "ProvDerivation", back_populates="activity", cascade="all, delete-orphan"
    )


class ProvAgent(Base):
    """An agent - something that bears some form of responsibility for an activity.

    Agents can be people, organizations, software, etc.
    """

    __tablename__: str = "prov_agent"

    agent_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_type: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)


class ProvGeneration(Base):
    """Generation - the completion of production of an entity by an activity.

    This is a moment in time when an entity becomes available for use.
    """

    __tablename__: str = "prov_generation"

    entity_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("prov_entity.entity_id"), primary_key=True
    )
    activity_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("prov_activity.activity_id"), nullable=False
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    entity: Mapped["ProvEntity"] = relationship(
        "ProvEntity", back_populates="generated_by"
    )
    activity: Mapped["ProvActivity"] = relationship(
        "ProvActivity", back_populates="generated"
    )


class ProvUsage(Base):
    """Usage - the beginning of utilizing an entity by an activity.

    This is a moment in time when an activity starts using an entity.
    """

    __tablename__: str = "prov_usage"

    activity_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("prov_activity.activity_id"), primary_key=True
    )
    entity_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("prov_entity.entity_id"), primary_key=True
    )
    used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    activity: Mapped["ProvActivity"] = relationship(
        "ProvActivity", back_populates="used"
    )
    entity: Mapped["ProvEntity"] = relationship("ProvEntity", back_populates="used_in")


class ProvDerivation(Base):
    """Derivation - a transformation of an entity into another, or construction
    of a new entity from a pre-existing one.

    This tracks lineage and enables understanding data provenance chains.
    """

    __tablename__: str = "prov_derivation"

    derived_entity_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("prov_entity.entity_id"), primary_key=True
    )
    source_entity_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("prov_entity.entity_id"), primary_key=True
    )
    activity_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("prov_activity.activity_id"), nullable=True
    )

    # Relationships
    derived_entity: Mapped["ProvEntity"] = relationship(
        "ProvEntity", foreign_keys=[derived_entity_id], back_populates="derived_from"
    )
    source_entity: Mapped["ProvEntity"] = relationship(
        "ProvEntity", foreign_keys=[source_entity_id], back_populates="derived_into"
    )
    activity: Mapped[ProvActivity | None] = relationship(
        "ProvActivity", back_populates="derived"
    )
