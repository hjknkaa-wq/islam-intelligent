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
    ) -> _EmbeddingResponse: """
        Generate embeddings for a batch of input texts using the specified model.
        
        Parameters:
            model (str): Model identifier to use for embedding generation.
            input (list[str]): List of input strings to embed; one embedding is produced per entry.
            dimensions (int | None): Optional target embedding dimensionality to request when the model supports explicit dimensions.
        
        Returns:
            _EmbeddingResponse: Response object containing the generated embeddings and any provider metadata.
        """
        ...


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
    ) -> object: """
        Encode a list of sentences into embedding vectors.
        
        Parameters:
            sentences (list[str]): Input texts to encode.
            normalize_embeddings (bool): If True, return vectors normalized to unit length.
            convert_to_numpy (bool): If True, return a NumPy ndarray; otherwise return a list of lists of floats.
            show_progress_bar (bool): If True, display a progress bar during encoding.
        
        Returns:
            ndarray | list[list[float]]: Embedding vectors for `sentences`. When `convert_to_numpy` is True an `ndarray` of shape (n, d) is returned; otherwise a list of `n` lists each of length `d`. Each vector is normalized when `normalize_embeddings` is True.
        """
        ...


class _SentenceTransformerConstructor(Protocol):
    def __call__(self, model_name: str) -> _SentenceTransformerModel: """
Return a sentence-transformers model instance for the given model name, constructing or retrieving the model implementation as required.

Parameters:
    model_name (str): Identifier or path of the sentence-transformers model to instantiate.

Returns:
    _SentenceTransformerModel: A model instance suitable for encoding texts with the sentence-transformers API.
"""
...


@dataclass(frozen=True)
class _ModelSpec:
    backend: str
    name: str
    supports_dimensions: bool
    fallback_dimension: int


