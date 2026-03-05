-- ISLAM INTELLIGENT - Migration: RAG Observability Metrics
-- Purpose: Persist per-query RAGAS metrics and dashboard aggregates
-- Created: 2026-03-05

-- ============================================
-- RAG METRICS LOG (PER QUERY)
-- ============================================
CREATE TABLE rag_metrics_log (
    metrics_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    query_id TEXT NOT NULL,
    query_text TEXT NOT NULL,

    pipeline_start_time TIMESTAMP WITH TIME ZONE,
    pipeline_end_time TIMESTAMP WITH TIME ZONE,
    total_latency_ms NUMERIC(12,3) NOT NULL DEFAULT 0 CHECK (total_latency_ms >= 0),

    retrieval_metrics JSONB NOT NULL DEFAULT '{}',
    generation_metrics JSONB NOT NULL DEFAULT '{}',
    verification_metrics JSONB NOT NULL DEFAULT '{}',

    -- RAGAS metrics (0..1 scale)
    ragas_faithfulness NUMERIC(5,4) CHECK (ragas_faithfulness >= 0 AND ragas_faithfulness <= 1),
    ragas_relevancy NUMERIC(5,4) CHECK (ragas_relevancy >= 0 AND ragas_relevancy <= 1),
    ragas_precision NUMERIC(5,4) CHECK (ragas_precision >= 0 AND ragas_precision <= 1),
    ragas_recall NUMERIC(5,4) CHECK (ragas_recall >= 0 AND ragas_recall <= 1),

    verdict TEXT NOT NULL CHECK (verdict IN ('answer', 'abstain', 'error')),
    abstain_reason TEXT,
    error_type TEXT,

    cost_estimate_usd NUMERIC(12,8) NOT NULL DEFAULT 0 CHECK (cost_estimate_usd >= 0),
    cost_actual_usd NUMERIC(12,8) NOT NULL DEFAULT 0 CHECK (cost_actual_usd >= 0),
    cost_governance_applied BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_rag_metrics_log_query_id ON rag_metrics_log(query_id);
CREATE INDEX idx_rag_metrics_log_created_at ON rag_metrics_log(created_at);
CREATE INDEX idx_rag_metrics_log_verdict ON rag_metrics_log(verdict);

COMMENT ON TABLE rag_metrics_log IS 'Per-query observability log with latency, cost, verdict, and RAGAS metrics';
COMMENT ON COLUMN rag_metrics_log.ragas_faithfulness IS 'RAGAS faithfulness score in range [0,1]';
COMMENT ON COLUMN rag_metrics_log.ragas_relevancy IS 'RAGAS answer relevancy score in range [0,1]';
COMMENT ON COLUMN rag_metrics_log.ragas_precision IS 'RAGAS context precision score in range [0,1]';
COMMENT ON COLUMN rag_metrics_log.ragas_recall IS 'RAGAS context recall score in range [0,1]';

-- ============================================
-- DASHBOARD VIEW (DAILY AGGREGATE)
-- ============================================
CREATE VIEW v_rag_metrics_dashboard_daily AS
SELECT
    DATE(created_at) AS day,
    COUNT(*) AS queries_per_day,
    AVG(total_latency_ms) AS avg_latency_ms,
    AVG(CASE WHEN verdict = 'abstain' THEN 1.0 ELSE 0.0 END) AS abstention_rate,
    SUM(cost_actual_usd) AS total_cost_usd
FROM rag_metrics_log
GROUP BY DATE(created_at)
ORDER BY day ASC;

COMMENT ON VIEW v_rag_metrics_dashboard_daily IS 'Daily dashboard series: query volume, latency, abstention rate, and cost';

-- ============================================
-- MIGRATION METADATA
-- ============================================
INSERT INTO schema_migrations (version, applied_at, description)
VALUES ('0005_observability_metrics', NOW(), 'Add RAG observability metrics table and daily dashboard view');
