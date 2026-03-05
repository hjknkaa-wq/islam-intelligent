"""Unit tests for cost governance controls."""

from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportUntypedBaseClass=false, reportMissingSuperCall=false, reportUnusedImport=false, reportAny=false, reportUnusedCallResult=false

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from islam_intelligent.cost_governance import (
    BudgetManager,
    CostAlert,
    CostEstimator,
    CostGovernanceService,
    CostRepository,
    CostUsageRecord,
    ModelRouter,
    SQLCostRepository,
)

UTC = timezone.utc


@dataclass
class InMemoryCostRepository(CostRepository):
    usage_records: list[CostUsageRecord]
    alert_records: list[CostAlert]

    def __init__(self) -> None:
        """
        Initialize an in-memory cost repository with empty storage for usage and alert records.
        
        The instance will hold:
        - `usage_records`: a list of recorded CostUsageRecord entries.
        - `alert_records`: a list of emitted CostAlert entries.
        """
        self.usage_records = []
        self.alert_records = []

    def record_usage(self, record: CostUsageRecord) -> None:
        """
        Append a cost usage record to the in-memory repository.
        
        Parameters:
            record (CostUsageRecord): The usage record to store; its fields describe tokens, costs, models, timestamps, and metadata.
        """
        self.usage_records.append(record)

    def sum_spend(self, window_start: datetime, window_end: datetime) -> float:
        """
        Calculate the total recorded cost in USD for usage records whose timestamps fall within the given time window.
        
        Parameters:
            window_start (datetime): Inclusive lower bound of the time window.
            window_end (datetime): Exclusive upper bound of the time window.
        
        Returns:
            float: Sum of `total_cost_usd` for records with `created_at` >= `window_start` and < `window_end`.
        """
        total = 0.0
        for record in self.usage_records:
            if window_start <= record.created_at < window_end:
                total += record.total_cost_usd
        return total

    def record_alert(self, alert: CostAlert) -> None:
        """
        Record a cost alert in the in-memory repository.
        
        Parameters:
            alert (CostAlert): Alert event to persist; will be appended to the repository's alert list.
        """
        self.alert_records.append(alert)


def _usage_record(total_cost: float, at: datetime) -> CostUsageRecord:
    """
    Constructs a deterministic CostUsageRecord prefilled with test values.
    
    Parameters:
        total_cost (float): Total cost in USD to assign to the record's `total_cost_usd`.
        at (datetime): Timestamp to assign to the record's `created_at`.
    
    Returns:
        CostUsageRecord: A record with fixed identifiers and models, `embedding_cost_usd` set to 0.01, `llm_cost_usd` set to `max(0.0, total_cost - 0.01)`, and `total_cost_usd` equal to `total_cost`.
    """
    return CostUsageRecord(
        rag_query_id=None,
        query_hash_sha256="a" * 64,
        embedding_model="text-embedding-3-small",
        llm_model="gpt-4o-mini",
        embedding_tokens=10,
        llm_prompt_tokens=10,
        llm_completion_tokens=10,
        embedding_cost_usd=0.01,
        llm_cost_usd=max(0.0, total_cost - 0.01),
        total_cost_usd=total_cost,
        degradation_mode="none",
        route_reason="test",
        created_at=at,
    )


def test_cost_estimator_tracks_embedding_and_llm_components() -> None:
    estimator = CostEstimator(
        embedding_price_per_1k={"embedding-test": 0.001},
        llm_price_per_1k={"llm-test": (0.01, 0.02)},
        chars_per_token=4.0,
        default_completion_tokens=20,
    )

    estimate = estimator.estimate_query_cost(
        query="x" * 40,
        embedding_model="embedding-test",
        llm_model="llm-test",
        expected_completion_tokens=20,
    )

    assert estimate.embedding_tokens == 10
    assert estimate.llm_prompt_tokens == 10
    assert estimate.llm_completion_tokens == 20
    assert estimate.embedding_cost_usd == pytest.approx(0.00001)
    assert estimate.llm_cost_usd == pytest.approx(0.0005)
    assert estimate.total_cost_usd == pytest.approx(0.00051)


