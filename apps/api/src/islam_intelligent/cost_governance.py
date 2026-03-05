"""Cost governance for API usage control.

This module provides:
- Cost estimation before embedding/LLM calls.
- Daily and weekly budget enforcement.
- Graceful degradation when cost caps are near/exceeded.
- Alerting hooks (logging by default, extensible for Slack/email).
- Model routing from cheap to expensive based on query complexity.
- Persistence of cost usage and alert events to the database.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol, cast

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .db.engine import SessionLocal

logger = logging.getLogger(__name__)
UTC = timezone.utc


def _utc_now() -> datetime:
    """
    Return the current timezone-aware UTC datetime.
    
    Returns:
        datetime: Current UTC datetime with tzinfo set to UTC.
    """
    return datetime.now(tz=UTC)


def _clamp_non_negative(value: float) -> float:
    """
    Clamp a numeric value to a minimum of 0.0.
    
    Parameters:
        value (float): The input number to clamp.
    
    Returns:
        float: The input converted to float if it is greater than or equal to 0.0, otherwise 0.0.
    """
    return max(0.0, float(value))


def _start_of_day_utc(at: datetime) -> datetime:
    """
    Return the UTC-aligned start of the day for the given datetime.
    
    Parameters:
    	at (datetime): Input datetime. If `at` is naive (no tzinfo), it is interpreted as UTC.
    
    Returns:
    	datetime: A timezone-aware `datetime` set to 00:00:00 at UTC on the same calendar day as `at`.
    """
    normalized = at if at.tzinfo is not None else at.replace(tzinfo=UTC)
    normalized = normalized.astimezone(UTC)
    return datetime(
        normalized.year,
        normalized.month,
        normalized.day,
        tzinfo=UTC,
    )


def _start_of_week_utc(at: datetime) -> datetime:
    """
    Return the UTC datetime at the start of the week (Monday 00:00:00) containing the given datetime.
    
    Parameters:
        at (datetime): Input datetime; its UTC-equivalent day is used to determine the week.
    
    Returns:
        datetime: UTC datetime set to 00:00:00 on Monday of the same week as `at`.
    """
    day_start = _start_of_day_utc(at)
    return day_start - timedelta(days=day_start.weekday())


@dataclass(frozen=True)
class CostEstimate:
    embedding_model: str
    llm_model: str
    embedding_tokens: int
    llm_prompt_tokens: int
    llm_completion_tokens: int
    embedding_cost_usd: float
    llm_cost_usd: float

    @property
    def total_cost_usd(self) -> float:
        """
        Total estimated cost in USD for the combined embedding and LLM usage.
        
        Returns:
            total_cost_usd (float): Sum of `embedding_cost_usd` and `llm_cost_usd`, rounded to 10 decimal places.
        """
        return round(self.embedding_cost_usd + self.llm_cost_usd, 10)


@dataclass
class CostTracker:
    daily_budget: float
    current_spend: float = 0.0

    def can_proceed(self, estimated_cost: float) -> bool:
        """
        Determine whether adding the given estimated cost to current spend remains within the daily budget.
        
        Returns:
            `true` if the sum of `current_spend` and `estimated_cost` is less than or equal to `daily_budget`, `false` otherwise.
        """
        estimated = _clamp_non_negative(estimated_cost)
        return self.current_spend + estimated <= self.daily_budget

    def add_spend(self, spend: float) -> None:
        """
        Increase the tracker's current spend by the given amount.
        
        Negative `spend` values are treated as zero and do not reduce `current_spend`.
        
        Parameters:
            spend (float): Amount to add to `current_spend`. Negative values are clamped to 0.
        """
        self.current_spend += _clamp_non_negative(spend)


@dataclass(frozen=True)
class CostUsageRecord:
    query_hash_sha256: str
    embedding_model: str
    llm_model: str
    embedding_tokens: int
    llm_prompt_tokens: int
    llm_completion_tokens: int
    embedding_cost_usd: float
    llm_cost_usd: float
    total_cost_usd: float
    rag_query_id: str | None = None
    degradation_mode: str = "none"
    route_reason: str | None = None
    metadata_json: str = "{}"
    created_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True)
class CostAlert:
    alert_type: str
    period: str
    threshold_ratio: float
    spend_usd: float
    budget_usd: float
    message: str
    metadata_json: str = "{}"
    created_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True)
class BudgetSnapshot:
    daily_budget: float
    weekly_budget: float
    daily_spend: float
    weekly_spend: float

    @property
    def daily_remaining(self) -> float:
        """
        Compute the remaining daily budget in USD.
        
        Returns:
            float: The remaining daily budget (daily_budget - daily_spend), clamped to a minimum of 0.0.
        """
        return max(0.0, self.daily_budget - self.daily_spend)

    @property
    def weekly_remaining(self) -> float:
        """
        Compute the remaining weekly budget in USD, clamped to zero.
        
        Returns:
            float: Remaining weekly budget in USD; `0.0` if weekly spend is greater than or equal to the weekly budget.
        """
        return max(0.0, self.weekly_budget - self.weekly_spend)

    @property
    def daily_remaining_ratio(self) -> float:
        """
        Fraction of the daily budget remaining as a value between 0.0 and 1.0.
        
        Returns:
            float: A value in [0.0, 1.0] representing the portion of the daily budget still available. Returns 0.0 when the configured daily budget is less than or equal to zero.
        """
        if self.daily_budget <= 0:
            return 0.0
        return max(0.0, min(1.0, self.daily_remaining / self.daily_budget))

    @property
    def weekly_remaining_ratio(self) -> float:
        """
        Compute the fraction of the weekly budget that remains, clamped to the range [0.0, 1.0].
        
        Returns:
            float: Ratio between 0.0 and 1.0 representing weekly_remaining divided by weekly_budget.
                   Returns 0.0 when `weekly_budget` is less than or equal to 0.
        """
        if self.weekly_budget <= 0:
            return 0.0
        return max(0.0, min(1.0, self.weekly_remaining / self.weekly_budget))


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    degraded: bool
    reason: str
    max_affordable_cost: float
    snapshot: BudgetSnapshot


@dataclass(frozen=True)
class ModelRoute:
    model: str
    complexity_score: float
    estimated_cost_usd: float
    degraded: bool
    blocked: bool
    reason: str


@dataclass(frozen=True)
class GovernancePlan:
    allowed: bool
    route: ModelRoute
    estimate: CostEstimate
    budget: BudgetDecision
    degradation_message: str | None = None


class CostRepository(Protocol):
    def record_usage(self, record: CostUsageRecord) -> None: """
