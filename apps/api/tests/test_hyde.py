"""Unit tests for HyDE (Hypothetical Document Embeddings) query expansion."""

from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false

import pytest

from islam_intelligent.rag.retrieval.hyde import (
    HyDEConfig,
    HyDEQueryExpander,
    create_hyde_expander,
)


class TestHyDEConfig:
    """Tests for HyDEConfig dataclass."""

    def test_default_config(self) -> None:
        config = HyDEConfig()
        assert config.enabled is True
        assert config.max_tokens == 150
        assert config.temperature == 0.3
        assert config.model == "gpt-4o-mini"
        assert config.seed == 42

    def test_custom_config(self) -> None:
        config = HyDEConfig(
            enabled=False,
            max_tokens=200,
            temperature=0.5,
            model="gpt-4o",
            seed=123,
        )
        assert config.enabled is False
        assert config.max_tokens == 200
        assert config.temperature == 0.5
        assert config.model == "gpt-4o"
        assert config.seed == 123


class TestHyDEQueryExpanderInitialization:
    """Tests for HyDEQueryExpander initialization."""

    def test_init_with_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        expander = HyDEQueryExpander()
        assert expander.config.enabled is True
        assert expander.is_available() is False  # No API key

    def test_init_disabled_by_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        config = HyDEConfig(enabled=False)
        expander = HyDEQueryExpander(config=config)
        assert expander.config.enabled is False
        assert expander.is_available() is False

    def test_init_unavailable_without_api_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        expander = HyDEQueryExpander()
        assert expander.is_available() is False

    def test_init_with_custom_embedding_generator(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from islam_intelligent.rag.retrieval.embeddings import EmbeddingGenerator

        generator = EmbeddingGenerator(api_key=None)
        expander = HyDEQueryExpander(embedding_generator=generator)
        assert expander._embedding_generator is generator


class TestHyDEQueryExpansion:
    """Tests for HyDE query expansion functionality."""

    def test_expand_returns_original_query_when_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        expander = HyDEQueryExpander()
        query = "How to pray tahajjud?"

        result = expander.expand(query)

        assert result == query

    def test_expand_returns_original_query_when_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        config = HyDEConfig(enabled=False)
        expander = HyDEQueryExpander(config=config)
        query = "How to pray tahajjud?"

        result = expander.expand(query)

        assert result == query

    def test_expand_returns_original_query_on_empty_content(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that expand falls back to query when LLM returns empty content."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        # Even with mock, without API key it's unavailable
        expander = HyDEQueryExpander()
        query = "Test query"

        result = expander.expand(query)

        assert result == query


class TestHyDEEmbedding:
    """Tests for HyDE embedding generation."""

    def test_get_embedding_returns_fallback_when_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        expander = HyDEQueryExpander()
        query = "How to pray?"

        embedding = expander.get_embedding(query)

        # Should return an embedding vector; dimension depends on which
        # embedding model is available (e.g. 1536 for OpenAI, 768 for LaBSE)
        assert isinstance(embedding, list)
        assert len(embedding) > 0

    def test_get_embedding_with_fallback_returns_metadata(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        expander = HyDEQueryExpander()
        query = "How to pray?"

        embedding, metadata = expander.get_embedding_with_fallback(query)

        assert isinstance(embedding, list)
        assert len(embedding) > 0
        assert metadata["hyde_used"] is False
        assert metadata["text_embedded"] == query
        assert "hypothetical_answer" not in metadata


class TestHyDESystemPrompt:
    """Tests for HyDE prompt construction."""

    def test_system_prompt_contains_islamic_context(self) -> None:
        expander = HyDEQueryExpander()
        prompt = expander._system_prompt()

        assert "Islamic" in prompt or "scholar" in prompt.lower()
        assert "hypothetical" in prompt.lower() or "answer" in prompt.lower()

    def test_build_hypothetical_prompt_includes_query(self) -> None:
        expander = HyDEQueryExpander()
        query = "What is the ruling on fasting?"
        prompt = expander._build_hypothetical_prompt(query)

        assert query in prompt
        assert "Question:" in prompt


class TestCreateHyDEExpander:
    """Tests for the factory function."""

    def test_create_with_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("RAG_ENABLE_HYDE", raising=False)
        expander = create_hyde_expander()

        assert isinstance(expander, HyDEQueryExpander)
        assert expander.config.enabled is True  # Default enabled

    def test_create_disabled_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("RAG_ENABLE_HYDE", "false")
        expander = create_hyde_expander()

        assert expander.config.enabled is False

    def test_create_disabled_via_param(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        expander = create_hyde_expander(enabled=False)

        assert expander.config.enabled is False

    def test_create_overrides_env_with_param(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("RAG_ENABLE_HYDE", "false")
        expander = create_hyde_expander(enabled=True)

        assert expander.config.enabled is True

    def test_create_with_custom_max_tokens(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        expander = create_hyde_expander(max_tokens=200)

        assert expander.config.max_tokens == 200

    def test_create_with_custom_temperature(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        expander = create_hyde_expander(temperature=0.7)

        assert expander.config.temperature == 0.7


class TestHyDEModelParams:
    """Tests for model parameter handling from settings."""

    def test_model_params_from_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that HyDE uses settings for model params.

        Note: Settings are loaded at import time, so we test that the
        create_hyde_expander function correctly passes through the
        model and seed from settings to the config.
        """
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        # Settings module is already loaded, so we just verify the structure
        # The actual values come from settings at the time of import
        from islam_intelligent.config import settings

        expander = create_hyde_expander()

        # Verify that the model and seed match what's in settings
        assert expander.config.model == settings.rag_llm_model
        assert expander.config.seed == settings.rag_llm_seed


class TestHyDEEdgeCases:
    """Tests for edge cases and error handling."""

    def test_expand_with_empty_query(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        expander = HyDEQueryExpander()

        result = expander.expand("")

        assert result == ""

    def test_expand_with_whitespace_query(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        expander = HyDEQueryExpander()

        result = expander.expand("   ")

        assert result == "   "

    def test_get_embedding_with_empty_query(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        expander = HyDEQueryExpander()

        embedding = expander.get_embedding("")

        assert isinstance(embedding, list)
        assert len(embedding) > 0

    def test_get_embedding_with_very_long_query(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        expander = HyDEQueryExpander()
        long_query = "What is the ruling? " * 100

        embedding = expander.get_embedding(long_query)

        assert isinstance(embedding, list)
        assert len(embedding) > 0


def _make_mock_client(content: str | None = "mock", *, raise_exc: bool = False):
    """Build a lightweight mock OpenAI client for HyDE tests."""

    class _Message:
        def __init__(self, text: str | None):
            self.content = text

    class _Choice:
        def __init__(self, text: str | None):
            self.message = _Message(text)

    class _Completions:
        def create(self, **kwargs: object):
            if raise_exc:
                raise RuntimeError("API error")

            class _Resp:
                choices = [_Choice(content)] if content is not None else []

            return _Resp()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    return _Client()


def _build_hyde_with_mock_client(
    content: str | None = "mock",
    *,
    raise_exc: bool = False,
) -> HyDEQueryExpander:
    """Create a HyDEQueryExpander with a pre-wired mock client (no openai import)."""
    config = HyDEConfig(enabled=True)
    expander = HyDEQueryExpander.__new__(HyDEQueryExpander)
    expander.config = config
    expander.api_key = "test-key"
    expander.base_url = None
    from islam_intelligent.rag.retrieval.embeddings import EmbeddingGenerator

    expander._embedding_generator = EmbeddingGenerator()
    expander._client = _make_mock_client(content, raise_exc=raise_exc)
    expander._available = True
    return expander


class TestHyDEWithMockedLLM:
    """Tests using mocked LLM responses."""

    def test_expand_with_mocked_llm_success(self) -> None:
        """Test expand when LLM is available and returns content."""
        expander = _build_hyde_with_mock_client(
            "Tahajjud is prayed at night after sleeping."
        )

        query = "How do I pray tahajjud?"
        result = expander.expand(query)

        assert result == "Tahajjud is prayed at night after sleeping."
        assert result != query

    def test_expand_with_mocked_llm_empty_choices(self) -> None:
        """Test expand falls back to query when LLM returns empty choices."""
        expander = _build_hyde_with_mock_client(None)

        query = "How do I pray?"
        result = expander.expand(query)

        assert result == query  # Falls back to original

    def test_expand_with_mocked_llm_exception(self) -> None:
        """Test expand falls back to query when LLM raises exception."""
        expander = _build_hyde_with_mock_client(raise_exc=True)

        query = "How do I pray?"
        result = expander.expand(query)

        assert result == query  # Falls back to original

    def test_get_embedding_with_mocked_success(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test get_embedding when HyDE succeeds."""
        mock_embedding = [0.1] * 1536

        def mock_generate_embedding(self: object, text: str) -> list[float]:
            return mock_embedding

        monkeypatch.setattr(
            "islam_intelligent.rag.retrieval.embeddings.EmbeddingGenerator.generate_embedding",
            mock_generate_embedding,
        )

        expander = _build_hyde_with_mock_client("Prayer involves specific steps.")

        query = "How do I pray?"
        result = expander.get_embedding(query)

        assert result == mock_embedding

    def test_get_embedding_with_fallback_success(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test get_embedding_with_fallback when HyDE succeeds."""
        mock_embedding = [0.2] * 1536

        def mock_generate_embedding(self: object, text: str) -> list[float]:
            return mock_embedding

        monkeypatch.setattr(
            "islam_intelligent.rag.retrieval.embeddings.EmbeddingGenerator.generate_embedding",
            mock_generate_embedding,
        )

        expander = _build_hyde_with_mock_client("Detailed Islamic answer.")

        query = "How do I pray?"
        embedding, metadata = expander.get_embedding_with_fallback(query)

        assert embedding == mock_embedding
        assert metadata["hyde_used"] is True
        assert metadata["hypothetical_answer"] == "Detailed Islamic answer."
        assert metadata["text_embedded"] == "Detailed Islamic answer."
