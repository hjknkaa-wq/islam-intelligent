"""RAG API endpoints."""

import logging
import threading
from typing import Any, cast

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...config import settings
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
                _pipeline = RAGPipeline(
                    RAGConfig(
                        enable_llm=settings.rag_enable_llm,
                        llm_model=settings.rag_llm_model,
                        llm_temperature=settings.rag_llm_temperature,
                        llm_seed=settings.rag_llm_seed,
                        llm_base_url=settings.rag_llm_base_url,
                        enable_hyde=settings.hyde_enabled,
                        hyde_max_tokens=settings.hyde_max_tokens,
                        enable_query_expansion=settings.query_expansion_enabled,
                        query_expansion_variations=settings.query_expansion_count,
                        enable_reranker=settings.rag_enable_reranker,
                        reranker_model=settings.rag_reranker_model,
                        reranker_top_k=settings.rag_reranker_top_k,
                        enable_faithfulness=settings.faithfulness_enabled,
                        faithfulness_threshold=settings.faithfulness_threshold,
                        enable_cost_governance=settings.cost_governance_enabled,
                        daily_budget_usd=settings.daily_budget_usd,
                        weekly_budget_usd=settings.weekly_budget_usd,
                        enable_metrics=settings.metrics_enabled,
                        metrics_db_enabled=settings.metrics_db_enabled,
                    )
                )
    return _pipeline


class QueryRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="User query (max 2000 characters)",
    )
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
async def rag_query(request: QueryRequest):
    """Query the RAG system.

    Returns an answer with citations or an abstention if evidence is insufficient.
    """
    pipeline = get_pipeline()

    try:
        result = cast(Any, await pipeline.aquery(request.query))
        return AnswerResponse(**result)
    except Exception:
        logger.exception("RAG pipeline error")
        raise HTTPException(status_code=500, detail="Internal server error")
