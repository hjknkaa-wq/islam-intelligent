"""Faithfulness verification for citation-grounded RAG answers.

This module implements an LLM-as-judge verifier that scores whether each
answer claim is supported by cited retrieved context on a 0-10 scale.

Fail-safe behavior:
- If LLM judge is unavailable, deterministic heuristic scoring is used.
- Every claim is still evaluated against citation context.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

logger = logging.getLogger(__name__)

_MAX_CONTEXT_CHARS = 1200
_MAX_TOTAL_CONTEXT_CHARS = 3000
_TOKEN_PATTERN = re.compile(r"\w+", flags=re.UNICODE)
_JSON_PATTERN = re.compile(r"\{[\s\S]*\}")

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "here",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "was",
    "with",
}

_GENERIC_META_TOKENS = {
    "about",
    "answer",
    "based",
    "context",
    "evidence",
    "information",
    "provided",
    "query",
    "sources",
}


@dataclass(frozen=True)
class ClaimFaithfulness:
    """Faithfulness score for one claim/statement."""

    claim_index: int
    claim_text: str
    citation_ids: tuple[str, ...]
    score: float
    supported: bool
    reason: str


@dataclass(frozen=True)
class FaithfulnessResult:
    """Aggregate faithfulness scoring result (0-10)."""

    overall_score: float
    claims_checked: int
    unsupported_claim_count: int
    per_claim: tuple[ClaimFaithfulness, ...]
    judge: str


@dataclass(frozen=True)
class _ClaimInput:
    claim_index: int
    claim_text: str
    citation_ids: tuple[str, ...]
    context_text: str


class CitationFaithfulnessVerifier:
    """Verify claim faithfulness with LLM-as-judge plus deterministic fallback."""

    api_key: str | None
    model: str
    temperature: float
    seed: int
    max_tokens: int
    base_url: str | None
    _client: object | None
    _available: bool

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.0,
        seed: int = 42,
        max_tokens: int = 900,
        base_url: str | None = None,
    ) -> None:
        """
        Initialize a CitationFaithfulnessVerifier configured for LLM-based judgment with a deterministic fallback.
        
        Parameters:
            api_key (str | None): OpenAI API key to enable the LLM judge; if None, the environment variable OPENAI_API_KEY is used.
            model (str): LLM model identifier to use for scoring.
            temperature (float): Sampling temperature for the LLM.
            seed (int): Deterministic seed used where applicable for reproducibility.
            max_tokens (int): Maximum tokens to request from the LLM for responses.
            base_url (str | None): Optional base URL for the OpenAI-compatible API; if None, will consult RAG_LLM_BASE_URL or OPENAI_BASE_URL environment variables.
        
        Behavior:
            Stores configuration and, when an API key is available, attempts to initialize an OpenAI client and mark the verifier as available; otherwise the verifier remains unavailable and will use the deterministic heuristic fallback.
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.temperature = temperature
        self.seed = seed
        self.max_tokens = max_tokens
        raw_base_url = (
            base_url or os.getenv("RAG_LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
        )
        self.base_url = (
            raw_base_url.strip()
            if isinstance(raw_base_url, str) and raw_base_url.strip()
            else None
        )
        self._client: object | None = None
        self._available = False

        if not self.api_key:
            return

        try:
            from openai import OpenAI

            if self.base_url:
                self._client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    max_retries=2,
                    timeout=30.0,
                )
            else:
                self._client = OpenAI(
                    api_key=self.api_key,
                    max_retries=2,
                    timeout=30.0,
                )
            self._available = True
        except ImportError:
            logger.warning("OpenAI SDK not installed; faithfulness judge disabled")

    def is_available(self) -> bool:
        """
        Indicates whether the verifier can use an LLM judge.
        
        Returns:
            `True` if an LLM client is configured and available, `False` otherwise.
        """
        return self._available and self._client is not None

    def evaluate(
        self,
        statements: Sequence[Mapping[str, object]],
        retrieved_context: Sequence[Mapping[str, object]] | None = None,
    ) -> FaithfulnessResult:
        """
        Evaluate each input statement as a claim against its cited context and produce an aggregate faithfulness score.
        
        Parameters:
            statements (Sequence[Mapping[str, object]]): Sequence of statement mappings; each mapping must include the claim text and any citation identifiers used to locate supporting context.
            retrieved_context (Sequence[Mapping[str, object]] | None): Optional sequence of retrieved context items indexed by citation identifiers to use when checking claims; if omitted, only inline citation snippets (if present in statements) will be considered.
        
        Returns:
            FaithfulnessResult: Aggregate result containing an overall score (0-10), the number of claims checked, count of unsupported claims, per-claim details, and the identifier of the judge used.
        """
        claims = self._build_claim_inputs(statements, retrieved_context)
        if not claims:
            return FaithfulnessResult(
                overall_score=0.0,
                claims_checked=0,
                unsupported_claim_count=0,
                per_claim=(),
                judge="none",
            )

        llm_result = self._score_with_llm(claims)
        if llm_result is not None:
            return llm_result

        return self._score_with_heuristic(claims)

    def _build_claim_inputs(
        self,
        statements: Sequence[Mapping[str, object]],
        retrieved_context: Sequence[Mapping[str, object]] | None,
    ) -> list[_ClaimInput]:
        """
        Builds a list of internal claim inputs by extracting claim text, citation IDs, and merged context for each non-empty statement.
        
        Parameters:
            statements: A sequence of mappings representing claims. Each mapping should contain a "text" key (the claim string) and may include a "citations" key with a list of mappings; each citation mapping may provide "evidence_span_id" (string) and/or "snippet" (string).
            retrieved_context: Optional sequence of mappings produced by the retriever; entries are used to look up and include cited context corresponding to an "evidence_span_id".
        
        Returns:
            A list of _ClaimInput objects, one per non-empty statement. Each _ClaimInput contains:
              - claim_index: 1-based index of the statement in the input sequence,
              - claim_text: the statement text,
              - citation_ids: deduplicated tuple of citation IDs (from evidence_span_id),
              - context_text: merged context text assembled from retrieved context lookups and any provided citation snippets.
        """
        lookup = self._build_retrieved_lookup(retrieved_context)
        claims: list[_ClaimInput] = []

        for claim_index, statement in enumerate(statements, start=1):
            claim_text = str(statement.get("text", "")).strip()
            if not claim_text:
                continue

            citation_ids: list[str] = []
            context_chunks: list[str] = []

            raw_citations = statement.get("citations", [])
            if isinstance(raw_citations, list):
                raw_citations_typed = cast(list[Mapping[str, object]], raw_citations)
                for raw_citation in raw_citations_typed:
                    if not isinstance(raw_citation, Mapping):
                        continue

                    evidence_span_id = raw_citation.get("evidence_span_id")
                    if isinstance(evidence_span_id, str) and evidence_span_id.strip():
                        clean_id = evidence_span_id.strip()
                        citation_ids.append(clean_id)
                        looked_up = lookup.get(clean_id)
                        if looked_up:
                            context_chunks.append(looked_up)

                    snippet = raw_citation.get("snippet")
                    if isinstance(snippet, str) and snippet.strip():
                        context_chunks.append(snippet.strip())

            claims.append(
                _ClaimInput(
                    claim_index=claim_index,
                    claim_text=claim_text,
                    citation_ids=tuple(_dedupe_keep_order(citation_ids)),
                    context_text=self._merge_context_chunks(context_chunks),
                )
            )

        return claims

    def _build_retrieved_lookup(
        self,
        retrieved_context: Sequence[Mapping[str, object]] | None,
    ) -> dict[str, str]:
        """
        Builds a lookup that maps retrieved-context identifiers to their merged text content.
        
        Parameters:
            retrieved_context (Sequence[Mapping[str, object]] | None): Sequence of retrieved context items; each item may contain identifier fields (`evidence_span_id`, `text_unit_id`) and text fields (`snippet`, `text_canonical`, `text`, `content`).
        
        Returns:
            dict[str, str]: Mapping from each found identifier (from `evidence_span_id` or `text_unit_id`) to the merged context text constructed from the available text fields. Returns an empty dict if no valid context or identifiers are present.
        """
        if not retrieved_context:
            return {}

        lookup: dict[str, str] = {}
        for item in retrieved_context:
            ids: list[str] = []
            evidence_span_id = item.get("evidence_span_id")
            text_unit_id = item.get("text_unit_id")
            if isinstance(evidence_span_id, str) and evidence_span_id.strip():
                ids.append(evidence_span_id.strip())
            if isinstance(text_unit_id, str) and text_unit_id.strip():
                ids.append(text_unit_id.strip())

            context_chunks: list[str] = []
            for key in ("snippet", "text_canonical", "text", "content"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    context_chunks.append(value.strip())

            merged = self._merge_context_chunks(context_chunks)
            if not merged:
                continue

            for context_id in ids:
                if context_id not in lookup:
                    lookup[context_id] = merged

        return lookup

    def _merge_context_chunks(self, chunks: Sequence[str]) -> str:
        """
        Merge and deduplicate context chunks into a single text block, enforcing the module's total-context character limit.
        
        Parameters:
            chunks (Sequence[str]): Iterable of context text fragments; empty or falsy elements are ignored.
        
        Returns:
            str: The joined, deduplicated context text. If the result exceeds _MAX_TOTAL_CONTEXT_CHARS, it is truncated to that length.
        """
        merged = "\n".join(_dedupe_keep_order([c for c in chunks if c]))
        if len(merged) <= _MAX_TOTAL_CONTEXT_CHARS:
            return merged
        return merged[:_MAX_TOTAL_CONTEXT_CHARS]

    def _score_with_llm(
        self, claims: Sequence[_ClaimInput]
    ) -> FaithfulnessResult | None:
        """
        Use the configured LLM judge to score each claim against its cited context and convert the judge's response into a FaithfulnessResult.
        
        Parameters:
            claims (Sequence[_ClaimInput]): Sequence of internal claim inputs to evaluate.
        
        Returns:
            FaithfulnessResult: Aggregated result with per-claim scores when the LLM returns a valid, parseable judgement.
            None: If the LLM client is unavailable, the request fails, or the judge's response cannot be parsed.
        """
        if not self.is_available():
            return None

        client = self._client
        if client is None:
            return None

        payload = [
            {
                "claim_index": claim.claim_index,
                "claim": claim.claim_text,
                "citation_ids": list(claim.citation_ids),
                "context": claim.context_text[:_MAX_CONTEXT_CHARS],
            }
            for claim in claims
        ]

        prompt = (
            "Evaluate faithfulness for each claim against its cited context only.\n"
            "Do not use outside knowledge.\n"
            "Scoring guide: 0 means unsupported/fabricated, 10 means fully supported.\n"
            "Return strict JSON with this shape:\n"
            '{"claims":[{"claim_index":1,"score":0,"supported":false,"reason":"..."}],'
            '"overall_score":0}\n\n'
            f"Claims:\n{json.dumps(payload, ensure_ascii=True)}"
        )

        try:
            chat = getattr(client, "chat", None)
            completions = getattr(chat, "completions", None)
            create = getattr(completions, "create", None)
            if create is None or not callable(create):
                return None
            create_fn = cast(Callable[..., object], create)

            response = create_fn(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a strict citation faithfulness judge.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                seed=self.seed,
            )
            choices = getattr(response, "choices", [])
            if not choices:
                return None

            message = getattr(choices[0], "message", None)
            content = str(cast(object, getattr(message, "content", "")) or "")
            parsed = self._parse_llm_json(content)
            if parsed is None:
                return None

            return self._coerce_llm_result(parsed, claims)
        except Exception as exc:
            logger.warning(
                "Faithfulness LLM judge failed; using heuristic fallback: %s", exc
            )
            return None

    def _parse_llm_json(self, content: str) -> Mapping[str, object] | None:
        """
        Parse and return the first JSON object found in a text string.
        
        Parameters:
            content (str): Text that may contain a JSON object or be a JSON document.
        
        Returns:
            Mapping[str, object] | None: A mapping representing the parsed JSON object if one is present and valid; otherwise `None`.
        """
        if not content.strip():
            return None

        direct = _load_json_object(content)
        if direct is not None:
            return direct

        match = _JSON_PATTERN.search(content)
        if not match:
            return None
        return _load_json_object(match.group(0))

    def _coerce_llm_result(
        self,
        parsed: Mapping[str, object],
        claims: Sequence[_ClaimInput],
    ) -> FaithfulnessResult:
        """
        Convert a parsed LLM response into a FaithfulnessResult for the given claims, falling back to the heuristic scorer if the parsed structure is invalid or incomplete.
        
        Parameters:
            parsed (Mapping[str, object]): Parsed JSON-like mapping produced from the LLM response; expected to contain a "claims" list with per-claim objects and optionally "overall_score".
            claims (Sequence[_ClaimInput]): The list of claim inputs that were submitted to the LLM; used to align LLM judgments to the original claims.
        
        Returns:
            FaithfulnessResult: Aggregated faithfulness result with per-claim scores, supported flags, reasons, overall score, and the judge set to "llm". If the parsed response is missing or malformed, returns the result produced by the deterministic heuristic scorer.
        """
        raw_claims = parsed.get("claims")
        if not isinstance(raw_claims, list):
            return self._score_with_heuristic(claims)

        llm_by_index: dict[int, Mapping[str, object]] = {}
        for raw in raw_claims:
            if not isinstance(raw, Mapping):
                continue
            claim_index = _coerce_int(raw.get("claim_index"), default=0)
            if claim_index <= 0:
                continue
            llm_by_index[claim_index] = raw

        per_claim: list[ClaimFaithfulness] = []
        for claim in claims:
            raw = llm_by_index.get(claim.claim_index)
            if raw is None:
                return self._score_with_heuristic(claims)

            score = _clamp_score(_coerce_float(raw.get("score"), default=0.0))
            supported_raw = raw.get("supported")
            supported = (
                bool(supported_raw) if isinstance(supported_raw, bool) else score >= 6.0
            )
            reason = str(raw.get("reason", "")).strip() or "llm_judgment"

            per_claim.append(
                ClaimFaithfulness(
                    claim_index=claim.claim_index,
                    claim_text=claim.claim_text,
                    citation_ids=claim.citation_ids,
                    score=score,
                    supported=supported,
                    reason=reason,
                )
            )

        raw_overall = parsed.get("overall_score")
        if raw_overall is None:
            overall = _mean([item.score for item in per_claim])
        else:
            overall = _clamp_score(_coerce_float(raw_overall, default=0.0))

        unsupported = sum(1 for item in per_claim if not item.supported)
        return FaithfulnessResult(
            overall_score=overall,
            claims_checked=len(per_claim),
            unsupported_claim_count=unsupported,
            per_claim=tuple(per_claim),
            judge="llm",
        )

    def _score_with_heuristic(
        self, claims: Sequence[_ClaimInput]
    ) -> FaithfulnessResult:
        """
        Deterministically score a sequence of claims against their cited context using token-overlap heuristics and simple rules.
        
        For each claim produces a ClaimFaithfulness with one of these outcomes:
        - If there is no cited context: score 0.0, reason "no_cited_context".
        - If tokenization yields no usable tokens for the claim or its context: score 0.0, reason "insufficient_tokens".
        - If the claim consists only of generic/meta tokens: score 8.0, reason "generic_meta_claim" and marked supported.
        - Otherwise: compute the fraction of claim tokens present in the context, scale it to a 0–10 score (rounded to two decimals), reason "token_overlap"; a score >= 6.0 is considered supported.
        
        Parameters:
            claims (Sequence[_ClaimInput]): Sequence of internal claim inputs, each containing the claim text, cited IDs, and merged context text.
        
        Returns:
            FaithfulnessResult: Aggregated result containing the mean overall score, number of claims checked, count of unsupported claims, per-claim details, and `judge` set to "heuristic".
        """
        per_claim: list[ClaimFaithfulness] = []
        for claim in claims:
            if not claim.context_text:
                score = 0.0
                supported = False
                reason = "no_cited_context"
            else:
                claim_tokens = _tokenize(claim.claim_text)
                context_tokens = _tokenize(claim.context_text)
                if not claim_tokens or not context_tokens:
                    score = 0.0
                    supported = False
                    reason = "insufficient_tokens"
                elif claim_tokens.issubset(_GENERIC_META_TOKENS):
                    score = 8.0
                    supported = True
                    reason = "generic_meta_claim"
                else:
                    overlap = len(claim_tokens.intersection(context_tokens)) / len(
                        claim_tokens
                    )
                    score = _clamp_score(round(overlap * 10.0, 2))
                    supported = score >= 6.0
                    reason = "token_overlap"

            per_claim.append(
                ClaimFaithfulness(
                    claim_index=claim.claim_index,
                    claim_text=claim.claim_text,
                    citation_ids=claim.citation_ids,
                    score=score,
                    supported=supported,
                    reason=reason,
                )
            )

        unsupported = sum(1 for item in per_claim if not item.supported)
        return FaithfulnessResult(
            overall_score=_mean([item.score for item in per_claim]),
            claims_checked=len(per_claim),
            unsupported_claim_count=unsupported,
            per_claim=tuple(per_claim),
            judge="heuristic",
        )


def _dedupe_keep_order(values: Sequence[str]) -> list[str]:
    """
    Remove duplicate strings from a sequence while preserving their first-occurrence order.
    
    Parameters:
        values (Sequence[str]): Sequence of strings to deduplicate.
    
    Returns:
        list[str]: A new list containing the first occurrence of each string from `values`, in their original order.
    """
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _coerce_float(raw: object, *, default: float) -> float:
    """
    Convert a value to a float, returning a fallback when conversion is not possible.
    
    Parameters:
        raw (object): The input value to coerce to float; accepted types are int, float, or str representing a number.
        default (float): Value to return if `raw` cannot be converted to a float.
    
    Returns:
        float: The converted float value, or `default` if conversion fails.
    """
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        try:
            return float(raw)
        except ValueError:
            return default
    return default


def _coerce_int(raw: object, *, default: int) -> int:
    """
    Convert a value to an integer, falling back to a provided default when conversion isn't possible.
    
    Parameters:
        raw (object): The value to coerce to an int. If already an int it is returned unchanged; if a string, an attempt is made to parse it as an integer.
        default (int): The integer to return if `raw` cannot be coerced.
    
    Returns:
        int: The resulting integer from `raw` or `default` if conversion failed.
    """
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        try:
            return int(raw)
        except ValueError:
            return default
    return default


def _clamp_score(score: float) -> float:
    """
    Clamp a numeric score to the inclusive range 0.0–10.0.
    
    Parameters:
        score (float): Numeric score to clamp; will be converted to float if possible.
    
    Returns:
        float: The input coerced to a float and constrained to be between 0.0 and 10.0 inclusive.
    """
    return max(0.0, min(10.0, float(score)))


def _mean(values: Sequence[float]) -> float:
    """
    Compute the arithmetic mean of a sequence of floats, rounded to two decimal places.
    
    Returns:
        The mean of `values` rounded to two decimal places. Returns `0.0` if `values` is empty.
    """
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def _tokenize(text: str) -> set[str]:
    """
    Extract normalized word tokens from the input text, excluding numeric tokens, tokens of length two or less, and configured stopwords.
    
    Returns:
        A set of unique, lowercased tokens that remain after filtering.
    """
    raw_tokens = cast(list[str], _TOKEN_PATTERN.findall(text))
    tokens = {token.lower() for token in raw_tokens}
    filtered: set[str] = set()
    for token in tokens:
        if token.isdigit():
            continue
        if len(token) <= 2:
            continue
        if token in _STOPWORDS:
            continue
        filtered.add(token)
    return filtered


def _load_json_object(content: str) -> Mapping[str, object] | None:
    """
    Parse a JSON string and return it if the top-level value is a JSON object.
    
    Parameters:
        content (str): The JSON string to parse.
    
    Returns:
        Mapping[str, object] | None: The parsed mapping when `content` decodes to a JSON object; `None` if the string is not valid JSON or if the top-level JSON value is not an object.
    """
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, Mapping):
        return cast(Mapping[str, object], parsed)
    return None


__all__ = [
    "ClaimFaithfulness",
    "FaithfulnessResult",
    "CitationFaithfulnessVerifier",
]
