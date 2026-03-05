"""Integration tests for cross-encoder reranking functionality.

This module tests the reranker which uses cross-encoder models to improve
the relevance ordering of retrieved documents beyond what bi-encoders can achieve.

References:
- https://www.sbert.net/examples/applications/cross-encoder/README.html
"""

from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false

import time
from dataclasses import dataclass, field
from typing import Protocol
from unittest.mock import MagicMock, patch

import pytest


class CrossEncoderProtocol(Protocol):
    """Protocol for cross-encoder models."""

    def predict(self, sentence_pairs: list[tuple[str, str]]) -> list[float]: ...


@dataclass
class Document:
    """Represents a retrieved document."""

    id: str
    text: str
    score: float = 0.0
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class RerankerConfig:
    """Configuration for the reranker."""

    enabled: bool = True
    model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    top_k: int = 10
    batch_size: int = 32
    max_length: int = 512
    device: str = "cpu"


class CrossEncoderReranker:
    """Rerank retrieved documents using a cross-encoder model.

    Cross-encoders provide more accurate relevance scores by processing
    query and document together, unlike bi-encoders which encode them separately.

    Example:
        >>> reranker = CrossEncoderReranker()
        >>> docs = [Document(id="1", text="..."), ...]
        >>> ranked = reranker.rerank("query", docs)
    """

    def __init__(
        self,
        config: RerankerConfig | None = None,
        model: CrossEncoderProtocol | None = None,
    ) -> None:
        self.config = config or RerankerConfig()
        self._model = model
        self._available = False

        if not self.config.enabled:
            return

        if model is not None:
            self._model = model
            self._available = True
        else:
            try:
                from sentence_transformers import CrossEncoder

                self._model = CrossEncoder(
                    self.config.model_name,
                    device=self.config.device,
                    max_length=self.config.max_length,
                )
                self._available = True
            except ImportError:
                pass  # Will be unavailable
            except Exception:
                pass  # Model download/load failed; will be unavailable

    def is_available(self) -> bool:
        """Check if reranker is available and ready."""
        return self.config.enabled and self._available and self._model is not None

    def rerank(
        self,
        query: str,
        documents: list[Document],
        top_k: int | None = None,
    ) -> list[Document]:
        """Rerank documents by relevance to query.

        Args:
            query: The search query
            documents: Documents to rerank
            top_k: Maximum documents to return (default: config.top_k)

        Returns:
            Documents sorted by cross-encoder relevance score
        """
        if not self.is_available():
            # Return documents sorted by original score
            return sorted(documents, key=lambda d: d.score, reverse=True)[
                : (top_k or self.config.top_k)
            ]

        if not documents:
            return []

        target_k = top_k or self.config.top_k

        # Prepare sentence pairs for cross-encoder
        pairs: list[tuple[str, str]] = [(query, doc.text) for doc in documents]

        # Get cross-encoder scores
        try:
            ce_scores = self._model.predict(pairs)  # type: ignore[union-attr]
        except Exception:
            # Fallback to original scores on error
            return sorted(documents, key=lambda d: d.score, reverse=True)[:target_k]

        # Create new documents with updated scores
        reranked: list[Document] = []
        for doc, ce_score in zip(documents, ce_scores):
            reranked.append(
                Document(
                    id=doc.id,
                    text=doc.text,
                    score=float(ce_score),
                    metadata={
                        **doc.metadata,
                        "original_score": doc.score,
                        "reranked": True,
                    },
                )
            )

        # Sort by cross-encoder score (higher is more relevant)
        reranked.sort(key=lambda d: d.score, reverse=True)

        return reranked[:target_k]

    def rerank_batch(
        self,
        queries: list[str],
        doc_lists: list[list[Document]],
    ) -> list[list[Document]]:
        """Rerank multiple query-document sets efficiently.

        Args:
            queries: List of queries
            doc_lists: List of document lists (one per query)

        Returns:
            Reranked document lists
        """
        return [self.rerank(query, docs) for query, docs in zip(queries, doc_lists)]


