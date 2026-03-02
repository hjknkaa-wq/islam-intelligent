"""FastAPI application entrypoint for ingest service."""

from fastapi import FastAPI
from pydantic import BaseModel

from .ingest import IngestRequest, IngestResult, run_ingestion

app = FastAPI(title="Islam Intelligent Ingest Service")


class HealthResponse(BaseModel):
    status: str


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/ingest", response_model=IngestResult, tags=["ingest"])
async def ingest(payload: IngestRequest) -> IngestResult:
    return run_ingestion(payload)
