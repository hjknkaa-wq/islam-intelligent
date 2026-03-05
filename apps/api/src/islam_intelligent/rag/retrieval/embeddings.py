"""Fail-safe multi-model embedding generator with lazy loading and caching."""

from __future__ import annotations

import logging
import os
from importlib import import_module
from collections import OrderedDict
from dataclasses import dataclass
from typing import Protocol, cast

from ...config import settings

logger = logging.getLogger(__name__)

_BACKEND_OPENAI = "openai"
_BACKEND_SENTENCE_TRANSFORMERS = "sentence-transformers"

_OPENAI_DEFAULT_MODEL = "text-embedding-3-small"
_LABSE_MODEL = "sentence-transformers/LaBSE"
_E5_MODEL = "intfloat/multilingual-e5-large"


class _EmbeddingItem(Protocol):
    embedding: list[float]


class _EmbeddingResponse(Protocol):
    data: list[_EmbeddingItem]


class _EmbeddingsAPI(Protocol):
    def create(
        self,
        *,
        model: str,
        input: list[str],
        dimensions: int | None = None,
    ) -> _EmbeddingResponse: ...


class _OpenAIClient(Protocol):
    embeddings: _EmbeddingsAPI


class _SentenceTransformerModel(Protocol):
    def encode(
        self,
        sentences: list[str],
        *,
        normalize_embeddings: bool = True,
        convert_to_numpy: bool = True,
        show_progress_bar: bool = False,
    ) -> object: ...


class _SentenceTransformerConstructor(Protocol):
    def __call__(self, model_name: str) -> _SentenceTransformerModel: ...


@dataclass(frozen=True)
class _ModelSpec:
    backend: str
    name: str
    supports_dimensions: bool
    fallback_dimension: int


def _resolve_model_spec(model: str, configured_dimension: int) -> _ModelSpec:
    cleaned_model = model.strip()
    normalized = cleaned_model.lower()

    if normalized.startswith("openai:"):
        resolved = cleaned_model.split(":", 1)[1].strip() or _OPENAI_DEFAULT_MODEL
        return _ModelSpec(
            backend=_BACKEND_OPENAI,
            name=resolved,
            supports_dimensions=True,
            fallback_dimension=configured_dimension
            if configured_dimension > 0
            else 1536,
        )

    if normalized.startswith("sentence-transformers:"):
        resolved = cleaned_model.split(":", 1)[1].strip() or _LABSE_MODEL
        return _ModelSpec(
            backend=_BACKEND_SENTENCE_TRANSFORMERS,
            name=resolved,
            supports_dimensions=False,
            fallback_dimension=configured_dimension
            if configured_dimension > 0
            else 768,
        )

    if normalized in {
        "labse",
        "sentence-transformers/labse",
    }:
        return _ModelSpec(
            backend=_BACKEND_SENTENCE_TRANSFORMERS,
            name=_LABSE_MODEL,
            supports_dimensions=False,
            fallback_dimension=configured_dimension
            if configured_dimension > 0
            else 768,
        )

    if normalized in {
        "multilingual-e5-large",
        "e5-large",
        "intfloat/multilingual-e5-large",
    }:
        return _ModelSpec(
            backend=_BACKEND_SENTENCE_TRANSFORMERS,
            name=_E5_MODEL,
            supports_dimensions=False,
            fallback_dimension=configured_dimension
            if configured_dimension > 0
            else 1024,
        )

    if "/" in cleaned_model and not cleaned_model.startswith("text-embedding-"):
        return _ModelSpec(
            backend=_BACKEND_SENTENCE_TRANSFORMERS,
            name=cleaned_model,
            supports_dimensions=False,
            fallback_dimension=configured_dimension
            if configured_dimension > 0
            else 768,
        )

    return _ModelSpec(
        backend=_BACKEND_OPENAI,
        name=cleaned_model or _OPENAI_DEFAULT_MODEL,
        supports_dimensions=True,
        fallback_dimension=configured_dimension if configured_dimension > 0 else 1536,
    )


def _coerce_vector(raw_vector: object) -> list[float]:
    candidate: object = raw_vector
    tolist = getattr(candidate, "tolist", None)
    if callable(tolist):
        candidate = tolist()

    if not isinstance(candidate, (list, tuple)):
        return []

    sequence = cast(list[object] | tuple[object, ...], candidate)

    vector: list[float] = []
    for value in sequence:
        if isinstance(value, (int, float, str)):
            vector.append(float(value))
            continue
        return []
    return vector