def create_reranker(
    enabled: bool | None = None,
    model_name: str | None = None,
    top_k: int | None = None,
) -> CrossEncoderReranker:
    """Factory function to create a configured reranker."""
    # Determine if enabled
    if enabled is None:
        import os

        enabled = os.getenv("RAG_ENABLE_RERANKER", "true").lower() in (
            "true",
            "1",
            "yes",
        )

    config = RerankerConfig(
        enabled=enabled,
        model_name=model_name or "cross-encoder/ms-marco-MiniLM-L-6-v2",
        top_k=top_k or 10,
    )

    return CrossEncoderReranker(config=config)


class TestRerankerConfig:
    """Tests for RerankerConfig dataclass."""

    def test_default_config(self) -> None:
        config = RerankerConfig()
        assert config.enabled is True
        assert config.model_name == "cross-encoder/ms-marco-MiniLM-L-6-v2"
        assert config.top_k == 10
        assert config.batch_size == 32
        assert config.max_length == 512
        assert config.device == "cpu"

    def test_custom_config(self) -> None:
        config = RerankerConfig(
            enabled=False,
            model_name="custom-model",
            top_k=5,
            batch_size=16,
            max_length=256,
            device="cuda",
        )
        assert config.enabled is False
        assert config.model_name == "custom-model"
        assert config.top_k == 5
        assert config.batch_size == 16
        assert config.max_length == 256
        assert config.device == "cuda"


class TestCrossEncoderRerankerInitialization:
    """Tests for reranker initialization."""

    def test_init_with_defaults(self) -> None:
        reranker = CrossEncoderReranker()
        assert reranker.config.enabled is True
        assert (
            reranker.is_available() is False
        )  # No model without sentence-transformers

    def test_init_disabled_by_config(self) -> None:
        config = RerankerConfig(enabled=False)
        reranker = CrossEncoderReranker(config=config)
        assert reranker.config.enabled is False
        assert reranker.is_available() is False

    def test_init_with_mock_model(self) -> None:
        mock_model = MagicMock()
        reranker = CrossEncoderReranker(model=mock_model)
        assert reranker.is_available() is True
        assert reranker._model is mock_model


class TestRerankerFunctionality:
    """Tests for core reranking functionality."""

    def test_rerank_returns_sorted_documents(self) -> None:
        """Test that rerank returns documents sorted by cross-encoder scores."""
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.8, 0.3, 0.9, 0.1]

        reranker = CrossEncoderReranker(model=mock_model)
        documents = [
            Document(id="1", text="doc1", score=0.5),
            Document(id="2", text="doc2", score=0.8),
            Document(id="3", text="doc3", score=0.2),
            Document(id="4", text="doc4", score=0.9),
        ]

        result = reranker.rerank("query", documents)

        assert len(result) == 4
        # Should be sorted by cross-encoder scores: 0.9, 0.8, 0.3, 0.1
        assert result[0].id == "3"
        assert result[1].id == "1"
        assert result[2].id == "2"
        assert result[3].id == "4"

    def test_rerank_respects_top_k(self) -> None:
        """Test that rerank respects the top_k parameter."""
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.5, 0.6, 0.7, 0.8, 0.9]

        reranker = CrossEncoderReranker(model=mock_model)
        documents = [
            Document(id=str(i), text=f"doc{i}", score=0.1 * i) for i in range(5)
        ]

        result = reranker.rerank("query", documents, top_k=3)

        assert len(result) == 3

    def test_rerank_includes_metadata(self) -> None:
        """Test that reranked documents include original score metadata."""
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.8]

        reranker = CrossEncoderReranker(model=mock_model)
        documents = [
            Document(id="1", text="doc1", score=0.5, metadata={"source": "test"})
        ]

        result = reranker.rerank("query", documents)

        assert len(result) == 1
        assert result[0].metadata["original_score"] == 0.5
        assert result[0].metadata["reranked"] is True
        assert result[0].metadata["source"] == "test"

    def test_rerank_empty_documents(self) -> None:
        """Test reranking empty document list."""
        mock_model = MagicMock()
        reranker = CrossEncoderReranker(model=mock_model)

        result = reranker.rerank("query", [])

        assert result == []

    def test_rerank_preserves_document_fields(self) -> None:
        """Test that reranking preserves all document fields except score."""
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.9]

        reranker = CrossEncoderReranker(model=mock_model)
        documents = [
            Document(
                id="test-id",
                text="test text",
                score=0.5,
                metadata={"key": "value"},
            )
        ]

        result = reranker.rerank("query", documents)

        assert len(result) == 1
        assert result[0].id == "test-id"
        assert result[0].text == "test text"
        assert result[0].score == 0.9


