"""Tests for LLM availability and fallback-to-mock behavior."""

from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false

import pytest

from islam_intelligent.rag.generator import LLMGenerator
from islam_intelligent.rag.pipeline import RAGConfig, RAGPipeline


def _trusted_result(evidence_span_id: str, score: float = 0.9) -> dict[str, object]:
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
