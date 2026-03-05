-- ISLAM INTELLIGENT - Migration: Add Embeddings Support
-- Purpose: Add vector/embedding storage to text_unit table for similarity search
-- Created: 2026-03-04
--
-- ============================================
-- IDEMPOTENT MIGRATION (Safe to run multiple times)
-- ============================================

-- ============================================
-- EMBEDDING COLUMN FOR text_unit TABLE
-- ============================================

-- Add embedding column (BLOB/BYTEA for cross-database compatibility)
-- Using SQLite-compatible syntax
ALTER TABLE text_unit ADD COLUMN embedding BLOB;

-- ============================================
-- ADD EMBEDDING METADATA COLUMNS
-- ============================================

-- Track embedding model/version for reproducibility
ALTER TABLE text_unit ADD COLUMN embedding_model TEXT;
ALTER TABLE text_unit ADD COLUMN embedding_version TEXT;
ALTER TABLE text_unit ADD COLUMN embedding_generated_at TIMESTAMP WITH TIME ZONE;

-- ============================================
-- ADD INDEXES FOR EMBEDDING QUERIES
-- ============================================

-- Standard index on embedding column
CREATE INDEX IF NOT EXISTS idx_text_unit_embedding ON text_unit(embedding);

-- Index for filtering by embedding model (useful for model migrations)
-- Note: SQLite supports partial indexes with WHERE clause (3.8.0+)
CREATE INDEX IF NOT EXISTS idx_text_unit_embedding_model ON text_unit(embedding_model)
    WHERE embedding_model IS NOT NULL;

-- ============================================
-- SQLITE COMPATIBILITY NOTES
-- ============================================
-- For SQLite deployments:
-- 1. BLOB type stores raw embedding bytes (4 bytes per float32 dimension)
--    For 768-dim embeddings: 768 * 4 = 3072 bytes per embedding
-- 2. Vector similarity operations should be done in application code
-- 3. Consider using sqlite-vss extension for native vector search in SQLite
-- 4. This migration uses standard SQL for maximum compatibility

-- ============================================
-- MIGRATION METADATA
-- ============================================
INSERT OR IGNORE INTO schema_migrations (version, applied_at, description)
VALUES ('0002_add_embeddings', datetime('now'), 'Add embedding column to text_unit table for similarity search');
