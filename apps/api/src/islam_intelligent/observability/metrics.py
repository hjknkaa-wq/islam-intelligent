"""Observability and RAGAS-style metrics for RAG pipeline executions.

This module provides:
- Per-query metric payload storage into ``rag_metrics_log``
- RAGAS metric calculation helpers (faithfulness, relevancy, precision, recall)
- Dashboard aggregates (queries/day, latency, abstention rate, cost)
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..db.engine import SessionLocal

logger = logging.getLogger(__name__)
UTC = timezone.utc
_TOKEN_PATTERN = re.compile(r"[a-z0-9']+")


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _clamp_01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _tokenize(text_value: str) -> set[str]:
    return set(_TOKEN_PATTERN.findall(text_value.lower()))


def _jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    intersection = len(left & right)
    union = len(left | right)
    if union == 0:
        return 0.0
    return intersection / union


def _coerce_faithfulness(raw_score: float | None) -> float:
    if raw_score is None:
        return 0.0
    score = float(raw_score)
    if score > 1.0:
        score = score / 10.0
    return _clamp_01(score)


def _extract_retrieved_id(item: Mapping[str, object]) -> str | None:
    evidence_span_id = item.get("evidence_span_id")
    if isinstance(evidence_span_id, str) and evidence_span_id.strip():
        return evidence_span_id.strip()
    text_unit_id = item.get("text_unit_id")
    if isinstance(text_unit_id, str) and text_unit_id.strip():
        return text_unit_id.strip()
    return None


def _extract_citation_id(citation: object) -> str | None:
    if not isinstance(citation, Mapping):
        return None
    citation_id = citation.get("evidence_span_id")
    if isinstance(citation_id, str) and citation_id.strip():
        return citation_id.strip()
    return None


@dataclass(frozen=True)
class RagasScores:
    """RAGAS-like metrics represented on 0..1 scale."""

    faithfulness: float = 0.0
    relevancy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "faithfulness": self.faithfulness,
            "relevancy": self.relevancy,
            "precision": self.precision,
            "recall": self.recall,
        }


def compute_ragas_metrics(
    *,
    query: str,
    statements: Sequence[Mapping[str, object]],
    retrieved: Sequence[Mapping[str, object]],
    faithfulness_score: float | None = None,
) -> RagasScores:
    """Compute deterministic RAGAS-style metrics from pipeline artifacts.

    The implementation is intentionally deterministic and lightweight so it can run
    in CI/local environments without requiring external judge APIs.
    """

    query_tokens = _tokenize(query)

    relevancy_components: list[float] = []
    cited_ids: set[str] = set()
    for statement in statements:
        statement_text_raw = statement.get("text")
        statement_text = (
            str(statement_text_raw).strip()
            if isinstance(statement_text_raw, str)
            else ""
        )
        statement_tokens = _tokenize(statement_text)
        relevancy_components.append(_jaccard_similarity(query_tokens, statement_tokens))

        citations_raw = statement.get("citations")
        if isinstance(citations_raw, Sequence) and not isinstance(
            citations_raw, str | bytes
        ):
            for citation in citations_raw:
                citation_id = _extract_citation_id(citation)
                if citation_id:
                    cited_ids.add(citation_id)

    retrieved_ids: set[str] = {
        candidate_id
        for item in retrieved
        if (candidate_id := _extract_retrieved_id(item)) is not None
    }
    matched_ids = cited_ids & retrieved_ids

    precision = len(matched_ids) / len(cited_ids) if cited_ids else 0.0
    recall = len(matched_ids) / len(retrieved_ids) if retrieved_ids else 0.0
    relevancy = (
        sum(relevancy_components) / len(relevancy_components)
        if relevancy_components
        else 0.0
    )

    faithfulness = _coerce_faithfulness(faithfulness_score)
    if faithfulness_score is None and cited_ids:
        faithfulness = _clamp_01(precision)

    return RagasScores(
        faithfulness=round(faithfulness, 4),
        relevancy=round(_clamp_01(relevancy), 4),
        precision=round(_clamp_01(precision), 4),
        recall=round(_clamp_01(recall), 4),
    )


@dataclass(frozen=True)
class QueryMetricsPayload:
    """Persistable per-query metrics payload."""

    query_id: str
    query_text: str
    verdict: str
    total_latency_ms: float

    pipeline_start_time: datetime | None = None
    pipeline_end_time: datetime | None = None
    retrieval_metrics_json: str = "{}"
    generation_metrics_json: str = "{}"
    verification_metrics_json: str = "{}"
    abstain_reason: str | None = None
    error_type: str | None = None

    cost_estimate_usd: float = 0.0
    cost_actual_usd: float = 0.0
    cost_governance_applied: bool = False

    ragas: RagasScores = field(default_factory=RagasScores)
    created_at: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True)
class DashboardDataPoint:
    """One daily dashboard row."""

    day: date
    queries_per_day: int
    avg_latency_ms: float
    abstention_rate: float
    total_cost_usd: float


@dataclass(frozen=True)
class DashboardSummary:
    """Window-level dashboard summary."""

    total_queries: int
    avg_latency_ms: float
    abstention_rate: float
    total_cost_usd: float
    daily: tuple[DashboardDataPoint, ...]


class ObservabilityStore(Protocol):
    """Storage protocol for observability records."""

    def record_query_metrics(self, payload: QueryMetricsPayload) -> None: ...

    def load_dashboard_data(
        self, window_days: int = 30
    ) -> list[DashboardDataPoint]: ...

    def load_dashboard_summary(self, window_days: int = 30) -> DashboardSummary: ...


class SQLObservabilityStore:
    """SQL-backed observability storage implementation."""

    _session_factory: Callable[[], Session]

    def __init__(
        self,
        session_factory: Callable[[], Session] = SessionLocal,
    ) -> None:
        self._session_factory = session_factory

    def record_query_metrics(self, payload: QueryMetricsPayload) -> None:
        session = self._session_factory()
        try:
            _ = session.execute(
                text(
                    """
                    INSERT INTO rag_metrics_log (
                        metrics_id,
                        query_id,
                        query_text,
                        pipeline_start_time,
                        pipeline_end_time,
                        total_latency_ms,
                        retrieval_metrics,
                        generation_metrics,
                        verification_metrics,
                        ragas_faithfulness,
                        ragas_relevancy,
                        ragas_precision,
                        ragas_recall,
                        verdict,
                        abstain_reason,
                        error_type,
                        cost_estimate_usd,
                        cost_actual_usd,
                        cost_governance_applied,
                        created_at
                    ) VALUES (
                        :metrics_id,
                        :query_id,
                        :query_text,
                        :pipeline_start_time,
                        :pipeline_end_time,
                        :total_latency_ms,
                        :retrieval_metrics,
                        :generation_metrics,
                        :verification_metrics,
                        :ragas_faithfulness,
                        :ragas_relevancy,
                        :ragas_precision,
                        :ragas_recall,
                        :verdict,
                        :abstain_reason,
                        :error_type,
                        :cost_estimate_usd,
                        :cost_actual_usd,
                        :cost_governance_applied,
                        :created_at
                    )
                    """
                ),
                {
                    "metrics_id": str(uuid.uuid4()),
                    "query_id": payload.query_id,
                    "query_text": payload.query_text[:1000],
                    "pipeline_start_time": payload.pipeline_start_time,
                    "pipeline_end_time": payload.pipeline_end_time,
                    "total_latency_ms": max(0.0, float(payload.total_latency_ms)),
                    "retrieval_metrics": payload.retrieval_metrics_json,
                    "generation_metrics": payload.generation_metrics_json,
                    "verification_metrics": payload.verification_metrics_json,
                    "ragas_faithfulness": payload.ragas.faithfulness,
                    "ragas_relevancy": payload.ragas.relevancy,
                    "ragas_precision": payload.ragas.precision,
                    "ragas_recall": payload.ragas.recall,
                    "verdict": payload.verdict,
                    "abstain_reason": payload.abstain_reason,
                    "error_type": payload.error_type,
                    "cost_estimate_usd": max(0.0, float(payload.cost_estimate_usd)),
                    "cost_actual_usd": max(0.0, float(payload.cost_actual_usd)),
                    "cost_governance_applied": payload.cost_governance_applied,
                    "created_at": payload.created_at,
                },
            )
            session.commit()
        except SQLAlchemyError:
            session.rollback()
            logger.exception("Failed to persist query metrics")
        finally:
            session.close()

    def load_dashboard_data(self, window_days: int = 30) -> list[DashboardDataPoint]:
        if window_days <= 0:
            return []

        window_start = _utc_now() - timedelta(days=window_days)
        session = self._session_factory()
        try:
            rows = session.execute(
                text(
                    """
                    SELECT
                        DATE(created_at) AS day,
                        COUNT(*) AS queries_per_day,
                        COALESCE(AVG(total_latency_ms), 0) AS avg_latency_ms,
                        COALESCE(AVG(CASE WHEN verdict = 'abstain' THEN 1.0 ELSE 0.0 END), 0) AS abstention_rate,
                        COALESCE(SUM(cost_actual_usd), 0) AS total_cost_usd
                    FROM rag_metrics_log
                    WHERE created_at >= :window_start
                    GROUP BY DATE(created_at)
                    ORDER BY day ASC
                    """
                ),
                {"window_start": window_start},
            ).mappings()

            points: list[DashboardDataPoint] = []
            for row in rows:
                raw_day = row["day"]
                day_value = raw_day
                if isinstance(raw_day, str):
                    day_value = datetime.fromisoformat(raw_day).date()
                elif isinstance(raw_day, datetime):
                    day_value = raw_day.date()
                if not isinstance(day_value, date):
                    continue

                points.append(
                    DashboardDataPoint(
                        day=day_value,
                        queries_per_day=int(row["queries_per_day"]),
                        avg_latency_ms=float(row["avg_latency_ms"]),
                        abstention_rate=float(row["abstention_rate"]),
                        total_cost_usd=float(row["total_cost_usd"]),
                    )
                )
            return points
        except SQLAlchemyError:
            logger.exception("Failed to load dashboard data")
            return []
        finally:
            session.close()

    def load_dashboard_summary(self, window_days: int = 30) -> DashboardSummary:
        if window_days <= 0:
            return DashboardSummary(
                total_queries=0,
                avg_latency_ms=0.0,
                abstention_rate=0.0,
                total_cost_usd=0.0,
                daily=(),
            )

        daily_points = tuple(self.load_dashboard_data(window_days=window_days))
        window_start = _utc_now() - timedelta(days=window_days)

        session = self._session_factory()
        try:
            row = (
                session.execute(
                    text(
                        """
                    SELECT
                        COUNT(*) AS total_queries,
                        COALESCE(AVG(total_latency_ms), 0) AS avg_latency_ms,
                        COALESCE(AVG(CASE WHEN verdict = 'abstain' THEN 1.0 ELSE 0.0 END), 0) AS abstention_rate,
                        COALESCE(SUM(cost_actual_usd), 0) AS total_cost_usd
                    FROM rag_metrics_log
                    WHERE created_at >= :window_start
                    """
                    ),
                    {"window_start": window_start},
                )
                .mappings()
                .one()
            )

            return DashboardSummary(
                total_queries=int(row["total_queries"]),
                avg_latency_ms=float(row["avg_latency_ms"]),
                abstention_rate=float(row["abstention_rate"]),
                total_cost_usd=float(row["total_cost_usd"]),
                daily=daily_points,
            )
        except SQLAlchemyError:
            logger.exception("Failed to load dashboard summary")
            return DashboardSummary(
                total_queries=0,
                avg_latency_ms=0.0,
                abstention_rate=0.0,
                total_cost_usd=0.0,
                daily=daily_points,
            )
        finally:
            session.close()


__all__ = [
    "DashboardDataPoint",
    "DashboardSummary",
    "ObservabilityStore",
    "QueryMetricsPayload",
    "RagasScores",
    "SQLObservabilityStore",
    "compute_ragas_metrics",
]