Persist a cost usage event and update the manager's budget snapshot.

Persists the provided CostUsageRecord to the configured repository and refreshes the BudgetManager's cached snapshot so subsequent budget checks reflect the new spend.

Parameters:
    record (CostUsageRecord): The usage event to persist.
"""
...

    def sum_spend(self, window_start: datetime, window_end: datetime) -> float: """
Return the total USD spend recorded between the given window boundaries.

Parameters:
    window_start (datetime): Inclusive start of the time window in UTC.
    window_end (datetime): Exclusive end of the time window in UTC.

Returns:
    total_spend_usd (float): Sum of `total_cost_usd` for records in the window; `0.0` if no matching records or if an error occurs.
"""
...

    def record_alert(self, alert: CostAlert) -> None: """
Persist a CostAlert event to the repository storage.

Parameters:
    alert (CostAlert): The budget alert event to persist.

Notes:
    The implementation writes the alert to the underlying database. On database errors the transaction is rolled back and the error is logged.
"""
...


class SQLCostRepository:
    """Persist/query cost governance data via SQLAlchemy sessions."""

    _session_factory: Callable[[], Session]

    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        """
        Initialize the SQLCostRepository with a session factory used to create SQLAlchemy sessions.
        
        Parameters:
            session_factory (Callable[[], Session]): Factory that returns a new SQLAlchemy Session; defaults to SessionLocal.
        """
        self._session_factory = session_factory

    def record_usage(self, record: CostUsageRecord) -> None:
        """
        Persist a CostUsageRecord into the SQL `cost_usage_log` table.
        
        Inserts a new row using values from `record`. On database errors the transaction is rolled back and an error is logged; the method does not re-raise SQLAlchemy exceptions.
        
        Parameters:
            record (CostUsageRecord): The usage event to persist.
        """
        session = self._session_factory()
        try:
            _ = session.execute(
                text(
                    """
                    INSERT INTO cost_usage_log (
                        cost_usage_id,
                        rag_query_id,
                        query_hash_sha256,
                        embedding_model,
                        llm_model,
                        embedding_tokens,
                        llm_prompt_tokens,
                        llm_completion_tokens,
                        embedding_cost_usd,
                        llm_cost_usd,
                        total_cost_usd,
                        degradation_mode,
                        route_reason,
                        metadata_json,
                        created_at
                    ) VALUES (
                        :cost_usage_id,
                        :rag_query_id,
                        :query_hash_sha256,
                        :embedding_model,
                        :llm_model,
                        :embedding_tokens,
                        :llm_prompt_tokens,
                        :llm_completion_tokens,
                        :embedding_cost_usd,
                        :llm_cost_usd,
                        :total_cost_usd,
                        :degradation_mode,
                        :route_reason,
                        :metadata_json,
                        :created_at
                    )
                    """
                ),
                {
                    "cost_usage_id": str(uuid.uuid4()),
                    "rag_query_id": record.rag_query_id,
                    "query_hash_sha256": record.query_hash_sha256,
                    "embedding_model": record.embedding_model,
                    "llm_model": record.llm_model,
                    "embedding_tokens": int(record.embedding_tokens),
                    "llm_prompt_tokens": int(record.llm_prompt_tokens),
                    "llm_completion_tokens": int(record.llm_completion_tokens),
                    "embedding_cost_usd": float(record.embedding_cost_usd),
                    "llm_cost_usd": float(record.llm_cost_usd),
                    "total_cost_usd": float(record.total_cost_usd),
                    "degradation_mode": record.degradation_mode,
                    "route_reason": record.route_reason,
                    "metadata_json": record.metadata_json,
                    "created_at": record.created_at,
                },
            )
            session.commit()
        except SQLAlchemyError:
            session.rollback()
            logger.exception("Failed to persist cost usage record")
        finally:
            session.close()

    def sum_spend(self, window_start: datetime, window_end: datetime) -> float:
        """
        Compute the total USD spend recorded in cost_usage_log for the half-open interval [window_start, window_end).
        
        Parameters:
            window_start (datetime): Inclusive start of the time window (should match UTC-normalized created_at values).
            window_end (datetime): Exclusive end of the time window.
        
        Returns:
            float: Sum of total_cost_usd for records with created_at >= window_start and < window_end. Returns 0.0 if no records are found or if a database error occurs.
        """
        session = self._session_factory()
        try:
            raw_value = cast(
                float | int | None,
                session.execute(
                    text(
                        """
                        SELECT COALESCE(SUM(total_cost_usd), 0)
                        FROM cost_usage_log
                        WHERE created_at >= :window_start
                          AND created_at < :window_end
                        """
                    ),
                    {
                        "window_start": window_start,
                        "window_end": window_end,
                    },
                ).scalar_one(),
            )
            if raw_value is None:
                return 0.0
            return max(0.0, float(raw_value))
        except SQLAlchemyError:
            logger.exception("Failed to aggregate spend from cost_usage_log")
            return 0.0
        finally:
            session.close()

    def record_alert(self, alert: CostAlert) -> None:
        """
        Persist a CostAlert event into the SQL-backed cost_alert_event table.
        
        Inserts a new row using fields from `alert`, generates a UUID for `cost_alert_id`, commits the transaction on success, and rolls back while logging on SQL errors. This method swallows database exceptions and does not raise them.
        
        Parameters:
            alert (CostAlert): Alert event whose fields (alert_type, period, threshold_ratio, spend_usd, budget_usd, message, metadata_json, created_at) will be persisted.
        """
        session = self._session_factory()
        try:
            _ = session.execute(
                text(
                    """
                    INSERT INTO cost_alert_event (
                        cost_alert_id,
                        alert_type,
                        period,
                        threshold_ratio,
                        spend_usd,
                        budget_usd,
                        message,
                        metadata_json,
                        created_at
                    ) VALUES (
                        :cost_alert_id,
                        :alert_type,
                        :period,
                        :threshold_ratio,
                        :spend_usd,
                        :budget_usd,
                        :message,
                        :metadata_json,
                        :created_at
                    )
                    """
                ),
                {
                    "cost_alert_id": str(uuid.uuid4()),
                    "alert_type": alert.alert_type,
                    "period": alert.period,
                    "threshold_ratio": float(alert.threshold_ratio),
                    "spend_usd": float(alert.spend_usd),
                    "budget_usd": float(alert.budget_usd),
                    "message": alert.message,
                    "metadata_json": alert.metadata_json,
                    "created_at": alert.created_at,
                },
            )
            session.commit()
        except SQLAlchemyError:
            session.rollback()
            logger.exception("Failed to persist cost alert event")
        finally:
            session.close()


class CostEstimator:
    """Estimate embedding and LLM usage costs before execution."""

    embedding_price_per_1k: dict[str, float]
    llm_price_per_1k: dict[str, tuple[float, float]]
    chars_per_token: float
    default_completion_tokens: int
    default_embedding_price_per_1k: float
    default_llm_price_per_1k: tuple[float, float]

    def __init__(
        self,
        *,
        embedding_price_per_1k: dict[str, float] | None = None,
        llm_price_per_1k: dict[str, tuple[float, float]] | None = None,
        chars_per_token: float = 4.0,
        default_completion_tokens: int = 180,
        default_embedding_price_per_1k: float = 0.00002,
        default_llm_price_per_1k: tuple[float, float] = (0.0006, 0.0018),
    ) -> None:
        """
        Initialize estimator pricing and token heuristics for cost calculations.
        
        Parameters:
        	embedding_price_per_1k (dict[str, float] | None): Optional per-model embedding price in USD per 1,000 tokens; entries override built-in defaults.
        	llm_price_per_1k (dict[str, tuple[float, float]] | None): Optional per-model LLM prices as (input_price_per_1k_usd, output_price_per_1k_usd); entries override built-in defaults.
        	chars_per_token (float): Average characters per token used to estimate token counts from text.
        	default_completion_tokens (int): Default expected number of completion tokens when none are provided.
        	default_embedding_price_per_1k (float): Fallback embedding price in USD per 1,000 tokens used when a model price is not available.
        	default_llm_price_per_1k (tuple[float, float]): Fallback LLM prices as (input_price_per_1k_usd, output_price_per_1k_usd) used when a model price is not available.
        """
        self.embedding_price_per_1k = {
            "text-embedding-3-small": 0.00002,
            "text-embedding-3-large": 0.00013,
            **(embedding_price_per_1k or {}),
        }
        self.llm_price_per_1k = {
            "gpt-4o-mini": (0.00015, 0.0006),
            "gpt-4.1-mini": (0.0004, 0.0016),
            "gpt-4o": (0.0025, 0.0100),
            **(llm_price_per_1k or {}),
        }
        self.chars_per_token = max(1.0, float(chars_per_token))
        self.default_completion_tokens = max(1, int(default_completion_tokens))
        self.default_embedding_price_per_1k = _clamp_non_negative(
            default_embedding_price_per_1k
        )
        in_price, out_price = default_llm_price_per_1k
        self.default_llm_price_per_1k = (
            _clamp_non_negative(in_price),
            _clamp_non_negative(out_price),
        )

    def estimate_tokens(self, text_value: str) -> int:
        """
        Estimate the number of tokens for a given text using the estimator's character-to-token ratio.
        
        Parameters:
            text_value (str): The input text to estimate tokens for.
        
        Returns:
            int: Estimated token count. Returns 0 for empty or whitespace-only input; otherwise at least 1 token.
        """
        text_str = text_value.strip()
        if not text_str:
            return 0
        base = math.ceil(len(text_str) / self.chars_per_token)
        punctuation_bonus = text_str.count("\n") + text_str.count("?")
        return max(1, base + punctuation_bonus)

    def estimate_embedding_cost(
        self, texts: Sequence[str], model: str
    ) -> tuple[int, float]:
        """
        Estimate the total token usage and embedding cost for the given texts using the configured per-1k-token price for the specified model.
        
        Parameters:
            texts (Sequence[str]): Text inputs to be embedded.
            model (str): Embedding model name used to select the per-1k-token price.
        
        Returns:
            tuple[int, float]: A tuple of (token_count, embedding_cost_usd). `token_count` is the summed token estimate for all texts; `embedding_cost_usd` is the computed cost rounded to 10 decimal places.
        """
        token_count = sum(self.estimate_tokens(text_item) for text_item in texts)
        rate = self.embedding_price_per_1k.get(
            model, self.default_embedding_price_per_1k
        )
        cost = (token_count / 1000.0) * rate
        return token_count, round(cost, 10)

    def llm_cost_from_tokens(
        self,
        *,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> float:
        """
        Compute the LLM cost for given prompt and completion token counts using the configured per-1k-token rates.
        
        Parameters:
            model (str): Model identifier used to look up per-1k input/output rates; falls back to the estimator's default if missing.
            prompt_tokens (int): Number of prompt (input) tokens; negative values are treated as 0.
            completion_tokens (int): Number of completion (output) tokens; negative values are treated as 0.
        
        Returns:
            float: Total cost in USD for the provided token counts, rounded to 10 decimal places.
        """
        in_rate, out_rate = self.llm_price_per_1k.get(
            model, self.default_llm_price_per_1k
        )
        prompt_safe = max(0, int(prompt_tokens))
        completion_safe = max(0, int(completion_tokens))
        cost = ((prompt_safe / 1000.0) * in_rate) + (
            (completion_safe / 1000.0) * out_rate
        )
        return round(cost, 10)

    def estimate_llm_cost(
        self,
        *,
        prompt_text: str,
        model: str,
        expected_completion_tokens: int | None = None,
    ) -> tuple[int, int, float]:
        """
        Estimate token usage and cost for an LLM given a prompt and model.
        
        Parameters:
        	prompt_text (str): The prompt text to estimate tokens for.
        	model (str): The LLM model identifier used to compute cost rates.
        	expected_completion_tokens (int | None): Optional expected number of completion tokens; if None the estimator's default completion token count is used. If provided, values less than 1 are clamped to 1.
        
        Returns:
        	prompt_tokens (int): Estimated number of tokens in the prompt.
        	completion_tokens (int): Number of completion tokens to charge (either the provided expected value clamped to at least 1, or the estimator default).
        	llm_cost (float): Estimated LLM cost in USD for the prompt and completion token counts.
        """
        prompt_tokens = self.estimate_tokens(prompt_text)
        completion_tokens = (
            max(1, int(expected_completion_tokens))
            if expected_completion_tokens is not None
            else self.default_completion_tokens
        )
        llm_cost = self.llm_cost_from_tokens(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        return prompt_tokens, completion_tokens, llm_cost

    def estimate_query_cost(
        self,
        *,
        query: str,
        embedding_model: str,
        llm_model: str,
        expected_completion_tokens: int | None = None,
        prompt_context: str = "",
    ) -> CostEstimate:
        """
        Produce a pre-execution cost estimate for a single query, combining embedding and LLM prompt/completion cost estimates.
        
        Parameters:
            query (str): The user query text to estimate.
            embedding_model (str): The embedding model identifier used to estimate embedding tokens/cost.
            llm_model (str): The LLM model identifier used to estimate prompt/completion tokens and cost.
            expected_completion_tokens (int | None): Optional hint for expected completion token count; if omitted the estimator will choose a default.
            prompt_context (str): Optional additional context appended to the query when estimating LLM prompt tokens.
        
        Returns:
            CostEstimate: Dataclass containing:
                - embedding_model, llm_model
                - embedding_tokens, llm_prompt_tokens, llm_completion_tokens
                - embedding_cost_usd, llm_cost_usd
                - total_cost_usd (computed property)
        """
        embedding_tokens, embedding_cost = self.estimate_embedding_cost(
            [query],
            embedding_model,
        )
        prompt = query if not prompt_context else f"{query}\n\n{prompt_context}"
        prompt_tokens, completion_tokens, llm_cost = self.estimate_llm_cost(
            prompt_text=prompt,
            model=llm_model,
            expected_completion_tokens=expected_completion_tokens,
        )
        return CostEstimate(
            embedding_model=embedding_model,
            llm_model=llm_model,
            embedding_tokens=embedding_tokens,
            llm_prompt_tokens=prompt_tokens,
            llm_completion_tokens=completion_tokens,
            embedding_cost_usd=embedding_cost,
            llm_cost_usd=llm_cost,
        )


class BudgetManager:
    """Track spend, enforce daily/weekly caps, and emit budget alerts."""

    daily_budget: float
    weekly_budget: float
    repository: CostRepository
    clock: Callable[[], datetime]
    alert_sink: Callable[[CostAlert], None]
    alert_thresholds: tuple[float, ...]
    _emitted_alerts: set[tuple[str, str, float]]

    def __init__(
        self,
        *,
        daily_budget: float,
        weekly_budget: float,
        repository: CostRepository | None = None,
        alert_thresholds: Sequence[float] = (0.8, 0.9, 1.0),
        alert_sink: Callable[[CostAlert], None] | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        """
        Initialize a BudgetManager that enforces daily and weekly spend limits and emits alerts when thresholds are crossed.
        
        Parameters:
            daily_budget (float): Daily budget in USD; negative values are clamped to 0.
            weekly_budget (float): Weekly budget in USD; negative values are clamped to 0.
            repository (CostRepository | None): Persistence backend for usage and alerts. Defaults to an SQL-backed repository when None.
            alert_thresholds (Sequence[float]): Iterable of threshold ratios (each > 0 and <= 1.0) used to trigger alerts; values are deduplicated, rounded to three decimals, and sorted ascending.
            alert_sink (Callable[[CostAlert], None] | None): Callable invoked for each emitted alert. Defaults to the manager's internal logging sink when None.
            clock (Callable[[], datetime]): Function that returns the current datetime in UTC; used for timestamping snapshots and alerts. Defaults to _utc_now.
        """
        self.daily_budget = _clamp_non_negative(daily_budget)
        self.weekly_budget = _clamp_non_negative(weekly_budget)
        self.repository = repository or SQLCostRepository()
        self.clock = clock
        self.alert_sink = alert_sink or self._default_alert_sink
        self.alert_thresholds = tuple(
            sorted(
                {
                    round(value, 3)
                    for value in alert_thresholds
                    if value > 0 and value <= 1.0
                }
            )
        )
        self._emitted_alerts = set()

    def _default_alert_sink(self, alert: CostAlert) -> None:
        """
        Log a budget-related alert using the service's default alert sink.
        
        Parameters:
            alert (CostAlert): The alert event containing period, type, threshold ratio, spend, budget, and a human-readable message.
        """
        logger.warning(
            "cost alert [%s/%s] %.2f%% used (spend=$%.6f budget=$%.6f): %s",
            alert.period,
            alert.alert_type,
            alert.threshold_ratio * 100,
            alert.spend_usd,
            alert.budget_usd,
            alert.message,
        )

    def _usage_ratio(self, spend: float, budget: float) -> float:
        """
        Compute the ratio of spend to budget, clamped to a sensible range.
        
        Parameters:
            spend (float): Amount spent in the period.
            budget (float): Budget for the period.
        
        Returns:
            ratio (float): Value in [0.0, 1.0] representing spend / budget. If budget > 0, returns max(0.0, spend / budget). If budget <= 0, returns 1.0 when spend > 0, otherwise 0.0.
        """
        if budget <= 0:
            return 1.0 if spend > 0 else 0.0
        return max(0.0, spend / budget)

    def _emit_alerts(self, snapshot: BudgetSnapshot, at: datetime) -> None:
        """
        Emit budget alerts when spend crosses configured thresholds.
        
        Evaluates daily and weekly usage in the provided BudgetSnapshot against configured alert thresholds and, for each threshold crossed, creates and emits a CostAlert via the configured sink and persists it to the repository. Alerts are deduplicated per period (day or week) and threshold so the same alert is emitted only once for a given period-key and threshold. If no alert thresholds are configured, this method does nothing.
        
        Parameters:
            snapshot (BudgetSnapshot): Current budget and spend snapshot for daily and weekly windows.
            at (datetime): Reference UTC timestamp used to derive the period keys (start-of-day and start-of-week) included in emitted alerts.
        """
        if not self.alert_thresholds:
            return

        day_key = _start_of_day_utc(at).date().isoformat()
        week_key = _start_of_week_utc(at).date().isoformat()

        period_views = (
            ("daily", day_key, snapshot.daily_spend, snapshot.daily_budget),
            ("weekly", week_key, snapshot.weekly_spend, snapshot.weekly_budget),
        )

        for period, period_key, spend, budget in period_views:
            ratio = self._usage_ratio(spend, budget)
            for threshold in self.alert_thresholds:
                if ratio < threshold:
                    continue
                dedupe_key = (period, period_key, threshold)
                if dedupe_key in self._emitted_alerts:
                    continue

                alert_type = "budget_exceeded" if ratio >= 1.0 else "budget_threshold"
                message = (
                    f"{period.capitalize()} budget reached {ratio * 100:.1f}% "
                    f"(threshold {threshold * 100:.1f}%)."
                )
                alert = CostAlert(
                    alert_type=alert_type,
                    period=period,
                    threshold_ratio=threshold,
                    spend_usd=spend,
                    budget_usd=budget,
                    message=message,
                    metadata_json=json.dumps(
                        {"ratio": round(ratio, 6), "period_key": period_key},
                        ensure_ascii=True,
                        sort_keys=True,
                    ),
                    created_at=at,
                )
                self.alert_sink(alert)
                self.repository.record_alert(alert)
                self._emitted_alerts.add(dedupe_key)

    def snapshot(self, at: datetime | None = None) -> BudgetSnapshot:
        """
        Builds a BudgetSnapshot for the given time and emits any configured budget alerts.
        
        Parameters:
            at (datetime | None): Reference timestamp to compute the day/week windows. If omitted, the manager's clock is used.
        
        Returns:
            BudgetSnapshot: Snapshot containing daily and weekly budgets and the corresponding spend totals for the day and week.
        
        Notes:
            As a side effect, this method will evaluate alert thresholds for the snapshot and emit (and persist) any resulting budget alerts via the manager's configured alert sink and repository.
        """
        point_in_time = at or self.clock()
        day_start = _start_of_day_utc(point_in_time)
        week_start = _start_of_week_utc(point_in_time)

        daily_spend = self.repository.sum_spend(
            window_start=day_start,
            window_end=day_start + timedelta(days=1),
        )
        weekly_spend = self.repository.sum_spend(
            window_start=week_start,
            window_end=week_start + timedelta(days=7),
        )

        snapshot = BudgetSnapshot(
            daily_budget=self.daily_budget,
            weekly_budget=self.weekly_budget,
            daily_spend=daily_spend,
            weekly_spend=weekly_spend,
        )
        self._emit_alerts(snapshot, point_in_time)
        return snapshot

    def can_proceed(self, estimated_cost: float, at: datetime | None = None) -> bool:
        """
        Determine whether a proposed spend can be allowed under the current daily and weekly budgets.
        
        Parameters:
            estimated_cost (float): Proposed additional spend in USD; negative values are treated as zero.
            at (datetime | None): Reference time for computing the budget snapshot; if None, the current UTC time is used.
        
        Returns:
            bool: `True` if adding the estimated cost stays within both the daily and weekly budgets at `at`, `False` otherwise.
        """
        estimate = _clamp_non_negative(estimated_cost)
        snapshot = self.snapshot(at=at)
        daily_tracker = CostTracker(
            daily_budget=self.daily_budget,
            current_spend=snapshot.daily_spend,
        )
        weekly_ok = snapshot.weekly_spend + estimate <= self.weekly_budget
        return daily_tracker.can_proceed(estimate) and weekly_ok

    def evaluate(
        self,
        estimated_cost: float,
        *,
        at: datetime | None = None,
        snapshot: BudgetSnapshot | None = None,
    ) -> BudgetDecision:
        """
        Evaluate whether the given estimated cost can proceed against configured daily and weekly budgets and return a decision describing allowance, degradation, and affordability.
        
        Parameters:
            estimated_cost (float): Estimated total cost in USD (values are clamped to be >= 0).
            at (datetime | None): Optional reference time for budget evaluation; when omitted, the current UTC time is used.
            snapshot (BudgetSnapshot | None): Optional precomputed budget snapshot to use instead of querying the repository.
        
        Returns:
            BudgetDecision: Decision containing `allowed` (whether the cost may proceed), `degraded` (whether a degraded flow is required), `reason` (one of "within_budget", "budget_cap_near_exhausted", or "budget_exceeded"), `max_affordable_cost` (the largest cost still allowable in USD), and the `snapshot` used for the evaluation.
        """
        estimate = _clamp_non_negative(estimated_cost)
        current_snapshot = snapshot or self.snapshot(at=at)
        daily_tracker = CostTracker(
            daily_budget=self.daily_budget,
            current_spend=current_snapshot.daily_spend,
        )
        weekly_ok = current_snapshot.weekly_spend + estimate <= self.weekly_budget

        if daily_tracker.can_proceed(estimate) and weekly_ok:
            return BudgetDecision(
                allowed=True,
                degraded=False,
                reason="within_budget",
                max_affordable_cost=min(
                    current_snapshot.daily_remaining,
                    current_snapshot.weekly_remaining,
                ),
                snapshot=current_snapshot,
            )

        max_affordable_cost = min(
            current_snapshot.daily_remaining,
            current_snapshot.weekly_remaining,
        )
        if max_affordable_cost > 0.0:
            return BudgetDecision(
                allowed=True,
                degraded=True,
                reason="budget_cap_near_exhausted",
                max_affordable_cost=max_affordable_cost,
                snapshot=current_snapshot,
            )

        return BudgetDecision(
            allowed=False,
            degraded=True,
            reason="budget_exceeded",
            max_affordable_cost=0.0,
            snapshot=current_snapshot,
        )

    def record_usage(self, record: CostUsageRecord) -> None:
        """
        Persist a cost usage event and refresh the budget snapshot for the record's timestamp.
        
        Parameters:
            record (CostUsageRecord): Usage event to persist; its `created_at` timestamp is used to refresh the budget snapshot.
        """
        self.repository.record_usage(record)
        _ = self.snapshot(at=record.created_at)


class ModelRouter:
    """Route queries to model tiers using complexity and budget pressure."""

    COMPLEXITY_HINTS: tuple[str, ...] = (
        "compare",
        "contrast",
        "analyze",
        "synthesize",
        "derive",
        "evidence",
        "fiqh",
        "tafsir",
        "isnad",
        "context",
        "explain why",
        "step by step",
    )

    cheap_model: str
    standard_model: str
    expensive_model: str
    low_complexity_threshold: float
    high_complexity_threshold: float
    _tiers: list[str]

    def __init__(
        self,
        *,
        cheap_model: str = "gpt-4o-mini",
        standard_model: str = "gpt-4.1-mini",
        expensive_model: str = "gpt-4o",
        low_complexity_threshold: float = 0.35,
        high_complexity_threshold: float = 0.72,
    ) -> None:
        """
        Initialize a ModelRouter with tiered model names and complexity thresholds.
        
        Parameters:
            cheap_model (str): Model name used for low-complexity queries (lowest cost).
            standard_model (str): Model name used for medium-complexity queries.
            expensive_model (str): Model name used for high-complexity queries (highest capability/cost).
            low_complexity_threshold (float): Complexity score below this value maps to the cheap tier (expected in [0.0, 1.0]).
            high_complexity_threshold (float): Complexity score above this value maps to the expensive tier (expected in [0.0, 1.0]).
        """
        self.cheap_model = cheap_model
        self.standard_model = standard_model
        self.expensive_model = expensive_model
        self.low_complexity_threshold = low_complexity_threshold
        self.high_complexity_threshold = high_complexity_threshold
        self._tiers = [self.cheap_model, self.standard_model, self.expensive_model]

    def assess_complexity(self, query: str) -> float:
        """
        Estimate a complexity score for a user query to guide model routing.
        
        Parameters:
            query (str): The raw user query text to assess.
        
        Returns:
            float: A complexity score between 0.0 and 1.0 (higher means more complex), rounded to four decimal places. The score reflects query length, presence of complexity hint phrases, and structural cues such as questions or line breaks.
        """
        query_str = query.strip()
        if not query_str:
            return 0.0

        lower_query = query_str.lower()
        token_estimate = max(1.0, len(query_str) / 4.0)
        token_score = min(1.0, token_estimate / 180.0)

        hint_hits = sum(1 for hint in self.COMPLEXITY_HINTS if hint in lower_query)
        hint_score = min(0.6, hint_hits * 0.08)

        structure_score = min(
            0.25, (query_str.count("?") * 0.04) + (query_str.count("\n") * 0.05)
        )
        complexity = min(1.0, (0.45 * token_score) + hint_score + structure_score)
        return round(complexity, 4)

    def _base_tier_index(self, complexity_score: float) -> int:
        """
        Map a complexity score to a model tier index (0=cheap, 1=standard, 2=expensive).
        
        Parameters:
            complexity_score (float): Complexity score, typically in the range 0.0 to 1.0.
        
        Returns:
            int: Tier index — 0 for cheap, 1 for standard, 2 for expensive.
        """
        if complexity_score >= self.high_complexity_threshold:
            return 2
        if complexity_score >= self.low_complexity_threshold:
            return 1
        return 0

    def _candidate_order(self, base_index: int, budget_ratio: float) -> list[int]:
        """
        Builds an ordered list of tier indices to try for routing based on a preferred base tier and current budget pressure.
        
        Parameters:
            base_index (int): The preferred tier index (0 = cheapest, increasing = more expensive).
            budget_ratio (float): Remaining budget ratio in [0,1]; lower values bias selection toward cheaper tiers.
        
        Returns:
            list[int]: Tier indices in priority order to attempt. When budget_ratio <= 0.10 returns only [0]; when budget_ratio <= 0.25 the base index is lowered by one (if possible); otherwise the returned list starts from the (possibly adjusted) base, then lists cheaper tiers descending, then more expensive tiers ascending.
        """
        if budget_ratio <= 0.10:
            return [0]

        adjusted_base = base_index
        if budget_ratio <= 0.25 and adjusted_base > 0:
            adjusted_base -= 1

        ordered = [adjusted_base]
        for index in range(adjusted_base - 1, -1, -1):
            ordered.append(index)
        for index in range(adjusted_base + 1, len(self._tiers)):
            ordered.append(index)
        return ordered

    def route(
        self,
        *,
        query: str,
        estimator: CostEstimator,
        embedding_model: str,
        max_total_cost: float | None = None,
        budget_ratio: float = 1.0,
        expected_completion_tokens: int | None = None,
    ) -> ModelRoute:
        """
        Selects an appropriate model tier for a query based on complexity, budget guidance, and optional cost cap.
        
        Parameters:
            query (str): The user query to assess for complexity.
            estimator (CostEstimator): Estimates embedding and LLM costs for candidate models.
            embedding_model (str): Embedding model name used for cost estimation.
            max_total_cost (float | None): If set, candidate routes whose estimated total cost exceed this cap are rejected.
            budget_ratio (float): Multiplicative factor [0.0, ∞) biasing candidate selection toward cheaper tiers when < 1.0.
            expected_completion_tokens (int | None): Optional hint for expected LLM completion length used by the estimator.
        
        Returns:
            ModelRoute: Routing decision including chosen model, complexity score, estimated total cost in USD, degradation and blocking flags, and a textual reason.
        """
        complexity = self.assess_complexity(query)
        base_index = self._base_tier_index(complexity)
        base_model = self._tiers[base_index]
        candidates = self._candidate_order(base_index, max(0.0, budget_ratio))

        for tier_index in candidates:
            candidate_model = self._tiers[tier_index]
            estimate = estimator.estimate_query_cost(
                query=query,
                embedding_model=embedding_model,
                llm_model=candidate_model,
                expected_completion_tokens=expected_completion_tokens,
            )
            if max_total_cost is None or estimate.total_cost_usd <= max_total_cost:
                is_degraded = candidate_model != base_model
                reason = "complexity_match" if not is_degraded else "budget_pressure"
                return ModelRoute(
                    model=candidate_model,
                    complexity_score=complexity,
                    estimated_cost_usd=estimate.total_cost_usd,
                    degraded=is_degraded,
                    blocked=False,
                    reason=reason,
                )

        fallback_estimate = estimator.estimate_query_cost(
            query=query,
            embedding_model=embedding_model,
            llm_model=self.cheap_model,
            expected_completion_tokens=expected_completion_tokens,
        )
        return ModelRoute(
            model=self.cheap_model,
            complexity_score=complexity,
            estimated_cost_usd=fallback_estimate.total_cost_usd,
            degraded=True,
            blocked=True,
            reason="budget_exceeded",
        )


class CostGovernanceService:
    """High-level orchestration for estimate -> route -> enforce -> persist."""

    budget_manager: BudgetManager
    estimator: CostEstimator
    model_router: ModelRouter
    embedding_model: str
    budget_exceeded_message: str

    def __init__(
        self,
        *,
        budget_manager: BudgetManager,
        estimator: CostEstimator | None = None,
        model_router: ModelRouter | None = None,
        embedding_model: str = "text-embedding-3-small",
        budget_exceeded_message: str = (
            "Budget exceeded. Switched to low-cost mode; answer may be abbreviated."
        ),
    ) -> None:
        """
        Initialize the CostGovernanceService with required managers and configurable components.
        
        Parameters:
            budget_manager (BudgetManager): Manager responsible for budget snapshots, evaluation, alerting, and persisting usage.
            estimator (CostEstimator | None): Optional cost estimator used to produce embedding and LLM cost estimates; a default CostEstimator is created when omitted.
            model_router (ModelRouter | None): Optional router that selects model tiers based on query complexity and budget; a default ModelRouter is created when omitted.
            embedding_model (str): Default embedding model identifier used when estimating embeddings.
            budget_exceeded_message (str): Message used in governance plans when the budget is exceeded or the query is routed into a low-cost/degraded mode.
        """
        self.budget_manager = budget_manager
        self.estimator = estimator or CostEstimator()
        self.model_router = model_router or ModelRouter()
        self.embedding_model = embedding_model
        self.budget_exceeded_message = budget_exceeded_message

    def plan_query(
        self,
        *,
        query: str,
        at: datetime | None = None,
        expected_completion_tokens: int | None = None,
    ) -> GovernancePlan:
        """
        Constructs a governance plan for a query by selecting a model route, estimating costs, and evaluating budget constraints.
        
        Parameters:
            query (str): The user query to route and estimate.
            at (datetime | None): Reference time used for budget snapshot and evaluation; defaults to now when omitted.
            expected_completion_tokens (int | None): Hint for expected LLM completion token usage to improve cost estimation and routing decisions.
        
        Returns:
            GovernancePlan: A plan containing the chosen ModelRoute, CostEstimate, and BudgetDecision plus an optional degradation message. If the selected route is blocked or the budget evaluation disallows the request, the returned plan will have `allowed = False` and include a budget-exceeded degradation message.
        """
        snapshot = self.budget_manager.snapshot(at=at)
        remaining_budget = min(snapshot.daily_remaining, snapshot.weekly_remaining)
        budget_ratio = min(
            snapshot.daily_remaining_ratio, snapshot.weekly_remaining_ratio
        )

        route = self.model_router.route(
            query=query,
            estimator=self.estimator,
            embedding_model=self.embedding_model,
            max_total_cost=remaining_budget if remaining_budget > 0.0 else 0.0,
            budget_ratio=budget_ratio,
            expected_completion_tokens=expected_completion_tokens,
        )

        estimate = self.estimator.estimate_query_cost(
            query=query,
            embedding_model=self.embedding_model,
            llm_model=route.model,
            expected_completion_tokens=expected_completion_tokens,
        )
        decision = self.budget_manager.evaluate(
            estimate.total_cost_usd,
            at=at,
            snapshot=snapshot,
        )

        if route.blocked or not decision.allowed:
            return GovernancePlan(
                allowed=False,
                route=route,
                estimate=estimate,
                budget=decision,
                degradation_message=self.budget_exceeded_message,
            )

        degradation_message = None
        if route.degraded or decision.degraded:
            degradation_message = (
                "Budget pressure detected. Routing to a lower-cost model tier."
            )

        return GovernancePlan(
            allowed=True,
            route=route,
            estimate=estimate,
            budget=decision,
            degradation_message=degradation_message,
        )

    def record_usage(
        self,
        *,
        query: str,
        estimate: CostEstimate,
        route: ModelRoute,
        rag_query_id: str | None = None,
        actual_completion_tokens: int | None = None,
        metadata: dict[str, object] | None = None,
        at: datetime | None = None,
    ) -> CostUsageRecord:
        """
        Create a CostUsageRecord for a query, persist it via the BudgetManager, and return the record.
        
        Parameters:
            query: The original user query text; used to compute a SHA-256 hash for the record.
            estimate: Pre-computed CostEstimate describing embedding and LLM token counts and estimated embedding cost.
            route: The ModelRoute chosen for execution; its model and routing flags are recorded.
            rag_query_id: Optional external identifier linking this usage to a RAG/query lifecycle entry.
            actual_completion_tokens: If provided, overrides the estimated completion tokens and is used to compute the final LLM cost.
            metadata: Optional arbitrary metadata that will be JSON-serialized and stored with the record.
            at: Optional timestamp to use as the record's creation time; defaults to the current UTC time.
        
        Returns:
            The persisted CostUsageRecord representing the recorded usage event.
        """
        completion_tokens = (
            max(0, int(actual_completion_tokens))
            if actual_completion_tokens is not None
            else estimate.llm_completion_tokens
        )
        llm_cost = self.estimator.llm_cost_from_tokens(
            model=route.model,
            prompt_tokens=estimate.llm_prompt_tokens,
            completion_tokens=completion_tokens,
        )
        total_cost = round(estimate.embedding_cost_usd + llm_cost, 10)

        metadata_json = json.dumps(
            metadata or {},
            ensure_ascii=True,
            sort_keys=True,
        )
        query_hash = hashlib.sha256(query.strip().encode("utf-8")).hexdigest()
        recorded_at = at or _utc_now()

        record = CostUsageRecord(
            rag_query_id=rag_query_id,
            query_hash_sha256=query_hash,
            embedding_model=estimate.embedding_model,
            llm_model=route.model,
            embedding_tokens=estimate.embedding_tokens,
            llm_prompt_tokens=estimate.llm_prompt_tokens,
            llm_completion_tokens=completion_tokens,
            embedding_cost_usd=estimate.embedding_cost_usd,
            llm_cost_usd=llm_cost,
            total_cost_usd=total_cost,
            degradation_mode="budget" if route.degraded else "none",
            route_reason=route.reason,
            metadata_json=metadata_json,
            created_at=recorded_at,
        )
        self.budget_manager.record_usage(record)
        return record


__all__ = [
    "BudgetDecision",
    "BudgetManager",
    "BudgetSnapshot",
    "CostAlert",
    "CostEstimate",
    "CostEstimator",
    "CostGovernanceService",
    "CostRepository",
    "CostTracker",
    "CostUsageRecord",
    "GovernancePlan",
    "ModelRoute",
    "ModelRouter",
    "SQLCostRepository",
]
