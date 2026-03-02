"""RAG engine stubs."""

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    max_results: int = Field(default=5, ge=1, le=50)


class QueryResponse(BaseModel):
    verdict: str
    answer: str | None
    citations: list[str]
    message: str


def run_query(request: QueryRequest) -> QueryResponse:
    """Run RAG query stub."""
    return QueryResponse(
        verdict="abstain",
        answer=None,
        citations=[],
        message=f"RAG engine not implemented yet for query '{request.query}'.",
    )
