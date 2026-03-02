-- ISLAM INTELLIGENT - Minimal Schema Migration
-- Evidence-first Islamic knowledge system
-- Created: 2026-03-02

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- 1) SOURCE REGISTRY
-- ============================================
-- Stores metadata about primary sources with full provenance and licensing info

CREATE TYPE source_type_enum AS ENUM (
    'quran_text',
    'hadith_collection', 
    'tafsir',
    'fiqh',
    'sirah',
    'translation',
    'other'
);

CREATE TYPE trust_status_enum AS ENUM (
    'untrusted',
    'trusted'
);

CREATE TABLE source_document (
    source_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_type source_type_enum NOT NULL,
    work_title TEXT NOT NULL,
    author TEXT,
    edition TEXT,
    language TEXT NOT NULL CHECK (language ~ '^[a-z]{2}(-[A-Z]{2})?$'), -- BCP-47-like: ar, en, id
    canonical_ref TEXT, -- bibliographic reference or URL
    license_id TEXT NOT NULL,
    license_url TEXT NOT NULL,
    rights_holder TEXT,
    attribution_text TEXT,
    retrieved_at TIMESTAMP WITH TIME ZONE,
    content_hash_sha256 TEXT NOT NULL CHECK (content_hash_sha256 ~ '^[a-f0-9]{64}$'),
    content_mime TEXT NOT NULL DEFAULT 'text/plain',
    content_length_bytes INTEGER NOT NULL CHECK (content_length_bytes >= 0),
    storage_path TEXT NOT NULL,
    trust_status trust_status_enum NOT NULL DEFAULT 'untrusted',
    supersedes_source_id UUID REFERENCES source_document(source_id) ON DELETE RESTRICT,
    retraction_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Self-referential constraint: if superseded, must have a reason
    CONSTRAINT retraction_requires_reason 
        CHECK (supersedes_source_id IS NULL OR retraction_reason IS NOT NULL)
);

CREATE INDEX idx_source_document_type ON source_document(source_type);
CREATE INDEX idx_source_document_trust ON source_document(trust_status);
CREATE INDEX idx_source_document_supersedes ON source_document(supersedes_source_id);

COMMENT ON TABLE source_document IS 'Registry of all primary Islamic sources with provenance and licensing';
COMMENT ON COLUMN source_document.content_hash_sha256 IS 'SHA-256 hash of the canonical source content';
COMMENT ON COLUMN source_document.trust_status IS 'Gates answering: only trusted sources can be cited';

-- ============================================
-- 2) TEXT UNITS
-- ============================================
-- Canonical storage for Quran ayat and hadith items

CREATE TYPE unit_type_enum AS ENUM (
    'quran_ayah',
    'hadith_item'
);

CREATE TABLE text_unit (
    text_unit_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id UUID NOT NULL REFERENCES source_document(source_id) ON DELETE RESTRICT,
    unit_type unit_type_enum NOT NULL,
    canonical_id TEXT NOT NULL UNIQUE CHECK (
        -- Quran: quran:{surah}:{ayah}
        canonical_id ~ '^quran:([1-9]|[1-9][0-9]|1[0-1][0-9]|11[0-4]):([1-9]|[1-9][0-9]|[1-2][0-9]{2})$'
        OR
        -- Hadith: hadith:{collection}:{numbering_system}:{number}
        canonical_id ~ '^hadith:[a-z]+:[a-z_]+:[1-9][0-9]*$'
    ),
    canonical_locator_json JSONB NOT NULL,
    text_canonical TEXT NOT NULL, -- Unicode NFC normalized
    text_canonical_utf8_sha256 TEXT NOT NULL CHECK (text_canonical_utf8_sha256 ~ '^[a-f0-9]{64}$'),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    CONSTRAINT valid_quran_id CHECK (
        unit_type != 'quran_ayah' 
        OR canonical_id ~ '^quran:'
    ),
    CONSTRAINT valid_hadith_id CHECK (
        unit_type != 'hadith_item' 
        OR canonical_id ~ '^hadith:'
    )
);

CREATE INDEX idx_text_unit_source ON text_unit(source_id);
CREATE INDEX idx_text_unit_type ON text_unit(unit_type);
CREATE INDEX idx_text_unit_canonical_id ON text_unit(canonical_id);

COMMENT ON TABLE text_unit IS 'Canonical text units: Quran ayat and hadith items';
COMMENT ON COLUMN text_unit.text_canonical IS 'Unicode NFC normalized text, source of truth';
COMMENT ON COLUMN text_unit.text_canonical_utf8_sha256 IS 'SHA-256 of UTF-8 encoded canonical text';

-- ============================================
-- 3) EVIDENCE SPANS
-- ============================================
-- Byte-offset based evidence pointers with hash verification

