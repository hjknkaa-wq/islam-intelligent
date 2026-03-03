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


settings = Settings()
