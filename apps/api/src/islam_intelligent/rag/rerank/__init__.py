"""Cross-encoder reranker for improving retrieval relevance.

This module implements cross-encoder reranking to refine initial retrieval
results by scoring query-document pairs directly, providing more accurate
relevance scores than bi-encoder approaches alone.

References:
- Reimers & Gurevych: "Sentence-BERT: Sentence Embeddings using Siamese
  BERT-Networks" https://arxiv.org/abs/1908.10084
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)


class RerankResult:
    """Result from reranking with cross-encoder."""

    def __init__(
        self,
        text_unit_id: str,
        score: float,
        snippet: str,
        canonical_id: str | None = None,
        source_id: str | None = None,
        trust_status: str | None = None,
    ) -> None:
        """
        Initialize a RerankResult representing a single reranked item and its metadata.
        
        Parameters:
            text_unit_id (str): Identifier of the text unit (document or passage).
            score (float): Normalized relevance score for the query–document pair (typically in [0, 1]).
            snippet (str): Text snippet used for scoring or displaying to the user.
            canonical_id (str | None): Optional canonical identifier for the document, if available.
            source_id (str | None): Optional identifier of the source or corpus the text unit originates from.
            trust_status (str | None): Optional trust or provenance indicator for the text unit.
        """
        self.text_unit_id = text_unit_id
        self.score = score
        self.snippet = snippet
        self.canonical_id = canonical_id
        self.source_id = source_id
        self.trust_status = trust_status

    def to_dict(self) -> dict[str, object]:
        """
        Return a dictionary representation of the reranked item.
        
        Includes the keys "text_unit_id", "score", and "snippet"; adds "canonical_id", "source_id",
        and "trust_status" only when those attributes are present.
         
        Returns:
            dict[str, object]: The result represented as a dictionary.
        """
        result: dict[str, object] = {
            "text_unit_id": self.text_unit_id,
            "score": self.score,
            "snippet": self.snippet,
        }
        if self.canonical_id:
            result["canonical_id"] = self.canonical_id
        if self.source_id:
            result["source_id"] = self.source_id
        if self.trust_status:
            result["trust_status"] = self.trust_status
        return result


@dataclass(frozen=True)
class RerankerConfig:
    """Configuration for cross-encoder reranker.

    Attributes:
        enabled: Whether reranking is enabled
        model: Model name or path for cross-encoder
        top_k: Number of top results to return after reranking
        batch_size: Batch size for model inference
        max_length: Maximum sequence length for model
        device: Device to run model on (cpu/cuda)
    """

    enabled: bool = True
    model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    top_k: int = 10
    batch_size: int = 32
    max_length: int = 512
    device: str = "cpu"


class CrossEncoderProtocol(Protocol):
    """Protocol for cross-encoder models."""

    def predict(
        self, sentences: list[tuple[str, str]], batch_size: int = 32
    ) -> list[float]: """
        Score pairs of (query, snippet) with a cross-encoder.
        
        Parameters:
            sentences (list[tuple[str, str]]): List of (query, snippet) pairs to score.
            batch_size (int): Maximum number of pairs processed at once by the model.
        
        Returns:
            list[float]: A list of scores, one per input pair; larger values indicate greater predicted relevance.
        """
        ...


class CrossEncoderReranker:
    """Rerank retrieval results using cross-encoder model.

    Cross-encoders provide more accurate relevance scoring by processing
    query-document pairs together, capturing interactions that bi-encoders
    miss. This is applied as a second-stage refinement after initial retrieval.

    Example:
        >>> reranker = CrossEncoderReranker()
        >>> results = reranker.rerank(
        ...     "How to pray tahajjud?",
        ...     initial_results
        ... )
        >>> print(f"Top result: {results[0]['snippet']}")
    """

    config: RerankerConfig
    _model: CrossEncoderProtocol | None
    _available: bool

    def __init__(
        self,
        config: RerankerConfig | None = None,
        model: CrossEncoderProtocol | None = None,
    ) -> None:
        """Initialize the cross-encoder reranker.

        Args:
            config: Reranker configuration. Uses defaults if not provided.
            model: Pre-initialized model instance for testing.
        """
        self.config = config or RerankerConfig()
        self._model = model
        self._available = False

        if not self.config.enabled:
            logger.debug("Cross-encoder reranking disabled by configuration")
            return

        if self._model is not None:
            self._available = True
            logger.debug("Cross-encoder reranker initialized with provided model")
            return

        # Try to initialize the model
        try:
            from sentence_transformers import CrossEncoder

            device = self.config.device
            # Auto-detect CUDA if available and not explicitly set to cpu
            if device == "cpu" and os.getenv("RAG_RERANKER_FORCE_CPU") != "1":
                import torch

                if torch.cuda.is_available():
                    device = "cuda"

            self._model = CrossEncoder(
                self.config.model,
                max_length=self.config.max_length,
                device=device,
            )
            self._available = True
            logger.info(
                f"Cross-encoder reranker initialized with model: {self.config.model}"
            )
        except ImportError:
            logger.warning(
                "sentence-transformers not installed; cross-encoder reranking disabled"
            )
        except Exception as exc:
            logger.warning(f"Failed to initialize cross-encoder model: {exc}")

    def is_available(self) -> bool:
        """Check if reranker is available (enabled and model loaded)."""
        return self.config.enabled and self._available and self._model is not None

    def rerank(
        self,
        query: str,
        results: list[dict[str, object]],
        top_k: int | None = None,
    ) -> list[RerankResult]:
        """
        Rerank initial retrieval results by scoring query–snippet pairs with the configured cross-encoder.
        
        Args:
            query: Original user query.
            results: Initial retrieval results (list of result dicts) to be rescored.
            top_k: Maximum number of results to return; falls back to the reranker configuration value if None.
        
        Returns:
            Reranked results as a list of RerankResult ordered by normalized relevance score. If the reranker is unavailable or reranking fails, returns the original results converted to RerankResult objects.
        
        Raises:
            ValueError: If `query` is empty or only whitespace.
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty or None")

        if not results:
            return []

        # Return original results if reranker is not available
        if not self.is_available():
            logger.debug("Reranker unavailable, returning original results")
            return self._convert_to_results(results)

        target_k = top_k if top_k is not None else self.config.top_k
        target_k = max(1, target_k)

        # Prepare query-document pairs
        pairs: list[tuple[str, str]] = []
        for result in results:
            snippet = str(result.get("snippet", ""))
            if not snippet:
                # Use text_unit_id as fallback (for cases where snippet is missing)
                snippet = str(result.get("text_unit_id", ""))
            pairs.append((query.strip(), snippet))

        if not pairs:
            return []

        try:
            # Score pairs using cross-encoder
            scores = self._model.predict(  # type: ignore[union-attr]
                pairs,
                batch_size=self.config.batch_size,
            )

            # Combine results with new scores
            reranked: list[tuple[float, dict[str, object]]] = []
            for i, (result, score) in enumerate(zip(results, scores)):
                # Normalize score to [0, 1] range (cross-encoders can output any range)
                normalized_score = self._normalize_score(float(score))
                reranked.append((normalized_score, result))

            # Sort by new scores and take top_k
            reranked.sort(key=lambda x: x[0], reverse=True)

            # Convert to RerankResult objects
            final_results: list[RerankResult] = []
            for score, result in reranked[:target_k]:
                final_results.append(
                    RerankResult(
                        text_unit_id=str(result.get("text_unit_id", "")),
                        score=score,
                        snippet=str(result.get("snippet", "")),
                        canonical_id=str(result.get("canonical_id"))
                        if result.get("canonical_id")
                        else None,
                        source_id=str(result.get("source_id"))
                        if result.get("source_id")
                        else None,
                        trust_status=str(result.get("trust_status"))
                        if result.get("trust_status")
                        else None,
                    )
                )

            logger.debug(
                f"Reranked {len(results)} results to {len(final_results)} "
                f"(top score: {final_results[0].score:.3f})"
            )
            return final_results

        except Exception as exc:
            logger.warning(f"Reranking failed, returning original results: {exc}")
            return self._convert_to_results(results)

    def _normalize_score(self, raw_score: float) -> float:
        """
        Normalize a raw cross-encoder score into the [0, 1] range.
        
        Parameters:
            raw_score (float): Raw model output (logit or unbounded score) to normalize.
        
        Returns:
            float: A value between 0 and 1 produced by the logistic sigmoid. Returns 0.5 if the input causes an overflow or is otherwise invalid.
        """
        import math

        # Use logistic function (sigmoid) for normalization
        # This maps any real number to (0, 1)
        try:
            return 1.0 / (1.0 + math.exp(-raw_score))
        except (OverflowError, ValueError):
            return 0.5  # Safe fallback

    def _convert_to_results(
        self, results: list[dict[str, object]]
    ) -> list[RerankResult]:
        """
        Convert a list of raw result dictionaries into RerankResult instances without changing their scores.
        
        Parameters:
            results (list[dict[str, object]]): List of retrieval result dictionaries. Expected keys:
                - "text_unit_id": identifier used as the result id (defaults to empty string if missing).
                - "score": numerical score (defaults to 0.0 if missing).
                - "snippet": text snippet to display (defaults to empty string if missing).
                - "canonical_id", "source_id", "trust_status": optional metadata keys included when present; otherwise set to None.
        
        Returns:
            list[RerankResult]: Converted RerankResult objects preserving provided scores and mapping optional metadata to None when absent.
        """
        return [
            RerankResult(
                text_unit_id=str(r.get("text_unit_id", "")),
                score=float(r.get("score", 0.0)),
                snippet=str(r.get("snippet", "")),
                canonical_id=str(r.get("canonical_id"))
                if r.get("canonical_id")
                else None,
                source_id=str(r.get("source_id")) if r.get("source_id") else None,
                trust_status=str(r.get("trust_status"))
                if r.get("trust_status")
                else None,
            )
            for r in results
        ]


