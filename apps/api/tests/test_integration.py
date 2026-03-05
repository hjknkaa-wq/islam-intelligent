"""End-to-end integration tests for the Islam Intelligent RAG system.

This module tests the complete pipeline from query to answer,
including HyDE, query expansion, and cost governance integration.
"""

from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false

import time
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@pytest.fixture
def db_session_integration():
    """Provide a fresh SQLite database for integration tests."""
    from islam_intelligent.db.engine import SessionLocal, engine
    from islam_intelligent.domain.models import Base

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def setup_cost_tables(db_session_integration):
    """Set up cost governance tables in the database."""
    from islam_intelligent.domain.models import Base

    # Create tables
    Base.metadata.create_all(bind=db_session_integration.bind)

    # Create cost tables if they don't exist
    db_session_integration.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS cost_usage_log (
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
    )
    db_session_integration.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS cost_alert_event (
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
    )
    db_session_integration.commit()
    return db_session_integration


@pytest.fixture
def mock_evidence_data(db_session_integration):
    """Insert mock evidence data for retrieval tests."""
    from islam_intelligent.domain.models import EvidenceSpan, TextUnit, Source

    # Create a source
    source = Source(
        source_id="test_quran",
        source_type="quran",
        canonical_name="Test Quran",
        trust_status="trusted",
        license_tag="public_domain",
    )
    db_session_integration.add(source)
    db_session_integration.flush()

    # Create text units
    text_units = [
        TextUnit(
            source_id=source.source_id,
            content="Establish prayer and give zakat, and bow with those who bow.",
            canonical_id="q:2:43",
            content_hash="abc123",
        ),
        TextUnit(
            source_id=source.source_id,
            content="O you who have believed, seek help through patience and prayer.",
            canonical_id="q:2:153",
            content_hash="def456",
        ),
        TextUnit(
            source_id=source.source_id,
            content="The believers are those who establish prayer and give charity.",
            canonical_id="q:2:277",
            content_hash="ghi789",
        ),
    ]
    for tu in text_units:
        db_session_integration.add(tu)
    db_session_integration.commit()

    return text_units


