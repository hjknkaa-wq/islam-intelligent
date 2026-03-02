"""FastAPI application entrypoint for RAG service."""

from fastapi import FastAPI
from pydantic import BaseModel

from .rag_engine import QueryRequest, QueryResponse, run_query

app = FastAPI(title="Islam Intelligent RAG Service")


class HealthResponse(BaseModel):
    status: str


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/query", response_model=QueryResponse, tags=["rag"])
async def query(payload: QueryRequest) -> QueryResponse:
    return run_query(payload)
