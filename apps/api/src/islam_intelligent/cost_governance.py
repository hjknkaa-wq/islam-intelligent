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
    return datetime.now(tz=UTC)


def _clamp_non_negative(value: float) -> float:
    return max(0.0, float(value))


def _start_of_day_utc(at: datetime) -> datetime:
    normalized = at if at.tzinfo is not None else at.replace(tzinfo=UTC)
    normalized = normalized.astimezone(UTC)
    return datetime(
        normalized.year,
        normalized.month,
        normalized.day,
        tzinfo=UTC,
    )


def _start_of_week_utc(at: datetime) -> datetime:
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
        return round(self.embedding_cost_usd + self.llm_cost_usd, 10)


@dataclass
class CostTracker:
    daily_budget: float
    current_spend: float = 0.0

    def can_proceed(self, estimated_cost: float) -> bool:
        estimated = _clamp_non_negative(estimated_cost)
        return self.current_spend + estimated <= self.daily_budget

    def add_spend(self, spend: float) -> None:
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
        return max(0.0, self.daily_budget - self.daily_spend)

    @property
    def weekly_remaining(self) -> float:
        return max(0.0, self.weekly_budget - self.weekly_spend)

    @property
    def daily_remaining_ratio(self) -> float:
        if self.daily_budget <= 0:
            return 0.0
        return max(0.0, min(1.0, self.daily_remaining / self.daily_budget))

    @property
    def weekly_remaining_ratio(self) -> float:
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
    def record_usage(self, record: CostUsageRecord) -> None: ...

    def sum_spend(self, window_start: datetime, window_end: datetime) -> float: ...

    def record_alert(self, alert: CostAlert) -> None: ...


class SQLCostRepository:
    """Persist/query cost governance data via SQLAlchemy sessions."""

    _session_factory: Callable[[], Session]

    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    def record_usage(self, record: CostUsageRecord) -> None:
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
        text_str = text_value.strip()
        if not text_str:
            return 0
        base = math.ceil(len(text_str) / self.chars_per_token)
        punctuation_bonus = text_str.count("\n") + text_str.count("?")
        return max(1, base + punctuation_bonus)

    def estimate_embedding_cost(
        self, texts: Sequence[str], model: str
    ) -> tuple[int, float]:
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
        if budget <= 0:
            return 1.0 if spend > 0 else 0.0
        return max(0.0, spend / budget)

    def _emit_alerts(self, snapshot: BudgetSnapshot, at: datetime) -> None:
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
        self.cheap_model = cheap_model
        self.standard_model = standard_model
        self.expensive_model = expensive_model
        self.low_complexity_threshold = low_complexity_threshold
        self.high_complexity_threshold = high_complexity_threshold
        self._tiers = [self.cheap_model, self.standard_model, self.expensive_model]

    def assess_complexity(self, query: str) -> float:
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
        if complexity_score >= self.high_complexity_threshold:
            return 2
        if complexity_score >= self.low_complexity_threshold:
            return 1
        return 0

    def _candidate_order(self, base_index: int, budget_ratio: float) -> list[int]:
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