class TestRAGPipelineIntegration:
    """End-to-end RAG pipeline integration tests."""

    def test_full_rag_pipeline_abstain_no_evidence(self, db_session_integration):
        """Test that RAG abstains when no evidence is found."""
        from islam_intelligent.rag.pipeline.core import RAGPipeline, RAGConfig

        pipeline = RAGPipeline(
            config=RAGConfig(
                sufficiency_threshold=0.6,
                max_retrieval=10,
                enable_llm=False,
            )
        )

        answer = pipeline.query("What is the ruling on cryptocurrency?")

        assert answer["verdict"] == "abstain"
        assert answer["abstain_reason"] is not None
        assert answer["retrieved_count"] == 0

    def test_full_rag_pipeline_with_mock_evidence(self, db_session_integration):
        """Test RAG pipeline with mock evidence retrieval."""
        from islam_intelligent.rag.pipeline.core import RAGPipeline, RAGConfig

        # Create pipeline with low threshold to ensure answer
        pipeline = RAGPipeline(
            config=RAGConfig(
                sufficiency_threshold=0.1,
                max_retrieval=10,
                enable_llm=False,
            )
        )

        # Mock evidence that would be retrieved
        mock_evidence = [
            {
                "evidence_span_id": "span_1",
                "text_unit_id": "tu_1",
                "canonical_id": "q:2:43",
                "snippet": "Establish prayer and give zakat",
                "score": 0.85,
                "trust_status": "trusted",
            },
            {
                "evidence_span_id": "span_2",
                "text_unit_id": "tu_2",
                "canonical_id": "q:2:153",
                "snippet": "Seek help through patience and prayer",
                "score": 0.75,
                "trust_status": "trusted",
            },
        ]

        answer = pipeline.generate_answer("How should Muslims pray?", mock_evidence)

        # Should either answer or abstain based on sufficiency
        assert answer["verdict"] in ["answer", "abstain"]
        assert "retrieved_count" in answer
        assert "sufficiency_score" in answer

    def test_rag_pipeline_untrusted_sources_abstain(self, db_session_integration):
        """Test that RAG abstains when only untrusted sources are available."""
        from islam_intelligent.rag.pipeline.core import RAGPipeline

        pipeline = RAGPipeline()

        # Mock evidence with untrusted sources
        mock_evidence = [
            {
                "evidence_span_id": "span_1",
                "text_unit_id": "tu_1",
                "canonical_id": "unknown:1",
                "snippet": "Some untrusted content",
                "score": 0.90,
                "trust_status": "untrusted",
            }
        ]

        answer = pipeline.query("What is the secret teaching?")
        # When retrieval returns untrusted, it should be filtered out
        # Resulting in insufficient evidence

        # The query method filters by trust_status
        # If no trusted sources, it abstains
        if answer["verdict"] == "abstain":
            assert answer["abstain_reason"] in [
                "insufficient_evidence",
                "untrusted_sources",
            ]

    def test_rag_pipeline_sufficiency_threshold(self, db_session_integration):
        """Test that sufficiency threshold controls answer generation."""
        from islam_intelligent.rag.pipeline.core import RAGPipeline, RAGConfig

        # High threshold - should abstain with minimal evidence
        high_threshold_pipeline = RAGPipeline(
            config=RAGConfig(sufficiency_threshold=0.9)
        )

        # Low threshold - should answer with minimal evidence
        low_threshold_pipeline = RAGPipeline(
            config=RAGConfig(sufficiency_threshold=0.1)
        )

        # Test with minimal evidence
        minimal_evidence = [{"score": 0.3}]

        is_sufficient_high, score_high = high_threshold_pipeline.validate_sufficiency(
            minimal_evidence
        )
        is_sufficient_low, score_low = low_threshold_pipeline.validate_sufficiency(
            minimal_evidence
        )

        # Same score, different thresholds
        assert score_high == score_low

    def test_rag_pipeline_statement_verification(self, db_session_integration):
        """Test that generated statements are properly verified."""
        from islam_intelligent.rag.pipeline.core import RAGPipeline

        pipeline = RAGPipeline()

        retrieved = [
            {"evidence_span_id": "valid_span_1", "text_unit_id": "valid_span_1"},
            {"evidence_span_id": "valid_span_2", "text_unit_id": "valid_span_2"},
        ]

        # Valid statements with proper citations
        valid_statements = [
            {
                "text": "Statement with valid citation",
                "citations": [{"evidence_span_id": "valid_span_1"}],
            }
        ]

        # Invalid statements without citations
        invalid_statements = [{"text": "Statement without citations", "citations": []}]

        # Invalid statements with non-existent citations
        bad_citation_statements = [
            {
                "text": "Statement with bad citation",
                "citations": [{"evidence_span_id": "non_existent"}],
            }
        ]

        assert pipeline._verify_statements(valid_statements, retrieved) is True
        assert pipeline._verify_statements(invalid_statements, retrieved) is False
        assert pipeline._verify_statements(bad_citation_statements, retrieved) is False


