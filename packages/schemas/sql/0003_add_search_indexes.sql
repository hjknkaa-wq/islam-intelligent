-- ISLAM INTELLIGENT - Migration: Add Search Indexes
-- Purpose: Add PostgreSQL full-text and ANN indexes for text_unit retrieval.
-- Created: 2026-03-05
--
-- Target: PostgreSQL 15+ with pgvector extension.
-- Idempotency: all DDL uses IF NOT EXISTS and migration metadata uses ON CONFLICT.

-- ============================================
-- DATABASE EXTENSIONS
-- ============================================
-- Ensure pgvector is available before creating vector columns/indexes.
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================
-- SEARCH COLUMNS
-- ============================================
-- Full-text search tsvector derived from text_canonical.
ALTER TABLE text_unit
    ADD COLUMN IF NOT EXISTS text_search_tsv tsvector;

-- ANN vector column (1536 dims matches EMBEDDING_DIMENSION default in API config).
ALTER TABLE text_unit
    ADD COLUMN IF NOT EXISTS embedding_vector vector(1536);

-- ============================================
-- BACKFILL EXISTING DATA
-- ============================================
-- Backfill full-text vectors for existing rows.
UPDATE text_unit
SET text_search_tsv = to_tsvector('simple', COALESCE(text_canonical, ''))
WHERE text_search_tsv IS DISTINCT FROM to_tsvector('simple', COALESCE(text_canonical, ''));

-- Best-effort backfill for embeddings if legacy values are already in
-- pgvector-compatible text form (e.g. "[0.1, 0.2, ...]").
UPDATE text_unit
SET embedding_vector = embedding::text::vector
WHERE embedding_vector IS NULL
  AND embedding IS NOT NULL
  AND embedding::text ~ '^\[[0-9eE+.,\s-]+\]$';

-- ============================================
-- INDEXES
-- ============================================
-- GIN index for lexical full-text search.
CREATE INDEX IF NOT EXISTS idx_text_unit_text_search_tsv_gin
    ON text_unit USING gin (text_search_tsv);

-- HNSW index for cosine-distance ANN search.
CREATE INDEX IF NOT EXISTS idx_text_unit_embedding_vector_hnsw
    ON text_unit USING hnsw (embedding_vector vector_cosine_ops)
    WHERE embedding_vector IS NOT NULL;

-- ============================================
-- MIGRATION METADATA
-- ============================================
INSERT INTO schema_migrations (version, applied_at, description)
VALUES (
    '0003_add_search_indexes',
    NOW(),
    'Add text_search_tsv + GIN and embedding_vector + HNSW indexes on text_unit'
)
ON CONFLICT (version) DO NOTHING;

-- ============================================
-- ROLLBACK (MANUAL)
-- ============================================
-- DROP INDEX IF EXISTS idx_text_unit_embedding_vector_hnsw;
-- DROP INDEX IF EXISTS idx_text_unit_text_search_tsv_gin;
-- ALTER TABLE text_unit DROP COLUMN IF EXISTS embedding_vector;
-- ALTER TABLE text_unit DROP COLUMN IF EXISTS text_search_tsv;
-- DELETE FROM schema_migrations WHERE version = '0003_add_search_indexes';