CREATE TABLE evidence_span (
    evidence_span_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    text_unit_id UUID NOT NULL REFERENCES text_unit(text_unit_id) ON DELETE RESTRICT,
    start_byte INTEGER NOT NULL CHECK (start_byte >= 0),
    end_byte INTEGER NOT NULL CHECK (end_byte > start_byte),
    snippet_text TEXT, -- Optional: the actual span text
    snippet_utf8_sha256 TEXT NOT NULL CHECK (snippet_utf8_sha256 ~ '^[a-f0-9]{64}$'),
    prefix_text TEXT, -- Optional: context before span for re-anchoring
    suffix_text TEXT, -- Optional: context after span for re-anchoring
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_evidence_span_text_unit ON evidence_span(text_unit_id);
CREATE INDEX idx_evidence_span_range ON evidence_span(text_unit_id, start_byte, end_byte);

COMMENT ON TABLE evidence_span IS 'Evidence spans with UTF-8 byte offsets and hash verification';
COMMENT ON COLUMN evidence_span.start_byte IS 'Inclusive UTF-8 byte offset';
COMMENT ON COLUMN evidence_span.end_byte IS 'Exclusive UTF-8 byte offset';
COMMENT ON COLUMN evidence_span.snippet_utf8_sha256 IS 'SHA-256 of the UTF-8 bytes from start_byte to end_byte';

-- ============================================
-- 4) KNOWLEDGE GRAPH ENTITIES
-- ============================================
-- Named entities for the knowledge graph

CREATE TABLE kg_entity (
    entity_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type TEXT NOT NULL, -- e.g., 'person', 'concept', 'event', 'location'
    canonical_name TEXT NOT NULL,
    aliases_json JSONB NOT NULL DEFAULT '[]', -- Array of alternative names
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    CONSTRAINT unique_canonical_name_per_type UNIQUE (entity_type, canonical_name)
);

CREATE INDEX idx_kg_entity_type ON kg_entity(entity_type);
CREATE INDEX idx_kg_entity_name ON kg_entity(canonical_name);

COMMENT ON TABLE kg_entity IS 'Knowledge graph entities: people, concepts, events, etc.';

-- ============================================
-- 5) KNOWLEDGE GRAPH EDGES
-- ============================================
-- Relationships between entities with literal support

CREATE TABLE kg_edge (
    edge_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    subject_entity_id UUID NOT NULL REFERENCES kg_entity(entity_id) ON DELETE RESTRICT,
    predicate TEXT NOT NULL, -- e.g., 'authored', 'mentions', 'is_a', 'related_to'
    object_entity_id UUID REFERENCES kg_entity(entity_id) ON DELETE RESTRICT,
    object_literal TEXT, -- For literal values (dates, quantities, etc.)
    confidence_score NUMERIC(3,2) CHECK (confidence_score >= 0 AND confidence_score <= 1),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    CONSTRAINT edge_has_object CHECK (
        object_entity_id IS NOT NULL OR object_literal IS NOT NULL
    )
);

CREATE INDEX idx_kg_edge_subject ON kg_edge(subject_entity_id);
CREATE INDEX idx_kg_edge_object ON kg_edge(object_entity_id);
CREATE INDEX idx_kg_edge_predicate ON kg_edge(predicate);

COMMENT ON TABLE kg_edge IS 'Knowledge graph edges linking entities';
COMMENT ON COLUMN kg_edge.object_entity_id IS 'Linked entity (optional if object_literal is set)';
COMMENT ON COLUMN kg_edge.object_literal IS 'Literal value (optional if object_entity_id is set)';

-- ============================================
-- 6) KG EDGE EVIDENCE
-- ============================================
-- Junction table linking edges to their evidence spans
-- ENFORCES: Every edge MUST have >= 1 evidence span

CREATE TABLE kg_edge_evidence (
    edge_id UUID NOT NULL REFERENCES kg_edge(edge_id) ON DELETE CASCADE,
    evidence_span_id UUID NOT NULL REFERENCES evidence_span(evidence_span_id) ON DELETE RESTRICT,
    relevance_score NUMERIC(3,2) CHECK (relevance_score >= 0 AND relevance_score <= 1),
    asserted_activity_id UUID, -- References provenance activity
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    PRIMARY KEY (edge_id, evidence_span_id)
);

CREATE INDEX idx_kg_edge_evidence_span ON kg_edge_evidence(evidence_span_id);

COMMENT ON TABLE kg_edge_evidence IS 'Links KG edges to evidence spans; enforces evidence requirement';

-- ============================================
-- 7) RAG PIPELINE LOGS
-- ============================================
-- Complete audit trail for every query through the system