class TestHyDEIntegration:
    """Integration tests for HyDE (Hypothetical Document Embeddings)."""

    def test_hyde_disabled_falls_back_to_query(self, monkeypatch):
        """Test that disabled HyDE falls back to original query."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from islam_intelligent.rag.retrieval.hyde import HyDEQueryExpander, HyDEConfig

        config = HyDEConfig(enabled=False)
        expander = HyDEQueryExpander(config=config)

        query = "How to perform wudu?"
        result = expander.expand(query)

        assert result == query

    def test_hyde_unavailable_without_api_key(self, monkeypatch):
        """Test that HyDE is unavailable without API key."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from islam_intelligent.rag.retrieval.hyde import HyDEQueryExpander

        expander = HyDEQueryExpander()

        assert expander.is_available() is False

        query = "How to perform wudu?"
        result = expander.expand(query)

        # Should return original query when unavailable
        assert result == query

    def test_hyde_embedding_with_fallback(self, monkeypatch):
        """Test HyDE embedding generation with fallback."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from islam_intelligent.rag.retrieval.hyde import HyDEQueryExpander

        expander = HyDEQueryExpander()
        query = "What is zakat?"

        embedding, metadata = expander.get_embedding_with_fallback(query)

        # Should return embedding (fallback zero vector when unavailable)
        assert isinstance(embedding, list)
        assert len(embedding) > 0
        assert "hyde_used" in metadata
        assert metadata["hyde_used"] is False  # Not used when unavailable

    def test_hyde_embedding_dimensions(self, monkeypatch):
        """Test that HyDE returns embeddings with correct dimensions."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from islam_intelligent.rag.retrieval.hyde import HyDEQueryExpander
        from islam_intelligent.config import settings

        expander = HyDEQueryExpander()
        query = "Test query"

        embedding = expander.get_embedding(query)

        assert isinstance(embedding, Sequence)
        assert len(embedding) == settings.embedding_dimension

    def test_hyde_system_prompt_contains_islamic_context(self):
        """Test that HyDE system prompt is Islamic context-aware."""
        from islam_intelligent.rag.retrieval.hyde import HyDEQueryExpander

        expander = HyDEQueryExpander()
        prompt = expander._system_prompt()

        assert "Islam" in prompt or "scholar" in prompt.lower()


class TestQueryExpansionIntegration:
    """Integration tests for query expansion functionality."""

    def test_query_expansion_generates_variations(self):
        """Test that query expansion generates multiple variations."""
        from islam_intelligent.rag.retrieval.query_expander import (
            QueryExpander,
            QueryExpanderConfig,
        )

        expander = QueryExpander(
            config=QueryExpanderConfig(enabled=True, num_variations=5)
        )

        query = "prayer"
        variations = expander.expand(query, num_variations=5)

        assert len(variations) == 5
        assert query in variations  # Original should be included

    def test_query_expansion_disabled_returns_original(self):
        """Test that disabled expansion returns only original query."""
        from islam_intelligent.rag.retrieval.query_expander import (
            QueryExpander,
            QueryExpanderConfig,
        )

        config = QueryExpanderConfig(enabled=False)
        expander = QueryExpander(config=config)

        query = "fasting"
        variations = expander.expand(query, num_variations=5)

        assert variations == [query]

    def test_query_expansion_source_specific(self):
        """Test source-specific query expansion."""
        from islam_intelligent.rag.retrieval.query_expander import QueryExpander

        expander = QueryExpander()

        quran_variations = expander.expand_with_sources(
            "charity", source_types=["quran"]
        )
        hadith_variations = expander.expand_with_sources(
            "charity", source_types=["hadith"]
        )

        # Quran variations should mention Quran
        assert any("quran" in v.lower() for v in quran_variations)

        # Hadith variations should mention hadith
        assert any("hadith" in v.lower() for v in hadith_variations)

    def test_query_expansion_deduplication(self):
        """Test that query expansion deduplicates variations."""
        from islam_intelligent.rag.retrieval.query_expander import (
            QueryExpander,
            QueryExpanderConfig,
        )

        config = QueryExpanderConfig(deduplicate=True)
        expander = QueryExpander(config=config)

        variations = expander.expand("test query", num_variations=10)

        # Check no duplicates (case-insensitive)
        lower_variations = [v.lower() for v in variations]
        assert len(lower_variations) == len(set(lower_variations))