class TestRerankerFallback:
    """Tests for reranker fallback behavior."""

    def test_rerank_fallback_when_unavailable(self) -> None:
        """Test that rerank falls back to original scores when model unavailable."""
        config = RerankerConfig(enabled=False)
        reranker = CrossEncoderReranker(config=config)
        documents = [
            Document(id="1", text="doc1", score=0.5),
            Document(id="2", text="doc2", score=0.9),
            Document(id="3", text="doc3", score=0.3),
        ]

        result = reranker.rerank("query", documents)

        # Should return sorted by original scores
        assert result[0].id == "2"
        assert result[1].id == "1"
        assert result[2].id == "3"

    def test_rerank_fallback_on_model_error(self) -> None:
        """Test that rerank falls back when model raises exception."""
        mock_model = MagicMock()
        mock_model.predict.side_effect = RuntimeError("Model error")

        reranker = CrossEncoderReranker(model=mock_model)
        documents = [
            Document(id="1", text="doc1", score=0.5),
            Document(id="2", text="doc2", score=0.9),
        ]

        result = reranker.rerank("query", documents)

        # Should return sorted by original scores
        assert result[0].id == "2"
        assert result[1].id == "1"


class TestRerankerBatch:
    """Tests for batch reranking."""

    def test_rerank_batch_multiple_queries(self) -> None:
        """Test batch reranking for multiple queries."""
        mock_model = MagicMock()
        mock_model.predict.side_effect = [
            [0.8, 0.3],  # First query
            [0.4, 0.9],  # Second query
        ]

        reranker = CrossEncoderReranker(model=mock_model)
        queries = ["query1", "query2"]
        doc_lists = [
            [
                Document(id="a", text="doc a", score=0.5),
                Document(id="b", text="doc b", score=0.5),
            ],
            [
                Document(id="c", text="doc c", score=0.5),
                Document(id="d", text="doc d", score=0.5),
            ],
        ]

        results = reranker.rerank_batch(queries, doc_lists)

        assert len(results) == 2
        assert results[0][0].id == "a"  # Higher score for query1
        assert results[1][0].id == "d"  # Higher score for query2


class TestCreateReranker:
    """Tests for the factory function."""

    def test_create_with_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("RAG_ENABLE_RERANKER", raising=False)
        reranker = create_reranker()

        assert isinstance(reranker, CrossEncoderReranker)
        assert reranker.config.enabled is True

    def test_create_disabled_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RAG_ENABLE_RERANKER", "false")
        reranker = create_reranker()

        assert reranker.config.enabled is False

    def test_create_disabled_via_param(self) -> None:
        reranker = create_reranker(enabled=False)

        assert reranker.config.enabled is False

    def test_create_with_custom_model(self) -> None:
        reranker = create_reranker(model_name="custom-model")

        assert reranker.config.model_name == "custom-model"

    def test_create_with_custom_top_k(self) -> None:
        reranker = create_reranker(top_k=5)

        assert reranker.config.top_k == 5


