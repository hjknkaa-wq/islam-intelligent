"""FastAPI routes for EvidenceSpan management.

Provides endpoints for creating, retrieving, and verifying EvidenceSpan records
that cite exact byte ranges within TextUnit documents.
"""

from collections.abc import Generator
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ...db.engine import SessionLocal
from ...domain.models import TextUnit
from ...domain.span_builder import create_span, verify_span_hash
from ...kg.models import EvidenceSpan

router = APIRouter(prefix="/spans", tags=["spans"])


# Dependency
def get_db() -> Generator[Session, None, None]:
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

    model_config = ConfigDict(from_attributes=True)


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


def _to_response(span: EvidenceSpan, verified: bool = False) -> SpanResponse:
    """Convert EvidenceSpan ORM object to response model."""
    return SpanResponse(
        span_id=span.evidence_span_id,
        text_unit_id=span.text_unit_id,
        start_byte=span.start_byte,
        end_byte=span.end_byte,
        snippet_text=span.snippet_text or "",
        snippet_hash=span.snippet_utf8_sha256,
        prefix=span.prefix_text or "",
        suffix=span.suffix_text or "",
        verified=verified,
    )


def _to_verification_payload(span: EvidenceSpan) -> dict[str, str | int]:
    """Convert EvidenceSpan ORM object to verify_span_hash payload."""
    return {
        "start_byte": span.start_byte,
        "end_byte": span.end_byte,
        "snippet_hash": span.snippet_utf8_sha256,
    }


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

    span = EvidenceSpan(
        text_unit_id=span_data["text_unit_id"],
        start_byte=span_data["start_byte"],
        end_byte=span_data["end_byte"],
        snippet_text=span_data["snippet_text"],
        snippet_utf8_sha256=span_data["snippet_hash"],
        prefix_text=span_data["prefix"],
        suffix_text=span_data["suffix"],
    )
    db.add(span)
    db.commit()
    db.refresh(span)

    return _to_response(span, verified=True)


@router.get("/{span_id}", response_model=SpanResponse)
async def get_span(
    span_id: str,
    verify: bool = Query(False, description="Verify span hash against stored text"),
    db: Session = Depends(get_db),
) -> SpanResponse:
    """Get an evidence span by ID.

    Returns the span with optional hash verification against the source TextUnit.
    """
    span = (
        db.query(EvidenceSpan).filter(EvidenceSpan.evidence_span_id == span_id).first()
    )
    if span is None:
        raise HTTPException(status_code=404, detail=f"Span {span_id} not found")

    # Optionally verify the span
    verified = False
    if verify:
        text_unit = (
            db.query(TextUnit)
            .filter(TextUnit.text_unit_id == span.text_unit_id)
            .first()
        )
        if text_unit:
            is_valid, _ = verify_span_hash(
                _to_verification_payload(span), text_unit.text_canonical
            )
            verified = is_valid

    return _to_response(span, verified=verified)


@router.post("/{span_id}/verify", response_model=SpanVerificationResponse)
async def verify_span(
    span_id: str,
    data: SpanVerificationRequest,
    db: Session = Depends(get_db),
) -> SpanVerificationResponse:
    """Verify an evidence span's hash against provided text.

    Recomputes the hash of the cited byte range and compares it to the stored hash.
    """
    span = (
        db.query(EvidenceSpan).filter(EvidenceSpan.evidence_span_id == span_id).first()
    )
    if span is None:
        raise HTTPException(status_code=404, detail=f"Span {span_id} not found")

    is_valid, message = verify_span_hash(
        _to_verification_payload(span), data.text_unit_text
    )

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
    db: Session = Depends(get_db),
) -> SpanListResponse:
    """List evidence spans with optional filters.

    Returns a paginated list of spans. Optionally filter by TextUnit ID.
    """
    query = db.query(EvidenceSpan)
    if text_unit_id:
        query = query.filter(EvidenceSpan.text_unit_id == text_unit_id)

    total = query.count()
    paginated = (
        query.order_by(EvidenceSpan.created_at, EvidenceSpan.evidence_span_id)
        .offset(offset)
        .limit(limit)
        .all()
    )

    return SpanListResponse(
        items=[_to_response(s) for s in paginated],
        total=total,
        limit=limit,
        offset=offset,
    )