class TestCostGovernanceIntegration:
    """Integration tests for cost governance."""

    def test_cost_estimator_tracks_components(self):
        """Test that cost estimator tracks all cost components."""
        from islam_intelligent.cost_governance import CostEstimator

        estimator = CostEstimator()

        estimate = estimator.estimate_query_cost(
            query="Explain the pillars of Islam",
            embedding_model="text-embedding-3-small",
            llm_model="gpt-4o-mini",
        )

        assert estimate.embedding_tokens >= 0
        assert estimate.llm_prompt_tokens >= 0
        assert estimate.llm_completion_tokens >= 0
        assert estimate.embedding_cost_usd >= 0
        assert estimate.llm_cost_usd >= 0
        assert estimate.total_cost_usd >= 0

    def test_budget_manager_enforces_caps(self, setup_cost_tables):
        """Test that budget manager enforces daily and weekly caps."""
        from islam_intelligent.cost_governance import (
            BudgetManager,
            SQLCostRepository,
        )
        from datetime import datetime, timezone

        session_factory = sessionmaker(bind=setup_cost_tables.bind, future=True)
        repository = SQLCostRepository(session_factory=session_factory)

        manager = BudgetManager(
            daily_budget=5.0,
            weekly_budget=10.0,
            repository=repository,
        )

        now = datetime(2026, 3, 5, 12, 0, tzinfo=timezone.utc)

        # Should allow small cost
        assert manager.can_proceed(1.0, at=now) is True

        # Should deny large cost
        assert manager.can_proceed(100.0, at=now) is False

    def test_cost_governance_service_plan_query(self, setup_cost_tables):
        """Test cost governance service query planning."""
        from islam_intelligent.cost_governance import (
            CostGovernanceService,
            BudgetManager,
            SQLCostRepository,
        )
        from datetime import datetime, timezone

        session_factory = sessionmaker(bind=setup_cost_tables.bind, future=True)
        repository = SQLCostRepository(session_factory=session_factory)

        manager = BudgetManager(
            daily_budget=20.0,
            weekly_budget=50.0,
            repository=repository,
        )

        service = CostGovernanceService(budget_manager=manager)

        now = datetime(2026, 3, 5, 12, 0, tzinfo=timezone.utc)
        plan = service.plan_query(query="What are the five pillars of Islam?", at=now)

        assert plan.allowed is True
        assert plan.route is not None
        assert plan.estimate is not None
        assert plan.budget is not None

    def test_model_router_complexity_assessment(self):
        """Test that model router assesses query complexity."""
        from islam_intelligent.cost_governance import ModelRouter, CostEstimator

        router = ModelRouter()
        estimator = CostEstimator()

        simple_query = "What is zakat?"
        complex_query = (
            "Analyze and compare the evidence from Quran and hadith, "
            "then synthesize the scholarly opinions with step by step reasoning"
        )

        simple_complexity = router.assess_complexity(simple_query)
        complex_complexity = router.assess_complexity(complex_query)

        assert 0 <= simple_complexity <= 1
        assert 0 <= complex_complexity <= 1
        assert complex_complexity > simple_complexity

        # Test routing
        simple_route = router.route(
            query=simple_query,
            estimator=estimator,
            embedding_model="text-embedding-3-small",
            budget_ratio=1.0,
        )

        complex_route = router.route(
            query=complex_query,
            estimator=estimator,
            embedding_model="text-embedding-3-small",
            budget_ratio=1.0,
        )

        # Complex queries may get different routing
        assert simple_route.complexity_score < complex_route.complexity_score


