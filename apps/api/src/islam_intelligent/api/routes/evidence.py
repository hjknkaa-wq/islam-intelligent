"""Evidence API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...db.engine import SessionLocal
from ...domain.models import TextUnit
from ...kg.models import EvidenceSpan as EvidenceSpanModel

router = APIRouter(prefix="/evidence", tags=["evidence"])


def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class EvidenceResponse(BaseModel):
    """Response schema for evidence."""

    evidence_span_id: str
    text_unit_id: str
    canonical_id: str
    start_byte: int
    end_byte: int
    snippet_text: str
    snippet_hash: str
    locator: dict
    source_info: dict


@router.get("/{evidence_span_id}", response_model=EvidenceResponse)
async def get_evidence(evidence_span_id: str, db: Session = Depends(get_db)):
    """Get evidence span with snippet, locator, and hashes.

    Returns complete evidence information including:
    - Snippet text and hash
    - Canonical locator (e.g., quran:1:1)
    - Source information
    """
    # Find the evidence span
    span = (
        db.query(EvidenceSpanModel)
        .filter(EvidenceSpanModel.evidence_span_id == evidence_span_id)
        .first()
    )

    if span is None:
        raise HTTPException(status_code=404, detail="Evidence span not found")

    # Get the text unit for locator and source
    text_unit = (
        db.query(TextUnit).filter(TextUnit.text_unit_id == span.text_unit_id).first()
    )

    if text_unit is None:
        raise HTTPException(status_code=404, detail="Text unit not found")

    return EvidenceResponse(
        evidence_span_id=span.evidence_span_id,
        text_unit_id=span.text_unit_id,
        canonical_id=text_unit.canonical_id,
        start_byte=span.start_byte,
        end_byte=span.end_byte,
        snippet_text=span.snippet_text,
        snippet_hash=span.snippet_utf8_sha256,
        locator=text_unit.canonical_locator_json or {},
        source_info={
            "source_id": text_unit.source_id,
            "unit_type": text_unit.unit_type,
        },
    )
