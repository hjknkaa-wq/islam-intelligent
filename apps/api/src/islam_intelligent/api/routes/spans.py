"""FastAPI routes for EvidenceSpan management.

Provides endpoints for creating, retrieving, and verifying EvidenceSpan records
that cite exact byte ranges within TextUnit documents.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...db.engine import SessionLocal
from ...domain.models import TextUnit
from ...domain.span_builder import create_span, verify_span_hash
from islam_intelligent.domain.models import TextUnit
from islam_intelligent.domain.span_builder import create_span, verify_span_hash

router = APIRouter(prefix="/spans", tags=["spans"])


# Dependency
def get_db() -> Session:
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Pydantic schemas
class SpanCreate(BaseModel):
    """Schema for creating a new evidence span."""

    text_unit_id: str = Field(..., description="UUID of the parent TextUnit")
    start_byte: int = Field(..., ge=0, description="Starting byte offset (inclusive)")
    end_byte: int = Field(..., gt=0, description="Ending byte offset (exclusive)")


class SpanResponse(BaseModel):
    """Schema for span response."""

    span_id: str
    text_unit_id: str
    start_byte: int
    end_byte: int
    snippet_text: str
    snippet_hash: str
    prefix: str
    suffix: str
    verified: bool

    class Config:
        from_attributes = True


class SpanVerificationRequest(BaseModel):
    """Schema for span verification request."""

    text_unit_text: str = Field(
        ..., description="Full text of the TextUnit for verification"
    )


class SpanVerificationResponse(BaseModel):
    """Schema for span verification response."""

    span_id: str
    verified: bool
    message: Optional[str] = None


class SpanListResponse(BaseModel):
    """Schema for paginated list response."""

    items: list[SpanResponse]
    total: int
    limit: int
    offset: int


# In-memory storage for spans (replace with database in production)
_spans: dict[str, dict] = {}
_span_counter: int = 0


def _generate_span_id() -> str:
    """Generate unique span ID."""
    global _span_counter
    _span_counter += 1
    return f"span_{_span_counter:08d}"


def _to_response(span: dict, verified: bool = False) -> SpanResponse:
    """Convert span dict to response model."""
    return SpanResponse(
        span_id=span.get("span_id", ""),
        text_unit_id=span["text_unit_id"],
        start_byte=span["start_byte"],
        end_byte=span["end_byte"],
        snippet_text=span["snippet_text"],
        snippet_hash=span["snippet_hash"],
        prefix=span["prefix"],
        suffix=span["suffix"],
        verified=verified,
    )


@router.post("", response_model=SpanResponse, status_code=201)
async def create_span_endpoint(
    data: SpanCreate,
    db: Session = Depends(get_db),
) -> SpanResponse:
    """Create a new evidence span.

    Creates a span citing a specific byte range within a TextUnit.
    The span includes a SHA-256 hash for integrity verification.
    """
    # Fetch the text unit from database
    text_unit = (
        db.query(TextUnit).filter(TextUnit.text_unit_id == data.text_unit_id).first()
    )

    if text_unit is None:
        raise HTTPException(
            status_code=404, detail=f"TextUnit {data.text_unit_id} not found"
        )

    # Validate byte offsets against text length
    text_bytes = text_unit.text_canonical.encode("utf-8")
    if data.end_byte > len(text_bytes):
        raise HTTPException(
            status_code=400,
            detail=f"end_byte ({data.end_byte}) exceeds text length ({len(text_bytes)})",
        )

    if data.start_byte >= data.end_byte:
        raise HTTPException(
            status_code=400,
            detail=f"start_byte ({data.start_byte}) must be less than end_byte ({data.end_byte})",
        )

    # Create the span
    try:
        span_data = create_span(
            text_unit_id=data.text_unit_id,
            start_byte=data.start_byte,
            end_byte=data.end_byte,
            text_unit_text=text_unit.text_canonical,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Assign span ID and store
    span_id = _generate_span_id()
    span_data["span_id"] = span_id
    _spans[span_id] = span_data

    return _to_response(span_data, verified=True)


@router.get("/{span_id}", response_model=SpanResponse)
async def get_span(
    span_id: str,
    verify: bool = Query(False, description="Verify span hash against stored text"),
    db: Session = Depends(get_db),
) -> SpanResponse:
    """Get an evidence span by ID.

    Returns the span with optional hash verification against the source TextUnit.
    """
    if span_id not in _spans:
        raise HTTPException(status_code=404, detail=f"Span {span_id} not found")

    span = _spans[span_id]

    # Optionally verify the span
    verified = False
    if verify:
        text_unit = (
            db.query(TextUnit)
            .filter(TextUnit.text_unit_id == span["text_unit_id"])
            .first()
        )
        if text_unit:
            is_valid, _ = verify_span_hash(span, text_unit.text_canonical)
            verified = is_valid

    return _to_response(span, verified=verified)


@router.post("/{span_id}/verify", response_model=SpanVerificationResponse)
async def verify_span(
    span_id: str,
    data: SpanVerificationRequest,
) -> SpanVerificationResponse:
    """Verify an evidence span's hash against provided text.

    Recomputes the hash of the cited byte range and compares it to the stored hash.
    """
    if span_id not in _spans:
        raise HTTPException(status_code=404, detail=f"Span {span_id} not found")

    span = _spans[span_id]

    is_valid, message = verify_span_hash(span, data.text_unit_text)

    return SpanVerificationResponse(
        span_id=span_id,
        verified=is_valid,
        message=message,
    )


@router.get("", response_model=SpanListResponse)
async def list_spans(
    text_unit_id: Optional[str] = Query(None, description="Filter by TextUnit ID"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
) -> SpanListResponse:
    """List evidence spans with optional filters.

    Returns a paginated list of spans. Optionally filter by TextUnit ID.
    """
    # Filter spans
    filtered_spans = list(_spans.values())
    if text_unit_id:
        filtered_spans = [
            s for s in filtered_spans if s["text_unit_id"] == text_unit_id
        ]

    # Apply pagination
    total = len(filtered_spans)
    paginated = filtered_spans[offset : offset + limit]

    return SpanListResponse(
        items=[_to_response(s) for s in paginated],
        total=total,
        limit=limit,
        offset=offset,
    )