-- Query initiation
CREATE TABLE rag_query (
    rag_query_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    query_text TEXT NOT NULL,
    query_hash_sha256 TEXT NOT NULL CHECK (query_hash_sha256 ~ '^[a-f0-9]{64}$'),
    session_id UUID, -- For grouping related queries
    request_metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_rag_query_session ON rag_query(session_id);
CREATE INDEX idx_rag_query_created ON rag_query(created_at);

COMMENT ON TABLE rag_query IS 'RAG query initiation log';

-- Retrieval results (what evidence was found)
CREATE TABLE rag_retrieval_result (
    retrieval_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rag_query_id UUID NOT NULL REFERENCES rag_query(rag_query_id) ON DELETE CASCADE,
    evidence_span_id UUID NOT NULL REFERENCES evidence_span(evidence_span_id) ON DELETE RESTRICT,
    rank INTEGER NOT NULL CHECK (rank > 0),
    score_lexical NUMERIC(5,4), -- Full-text search score
    score_vector NUMERIC(5,4), -- Vector similarity score
    score_final NUMERIC(5,4) NOT NULL, -- Combined/final score
    retrieval_method TEXT NOT NULL DEFAULT 'lexical', -- e.g., 'lexical', 'vector', 'hybrid'
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    CONSTRAINT unique_query_span_rank UNIQUE (rag_query_id, evidence_span_id, retrieval_method)
);

CREATE INDEX idx_retrieval_query ON rag_retrieval_result(rag_query_id);
CREATE INDEX idx_retrieval_span ON rag_retrieval_result(evidence_span_id);
CREATE INDEX idx_retrieval_score ON rag_retrieval_result(rag_query_id, score_final DESC);

COMMENT ON TABLE rag_retrieval_result IS 'Evidence retrieved for each query';

-- Validation gate (sufficiency check)
CREATE TYPE validation_verdict_enum AS ENUM (
    'pass',
    'fail_insufficient_evidence',
    'fail_untrusted_sources',
    'fail_other'
);

CREATE TABLE rag_validation (
    validation_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rag_query_id UUID NOT NULL UNIQUE REFERENCES rag_query(rag_query_id) ON DELETE CASCADE,
    sufficiency_score NUMERIC(3,2) NOT NULL CHECK (sufficiency_score >= 0 AND sufficiency_score <= 1),
    threshold_tau NUMERIC(3,2) NOT NULL CHECK (threshold_tau >= 0 AND threshold_tau <= 1),
    verdict validation_verdict_enum NOT NULL,
    fail_reason TEXT, -- e.g., 'insufficient_evidence', 'all_sources_untrusted', 'citation_verification_failed'
    evidence_count INTEGER NOT NULL DEFAULT 0,
    trusted_evidence_count INTEGER NOT NULL DEFAULT 0,
    validation_metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_validation_query ON rag_validation(rag_query_id);
CREATE INDEX idx_validation_verdict ON rag_validation(verdict);

COMMENT ON TABLE rag_validation IS 'Validation gate: decides if evidence is sufficient to generate answer';

-- Final answer (or abstention)
CREATE TYPE answer_verdict_enum AS ENUM (
    'answer',
    'abstain'
);

CREATE TABLE rag_answer (
    answer_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rag_query_id UUID NOT NULL UNIQUE REFERENCES rag_query(rag_query_id) ON DELETE CASCADE,
    verdict answer_verdict_enum NOT NULL,
    answer_json JSONB NOT NULL, -- Structured answer with citations per statement
    statements_count INTEGER NOT NULL DEFAULT 0,
    citations_count INTEGER NOT NULL DEFAULT 0,
    generation_time_ms INTEGER, -- Time to generate answer
    model_version TEXT, -- LLM version used (if any)
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_answer_query ON rag_answer(rag_query_id);
CREATE INDEX idx_answer_verdict ON rag_answer(verdict);

COMMENT ON TABLE rag_answer IS 'Final answer with statement-level citations or abstention reason';
COMMENT ON COLUMN rag_answer.answer_json IS 'JSON following rag_answer.json schema contract';

-- ============================================
-- INTEGRITY VIEWS AND FUNCTIONS
-- ============================================

-- View: Edges without evidence (should always return 0 rows)
CREATE VIEW v_kg_edges_without_evidence AS
SELECT e.*
FROM kg_edge e
LEFT JOIN kg_edge_evidence ee ON e.edge_id = ee.edge_id
WHERE ee.edge_id IS NULL;

COMMENT ON VIEW v_kg_edges_without_evidence IS 'Finds edges violating the evidence requirement (should be empty)';

-- View: Full provenance chain for evidence spans
CREATE VIEW v_evidence_span_full_provenance AS
SELECT 
    es.evidence_span_id,
    es.text_unit_id,
    es.start_byte,
    es.end_byte,
    es.snippet_text,
    es.snippet_utf8_sha256,
    tu.canonical_id,
    tu.unit_type,
    sd.source_id,
    sd.work_title,
    sd.edition,
    sd.license_id,
    sd.license_url,
    sd.trust_status
FROM evidence_span es
JOIN text_unit tu ON es.text_unit_id = tu.text_unit_id
JOIN source_document sd ON tu.source_id = sd.source_id;

COMMENT ON VIEW v_evidence_span_full_provenance IS 'Complete provenance chain from span to source';

-- ============================================
-- MIGRATION METADATA
-- ============================================

-- Create schema_migrations table if not exists (for idempotency)
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    description TEXT
);

INSERT INTO schema_migrations (version, applied_at, description)
VALUES ('0001_init', NOW(), 'Initial schema for evidence-first Islamic knowledge system');
