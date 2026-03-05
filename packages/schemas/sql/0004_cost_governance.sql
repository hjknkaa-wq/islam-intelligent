-- ISLAM INTELLIGENT - Migration: Cost Governance
-- Purpose: Persist API cost usage, budget alerts, and routing/degradation metadata
-- Created: 2026-03-05

-- ============================================
-- COST USAGE LOGS (PER QUERY)
-- ============================================
CREATE TABLE cost_usage_log (
    cost_usage_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rag_query_id UUID REFERENCES rag_query(rag_query_id) ON DELETE SET NULL,
    query_hash_sha256 TEXT NOT NULL CHECK (query_hash_sha256 ~ '^[a-f0-9]{64}$'),

    embedding_model TEXT NOT NULL,
    llm_model TEXT NOT NULL,
    embedding_tokens INTEGER NOT NULL DEFAULT 0 CHECK (embedding_tokens >= 0),
    llm_prompt_tokens INTEGER NOT NULL DEFAULT 0 CHECK (llm_prompt_tokens >= 0),
    llm_completion_tokens INTEGER NOT NULL DEFAULT 0 CHECK (llm_completion_tokens >= 0),

    embedding_cost_usd NUMERIC(12,8) NOT NULL DEFAULT 0 CHECK (embedding_cost_usd >= 0),
    llm_cost_usd NUMERIC(12,8) NOT NULL DEFAULT 0 CHECK (llm_cost_usd >= 0),
    total_cost_usd NUMERIC(12,8) NOT NULL DEFAULT 0 CHECK (total_cost_usd >= 0),

    degradation_mode TEXT NOT NULL DEFAULT 'none',
    route_reason TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_cost_usage_log_created ON cost_usage_log(created_at);
CREATE INDEX idx_cost_usage_log_query ON cost_usage_log(rag_query_id);
CREATE INDEX idx_cost_usage_log_total ON cost_usage_log(total_cost_usd DESC);

COMMENT ON TABLE cost_usage_log IS 'Per-query usage cost tracking for embeddings + LLM generation';
COMMENT ON COLUMN cost_usage_log.total_cost_usd IS 'Total query cost in USD';
COMMENT ON COLUMN cost_usage_log.degradation_mode IS 'Routing mode: none, budget, or other fallback mode';

-- ============================================
-- COST ALERT EVENTS
-- ============================================
CREATE TABLE cost_alert_event (
    cost_alert_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    alert_type TEXT NOT NULL,
    period TEXT NOT NULL CHECK (period IN ('daily', 'weekly')),
    threshold_ratio NUMERIC(4,3) NOT NULL CHECK (threshold_ratio >= 0 AND threshold_ratio <= 1),
    spend_usd NUMERIC(12,8) NOT NULL CHECK (spend_usd >= 0),
    budget_usd NUMERIC(12,8) NOT NULL CHECK (budget_usd >= 0),
    message TEXT NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_cost_alert_event_created ON cost_alert_event(created_at);
CREATE INDEX idx_cost_alert_event_period ON cost_alert_event(period);
CREATE INDEX idx_cost_alert_event_type ON cost_alert_event(alert_type);

COMMENT ON TABLE cost_alert_event IS 'Budget threshold/exceeded alerts for cost governance';

-- ============================================
-- MIGRATION METADATA
-- ============================================
INSERT INTO schema_migrations (version, applied_at, description)
VALUES ('0004_cost_governance', NOW(), 'Add cost usage and alert event tables for budget governance');
