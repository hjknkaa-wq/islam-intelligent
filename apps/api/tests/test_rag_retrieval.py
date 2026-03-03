"""Retrieval tests for the RAG pipeline.

Includes deterministic unit tests for:
- lexical search
- vector (placeholder) search
- hybrid composition logic
- trust filtering
"""

from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUntypedBaseClass=false, reportUnusedCallResult=false, reportUnknownLambdaType=false

import hashlib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from islam_intelligent.domain.models import Base, SourceDocument, TextUnit
from islam_intelligent.rag.pipeline import RAGPipeline
from islam_intelligent.rag.retrieval.hybrid import search_hybrid
from islam_intelligent.rag.retrieval.lexical import search_lexical
from islam_intelligent.rag.retrieval.vector import is_vector_available, search_vector


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture()
def lexical_inmemory(monkeypatch):  # type: ignore[no-untyped-def]
    """Patch lexical search to use an in-memory SQLite engine."""
    import islam_intelligent.rag.retrieval.lexical as lexical

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    monkeypatch.setattr(lexical, "engine", engine)
    monkeypatch.setattr(lexical, "SessionLocal", SessionLocal)
    monkeypatch.setattr(lexical, "_tables_initialized", False)

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _add_doc_and_unit(
    db,
    *,
    source_id: str,
    canonical_id: str,
    text_unit_id: str,
    text: str,
    trust_status: str = "trusted",
) -> None:
    existing = (
        db.query(SourceDocument)
        .filter(SourceDocument.source_id == source_id)
        .filter(SourceDocument.version == 1)
        .first()
    )
    if existing is None:
        doc = SourceDocument(
            source_id=source_id,
            source_type="quran",
            trust_status=trust_status,
            content_json="{}",
            content_sha256=_sha256_hex(""),
            manifest_sha256=_sha256_hex("manifest:" + source_id),
            version=1,
        )
        db.add(doc)
    unit = TextUnit(
        text_unit_id=text_unit_id,
        source_id=source_id,
        unit_type="quran_ayah",
        canonical_id=canonical_id,
        canonical_locator_json="{}",
        text_canonical=text,
        text_canonical_utf8_sha256=_sha256_hex(text),
    )
    db.add(unit)
    db.commit()


class TestLexicalSearch:
    def test_lexical_blank_query_returns_empty(self) -> None:
        assert search_lexical("") == []
        assert search_lexical("   ") == []

    def test_lexical_inmemory_returns_match(self, lexical_inmemory) -> None:  # type: ignore[no-untyped-def]
        _add_doc_and_unit(
            lexical_inmemory,
            source_id="src_1",
            canonical_id="quran:1:1",
            text_unit_id="tu_1",
            text="abc def ghi",
        )
        results = search_lexical("def", limit=5)
        assert len(results) == 1
        r = results[0]
        assert r["text_unit_id"] == "tu_1"
        assert r["canonical_id"] == "quran:1:1"
        assert r["trust_status"].lower() == "trusted"
        assert "def" in r["snippet"]
        assert 0.0 <= r["score"] <= 1.0

    def test_lexical_scores_exact_match_higher(self, lexical_inmemory) -> None:  # type: ignore[no-untyped-def]
        _add_doc_and_unit(
            lexical_inmemory,
            source_id="src_1",
            canonical_id="quran:1:1",
            text_unit_id="tu_partial",
            text="abc def ghi",
        )
        _add_doc_and_unit(
            lexical_inmemory,
            source_id="src_1",
            canonical_id="quran:1:2",
            text_unit_id="tu_exact",
            text="def",
        )
        results = search_lexical("def", limit=10)
        assert len(results) >= 2
        assert results[0]["text_unit_id"] == "tu_exact"
        assert results[0]["score"] == 1.0
        assert results[0]["score"] >= results[1]["score"]

    def test_lexical_respects_limit(self, lexical_inmemory) -> None:  # type: ignore[no-untyped-def]
        for i in range(5):
            _add_doc_and_unit(
                lexical_inmemory,
                source_id="src_1",
                canonical_id=f"quran:1:{i + 1}",
                text_unit_id=f"tu_{i}",
                text=f"def {i}",
            )
        results = search_lexical("def", limit=2)
        assert len(results) == 2


class TestVectorSearch:
    def test_vector_placeholder_disabled(self) -> None:
        assert is_vector_available() is False
        assert search_vector("anything", limit=5) == []