def _resolve_model_spec(model: str, configured_dimension: int) -> _ModelSpec:
    """
    Resolve a model identifier string into a _ModelSpec describing the chosen backend, canonical model name, whether the model supports explicit dimension requests, and a fallback embedding dimension.
    
    Parameters:
        model (str): Model identifier; may be:
            - prefixed with "openai:" to force the OpenAI backend (e.g., "openai:text-embedding-3-small"),
            - prefixed with "sentence-transformers:" to force a sentence-transformers model,
            - a short alias like "labse" or "e5-large",
            - a repository-style name containing "/" (treated as a sentence-transformers model),
            - or an unprefixed OpenAI model name (default backend).
        configured_dimension (int): User-configured embedding dimension; if greater than zero it becomes the spec's fallback_dimension, otherwise a backend- and model-appropriate default is used.
    
    Returns:
        _ModelSpec: Dataclass with fields (backend, name, supports_dimensions, fallback_dimension) representing the resolved model specification.
    """
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
    """
    Normalize an embedding-like object into a list of floats.
    
    Attempts to convert objects that expose a `tolist()` (e.g., numpy arrays) or plain Python sequences into a list of floats by casting each element that is an int, float, or numeric string to float. If the input is not a sequence or contains any element of an unsupported type, returns an empty list.
    
    Returns:
        list[float]: A list of float values parsed from the input sequence, or an empty list if conversion is not possible.
    """
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
    """
    Normalize various embedding input shapes into a list of float vectors.
    
    Accepts a single vector, a sequence of vectors, or array-like objects (including NumPy arrays) and coerces each element into a list of floats using _coerce_vector. Inputs that cannot be interpreted as a vector or sequence produce an empty list.
    
    Parameters:
        raw_vectors (object): The raw embedding(s) to normalize. Supported forms include:
            - A single vector represented as an iterable of numbers or numeric strings.
            - A sequence (list/tuple) of such vectors.
            - An array-like object that implements `tolist()` (e.g., NumPy arrays).
    
    Returns:
        list[list[float]]: A list of normalized embedding vectors; returns an empty list if the input is invalid or any element cannot be coerced.
    """
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
        """
        Initialize the embedding generator with model selection, optional fallback, dimension and cache configuration, and lazy-loading state.
        
        Parameters:
            api_key (str | None): OpenAI API key to use; if None, the OPENAI_API_KEY environment variable is used.
            model (str | None): Primary embedding model identifier; if None, the configured default is used.
            fallback_model (str | None): Fallback embedding model identifier; if None, the configured fallback is used.
            dimension (int | None): Desired embedding dimension; values less than 1 are treated as unspecified (0). If None, the configured default is used.
            cache_size (int | None): Maximum number of cached embeddings; values less than 1 disable caching (0). If None, the configured default is used.
            base_url (str | None): Optional base URL for the OpenAI API; empty strings are treated as None.
        
        Side effects:
            Resolves and stores the primary and (optional) fallback model specs, normalizes configuration values, and initializes internal caches and client/availability maps.
        """
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
        """
        Check whether at least one candidate embedding model is available.
        
        Returns:
            `true` if at least one candidate model was successfully loaded and is available, `false` otherwise.
        """
        for spec in self._candidate_specs():
            if self._ensure_model_loaded(spec):
                return True
        return False

    def generate_embedding(self, text: str) -> list[float]:
        """
        Generate an embedding vector for a single input text using the configured models and internal cache.
        
        Returns:
            A list of floats representing the embedding for the provided text. If generation fails, returns a zero-vector matching the configured or model-specific fallback dimension.
        """
        embeddings = self.generate_embeddings([text])
        if not embeddings:
            return self._fallback_vector()
        return embeddings[0]

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """
        Produce embeddings for a list of texts, reusing cached vectors and caching newly generated ones.
        
        Parameters:
            texts (list[str]): Input texts to embed. Elements will be cast to strings.
        
        Returns:
            list[list[float]]: Embedding vectors aligned with the input order. If embedding for a text cannot be produced, a deterministic fallback zero-vector (of the configured dimension) is returned in that position. An empty input list yields an empty result list.
        """
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
        """
        Attempt to generate embeddings for the given texts by trying candidate models in order and fall back to zero-vectors if all models fail.
        
        Parameters:
            texts (list[str]): The input texts that require embeddings.
        
        Returns:
            list[list[float]]: A list of embedding vectors corresponding to `texts`; if no candidate model produces embeddings, returns a zero-vector (fallback) for each input.
        """
        for spec in self._candidate_specs():
            vectors = self._generate_with_spec(spec, texts)
            if vectors is not None:
                return vectors

        return [self._fallback_vector() for _ in texts]

    def _generate_with_spec(
        self, spec: _ModelSpec, texts: list[str]
    ) -> list[list[float]] | None:
        """
        Attempt to generate embeddings for the given texts using the provided model specification.
        
        If the model cannot be loaded, the backend is unsupported, or generation fails, the function returns None.
        
        Returns:
            A list of embedding vectors (one list of floats per input text) when generation succeeds, or `None` if embeddings could not be produced.
        """
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
        """
        Generate embeddings for the given texts using the OpenAI backend model described by `spec`.
        
        This will use the generator's configured dimension when the model supports explicit dimensions and will retry without the dimensions if the first request fails due to that parameter.
        
        Parameters:
            spec (_ModelSpec): Resolved model specification identifying the OpenAI model to use.
            texts (list[str]): List of input strings to embed.
        
        Returns:
            list[list[float]]: One embedding vector per input text on success.
            None: If the OpenAI client is not available, the API calls fail, or the response count does not match the number of inputs.
        """
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
        """
        Generate embeddings for the given texts using a loaded sentence-transformers model.
        
        Parameters:
            spec (_ModelSpec): Specification of the model to use (name, backend, and dimension hints).
            texts (list[str]): Input strings to encode.
        
        Returns:
            list[list[float]] | None: A list of embedding vectors matching the input order, or `None` if the client is not loaded or embedding generation failed.
        """
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
        """
        Format input text for E5 models by trimming whitespace and ensuring a suitable `query:` or `passage:` prefix.
        
        Parameters:
            spec (_ModelSpec): Model specification used to determine E5-specific formatting.
            text (str): Original input text.
        
        Returns:
            str: If the spec is not an E5 model, returns `text` unchanged. For E5 models, returns the trimmed text unchanged if it already starts with `query:` or `passage:` (case-insensitive), returns `"query:"` for empty input, or returns the trimmed text prefixed with `"query: "`.
        """
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
        """
        Ensure the backend client for the given model spec is loaded and available.
        
        Checks cached availability for the spec; if unknown, attempts to load the appropriate backend client (OpenAI or sentence-transformers), caches the boolean result, and returns it.
        
        Parameters:
            spec (_ModelSpec): Model specification describing backend, name, and dimension support.
        
        Returns:
            bool: `True` if the model's backend client is available (successfully loaded), `False` otherwise.
        """
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
        """
        Ensure an OpenAI client for the given model spec is initialized and cached.
        
        Parameters:
            spec (_ModelSpec): Model specification used to derive the cache key for storing the initialized client.
        
        Returns:
            bool: `True` if an OpenAI client was successfully created and stored for the spec, `False` otherwise (for example when no API key is configured or the OpenAI SDK is unavailable).
        """
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
        """
        Attempt to load and initialize a local SentenceTransformer model and cache the instance.
        
        Attempts to import the `sentence_transformers` package, construct a `SentenceTransformer`
        using `spec.name`, and store the instantiated model in `self._clients` keyed by the
        spec. Does not raise on import or instantiation failures; those conditions return `False`.
        
        Parameters:
            spec (_ModelSpec): Specification of the model to load (backend, name, supported dimensions).
        
        Returns:
            True if the model was successfully loaded and cached, False otherwise.
        """
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
        """
        Retrieve a cached embedding for the given text and refresh its LRU position.
        
        Returns:
            list[float] | None: The cached embedding vector if present, `None` if the text is not in the cache.
        """
        cached = self._cache.get(text)
        if cached is None:
            return None
        self._cache.move_to_end(text)
        return cached

    def _cache_set(self, text: str, vector: list[float]) -> None:
        """
        Store an embedding vector for `text` in the internal LRU cache and evict the oldest entry when the cache exceeds its configured size.
        
        Parameters:
            text (str): Cache key corresponding to the input text.
            vector (list[float]): Embedding vector to store.
        
        Notes:
            Does nothing if the configured `cache_size` is less than or equal to zero.
        """
        if self.cache_size <= 0:
            return
        self._cache[text] = vector
        self._cache.move_to_end(text)
        if len(self._cache) > self.cache_size:
            _ = self._cache.popitem(last=False)

    def _candidate_specs(self) -> list[_ModelSpec]:
        """
        Provide the ordered candidate model specifications for embedding generation.
        
        Returns:
            list[_ModelSpec]: A list with the primary model spec first; includes the fallback spec second if one is configured.
        """
        specs = [self._primary_spec]
        if self._fallback_spec is not None:
            specs.append(self._fallback_spec)
        return specs

    def _spec_key(self, spec: _ModelSpec) -> tuple[str, str]:
        """
        Create a stable key identifying a model specification for use in caches and client maps.
        
        Parameters:
            spec (_ModelSpec): The model specification to convert into a key.
        
        Returns:
            key (tuple[str, str]): A tuple of `(backend, name)` representing the spec.
        """
        return (spec.backend, spec.name)

    def _fallback_vector(self) -> list[float]:
        """
        Return a zero-filled embedding vector using the configured or primary model fallback dimension.
        
        If the resolved dimension is less than or equal to zero, an empty list is returned.
        
        Returns:
            list[float]: Zero vector with length equal to the resolved dimension, or an empty list if no positive dimension is available.
        """
        dimension = (
            self.dimension
            if self.dimension > 0
            else self._primary_spec.fallback_dimension
        )
        if dimension <= 0:
            return []
        return [0.0] * dimension


__all__ = ["EmbeddingGenerator"]
