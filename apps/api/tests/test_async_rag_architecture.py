"""Tests for async RAG architecture and database pooling."""

from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false

import asyncio
import time
from types import MethodType
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from islam_intelligent.api.main import app
from islam_intelligent.api.routes import rag as rag_route
from islam_intelligent.db import engine as db_engine
from islam_intelligent.rag.pipeline.core import RAGPipeline


def _abstain_result() -> dict[str, Any]:
    """
    Return a standardized abstain result used by tests.
    
    The dictionary represents a pipeline decision that abstains due to insufficient evidence: no retrieved statements, both reason fields set to "insufficient_evidence", a retrieved_count of 0, and a sufficiency_score of 0.0.
    
    Returns:
        dict[str, Any]: A result dictionary containing keys:
            - "verdict": "abstain"
            - "statements": empty list
            - "abstain_reason": "insufficient_evidence"
            - "fail_reason": "insufficient_evidence"
            - "retrieved_count": 0
            - "sufficiency_score": 0.0
    """
    return {
        "verdict": "abstain",
        "statements": [],
        "abstain_reason": "insufficient_evidence",
        "fail_reason": "insufficient_evidence",
        "retrieved_count": 0,
        "sufficiency_score": 0.0,
    }


def test_engine_pool_configuration() -> None:
    assert db_engine.POOL_SIZE == 20
    assert db_engine.MAX_OVERFLOW == 30

    pool = db_engine.engine.pool
    pool_size = getattr(pool, "size", None)
    if callable(pool_size):
        assert pool_size() == 20

    max_overflow = getattr(pool, "_max_overflow", None)
    if isinstance(max_overflow, int):
        assert max_overflow == 30


@pytest.mark.asyncio()
async def test_async_session_support() -> None:
    if db_engine.AsyncSessionLocal is None:
        pytest.skip("Async database session is unavailable")

    async with db_engine.AsyncSessionLocal() as session:
        assert isinstance(session, AsyncSession)
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1


@pytest.mark.asyncio()
async def test_async_pipeline_wrapper_non_blocking() -> None:
    pipeline = RAGPipeline()

    def _slow_generate(
        self: RAGPipeline,
        query: str,
        retrieved: list[dict[str, object]] | None = None,
    ) -> dict[str, Any]:
        """
        Simulates a slow, blocking pipeline generate function for use in tests.
        
        Parameters:
            query (str): The input query string.
            retrieved (list[dict[str, object]] | None): Optional list of retrieved document records.
        
        Returns:
            dict[str, Any]: A dictionary representing an "abstain" verdict with empty statements and zeroed counts/scores.
        """
        _ = (query, retrieved)
        time.sleep(0.2)
        return _abstain_result()

    pipeline.generate_answer = MethodType(_slow_generate, pipeline)

    long_task = asyncio.create_task(pipeline.agenerate_answer("test-query"))
    await asyncio.wait_for(asyncio.sleep(0.01), timeout=0.05)
    assert long_task.done() is False

    result = await asyncio.wait_for(long_task, timeout=1.0)
    assert result["verdict"] == "abstain"


def test_rag_query_endpoint_uses_async_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verifies the /rag/query endpoint invokes the pipeline's async `aquery` and returns HTTP 200.
    
    Replaces the route's pipeline with a mock whose `aquery` is an AsyncMock that returns an abstain result, posts a query to the endpoint, and asserts the endpoint responds with status 200 and that `aquery` was awaited once with the provided query.
    """
    pipeline = MagicMock()
    pipeline.aquery = AsyncMock(return_value=_abstain_result())
    monkeypatch.setattr(rag_route, "get_pipeline", lambda: pipeline)

    client = TestClient(app)
    response = client.post("/rag/query", json={"query": "test query"})

    assert response.status_code == 200
    pipeline.aquery.assert_awaited_once_with("test query")


def test_rag_query_endpoint_handles_async_pipeline_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify the RAG query endpoint returns HTTP 500 when the asynchronous pipeline raises an error.
    
    Patches the route's pipeline provider with a mock whose `aquery` coroutine raises `RuntimeError("boom")`, sends a POST to `/rag/query`, and asserts the response status code is 500.
    """
    pipeline = MagicMock()
    pipeline.aquery = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(rag_route, "get_pipeline", lambda: pipeline)

    client = TestClient(app)
    response = client.post("/rag/query", json={"query": "test query"})

    assert response.status_code == 500