class TestHybridSearch:
    def test_hybrid_blank_query_returns_empty(self) -> None:
        assert search_hybrid("") == []
        assert search_hybrid("   ") == []

    def test_hybrid_vector_unavailable_returns_lexical_only(self, monkeypatch):  # type: ignore[no-untyped-def]
        import islam_intelligent.rag.retrieval.hybrid as hybrid

        monkeypatch.setattr(hybrid, "is_vector_available", lambda: False)
        monkeypatch.setattr(
            hybrid,
            "search_lexical",
            lambda q, limit=10: [
                {
                    "text_unit_id": "tu_1",
                    "score": 0.9,
                    "snippet": "lex",
                    "canonical_id": "quran:1:1",
                    "source_id": "src_1",
                    "trust_status": "trusted",
                }
            ],
        )
        out = hybrid.search_hybrid("q", limit=10)
        assert out == [
            {
                "text_unit_id": "tu_1",
                "score": 0.9,
                "snippet": "lex",
                "canonical_id": "quran:1:1",
                "source_id": "src_1",
                "trust_status": "trusted",
            }
        ]

    def test_hybrid_vector_available_but_empty_falls_back_to_lexical(self, monkeypatch):  # type: ignore[no-untyped-def]
        import islam_intelligent.rag.retrieval.hybrid as hybrid

        monkeypatch.setattr(hybrid, "is_vector_available", lambda: True)
        monkeypatch.setattr(hybrid, "search_vector", lambda q, limit=10: [])
        monkeypatch.setattr(
            hybrid,
            "search_lexical",
            lambda q, limit=10: [
                {"text_unit_id": "tu_1", "score": 0.8, "snippet": "lex"},
                {"text_unit_id": "tu_2", "score": 0.7, "snippet": "lex2"},
            ],
        )
        out = hybrid.search_hybrid("q", limit=1)
        assert out == [{"text_unit_id": "tu_1", "score": 0.8, "snippet": "lex"}]

    def test_hybrid_combines_scores_for_overlap(self, monkeypatch):  # type: ignore[no-untyped-def]
        import islam_intelligent.rag.retrieval.hybrid as hybrid

        monkeypatch.setattr(hybrid, "is_vector_available", lambda: True)
        monkeypatch.setattr(
            hybrid,
            "search_lexical",
            lambda q, limit=10: [
                {"text_unit_id": "tu_1", "score": 1.0, "snippet": "lex"},
            ],
        )
        monkeypatch.setattr(
            hybrid,
            "search_vector",
            lambda q, limit=10: [
                {"text_unit_id": "tu_1", "score": 0.0},
            ],
        )
        out = hybrid.search_hybrid("q", limit=10, lexical_weight=0.7, vector_weight=0.3)
        assert len(out) == 1
        assert out[0]["text_unit_id"] == "tu_1"
        assert out[0]["score"] == 0.7

    def test_hybrid_includes_vector_only_results_with_placeholder_snippet(
        self, monkeypatch
    ):  # type: ignore[no-untyped-def]
        import islam_intelligent.rag.retrieval.hybrid as hybrid

        monkeypatch.setattr(hybrid, "is_vector_available", lambda: True)
        monkeypatch.setattr(hybrid, "search_lexical", lambda q, limit=10: [])
        monkeypatch.setattr(
            hybrid,
            "search_vector",
            lambda q, limit=10: [
                {"text_unit_id": "tu_vec", "score": 0.9},
            ],
        )
        out = hybrid.search_hybrid("q", limit=10)
        assert out == [
            {"text_unit_id": "tu_vec", "score": 0.27, "snippet": "[vector match]"}
        ]

    def test_hybrid_sorts_by_score_and_respects_limit(self, monkeypatch):  # type: ignore[no-untyped-def]
        import islam_intelligent.rag.retrieval.hybrid as hybrid

        monkeypatch.setattr(hybrid, "is_vector_available", lambda: True)
        monkeypatch.setattr(
            hybrid,
            "search_lexical",
            lambda q, limit=10: [
                {"text_unit_id": "tu_low", "score": 0.2, "snippet": "lex"},
            ],
        )
        monkeypatch.setattr(
            hybrid,
            "search_vector",
            lambda q, limit=10: [
                {"text_unit_id": "tu_high", "score": 1.0},
            ],
        )
        out = hybrid.search_hybrid("q", limit=1, lexical_weight=0.7, vector_weight=0.3)
        assert len(out) == 1
        assert out[0]["text_unit_id"] == "tu_high"


class TestTrustFiltering:
    def test_filter_trusted_drops_non_trusted(self) -> None:
        pipeline = RAGPipeline()
        raw = [
            {"evidence_span_id": "es1", "trust_status": "trusted"},
            {"evidence_span_id": "es2", "trust_status": "untrusted"},
            {"evidence_span_id": "es3", "trust_status": "TRUSTED"},
            {"evidence_span_id": "es4"},
        ]
        trusted = pipeline._filter_trusted(raw)
        assert [r["evidence_span_id"] for r in trusted] == ["es1", "es3"]