class TestRerankerPerformance:
    """Performance benchmarks for the reranker."""

    def test_rerank_performance_small_batch(self) -> None:
        """Benchmark reranking 10 documents."""
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.5 + i * 0.05 for i in range(10)]

        reranker = CrossEncoderReranker(model=mock_model)
        documents = [
            Document(id=str(i), text=f"document text {i}", score=0.1 * i)
            for i in range(10)
        ]

        start = time.perf_counter()
        result = reranker.rerank("test query", documents)
        elapsed = time.perf_counter() - start

        assert len(result) == 10
        assert elapsed < 0.1  # Should complete in less than 100ms with mock

    def test_rerank_performance_large_batch(self) -> None:
        """Benchmark reranking 100 documents."""
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.5 + i * 0.005 for i in range(100)]

        reranker = CrossEncoderReranker(model=mock_model)
        documents = [
            Document(id=str(i), text=f"document text {i}", score=0.01 * i)
            for i in range(100)
        ]

        start = time.perf_counter()
        result = reranker.rerank("test query", documents, top_k=100)
        elapsed = time.perf_counter() - start

        assert len(result) == 100
        assert elapsed < 0.1  # Should complete in less than 100ms with mock

    def test_rerank_batch_performance(self) -> None:
        """Benchmark batch reranking."""
        mock_model = MagicMock()
        mock_model.predict.side_effect = [
            [0.5 + i * 0.05 for i in range(10)] for _ in range(5)
        ]

        reranker = CrossEncoderReranker(model=mock_model)
        queries = [f"query {i}" for i in range(5)]
        doc_lists = [
            [Document(id=str(j), text=f"doc {j}", score=0.1) for j in range(10)]
            for _ in range(5)
        ]

        start = time.perf_counter()
        results = reranker.rerank_batch(queries, doc_lists)
        elapsed = time.perf_counter() - start

        assert len(results) == 5
        assert elapsed < 0.5  # Should complete in less than 500ms with mock


class TestRerankerEdgeCases:
    """Tests for edge cases and error handling."""

    def test_rerank_single_document(self) -> None:
        """Test reranking a single document."""
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.8]

        reranker = CrossEncoderReranker(model=mock_model)
        documents = [Document(id="1", text="single doc", score=0.5)]

        result = reranker.rerank("query", documents)

        assert len(result) == 1
        assert result[0].id == "1"

    def test_rerank_identical_scores(self) -> None:
        """Test reranking documents with identical original scores."""
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.9, 0.6, 0.8]

        reranker = CrossEncoderReranker(model=mock_model)
        documents = [
            Document(id="1", text="doc1", score=0.5),
            Document(id="2", text="doc2", score=0.5),
            Document(id="3", text="doc3", score=0.5),
        ]

        result = reranker.rerank("query", documents)

        # Should be reordered by cross-encoder scores
        assert result[0].id == "1"
        assert result[1].id == "3"
        assert result[2].id == "2"

    def test_rerank_with_special_characters(self) -> None:
        """Test reranking documents with special characters."""
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.8]

        reranker = CrossEncoderReranker(model=mock_model)
        documents = [Document(id="1", text="الصلاة على النبي \n\t!@#$%", score=0.5)]

        result = reranker.rerank("الصلاة", documents)

        assert len(result) == 1
        assert result[0].id == "1"

    def test_rerank_with_empty_query(self) -> None:
        """Test reranking with empty query."""
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.5]

        reranker = CrossEncoderReranker(model=mock_model)
        documents = [Document(id="1", text="doc1", score=0.5)]

        result = reranker.rerank("", documents)

        assert len(result) == 1
        mock_model.predict.assert_called_once_with([("", "doc1")])

    def test_rerank_with_unicode(self) -> None:
        """Test reranking with unicode text."""
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.8, 0.6]

        reranker = CrossEncoderReranker(model=mock_model)
        documents = [
            Document(id="1", text="حَدَّثَنَا مُحَمَّدُ بْنُ عَبْدِ اللَّهِ", score=0.5),
            Document(id="2", text="قَالَ رَسُولُ اللَّهِ صَلَّى اللَّهُ عَلَيْهِ وَسَلَّمَ", score=0.5),
        ]

        result = reranker.rerank("حديث النبي", documents)

        assert len(result) == 2