def test_budget_manager_enforces_daily_and_weekly_caps() -> None:
    now = datetime(2026, 3, 5, 12, 0, tzinfo=UTC)
    repo = InMemoryCostRepository()
    repo.record_usage(_usage_record(4.5, now))
    repo.record_usage(_usage_record(4.5, now - timedelta(days=1)))

    manager = BudgetManager(daily_budget=5.0, weekly_budget=10.0, repository=repo)

    assert manager.can_proceed(0.4, at=now) is True
    assert manager.can_proceed(0.7, at=now) is False

    decision = manager.evaluate(0.7, at=now)
    assert decision.allowed is True
    assert decision.degraded is True
    assert decision.reason == "budget_cap_near_exhausted"
    assert decision.max_affordable_cost == pytest.approx(0.5)


def test_budget_exceeded_returns_graceful_degradation_plan() -> None:
    """
    Test that the governance service returns a blocked degradation plan when the daily and weekly budgets are exhausted.
    
    Sets up prior spend equal to the configured budgets, calls CostGovernanceService.plan_query, and verifies the returned plan is disallowed, the chosen route is blocked, and the degradation message indicates "Budget exceeded".
    """
    now = datetime(2026, 3, 5, 12, 0, tzinfo=UTC)
    repo = InMemoryCostRepository()
    repo.record_usage(_usage_record(1.0, now))

    manager = BudgetManager(daily_budget=1.0, weekly_budget=1.0, repository=repo)
    service = CostGovernanceService(
        budget_manager=manager,
        estimator=CostEstimator(default_completion_tokens=20),
    )

    plan = service.plan_query(query="How do I perform tahajjud prayer?", at=now)

    assert plan.allowed is False
    assert plan.route.blocked is True
    assert plan.degradation_message is not None
    assert "Budget exceeded" in plan.degradation_message


def test_budget_alerting_logs_once_per_threshold_period() -> None:
    now = datetime(2026, 3, 5, 12, 0, tzinfo=UTC)
    repo = InMemoryCostRepository()
    repo.record_usage(_usage_record(8.0, now))

    emitted: list[CostAlert] = []

    manager = BudgetManager(
        daily_budget=10.0,
        weekly_budget=100.0,
        repository=repo,
        alert_thresholds=(0.8, 1.0),
        alert_sink=emitted.append,
    )

    _ = manager.snapshot(at=now)
    _ = manager.snapshot(at=now + timedelta(minutes=30))
    assert len(emitted) == 1
    assert len(repo.alert_records) == 1
    assert emitted[0].period == "daily"
    assert emitted[0].threshold_ratio == 0.8

    repo.record_usage(_usage_record(3.0, now + timedelta(minutes=45)))
    _ = manager.snapshot(at=now + timedelta(hours=1))
    assert len(emitted) == 2
    assert emitted[-1].alert_type == "budget_exceeded"
    assert emitted[-1].threshold_ratio == 1.0


def test_model_router_uses_complexity_and_budget_pressure() -> None:
    estimator = CostEstimator(default_completion_tokens=50)
    router = ModelRouter(
        cheap_model="cheap-model",
        standard_model="standard-model",
        expensive_model="expensive-model",
        low_complexity_threshold=0.3,
        high_complexity_threshold=0.7,
    )

    simple_route = router.route(
        query="What is zakat?",
        estimator=estimator,
        embedding_model="text-embedding-3-small",
        budget_ratio=1.0,
    )

    complex_route = router.route(
        query=(
            "Compare and synthesize the evidence from Quran and hadith, then analyze "
            "the fiqh context with step by step reasoning and explain why scholarly "
            "opinions differ in practice."
        ),
        estimator=estimator,
        embedding_model="text-embedding-3-small",
        budget_ratio=1.0,
    )

    constrained_route = router.route(
        query=(
            "Compare and synthesize the evidence from Quran and hadith, then analyze "
            "the fiqh context with step by step reasoning and explain why scholarly "
            "opinions differ in practice."
        ),
        estimator=estimator,
        embedding_model="text-embedding-3-small",
        budget_ratio=0.2,
    )

    assert simple_route.model == "cheap-model"
    assert complex_route.model == "expensive-model"
    assert constrained_route.model == "standard-model"
    assert constrained_route.degraded is True