def create_reranker(
    enabled: bool | None = None,
    model: str | None = None,
    top_k: int | None = None,
) -> CrossEncoderReranker:
    """
    Create a CrossEncoderReranker configured from explicit arguments and environment variables.
    
    Parameters:
        enabled (bool | None): If provided, enable or disable reranking. If None, reads RAG_ENABLE_RERANKER from the environment (accepted true values: "1", "true", "yes", "on"); defaults to enabled when the variable is absent.
        model (str | None): Cross-encoder model name or path. If None, reads RAG_RERANKER_MODEL from the environment and falls back to "cross-encoder/ms-marco-MiniLM-L-6-v2" when unset.
        top_k (int | None): Number of top results to return after reranking. If None, reads RAG_RERANKER_TOP_K from the environment and falls back to 10; non-integer environment values fall back to 10.
    
    Returns:
        A configured CrossEncoderReranker instance.
    """
    # Determine settings from env vars if not provided
    if enabled is None:
        raw = os.getenv("RAG_ENABLE_RERANKER", "true").lower()
        enabled = raw in ("1", "true", "yes", "on")

    if model is None:
        model = os.getenv("RAG_RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

    if top_k is None:
        try:
            top_k = int(os.getenv("RAG_RERANKER_TOP_K", "10"))
        except ValueError:
            top_k = 10

    config = RerankerConfig(
        enabled=enabled,
        model=model,
        top_k=top_k,
    )

    return CrossEncoderReranker(config=config)


__all__ = [
    "CrossEncoderReranker",
    "RerankerConfig",
    "RerankResult",
    "create_reranker",
]
