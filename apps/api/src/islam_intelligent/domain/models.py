"""Domain model scaffolding."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Integer, Text, DateTime, func, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

if TYPE_CHECKING:
    # Avoid import cycles with islam_intelligent.provenance.models at type-check time.
    class ProvEntity:  # pragma: no cover
        pass


class Base(DeclarativeBase):
    pass


class SourceDocument(Base):
    """Source document with append-only versioning.

    Each update creates a NEW row; old rows remain accessible.
    The version chain is tracked via supersedes_source_id.
    """

    __tablename__: str = "source_document"

    # Primary key - unique per version
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Logical source identifier - same across versions
    source_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Version number (starts at 1)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Chain link: which source document this supersedes
    supersedes_source_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("source_document.source_id"), nullable=True, index=True
    )

    # Which version this supersedes
    supersedes_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Source metadata
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # e.g., 'quran', 'hadith_bukhari', 'tafsir', 'fiqh'

    # Trust gating status
    # NOTE: This column already exists in the DB schema; we map it here to enforce
    # trusted-only answering in RAG.
    trust_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="untrusted", index=True
    )

    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    author: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True, default="ar"
    )

    # Content - stored as JSON string for flexibility
    content_json: Mapped[str] = mapped_column(Text, nullable=False)

    # Content hash for integrity verification
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Full manifest hash (includes metadata)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Provenance link
    prov_entity_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("prov_entity.entity_id"), nullable=True, index=True
    )

    # Relationships
    prov_entity: Mapped[Optional["ProvEntity"]] = relationship("ProvEntity")

    # Self-referential relationship for version chain
    superseded_by: Mapped[Optional["SourceDocument"]] = relationship(
        "SourceDocument",
        primaryjoin=(
            "and_(SourceDocument.source_id==remote(SourceDocument.supersedes_source_id), "
            + "SourceDocument.version==remote(SourceDocument.supersedes_version))"
        ),
        remote_side=[source_id, version],
        uselist=False,
    )

    def __repr__(self) -> str:
        return f"<SourceDocument(source_id={self.source_id}, version={self.version})>"


class TextUnit(Base):
    """Text unit (ayah, hadith, tafsir section, etc.) with canonical ID.

    Each text unit represents an atomic piece of Islamic knowledge
    with a globally unique canonical identifier.
    """

    __tablename__: str = "text_unit"

    # Primary key - unique UUID
    text_unit_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, nullable=False
    )

    # Foreign key to source document
    source_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("source_document.source_id"), nullable=False, index=True
    )

    # Type of unit
    unit_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # e.g., 'quran_ayah', 'hadith_item', 'tafsir_section'

    # Globally unique canonical identifier
    canonical_id: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, index=True
    )
    # e.g., 'quran:1:1', 'hadith:bukhari:sahih:1'

    # Structured location information (JSON)
    canonical_locator_json: Mapped[str] = mapped_column(Text, nullable=False)

    # Canonical text (NFC normalized)
    text_canonical: Mapped[str] = mapped_column(Text, nullable=False)

    # SHA-256 hash of canonical text
    text_canonical_utf8_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationship to source document
    source: Mapped["SourceDocument"] = relationship("SourceDocument")

    def __repr__(self) -> str:
        return f"<TextUnit(canonical_id={self.canonical_id}, type={self.unit_type})>"
