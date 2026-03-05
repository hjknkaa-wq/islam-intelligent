"""HyDE (Hypothetical Document Embeddings) for query expansion.

This module implements the HyDE technique where:
1. Generate a hypothetical answer using an LLM
2. Embed the hypothetical answer (not the original query)
3. Use the hypothetical embedding for retrieval

The implementation is fail-safe and gracefully falls back to query-only embeddings
when the LLM is unavailable or disabled.

References:
- Gao et al. "Precise Zero-Shot Dense Retrieval without Relevance Labels"
  https://arxiv.org/abs/2212.10496
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from ...config import settings
from .embeddings import EmbeddingGenerator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HyDEConfig:
    """Configuration for HyDE query expansion."""

    enabled: bool = True
    max_tokens: int = 150
    temperature: float = 0.3
    model: str = "gpt-4o-mini"
    seed: int = 42


class HyDEQueryExpander:
    """Expand queries using HyDE: generate hypothetical answers for better retrieval.

    The HyDE technique improves retrieval by:
    1. Using an LLM to generate a hypothetical answer to the query
    2. Embedding that hypothetical answer instead of the query itself
    3. Retrieving documents similar to the hypothetical answer

    This works because hypothetical answers often contain richer semantic content
    and domain terminology than the original query.

    Example:
        >>> expander = HyDEQueryExpander()
        >>> hypothetical = expander.expand("How to pray tahajjud?")
        >>> print(hypothetical)
        'Tahajjud prayer is performed after sleeping and before Fajr...'
        >>> embedding = expander.get_embedding("How to pray tahajjud?")
        # Returns embedding of hypothetical answer, not the query
    """

    config: HyDEConfig
    api_key: str | None
    base_url: str | None
    _available: bool
    _client: object | None
    _embedding_generator: EmbeddingGenerator

    def __init__(
        self,
        config: HyDEConfig | None = None,
        embedding_generator: EmbeddingGenerator | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        """
        Initialize the HyDEQueryExpander with configuration, embedding generator, and optional OpenAI client settings.
        
        Parameters:
            config (HyDEConfig | None): HyDE configuration; a default HyDEConfig is used when None.
            embedding_generator (EmbeddingGenerator | None): Embedding generator to use; a new EmbeddingGenerator is created when None.
            api_key (str | None): OpenAI API key to initialize the LLM client; falls back to the OPENAI_API_KEY environment variable when None.
            base_url (str | None): Custom OpenAI-compatible API base URL; when None a base URL from environment variables may be used.
        """
        self.config = config or HyDEConfig()
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._embedding_generator = embedding_generator or EmbeddingGenerator()

        raw_base_url = (
            base_url or os.getenv("RAG_LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
        )
        self.base_url = (
            raw_base_url.strip()
            if isinstance(raw_base_url, str) and raw_base_url.strip()
            else None
        )

        self._client = None
        self._available = False

        # Only initialize LLM client if HyDE is enabled
        if not self.config.enabled:
            logger.debug("HyDE disabled by configuration")
            return

        if not self.api_key:
            logger.debug("HyDE LLM unavailable: no API key")
            return

        key = self.api_key

        try:
            from openai import OpenAI

            if self.base_url:
                self._client = OpenAI(
                    api_key=key,
                    base_url=self.base_url,
                    max_retries=2,
                    timeout=30.0,
                )
            else:
                self._client = OpenAI(
                    api_key=key,
                    max_retries=2,
                    timeout=30.0,
                )
            self._available = True
            logger.debug("HyDE LLM client initialized successfully")
        except ImportError:
            logger.warning("OpenAI SDK not installed; HyDE expansion disabled")

    def is_available(self) -> bool:
        """
        Report whether HyDE query expansion can be used.
        
        Returns:
            `true` if HyDE is enabled, the OpenAI-compatible SDK/client was successfully initialized, and a client instance exists; `false` otherwise.
        """
        return self.config.enabled and self._available and self._client is not None

    def expand(self, query: str) -> str:
        """
        Generate a brief hypothetical answer for the given query to use for embedding-based retrieval.
        
        If HyDE is unavailable or generation fails, the original query is returned as a fallback.
        
        Parameters:
            query (str): The original user query to expand.
        
        Returns:
            A hypothetical answer generated by the LLM, or the original query if HyDE is unavailable or generation failed.
        """
        if not self.is_available():
            logger.debug("HyDE unavailable, returning original query")
            return query

        client = self._client
        if client is None:
            return query

        prompt = self._build_hypothetical_prompt(query)

        try:
            chat = getattr(client, "chat", None)
            completions = getattr(chat, "completions", None)
            create = getattr(completions, "create", None)
            if create is None or not callable(create):
                logger.warning("OpenAI client does not expose chat.completions.create")
                return query

            response = create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                seed=self.config.seed,
            )

            choices = getattr(response, "choices", [])
            if not choices:
                logger.warning("HyDE LLM returned empty choices")
                return query

            message = getattr(choices[0], "message", None)
            content = str(getattr(message, "content", "") or "").strip()

            if not content:
                logger.warning("HyDE LLM returned empty content")
                return query

            logger.debug("HyDE generated hypothetical answer: %r", content[:100])
            return content

        except Exception as exc:
            logger.warning("HyDE generation failed, falling back to query: %s", exc)
            return query

    def get_embedding(self, query: str) -> list[float]:
        """
        Produce an embedding for retrieval by embedding HyDE's hypothetical answer to the provided query.
        
        Parameters:
            query (str): The original user query.
        
        Returns:
            list[float]: Embedding vector for the text that was embedded; uses the hypothetical answer if HyDE produced one, otherwise uses the original query.
        """
        # Generate hypothetical answer
        hypothetical = self.expand(query)

        # If we got back the original query (HyDE failed/unavailable),
        # use the original query for embedding
        text_to_embed = hypothetical if hypothetical != query else query

        # Generate embedding
        embedding = self._embedding_generator.generate_embedding(text_to_embed)

        logger.debug(
            "HyDE embedding generated for %s (hypothetical length: %d)",
            "hypothetical answer" if hypothetical != query else "original query",
            len(text_to_embed),
        )

        return embedding

    def get_embedding_with_fallback(
        self, query: str
    ) -> tuple[list[float], dict[str, object]]:
        """
        Return an embedding for the given query and metadata describing whether a HyDE hypothetical answer was used.
        
        Returns:
            A tuple (embedding, metadata) where:
                - embedding (list[float]): The embedding vector produced for the text actually embedded.
                - metadata (dict[str, object]): Information about the embedding:
                    - 'hyde_used' (bool): True if a hypothetical answer was generated and embedded, False if the original query was embedded.
                    - 'text_embedded' (str): The exact text that was embedded.
                    - 'hypothetical_answer' (str, optional): The generated hypothetical answer when 'hyde_used' is True.
        """
        hypothetical = self.expand(query)
        used_hyde = hypothetical != query
        text_to_embed = hypothetical if used_hyde else query

        embedding = self._embedding_generator.generate_embedding(text_to_embed)

        metadata: dict[str, object] = {
            "hyde_used": used_hyde,
            "text_embedded": text_to_embed,
        }

        if used_hyde:
            metadata["hypothetical_answer"] = hypothetical

        return embedding, metadata

    def _system_prompt(self) -> str:
        """
        Return the system prompt that guides generation of a concise hypothetical Islamic scholarly answer.
        
        Returns:
            prompt (str): A system prompt instructing the model to produce a brief (2–3 sentences), factual hypothetical answer using appropriate Islamic terminology.
        """
        return (
            "You are a knowledgeable Islamic scholar. "
            "Given a question, provide a brief, factual hypothetical answer "
            "that captures the key concepts and terminology that would appear "
            "in authoritative Islamic sources. Answer concisely in 2-3 sentences."
        )

    def _build_hypothetical_prompt(self, query: str) -> str:
        """
        Create the user prompt instructing the LLM to produce a concise hypothetical answer grounded in Islamic sources for the given query.
        
        Returns:
            prompt (str): A prompt string containing the question followed by instructions to generate a brief, factual hypothetical answer referencing the Quran, Hadith, or scholarly works and including relevant Arabic terms and key concepts.
        """
        return (
            f"Question: {query}\n\n"
            "Provide a brief hypothetical answer that would be found in "
            "Islamic sources (Quran, Hadith, or scholarly works). "
            "Include relevant Arabic terms and key concepts. "
            "Keep it factual and concise."
        )


def create_hyde_expander(
    enabled: bool | None = None,
    max_tokens: int = 150,
    temperature: float = 0.3,
) -> HyDEQueryExpander:
    """
    Create a HyDEQueryExpander configured from the given parameters and environment.
    
    If `enabled` is None, the RAG_ENABLE_HYDE environment variable is read (default "true") to determine enablement. The expander's `model` and `seed` are sourced from module settings.
    
    Parameters:
        enabled: If provided, explicitly enable or disable HyDE; otherwise derived from RAG_ENABLE_HYDE.
        max_tokens: Maximum tokens allowed for hypothetical answer generation.
        temperature: Sampling temperature for LLM generation.
    
    Returns:
        A configured HyDEQueryExpander instance.
    """
    # Determine if HyDE should be enabled
    if enabled is None:
        raw = os.getenv("RAG_ENABLE_HYDE", "true").lower()
        enabled = raw in ("1", "true", "yes", "on")

    config = HyDEConfig(
        enabled=enabled,
        max_tokens=max_tokens,
        temperature=temperature,
        model=settings.rag_llm_model,
        seed=settings.rag_llm_seed,
    )

    return HyDEQueryExpander(config=config)


__all__ = [
    "HyDEQueryExpander",
    "HyDEConfig",
    "create_hyde_expander",
]
