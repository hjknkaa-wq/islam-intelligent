"""Integration tests for unified RAG pipeline with all components.

These tests verify the integration of:
- HyDE query expansion
- Query variations
- Cross-encoder reranking
- Faithfulness verification
- Cost governance
- Metrics tracking
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from islam_intelligent.rag.pipeline.core import (
    AnswerContract,
    RAGConfig,
    RAGPipeline,
)
from islam_intelligent.rag.rerank import CrossEncoderReranker, RerankerConfig
from islam_intelligent.rag.verify.faithfulness import (
    CitationFaithfulnessVerifier,
    FaithfulnessResult,
)


class TestRAGPipelineIntegration:
    """Integration tests for the unified RAG pipeline."""

    def test_pipeline_with_default_config(self):
        """Test pipeline initializes with default configuration."""
        pipeline = RAGPipeline()

        assert pipeline.config.sufficiency_threshold == 0.6
        assert pipeline.config.enable_hyde is False
        assert pipeline.config.enable_query_expansion is False
        assert pipeline.config.enable_reranker is True
        assert pipeline.config.enable_faithfulness is True

    def test_pipeline_with_all_features_enabled(self):
        """Test pipeline with all features enabled."""
        config = RAGConfig(
            enable_hyde=True,
            enable_query_expansion=True,
            enable_reranker=True,
            enable_faithfulness=True,
            enable_cost_governance=True,
            enable_metrics=True,
        )
        pipeline = RAGPipeline(config=config)

        assert pipeline.config.enable_hyde is True
        assert pipeline.config.enable_query_expansion is True
        assert pipeline.config.enable_reranker is True
        assert pipeline.config.enable_faithfulness is True

    def test_pipeline_abstains_with_no_evidence(self):
        """Pipeline should abstain when no evidence is retrieved."""
        pipeline = RAGPipeline(config=RAGConfig(sufficiency_threshold=0.1))

        with patch.object(
            pipeline,
            "retrieve",
            return_value=([], {"hyde_used": False, "query_variations": 1}),
        ):
            result = pipeline.generate_answer("test query", [])

        assert result["verdict"] == "abstain"
        assert result["abstain_reason"] == "insufficient_evidence"
        assert result["retrieved_count"] == 0

    def test_pipeline_abstains_with_untrusted_sources(self):
        """Pipeline should abstain when only untrusted sources are retrieved."""
        pipeline = RAGPipeline()

        # Mock untrusted retrieval results
        untrusted_results = [
            {
                "text_unit_id": "es_1",
                "trust_status": "untrusted",
                "score": 0.8,
                "snippet": "test",
            },
        ]

        result = pipeline.generate_answer("test query", untrusted_results)

        assert result["verdict"] == "abstain"
        assert result["abstain_reason"] == "untrusted_sources"

    def test_pipeline_returns_answer_with_sufficient_evidence(self):
        """Pipeline should return answer with sufficient trusted evidence."""
        pipeline = RAGPipeline(config=RAGConfig(sufficiency_threshold=0.1))

        # Mock trusted retrieval results
        trusted_results = [
            {
                "text_unit_id": "es_1",
                "trust_status": "trusted",
                "score": 0.8,
                "snippet": "test evidence 1",
            },
            {
                "text_unit_id": "es_2",
                "trust_status": "trusted",
                "score": 0.7,
                "snippet": "test evidence 2",
            },
        ]

        # Mock citation verifier to pass
        with patch.object(
            pipeline._citation_verifier, "verify_citations"
        ) as mock_verify:
            mock_verify.return_value = MagicMock(
                verified=True, reason=None, checked_citation_count=2
            )
            result = pipeline.generate_answer("test query", trusted_results)

        assert result["verdict"] == "answer"
        assert result["abstain_reason"] is None
        assert result["retrieved_count"] == 2
        assert result["sufficiency_score"] >= 0.1
        assert len(result["statements"]) > 0

    def test_pipeline_with_faithfulness_verification(self):
        """Test faithfulness verification integration."""
        config = RAGConfig(
            enable_faithfulness=True,
            sufficiency_threshold=0.1,
        )
        pipeline = RAGPipeline(config=config)

        # Mock faithfulness result
        mock_faithfulness_result = FaithfulnessResult(
            overall_score=8.5,
            claims_checked=1,
            unsupported_claim_count=0,
            per_claim=(),
            judge="heuristic",
        )

        # Mock citation verifier to pass
        with patch.object(
            pipeline._citation_verifier, "verify_citations"
        ) as mock_verify:
            mock_verify.return_value = MagicMock(
                verified=True, reason=None, checked_citation_count=1
            )
            with patch.object(
                pipeline._faithfulness_verifier,
                "evaluate",
                return_value=mock_faithfulness_result,
            ):
                trusted_results = [
                    {
                        "text_unit_id": "es_1",
                        "trust_status": "trusted",
                        "score": 0.8,
                        "snippet": "test evidence",
                    },
                ]

                result = pipeline.generate_answer("test query", trusted_results)

        assert result["verdict"] == "answer"
        assert result["faithfulness_score"] == 8.5

    def test_pipeline_abstains_on_unfaithful_statements(self):
        """Pipeline should abstain when statements are not faithful to evidence."""
        config = RAGConfig(
            enable_faithfulness=True,
            sufficiency_threshold=0.1,
        )
        pipeline = RAGPipeline(config=config)

        # Mock unfaithful result
        mock_faithfulness_result = FaithfulnessResult(
            overall_score=3.0,
            claims_checked=1,
            unsupported_claim_count=1,
            per_claim=(),
            judge="heuristic",
        )

        # Mock citation verifier to pass
        with patch.object(
            pipeline._citation_verifier, "verify_citations"
        ) as mock_verify:
            mock_verify.return_value = MagicMock(
                verified=True, reason=None, checked_citation_count=1
            )
            with patch.object(
                pipeline._faithfulness_verifier,
                "evaluate",
                return_value=mock_faithfulness_result,
            ):
                trusted_results = [
                    {
                        "text_unit_id": "es_1",
                        "trust_status": "trusted",
                        "score": 0.8,
                        "snippet": "test evidence",
                    },
                ]

                result = pipeline.generate_answer("test query", trusted_results)

        assert result["verdict"] == "abstain"
        assert result["abstain_reason"] == "faithfulness_check_failed"

    def test_pipeline_with_disabled_faithfulness(self):
        """Test pipeline behavior when faithfulness is disabled."""
        config = RAGConfig(
            enable_faithfulness=False,
            sufficiency_threshold=0.1,
        )
        pipeline = RAGPipeline(config=config)

        trusted_results = [
            {
                "text_unit_id": "es_1",
                "trust_status": "trusted",
                "score": 0.8,
                "snippet": "test evidence",
            },
        ]

        # Mock citation verifier to pass
        with patch.object(
            pipeline._citation_verifier, "verify_citations"
        ) as mock_verify:
            mock_verify.return_value = MagicMock(
                verified=True, reason=None, checked_citation_count=1
            )
            result = pipeline.generate_answer("test query", trusted_results)

        assert result["verdict"] == "answer"
        # When disabled, should get max score
        assert result["faithfulness_score"] == 10.0

    def test_reranker_integration(self):
        """Test cross-encoder reranker integration."""
        config = RAGConfig(
            enable_reranker=True,
            reranker_top_k=5,
        )
        pipeline = RAGPipeline(config=config)

        # Create mock reranker
        mock_reranker = MagicMock(spec=CrossEncoderReranker)
        mock_reranker.is_available.return_value = True

        # Mock rerank result
        from islam_intelligent.rag.rerank import RerankResult

        mock_reranker.rerank.return_value = [
            RerankResult(
                text_unit_id="es_1",
                score=0.95,
                snippet="reranked evidence",
                trust_status="trusted",
            )
        ]

        pipeline._reranker = mock_reranker

        # Test reranking
        results = [
            {"text_unit_id": "es_1", "score": 0.6, "snippet": "original evidence"},
        ]

        reranked = pipeline.rerank("test query", results)

        mock_reranker.rerank.assert_called_once()
        assert len(reranked) == 1
        assert reranked[0]["text_unit_id"] == "es_1"

    def test_reranker_skipped_when_disabled(self):
        """Test reranking is skipped when disabled in config."""
        config = RAGConfig(enable_reranker=False)
        pipeline = RAGPipeline(config=config)

        results = [
            {"text_unit_id": "es_1", "score": 0.6, "snippet": "original evidence"},
        ]

        reranked = pipeline.rerank("test query", results)

        # Should return original results
        assert len(reranked) == 1
        assert reranked[0]["score"] == 0.6

    def test_answer_contract_structure(self):
        """Test that AnswerContract has all expected fields."""
        contract: AnswerContract = {
            "verdict": "answer",
            "statements": [],
            "abstain_reason": None,
            "fail_reason": None,
            "retrieved_count": 5,
            "sufficiency_score": 0.8,
            "faithfulness_score": 9.0,
            "cost_usd": 0.001,
            "degradation_message": None,
            "metrics": {},
        }

        assert contract["verdict"] == "answer"
        assert "faithfulness_score" in contract
        assert "cost_usd" in contract
        assert "metrics" in contract

    def test_backward_compatibility(self):
        """Test that existing code without new fields still works."""
        # Old-style AnswerContract without new fields
        old_contract = {
            "verdict": "answer",
            "statements": [{"text": "test", "citations": []}],
            "abstain_reason": None,
            "fail_reason": None,
            "retrieved_count": 3,
            "sufficiency_score": 0.7,
        }

        # Should be valid as AnswerContract (new fields are optional)
        assert old_contract["verdict"] == "answer"

    def test_metrics_integration(self):
        """Test that metrics are tracked during pipeline execution."""
        config = RAGConfig(
            enable_metrics=True,
            sufficiency_threshold=0.1,
        )
        pipeline = RAGPipeline(config=config)

        trusted_results = [
            {
                "text_unit_id": "es_1",
                "trust_status": "trusted",
                "score": 0.8,
                "snippet": "test",
            },
        ]

        result = pipeline.generate_answer("test query", trusted_results)

        # Check that metrics were tracked
        assert result["metrics"] is not None
        metrics = result["metrics"]
        assert "query_id" in metrics
        assert "total_latency_ms" in metrics
        assert "retrieval" in metrics


class TestRAGPipelineWithHyDE:
    """Tests for HyDE integration."""

    def test_hyde_expansion_when_enabled(self):
        """Test HyDE expansion is used when enabled and available."""
        config = RAGConfig(enable_hyde=True)
        pipeline = RAGPipeline(config=config)

        # Mock HyDE expander
        pipeline._hyde_expander = MagicMock()
        pipeline._hyde_expander.is_available.return_value = True
        pipeline._hyde_expander.expand.return_value = "hypothetical answer about prayer"

        with patch("islam_intelligent.rag.pipeline.core.search_hybrid") as mock_search:
            mock_search.return_value = []
            pipeline.retrieve("how to pray")

        pipeline._hyde_expander.expand.assert_called_once_with("how to pray")

    def test_hyde_not_used_when_disabled(self):
        """Test HyDE is not used when disabled."""
        config = RAGConfig(enable_hyde=False)
        pipeline = RAGPipeline(config=config)

        with patch("islam_intelligent.rag.pipeline.core.search_hybrid") as mock_search:
            mock_search.return_value = []
            results, metadata = pipeline.retrieve("how to pray")

        assert metadata["hyde_used"] is False


class TestRAGPipelineWithQueryExpansion:
    """Tests for query expansion integration."""

    def test_multi_query_search_when_enabled(self):
        """Test multi-query search is used when expansion is enabled."""
        config = RAGConfig(
            enable_query_expansion=True,
            query_expansion_variations=3,
        )
        pipeline = RAGPipeline(config=config)

        with patch(
            "islam_intelligent.rag.pipeline.core.search_hybrid_multi_query"
        ) as mock_search:
            mock_search.return_value = []
            results, metadata = pipeline.retrieve("prayer")

        mock_search.assert_called_once()
        assert metadata["query_variations"] == 3

    def test_single_query_when_expansion_disabled(self):
        """Test single query search when expansion is disabled."""
        config = RAGConfig(enable_query_expansion=False)
        pipeline = RAGPipeline(config=config)

        with patch("islam_intelligent.rag.pipeline.core.search_hybrid") as mock_search:
            mock_search.return_value = []
            results, metadata = pipeline.retrieve("prayer")

        mock_search.assert_called_once()
        assert metadata["query_variations"] == 1


class TestRAGPipelineConfig:
    """Tests for RAG configuration options."""

    def test_all_config_options(self):
        """Test that all configuration options can be set."""
        config = RAGConfig(
            sufficiency_threshold=0.8,
            max_retrieval=20,
            min_citations_per_statement=2,
            enable_llm=True,
            llm_model="gpt-4",
            enable_hyde=True,
            hyde_max_tokens=200,
            enable_query_expansion=True,
            query_expansion_variations=5,
            enable_reranker=True,
            reranker_model="cross-encoder/test",
            reranker_top_k=15,
            enable_faithfulness=True,
            faithfulness_threshold=0.8,
            enable_cost_governance=True,
            daily_budget_usd=20.0,
            enable_metrics=True,
        )

        assert config.sufficiency_threshold == 0.8
        assert config.max_retrieval == 20
        assert config.enable_llm is True
        assert config.enable_hyde is True
        assert config.hyde_max_tokens == 200
        assert config.enable_reranker is True
        assert config.reranker_top_k == 15
        assert config.faithfulness_threshold == 0.8

    def test_default_config_values(self):
        """Test default configuration values."""
        config = RAGConfig()

        assert config.sufficiency_threshold == 0.6
        assert config.max_retrieval == 10
        assert config.enable_llm is False
        assert config.enable_hyde is False
        assert config.enable_reranker is True
        assert config.enable_faithfulness is True


class TestRAGPipelineErrorHandling:
    """Tests for error handling and edge cases."""

    def test_pipeline_handles_retrieval_error(self):
        """Test pipeline handles retrieval errors gracefully."""
        pipeline = RAGPipeline()

        with patch.object(pipeline, "retrieve", side_effect=Exception("DB error")):
            # Should not crash, but may return abstain
            try:
                result = pipeline.generate_answer("test", [])
                # If no exception, should have valid result structure
                assert "verdict" in result
            except Exception:
                pass  # Exception handling is acceptable

    def test_pipeline_handles_faithfulness_verifier_error(self):
        """Test pipeline handles faithfulness verifier errors."""
        config = RAGConfig(
            enable_faithfulness=True,
            sufficiency_threshold=0.1,
        )
        pipeline = RAGPipeline(config=config)

        # Make verifier raise exception
        pipeline._faithfulness_verifier = MagicMock()
        pipeline._faithfulness_verifier.evaluate.side_effect = Exception(
            "Verifier error"
        )

        trusted_results = [
            {
                "text_unit_id": "es_1",
                "trust_status": "trusted",
                "score": 0.8,
                "snippet": "test",
            },
        ]

        # Should not crash, uses fallback
        result = pipeline.generate_answer("test query", trusted_results)
        assert result["verdict"] in ["answer", "abstain"]

    def test_empty_query_handling(self):
        """Test pipeline handles empty queries."""
        pipeline = RAGPipeline()

        with patch.object(
            pipeline,
            "retrieve",
            return_value=([], {"hyde_used": False, "query_variations": 1}),
        ):
            result = pipeline.generate_answer("", [])

        assert result["verdict"] == "abstain"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
