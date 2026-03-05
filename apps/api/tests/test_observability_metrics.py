"""Unit tests for observability and RAGAS metrics."""

from __future__ import annotations

# pyright: reportMissingImports=false

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from islam_intelligent.observability.metrics import (
    QueryMetricsPayload,
    RagasScores,
    SQLObservabilityStore,
    compute_ragas_metrics,
)
from islam_intelligent.rag.pipeline.core import RAGConfig, RAGPipeline

UTC = timezone.utc


def test_compute_ragas_metrics_tracks_core_scores() -> None:
    scores = compute_ragas_metrics(
        query="What does Islam teach about zakat?",
        statements=[
            {
                "text": "Zakat is an obligation and a pillar of Islam.",
                "citations": [
                    {"evidence_span_id": "es_1"},
                    {"evidence_span_id": "es_2"},
                ],
            }
        ],
        retrieved=[
            {"evidence_span_id": "es_1", "snippet": "..."},
            {"evidence_span_id": "es_3", "snippet": "..."},
        ],
        faithfulness_score=8.0,
    )

    assert scores.faithfulness == 0.8
    assert scores.precision == 0.5
    assert scores.recall == 0.5
    assert 0.0 <= scores.relevancy <= 1.0


def test_compute_ragas_metrics_handles_empty_inputs() -> None:
    scores = compute_ragas_metrics(query="", statements=[], retrieved=[])

    assert scores.faithfulness == 0.0
    assert scores.relevancy == 0.0
    assert scores.precision == 0.0
    assert scores.recall == 0.0


def test_sql_observability_store_persists_and_aggregates_dashboard() -> None:
    """
    Verify SQLObservabilityStore persists metrics and correctly aggregates dashboard data.
    
    Creates an in-memory SQLite table, records two query metrics (one answer and one abstain) with distinct RAGAS scores and costs, then asserts:
    - two rows exist and the stored max/min RAGAS faithfulness match the inputs,
    - daily dashboard data for a 30-day window contains one day with correct queries per day, average latency, abstention rate, and total cost,
    - dashboard summary aggregates total queries, average latency, abstention rate, and total cost as expected.
    """
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE rag_metrics_log (
                metrics_id TEXT PRIMARY KEY,
                query_id TEXT NOT NULL,
                query_text TEXT NOT NULL,
                pipeline_start_time TEXT,
                pipeline_end_time TEXT,
                total_latency_ms REAL NOT NULL,
                retrieval_metrics TEXT NOT NULL,
                generation_metrics TEXT NOT NULL,
                verification_metrics TEXT NOT NULL,
                ragas_faithfulness REAL,
                ragas_relevancy REAL,
                ragas_precision REAL,
                ragas_recall REAL,
                verdict TEXT NOT NULL,
                abstain_reason TEXT,
                error_type TEXT,
                cost_estimate_usd REAL NOT NULL,
                cost_actual_usd REAL NOT NULL,
                cost_governance_applied INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

    session_factory = sessionmaker(bind=engine, future=True)
    store = SQLObservabilityStore(session_factory=session_factory)
    created_at = datetime(2026, 3, 5, 8, 0, tzinfo=UTC)

    store.record_query_metrics(
        QueryMetricsPayload(
            query_id="q-1",
            query_text="query 1",
            verdict="answer",
            total_latency_ms=120.0,
            cost_actual_usd=0.1,
            ragas=RagasScores(
                faithfulness=0.9, relevancy=0.8, precision=1.0, recall=0.7
            ),
            created_at=created_at,
        )
    )
    store.record_query_metrics(
        QueryMetricsPayload(
            query_id="q-2",
            query_text="query 2",
            verdict="abstain",
            total_latency_ms=80.0,
            cost_actual_usd=0.2,
            ragas=RagasScores(
                faithfulness=0.0, relevancy=0.0, precision=0.0, recall=0.0
            ),
            created_at=created_at,
        )
    )

    session = session_factory()
    try:
        row = session.execute(
            text(
                "SELECT COUNT(*), MAX(ragas_faithfulness), MIN(ragas_faithfulness) FROM rag_metrics_log"
            )
        ).one()
    finally:
        session.close()

    assert int(row[0]) == 2
    assert float(row[1]) == 0.9
    assert float(row[2]) == 0.0

    daily = store.load_dashboard_data(window_days=30)
    assert len(daily) == 1
    assert daily[0].queries_per_day == 2
    assert daily[0].avg_latency_ms == 100.0
    assert daily[0].abstention_rate == 0.5
    assert daily[0].total_cost_usd == pytest.approx(0.3)

    summary = store.load_dashboard_summary(window_days=30)
    assert summary.total_queries == 2
    assert summary.avg_latency_ms == 100.0
    assert summary.abstention_rate == 0.5
    assert summary.total_cost_usd == pytest.approx(0.3)


def test_pipeline_emits_ragas_metrics_in_response() -> None:
    pipeline = RAGPipeline(
        config=RAGConfig(
            sufficiency_threshold=0.1,
            enable_metrics=True,
            enable_metrics_db=False,
        )
    )

    trusted_results = [
        {
            "text_unit_id": "es_1",
            "trust_status": "trusted",
            "score": 0.9,
            "snippet": "Give zakat and establish prayer.",
            "canonical_id": "quran:2:110",
        },
        {
            "text_unit_id": "es_2",
            "trust_status": "trusted",
            "score": 0.8,
            "snippet": "Charity purifies wealth.",
            "canonical_id": "hadith:bukhari:sahih:1",
        },
    ]

    result = pipeline.generate_answer("What is zakat?", trusted_results)
    metrics = result["metrics"]

    assert metrics is not None
    assert "ragas" in metrics
    ragas = metrics["ragas"]
    assert isinstance(ragas, dict)
    assert {"faithfulness", "relevancy", "precision", "recall"}.issubset(ragas.keys())
    assert all(0.0 <= float(ragas[key]) <= 1.0 for key in ragas)
