"""Tests for LLM availability and fallback-to-mock behavior."""

from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false

import pytest

from islam_intelligent.rag.generator import LLMGenerator
from islam_intelligent.rag.pipeline import RAGConfig, RAGPipeline


def _trusted_result(evidence_span_id: str, score: float = 0.9) -> dict[str, object]:
    """
    Constructs a synthetic trusted evidence dictionary used by tests.
    
    Parameters:
        evidence_span_id (str): Identifier for the evidence span; also used as the text unit id.
        score (float): Relevance/confidence score for the evidence, between 0 and 1 (default 0.9).
    
    Returns:
        dict: A dictionary representing a trusted evidence item with keys:
          - "evidence_span_id" (str)
          - "text_unit_id" (str)
          - "score" (float)
          - "snippet" (str)
          - "canonical_id" (str)
          - "source_id" (str)
          - "trust_status" (str)
    """
    return {
        "evidence_span_id": evidence_span_id,
        "text_unit_id": evidence_span_id,
        "score": score,
        "snippet": "sample snippet",
        "canonical_id": "quran:1:1",
        "source_id": "source:trusted",
        "trust_status": "trusted",
    }


def test_llm_generator_is_unavailable_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    generator = LLMGenerator(api_key=None)

    assert generator.is_available() is False


def test_pipeline_falls_back_to_mock_when_llm_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Verify that RAGPipeline falls back to a deterministic mock statement generator when the LLM is unavailable.
    
    Sets OPENAI_API_KEY to unset, constructs an LLMGenerator with no API key and a RAGPipeline configured to prefer using the LLM, then calls _generate_statements with mocked retrieved evidence. Asserts that the pipeline returns at least one statement, the first statement's text matches the expected mock output, and the first statement includes citations.
    """
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    generator = LLMGenerator(api_key=None)
    pipeline = RAGPipeline(
        config=RAGConfig(enable_llm=True, sufficiency_threshold=0.1),
        generator=generator,
    )
    retrieved = [_trusted_result("es_1"), _trusted_result("es_2", score=0.2)]

    statements = pipeline._generate_statements("test query", retrieved)

    assert statements
    assert (
        statements[0]["text"]
        == "Based on the evidence, here is information about the query."
    )
    assert statements[0]["citations"]


def test_generate_raises_runtime_error_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    generator = LLMGenerator(api_key=None)

    with pytest.raises(RuntimeError, match="LLM unavailable"):
        generator.generate("query", [_trusted_result("es_1")])
