"""RAG API endpoints."""

from typing import Any, cast

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...rag.pipeline import RAGConfig, RAGPipeline

router = APIRouter(prefix="/rag", tags=["rag"])

# Global pipeline instance
_pipeline = None


def get_pipeline():
    """Get or create RAG pipeline instance."""
    global _pipeline
    if _pipeline is None:
        _pipeline = RAGPipeline(RAGConfig())
    return _pipeline


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="User query")
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
