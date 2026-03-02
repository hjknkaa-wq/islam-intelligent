"""FastAPI routes for source document management."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from islam_intelligent.db.engine import SessionLocal
from islam_intelligent.ingest import source_registry
from islam_intelligent.domain.models import SourceDocument

router = APIRouter(prefix="/sources", tags=["sources"])


# Dependency
def get_db() -> Session:
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Pydantic schemas
class SourceCreate(BaseModel):
    """Schema for creating a new source document."""

    source_type: str = Field(
        ..., description="Type of source (e.g., 'quran', 'hadith_bukhari')"
    )
    content: dict[str, Any] = Field(..., description="Document content")
    title: Optional[str] = Field(None, description="Document title")
    author: Optional[str] = Field(None, description="Document author")
    language: str = Field(default="ar", description="Language code (default: 'ar')")
    source_id: Optional[str] = Field(None, description="Optional explicit source ID")


class SourceUpdate(BaseModel):
    """Schema for updating a source document."""

    content: dict[str, Any] = Field(..., description="New document content")
    title: Optional[str] = Field(None, description="New title")
    author: Optional[str] = Field(None, description="New author")
    language: Optional[str] = Field(None, description="New language code")
    source_type: Optional[str] = Field(None, description="New source type")


class SourceResponse(BaseModel):
    """Schema for source document response."""

    id: int
    source_id: str
    version: int
    source_type: str
    title: Optional[str]
    author: Optional[str]
    language: str
    content_sha256: str
    manifest_sha256: str
    created_at: str
    created_by: Optional[str]
    supersedes_source_id: Optional[str]
    supersedes_version: Optional[int]

    class Config:
        from_attributes = True


class SourceListResponse(BaseModel):
    """Schema for paginated list response."""

    items: list[SourceResponse]
    total: int
    limit: int
    offset: int


class ManifestResponse(BaseModel):
    """Schema for manifest response."""

    source_id: str
    version: int
    source_type: str
    title: Optional[str]
    author: Optional[str]
    language: str
    content_sha256: str
    manifest_sha256: str
    created_at: Optional[str]
    created_by: Optional[str]
    supersedes: Optional[dict[str, Any]]
    hash_verified: bool


# Helper to convert ORM to response
def _to_response(doc: SourceDocument) -> SourceResponse:
    """Convert SourceDocument ORM to response model."""
    return SourceResponse(
        id=doc.id,
        source_id=doc.source_id,
        version=doc.version,
        source_type=doc.source_type,
        title=doc.title,
        author=doc.author,
        language=doc.language,
        content_sha256=doc.content_sha256,
        manifest_sha256=doc.manifest_sha256,
        created_at=doc.created_at.isoformat() if doc.created_at else "",
        created_by=doc.created_by,
        supersedes_source_id=doc.supersedes_source_id,
        supersedes_version=doc.supersedes_version,
    )


@router.post("", response_model=SourceResponse, status_code=201)
async def create_source(
    data: SourceCreate,
    db: Session = Depends(get_db),
) -> SourceResponse:
    """Create a new source document.

    Creates the first version of a source document with generated hashes.
    """
    doc = source_registry.create_source_document(
        db=db,
        source_type=data.source_type,
        content=data.content,
        title=data.title,
        author=data.author,
        language=data.language,
        source_id=data.source_id,
    )
    return _to_response(doc)


@router.get("/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: str,
    version: Optional[int] = Query(None, description="Specific version to retrieve"),
    db: Session = Depends(get_db),
) -> SourceResponse:
    """Get a source document by ID.

    Returns the latest version by default, or a specific version if requested.
    """
    doc = source_registry.get_source_document(db, source_id, version)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")
    return _to_response(doc)


@router.get("", response_model=SourceListResponse)
async def list_sources(
    source_type: Optional[str] = Query(None, description="Filter by source type"),
    author: Optional[str] = Query(None, description="Filter by author"),
    language: Optional[str] = Query(None, description="Filter by language"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    latest_only: bool = Query(
        True, description="Return only latest version per source"
    ),
    db: Session = Depends(get_db),
) -> SourceListResponse:
    """List source documents with optional filters.

    Returns a paginated list of sources. By default, only returns the
    latest version of each source.
    """
    docs = source_registry.list_sources(
        db=db,
        source_type=source_type,
        author=author,
        language=language,
        limit=limit,
        offset=offset,
        latest_only=latest_only,
    )

    return SourceListResponse(
        items=[_to_response(d) for d in docs],
        total=len(docs),
        limit=limit,
        offset=offset,
    )


@router.put("/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: str,
    data: SourceUpdate,
    db: Session = Depends(get_db),
) -> SourceResponse:
    """Update a source document - creates NEW version.

    This is an append-only operation. The old version remains accessible
    via the version number. The new version links to the old via
    supersedes_source_id.
    """
    update_data = {"content": data.content}
    if data.title is not None:
        update_data["title"] = data.title
    if data.author is not None:
        update_data["author"] = data.author
    if data.language is not None:
        update_data["language"] = data.language
    if data.source_type is not None:
        update_data["source_type"] = data.source_type

    doc = source_registry.update_source(db, source_id, update_data)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")

    return _to_response(doc)


@router.get("/{source_id}/manifest", response_model=ManifestResponse)
async def get_manifest(
    source_id: str,
    db: Session = Depends(get_db),
) -> ManifestResponse:
    """Get manifest for a source document.

    Returns the complete manifest including all hashes for verification.
    """
    manifest = source_registry.generate_manifest(source_id, db)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")

    return ManifestResponse(**manifest)


@router.get("/{source_id}/versions", response_model=list[SourceResponse])
async def get_versions(
    source_id: str,
    db: Session = Depends(get_db),
) -> list[SourceResponse]:
    """Get complete version history for a source.

    Returns all versions ordered from oldest to newest.
    """
    docs = source_registry.get_version_history(db, source_id)
    return [_to_response(d) for d in docs]
