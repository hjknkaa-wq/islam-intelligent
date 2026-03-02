"""RAG API endpoints."""

import logging
import threading
from typing import Any, cast

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...rag.pipeline import RAGConfig, RAGPipeline

router = APIRouter(prefix="/rag", tags=["rag"])

logger = logging.getLogger(__name__)

# Global pipeline instance protected by a lock for thread safety
_pipeline: RAGPipeline | None = None
_pipeline_lock = threading.Lock()


def get_pipeline() -> RAGPipeline:
    """Get or create RAG pipeline instance (thread-safe)."""
    global _pipeline
    if _pipeline is None:
        with _pipeline_lock:
            if _pipeline is None:
                _pipeline = RAGPipeline(RAGConfig())
    return _pipeline


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="User query (max 2000 characters)")
    max_results: int = Field(default=10, ge=1, le=50)


class CitationResponse(BaseModel):
    evidence_span_id: str
    canonical_id: str
    snippet: str


class StatementResponse(BaseModel):
    text: str
    citations: list[CitationResponse]


class AnswerResponse(BaseModel):
    verdict: str  # "answer" or "abstain"
    statements: list[StatementResponse]
    abstain_reason: str | None
    fail_reason: str | None = None
    retrieved_count: int
    sufficiency_score: float


@router.post("/query", response_model=AnswerResponse)
def rag_query(request: QueryRequest):
    """Query the RAG system.

    Returns an answer with citations or an abstention if evidence is insufficient.
    """
    pipeline = get_pipeline()

    try:
        result = cast(Any, pipeline.query(request.query))
        return AnswerResponse(**result)
    except Exception:
        logger.exception("RAG pipeline error")
        raise HTTPException(status_code=500, detail="Internal server error")
