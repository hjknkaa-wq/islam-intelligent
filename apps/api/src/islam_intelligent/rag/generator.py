"""Optional LLM-backed statement generator for RAG pipeline.

This module is designed to be fail-safe:
- If OpenAI SDK or API key is unavailable, callers can fall back to mock generation.
- Output remains compatible with existing Statement/Citation contract.
"""

from __future__ import annotations

import logging
import os
import re
from typing import NotRequired, TypedDict

logger = logging.getLogger(__name__)


class EvidenceItem(TypedDict):
    text_unit_id: str
    canonical_id: NotRequired[str]
    snippet: NotRequired[str]
    text_canonical: NotRequired[str]
    evidence_span_id: NotRequired[str]


class Citation(TypedDict):
    evidence_span_id: str
    canonical_id: str
    snippet: str


class Statement(TypedDict):
    text: str
    citations: list[Citation]


class LLMGenerator:
    """Generate evidence-grounded statements using OpenAI Chat Completions."""

    api_key: str | None
    model: str
    temperature: float
    max_tokens: int
    seed: int
    base_url: str | None
    _available: bool
    _client: object | None

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.2,
        max_tokens: int = 500,
        seed: int = 42,
        base_url: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.seed = seed
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

        if not self.api_key:
            return
        api_key = self.api_key
        if not isinstance(api_key, str):
            return
        base_url = self.base_url
        if base_url is not None and not isinstance(base_url, str):
            base_url = None

        try:
            from openai import OpenAI

            if base_url:
                self._client = OpenAI(
                    api_key=api_key,
                    base_url=base_url,
                    max_retries=2,
                    timeout=30.0,
                )
            else:
                self._client = OpenAI(
                    api_key=api_key,
                    max_retries=2,
                    timeout=30.0,
                )
            self._available = True
        except ImportError:
            logger.warning("OpenAI SDK not installed; LLM generation disabled")

    def is_available(self) -> bool:
        return self._available and self._client is not None

    def generate(
        self, query: str, evidence: list[dict[str, object]], min_citations: int = 1
    ) -> list[dict[str, object]]:
        """Generate structured statements with citations.

        Returns list[dict[str, object]] so the pipeline can keep its current typed-dict
        contract without importing this module's specific Statement type.
        """
        if not self.is_available():
            raise RuntimeError("LLM unavailable")
        if not evidence:
            return []

        prompt = self._build_prompt(query, evidence, min_citations)

        client = self._client
        if client is None:
            raise RuntimeError("LLM client unavailable")

        chat = getattr(client, "chat", None)
        completions = getattr(chat, "completions", None)
        create = getattr(completions, "create", None)
        if create is None or not callable(create):
            raise RuntimeError("OpenAI client does not expose chat.completions.create")

        response = create(
            model=self.model,
            messages=[
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": prompt},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            seed=self.seed,
        )

        choices = getattr(response, "choices", [])
        if not choices:
            return []
        message = getattr(choices[0], "message", None)
        content = str(getattr(message, "content", "") or "")
        return self._parse(content, evidence)

    def _system_prompt(self) -> str:
        return (
            "You are an Islamic knowledge assistant. "
            "Answer strictly from provided evidence. "
            "Every statement must include citations [n]. "
            "If evidence is insufficient, keep answer concise and cautious."
        )

    def _build_prompt(
        self, query: str, evidence: list[dict[str, object]], min_citations: int
    ) -> str:
        parts: list[str] = [f"Question: {query}", "", "Evidence:"]
        for index, item in enumerate(evidence, start=1):
            canonical_id = str(item.get("canonical_id", "unknown"))
            snippet = str(item.get("snippet", "")).strip()
            arabic = str(item.get("text_canonical", "")).strip()
            lines = [f"[{index}] {canonical_id}"]
            if arabic:
                lines.append(f"Arabic: {arabic}")
            if snippet:
                lines.append(f"Snippet: {snippet}")
            parts.append("\n".join(lines))

        parts.extend(
            [
                "",
                "Instructions:",
                "- Return 1-3 short factual statements.",
                f"- Each statement must include at least {min_citations} citation marker(s) [n].",
                "- Do not invent sources or facts.",
            ]
        )
        return "\n".join(parts)

    def _parse(
        self, content: str, evidence: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        evidence_lookup: dict[str, dict[str, object]] = {
            str(i + 1): item for i, item in enumerate(evidence)
        }

        statements: list[dict[str, object]] = []
        for raw_line in [line.strip() for line in content.splitlines() if line.strip()]:
            citation_ids: list[str] = [
                match.group(1) for match in re.finditer(r"\[(\d+)\]", raw_line)
            ]
            citations: list[dict[str, str]] = []
            for cid in citation_ids:
                item = evidence_lookup.get(cid)
                if item is None:
                    continue
                citations.append(
                    {
                        "evidence_span_id": str(
                            item.get("evidence_span_id", item.get("text_unit_id", ""))
                        ),
                        "canonical_id": str(item.get("canonical_id", "unknown")),
                        "snippet": str(item.get("snippet", ""))[:200],
                    }
                )

            clean_text = re.sub(r"\[\d+\]", "", raw_line).strip()
            if not clean_text:
                continue
            statements.append({"text": clean_text, "citations": citations})

        return statements


__all__ = ["LLMGenerator"]