def _coerce_vectors(raw_vectors: object) -> list[list[float]]:
    candidate: object = raw_vectors
    tolist = getattr(candidate, "tolist", None)
    if callable(tolist):
        candidate = tolist()

    if not isinstance(candidate, (list, tuple)):
        return []

    sequence = cast(list[object] | tuple[object, ...], candidate)
    if not sequence:
        return []

    first = sequence[0]
    if isinstance(first, (int, float, str)):
        vector = _coerce_vector(sequence)
        return [vector] if vector else []

    vectors: list[list[float]] = []
    for item in sequence:
        vector = _coerce_vector(item)
        if not vector:
            return []
        vectors.append(vector)
    return vectors


class EmbeddingGenerator:
    """Generate embeddings with model selection and graceful fallback."""

    api_key: str | None
    model: str
    fallback_model: str
    dimension: int
    cache_size: int
    base_url: str | None
    _primary_spec: _ModelSpec
    _fallback_spec: _ModelSpec | None
    _availability: dict[tuple[str, str], bool]
    _clients: dict[tuple[str, str], object]
    _cache: OrderedDict[str, list[float]]

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        fallback_model: str | None = None,
        dimension: int | None = None,
        cache_size: int | None = None,
        base_url: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or settings.embedding_model
        self.fallback_model = fallback_model or settings.embedding_fallback_model
        self.dimension = max(
            0, dimension if dimension is not None else settings.embedding_dimension
        )
        self.cache_size = max(
            0, cache_size if cache_size is not None else settings.embedding_cache_size
        )
        raw_base_url = (
            base_url or os.getenv("RAG_LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
        )
        self.base_url = (
            raw_base_url.strip()
            if isinstance(raw_base_url, str) and raw_base_url.strip()
            else None
        )
        self._primary_spec = _resolve_model_spec(self.model, self.dimension)
        resolved_fallback = _resolve_model_spec(self.fallback_model, self.dimension)
        self._fallback_spec = (
            resolved_fallback if resolved_fallback != self._primary_spec else None
        )

        self._availability = {}
        self._clients = {}
        self._cache = OrderedDict()

    def is_available(self) -> bool:
        for spec in self._candidate_specs():
            if self._ensure_model_loaded(spec):
                return True
        return False

    def generate_embedding(self, text: str) -> list[float]:
        embeddings = self.generate_embeddings([text])
        if not embeddings:
            return self._fallback_vector()
        return embeddings[0]

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        vectors: list[list[float] | None] = [None] * len(texts)
        missing_indexes: list[int] = []
        missing_texts: list[str] = []

        for index, raw_text in enumerate(texts):
            text = str(raw_text)
            cached = self._cache_get(text)
            if cached is not None:
                vectors[index] = cached
                continue
            missing_indexes.append(index)
            missing_texts.append(text)

        if missing_texts:
            generated = self._generate_for_missing(missing_texts)
            for index, text, embedding in zip(
                missing_indexes, missing_texts, generated
            ):
                self._cache_set(text, embedding)
                vectors[index] = embedding

        fallback = self._fallback_vector()
        return [vector if vector is not None else fallback for vector in vectors]

    def _generate_for_missing(self, texts: list[str]) -> list[list[float]]:
        for spec in self._candidate_specs():
            vectors = self._generate_with_spec(spec, texts)
            if vectors is not None:
                return vectors

        return [self._fallback_vector() for _ in texts]

    def _generate_with_spec(
        self, spec: _ModelSpec, texts: list[str]
    ) -> list[list[float]] | None:
        if not self._ensure_model_loaded(spec):
            return None

        if spec.backend == _BACKEND_OPENAI:
            return self._generate_openai(spec, texts)
        if spec.backend == _BACKEND_SENTENCE_TRANSFORMERS:
            return self._generate_sentence_transformer(spec, texts)

        logger.warning("Unknown embedding backend: %s", spec.backend)
        return None

    def _generate_openai(
        self, spec: _ModelSpec, texts: list[str]
    ) -> list[list[float]] | None:
        key = self._spec_key(spec)
        client = self._clients.get(key)
        if client is None:
            return None
        typed_client = cast(_OpenAIClient, client)

        dimensions = (
            self.dimension if self.dimension > 0 and spec.supports_dimensions else None
        )
        try:
            response = typed_client.embeddings.create(
                model=spec.name,
                input=texts,
                dimensions=dimensions,
            )
        except Exception as exc:
            if dimensions is None:
                logger.warning(
                    "OpenAI embedding generation failed for model %s: %s",
                    spec.name,
                    exc,
                )
                return None

            try:
                response = typed_client.embeddings.create(model=spec.name, input=texts)
            except Exception as retry_exc:
                logger.warning(
                    "OpenAI embedding generation failed for model %s: %s",
                    spec.name,
                    retry_exc,
                )
                return None

        vectors: list[list[float]] = []
        for item in response.data:
            vectors.append(list(item.embedding))

        if len(vectors) != len(texts):
            logger.warning("Embedding response count mismatch for model %s", spec.name)
            return None
        return vectors

    def _generate_sentence_transformer(
        self, spec: _ModelSpec, texts: list[str]
    ) -> list[list[float]] | None:
        key = self._spec_key(spec)
        client = self._clients.get(key)
        if client is None:
            return None
        typed_client = cast(_SentenceTransformerModel, client)

        prepared_texts = [self._prepare_text(spec, text) for text in texts]
        try:
            raw_vectors = typed_client.encode(
                prepared_texts,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        except TypeError:
            try:
                raw_vectors = typed_client.encode(prepared_texts)
            except Exception as exc:
                logger.warning(
                    "Sentence-transformer embedding generation failed for model %s: %s",
                    spec.name,
                    exc,
                )
                return None
        except Exception as exc:
            logger.warning(
                "Sentence-transformer embedding generation failed for model %s: %s",
                spec.name,
                exc,
            )
            return None

        vectors = _coerce_vectors(raw_vectors)
        if len(vectors) != len(texts):
            logger.warning(
                "Sentence-transformer response count mismatch for model %s", spec.name
            )
            return None
        return vectors

    def _prepare_text(self, spec: _ModelSpec, text: str) -> str:
        if spec.name.lower() != _E5_MODEL.lower():
            return text

        stripped = text.strip()
        lowered = stripped.lower()
        if lowered.startswith("query:") or lowered.startswith("passage:"):
            return stripped
        if not stripped:
            return "query:"
        return f"query: {stripped}"

    def _ensure_model_loaded(self, spec: _ModelSpec) -> bool:
        key = self._spec_key(spec)
        known = self._availability.get(key)
        if known is not None:
            return known

        if spec.backend == _BACKEND_OPENAI:
            loaded = self._load_openai_client(spec)
        elif spec.backend == _BACKEND_SENTENCE_TRANSFORMERS:
            loaded = self._load_sentence_transformer(spec)
        else:
            logger.warning("Unsupported embedding backend: %s", spec.backend)
            loaded = False

        self._availability[key] = loaded
        return loaded

    def _load_openai_client(self, spec: _ModelSpec) -> bool:
        if not self.api_key:
            return False

        try:
            from openai import OpenAI
        except ImportError:
            logger.warning("OpenAI SDK not installed; OpenAI embeddings unavailable")
            return False

        try:
            if self.base_url:
                client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    max_retries=2,
                    timeout=30.0,
                )
            else:
                client = OpenAI(api_key=self.api_key, max_retries=2, timeout=30.0)
        except Exception as exc:
            logger.warning("Failed to initialize OpenAI client: %s", exc)
            return False

        self._clients[self._spec_key(spec)] = client
        return True

    def _load_sentence_transformer(self, spec: _ModelSpec) -> bool:
        try:
            module = import_module("sentence_transformers")
        except ImportError:
            logger.warning(
                "sentence-transformers not installed; local embedding models unavailable"
            )
            return False

        sentence_transformer_cls_obj: object = getattr(
            module, "SentenceTransformer", None
        )
        if sentence_transformer_cls_obj is None:
            logger.warning(
                "sentence-transformers package is missing SentenceTransformer"
            )
            return False
        if not callable(sentence_transformer_cls_obj):
            logger.warning("sentence-transformers SentenceTransformer is not callable")
            return False

        sentence_transformer_cls = cast(
            _SentenceTransformerConstructor, sentence_transformer_cls_obj
        )

        try:
            client = sentence_transformer_cls(spec.name)
        except Exception as exc:
            logger.warning("Failed to load embedding model %s: %s", spec.name, exc)
            return False

        self._clients[self._spec_key(spec)] = client
        return True

    def _cache_get(self, text: str) -> list[float] | None:
        cached = self._cache.get(text)
        if cached is None:
            return None
        self._cache.move_to_end(text)
        return cached

    def _cache_set(self, text: str, vector: list[float]) -> None:
        if self.cache_size <= 0:
            return
        self._cache[text] = vector
        self._cache.move_to_end(text)
        if len(self._cache) > self.cache_size:
            _ = self._cache.popitem(last=False)

    def _candidate_specs(self) -> list[_ModelSpec]:
        specs = [self._primary_spec]
        if self._fallback_spec is not None:
            specs.append(self._fallback_spec)
        return specs

    def _spec_key(self, spec: _ModelSpec) -> tuple[str, str]:
        return (spec.backend, spec.name)

    def _fallback_vector(self) -> list[float]:
        dimension = (
            self.dimension
            if self.dimension > 0
            else self._primary_spec.fallback_dimension
        )
        if dimension <= 0:
            return []
        return [0.0] * dimension


__all__ = ["EmbeddingGenerator"]