def test_sql_repository_persists_usage_and_alert_rows() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE cost_usage_log (
                cost_usage_id TEXT PRIMARY KEY,
                rag_query_id TEXT,
                query_hash_sha256 TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                llm_model TEXT NOT NULL,
                embedding_tokens INTEGER NOT NULL,
                llm_prompt_tokens INTEGER NOT NULL,
                llm_completion_tokens INTEGER NOT NULL,
                embedding_cost_usd REAL NOT NULL,
                llm_cost_usd REAL NOT NULL,
                total_cost_usd REAL NOT NULL,
                degradation_mode TEXT NOT NULL,
                route_reason TEXT,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE cost_alert_event (
                cost_alert_id TEXT PRIMARY KEY,
                alert_type TEXT NOT NULL,
                period TEXT NOT NULL,
                threshold_ratio REAL NOT NULL,
                spend_usd REAL NOT NULL,
                budget_usd REAL NOT NULL,
                message TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

    session_factory = sessionmaker(bind=engine, future=True)
    repository = SQLCostRepository(session_factory=session_factory)

    recorded_at = datetime(2026, 3, 5, 8, 0, tzinfo=UTC)
    usage = CostUsageRecord(
        rag_query_id="query-1",
        query_hash_sha256="b" * 64,
        embedding_model="text-embedding-3-small",
        llm_model="gpt-4o-mini",
        embedding_tokens=120,
        llm_prompt_tokens=80,
        llm_completion_tokens=40,
        embedding_cost_usd=0.01,
        llm_cost_usd=0.41,
        total_cost_usd=0.42,
        degradation_mode="none",
        route_reason="complexity_match",
        metadata_json="{}",
        created_at=recorded_at,
    )
    repository.record_usage(usage)

    daily_total = repository.sum_spend(
        window_start=datetime(2026, 3, 5, 0, 0, tzinfo=UTC),
        window_end=datetime(2026, 3, 6, 0, 0, tzinfo=UTC),
    )
    assert daily_total == pytest.approx(0.42)

    alert = CostAlert(
        alert_type="budget_threshold",
        period="daily",
        threshold_ratio=0.8,
        spend_usd=0.42,
        budget_usd=1.0,
        message="Daily budget reached 42%.",
        metadata_json="{}",
        created_at=recorded_at,
    )
    repository.record_alert(alert)

    session = session_factory()
    try:
        usage_count = session.execute(
            text("SELECT COUNT(*) FROM cost_usage_log")
        ).scalar_one()
        alert_count = session.execute(
            text("SELECT COUNT(*) FROM cost_alert_event")
        ).scalar_one()
    finally:
        session.close()

    assert usage_count == 1
    assert alert_count == 1


def test_service_records_per_query_costs_in_repository() -> None:
    """
    Verifies that CostGovernanceService records per-query usage into the repository with metadata and a non-negative total cost.
    
    Asserts that planning a query is allowed, that recording usage appends a CostUsageRecord to the repository with the provided rag_query_id, that the recorded metadata contains the original request identifier, and that the recorded total_cost_usd is greater than or equal to 0.0.
    """
    now = datetime(2026, 3, 5, 12, 0, tzinfo=UTC)
    repo = InMemoryCostRepository()
    manager = BudgetManager(daily_budget=20.0, weekly_budget=50.0, repository=repo)
    estimator = CostEstimator(default_completion_tokens=30)
    service = CostGovernanceService(budget_manager=manager, estimator=estimator)

    plan = service.plan_query(query="Explain wudu briefly.", at=now)
    assert plan.allowed is True

    recorded = service.record_usage(
        query="Explain wudu briefly.",
        estimate=plan.estimate,
        route=plan.route,
        rag_query_id="query-abc",
        metadata={"request_id": "req-123"},
        at=now,
    )

    assert len(repo.usage_records) == 1
    assert repo.usage_records[0].rag_query_id == "query-abc"
    assert "request_id" in recorded.metadata_json
    assert recorded.total_cost_usd >= 0.0
