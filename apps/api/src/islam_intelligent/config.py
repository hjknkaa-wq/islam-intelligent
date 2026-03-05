"""Application configuration scaffold."""

import os
from dataclasses import dataclass


def _as_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(raw: str | None, default: int) -> int:
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _as_float(raw: str | None, default: float) -> float:
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Islam Intelligent API")
    environment: str = os.getenv("APP_ENV", "development")
    rag_enable_llm: bool = _as_bool(os.getenv("RAG_ENABLE_LLM"), False)
    rag_llm_model: str = os.getenv("RAG_LLM_MODEL", "gpt-4o-mini")
    rag_llm_temperature: float = _as_float(os.getenv("RAG_LLM_TEMPERATURE"), 0.2)
    rag_llm_seed: int = _as_int(os.getenv("RAG_LLM_SEED"), 42)
    rag_llm_base_url: str = os.getenv(
        "RAG_LLM_BASE_URL", os.getenv("OPENAI_BASE_URL", "")
    )
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    embedding_fallback_model: str = os.getenv(
        "EMBEDDING_FALLBACK_MODEL", "sentence-transformers/LaBSE"
    )
    embedding_dimension: int = _as_int(os.getenv("EMBEDDING_DIMENSION"), 1536)
    embedding_cache_size: int = _as_int(os.getenv("EMBEDDING_CACHE_SIZE"), 2048)

    # Cross-Encoder Reranker Configuration
    rag_enable_reranker: bool = _as_bool(os.getenv("RAG_ENABLE_RERANKER"), True)
    rag_reranker_model: str = os.getenv(
        "RAG_RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"
    )
    rag_reranker_top_k: int = _as_int(os.getenv("RAG_RERANKER_TOP_K"), 10)

    # HyDE Configuration
    hyde_enabled: bool = _as_bool(os.getenv("HYDE_ENABLED"), True)
    hyde_max_tokens: int = _as_int(os.getenv("HYDE_MAX_TOKENS"), 256)
    hyde_temperature: float = _as_float(os.getenv("HYDE_TEMPERATURE"), 0.3)

    # Query Expansion Configuration
    query_expansion_enabled: bool = _as_bool(os.getenv("QUERY_EXPANSION_ENABLED"), True)
    query_expansion_count: int = _as_int(os.getenv("QUERY_EXPANSION_COUNT"), 3)

    # Faithfulness Verification Configuration
    faithfulness_enabled: bool = _as_bool(os.getenv("FAITHFULNESS_ENABLED"), True)
    faithfulness_threshold: float = _as_float(os.getenv("FAITHFULNESS_THRESHOLD"), 7.0)

    # Cost Governance Configuration
    cost_governance_enabled: bool = _as_bool(os.getenv("COST_GOVERNANCE_ENABLED"), True)
    daily_budget_usd: float = _as_float(os.getenv("DAILY_BUDGET_USD"), 10.0)
    weekly_budget_usd: float = _as_float(os.getenv("WEEKLY_BUDGET_USD"), 50.0)

    # Metrics and Observability Configuration
    metrics_enabled: bool = _as_bool(os.getenv("METRICS_ENABLED"), True)
    metrics_db_enabled: bool = _as_bool(os.getenv("METRICS_DB_ENABLED"), True)


settings = Settings()