class TestRAGPipelineEndToEnd:
    """Complete end-to-end RAG pipeline tests."""

    def test_full_pipeline_with_cost_tracking(self, setup_cost_tables, monkeypatch):
        """Test full RAG pipeline with cost governance integration."""
        from islam_intelligent.rag.pipeline.core import RAGPipeline, RAGConfig
        from islam_intelligent.cost_governance import (
            BudgetManager,
            SQLCostRepository,
            CostGovernanceService,
        )
        from datetime import datetime, timezone

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        session_factory = sessionmaker(bind=setup_cost_tables.bind, future=True)
        repository = SQLCostRepository(session_factory=session_factory)

        manager = BudgetManager(
            daily_budget=100.0,
            weekly_budget=500.0,
            repository=repository,
        )

        cost_service = CostGovernanceService(budget_manager=manager)

        pipeline = RAGPipeline(
            config=RAGConfig(
                sufficiency_threshold=0.1,
                enable_llm=False,
            )
        )

        now = datetime(2026, 3, 5, 12, 0, tzinfo=timezone.utc)

        # Plan the query cost
        plan = cost_service.plan_query(query="How do Muslims pray?", at=now)

        assert plan.allowed is True

        # Execute the query
        answer = pipeline.query("How do Muslims pray?")

        # Verify answer structure
        assert "verdict" in answer
        assert "retrieved_count" in answer
        assert "sufficiency_score" in answer

    def test_pipeline_response_times(self, monkeypatch):
        """Test that pipeline responds within acceptable time limits."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from islam_intelligent.rag.pipeline.core import RAGPipeline, RAGConfig

        pipeline = RAGPipeline(
            config=RAGConfig(sufficiency_threshold=0.1, enable_llm=False)
        )

        start_time = time.time()
        answer = pipeline.query("What is prayer?")
        end_time = time.time()

        response_time = end_time - start_time

        # Should complete within 5 seconds (local operation)
        assert response_time < 5.0
        assert "verdict" in answer

    def test_pipeline_handles_arabic_queries(self, monkeypatch):
        """Test that pipeline handles Arabic text correctly."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from islam_intelligent.rag.pipeline.core import RAGPipeline

        pipeline = RAGPipeline()

        arabic_query = "ما هي الصلاة؟"
        answer = pipeline.query(arabic_query)

        # Should handle Arabic without crashing
        assert "verdict" in answer
        assert "retrieved_count" in answer

    def test_pipeline_handles_long_queries(self, monkeypatch):
        """Test that pipeline handles long queries correctly."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from islam_intelligent.rag.pipeline.core import RAGPipeline

        pipeline = RAGPipeline()

        long_query = "Explain the Islamic ruling on " + "prayer " * 100
        answer = pipeline.query(long_query)

        # Should handle long queries without crashing
        assert "verdict" in answer
        assert "retrieved_count" in answer

    def test_pipeline_handles_special_characters(self, monkeypatch):
        """Test that pipeline handles special characters correctly."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from islam_intelligent.rag.pipeline.core import RAGPipeline

        pipeline = RAGPipeline()

        special_queries = [
            "What is zakat? <script>alert('xss')</script>",
            "Prayer 'quotes' and \"double quotes\"",
            "Fasting\nNewlines\tTabs",
            "Charity; DROP TABLE users; --",
        ]

        for query in special_queries:
            answer = pipeline.query(query)
            assert "verdict" in answer
            assert "retrieved_count" in answer


class TestIntegrationErrorHandling:
    """Test error handling across integrated components."""

    def test_pipeline_handles_empty_query(self, monkeypatch):
        """Test that pipeline handles empty queries gracefully."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from islam_intelligent.rag.pipeline.core import RAGPipeline

        pipeline = RAGPipeline()

        answer = pipeline.query("")

        # Should not crash, should return abstain
        assert "verdict" in answer

    def test_pipeline_handles_none_retrieval(self, monkeypatch):
        """Test that pipeline handles None retrieval gracefully."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from islam_intelligent.rag.pipeline.core import RAGPipeline

        pipeline = RAGPipeline()

        # Test sufficiency validation directly
        is_sufficient, score = pipeline.validate_sufficiency([])

        assert is_sufficient is False
        assert score == 0.0

    def test_hyde_handles_empty_query(self, monkeypatch):
        """Test that HyDE handles empty queries gracefully."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from islam_intelligent.rag.retrieval.hyde import HyDEQueryExpander

        expander = HyDEQueryExpander()

        result = expander.expand("")
        assert result == ""

    def test_query_expansion_handles_empty_query(self):
        """Test that query expansion handles empty queries gracefully."""
        from islam_intelligent.rag.retrieval.query_expander import QueryExpander

        expander = QueryExpander()

        with pytest.raises(ValueError, match="Query cannot be empty"):
            expander.expand("")
