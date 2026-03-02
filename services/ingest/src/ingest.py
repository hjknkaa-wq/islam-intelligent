"""Ingestion service stubs."""

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    source_type: str = Field(..., min_length=1)
    payload: dict[str, object] = Field(default_factory=dict)


class IngestResult(BaseModel):
    status: str
    ingested_records: int
    message: str


def run_ingestion(request: IngestRequest) -> IngestResult:
    """Run ingestion pipeline stub."""
    return IngestResult(
        status="stub",
        ingested_records=0,
        message=f"Ingestion pipeline not implemented yet for '{request.source_type}'.",
    )
