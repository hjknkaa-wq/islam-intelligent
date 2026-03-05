# MILESTONE 3: Real LLM Integration + Vector Search

## TL;DR

**Summary**: Enable real LLM generation and implement vector search for hybrid retrieval
**Deliverables**: Working LLM integration + pgvector search + hybrid retrieval
**Effort**: XL
**Critical Path**: Config → LLM → Vector → Hybrid → Test

---

## Context

### From PROPOSAL.md
- **Milestone 3**: "Integrasi LLM nyata + vector search" | 1-2 minggu | 🔲 TODO

### Current Status (from AGENTS.md)
- RAG uses **mock LLM** (`_mock_generate()`) - returns generic text
- Vector search **DISABLED** - `is_vector_available()` returns `False`
- Hybrid search falls back to **lexical-only** when vector unavailable
- Config: `RAG_ENABLE_LLM=false` (default)

### Root Cause Analysis
1. **LLM**: No API key configured, `enable_llm=False` by default
2. **Vector**: No embedding model, pgvector extension not enabled in SQLite dev

---

## Work Objectives

### Core Objective
Enable the system to:
1. Use **real LLM** (OpenAI or compatible) for answer generation
2. Use **vector embeddings** for semantic search
3. Combine lexical + vector in **hybrid retrieval**

### Must Have
- [ ] `RAG_ENABLE_LLM=true` works with real API calls
- [ ] Vector search returns meaningful results (not empty)
- [ ] Hybrid retrieval combines lexical + vector scores
- [ ] Abstention still works correctly with real LLM
- [ ] Citation verification still enforces rules

### Must NOT Have
- [ ] No hallucination - still enforce citations
- [ ] No API key leakage in logs/code
- [ ] No degradation of existing functionality

---

## Implementation Tasks

### Phase 1: LLM Integration (Days 1-3)

#### Task M3-1: Enable LLM Configuration
**What**:
- Update `apps/api/src/islam_intelligent/config.py` to add vector config
- Add environment variables: `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION`

**Files**:
- `apps/api/src/islam_intelligent/config.py`

**Acceptance**:
- [ ] Config accepts new environment variables
- [ ] Default values work for development

#### Task M3-2: Implement Real LLM Generator
**What**:
- Verify `LLMGenerator` in `generator.py` works with real API
- Add error handling for API failures
- Ensure fallback to mock still works

**Files**:
- `apps/api/src/islam_intelligent/rag/generator.py`

**Acceptance**:
- [ ] With `OPENAI_API_KEY`, generates real answers
- [ ] Without key or on error, falls back to mock
- [ ] Citations still included in output

#### Task M3-3: Add LLM Integration Tests
**What**:
- Add test for LLM availability detection
- Add test for fallback behavior
- Add test for citation format in LLM output

**Files**:
- `apps/api/tests/test_llm_integration.py` (new)

**Acceptance**:
- [ ] Tests pass for mock mode
- [ ] Tests handle real API (mocked)

---

### Phase 2: Vector Search Implementation (Days 4-7)

#### Task M3-4: Add Embedding Column to Schema
**What**:
- Add `embedding` column to text_unit table
- Add vector index for similarity search

**Files**:
- `packages/schemas/sql/0001_init.sql` (or new migration)
- `apps/api/src/islam_intelligent/domain/models.py`

**Acceptance**:
- [ ] Schema allows vector storage
- [ ] Index created for similarity search

#### Task M3-5: Implement Embedding Generation
**What**:
- Create embedding generator using OpenAI text-embedding-3-small
- Support configurable embedding model
- Cache embeddings for performance

**Files**:
- `apps/api/src/islam_intelligent/rag/retrieval/embeddings.py` (new)

**Acceptance**:
- [ ] Generates embeddings for text
- [ ] Caches results

#### Task M3-6: Implement Vector Search
**What**:
- Update `vector.py` to perform actual similarity search
- Use pgvector for SQLite (or numpy for in-memory)

**Files**:
- `apps/api/src/islam_intelligent/rag/retrieval/vector.py`

**Acceptance**:
- [ ] `is_vector_available()` returns True when configured
- [ ] `search_vector()` returns ranked results

#### Task M3-7: Update Hybrid Retrieval
**What**:
- Combine lexical and vector scores
- Weight configuration for hybrid search

**Files**:
- `apps/api/src/islam_intelligent/rag/retrieval/hybrid.py`

**Acceptance**:
- [ ] Hybrid returns combined results
- [ ] Weights configurable

---

### Phase 3: Testing & Verification (Days 8-14)

#### Task M3-8: Run Full Test Suite
**What**:
- Run all existing tests
- Verify no regression

**Command**:
```bash
PYTHONPATH=apps/api/src python -m pytest apps/api/tests -q
npm --prefix apps/ui test -- --run
```

**Acceptance**:
- [ ] All tests pass

#### Task M3-9: Run Eval Suite
**What**:
- Run `python scripts/run_eval.py --suite golden`
- Verify citation requirements still met

**Acceptance**:
- [ ] citation_required_pass_rate == 1.0
- [ ] abstention_f1 >= 0.95

#### Task M3-10: Manual Integration Test
**What**:
- Start services with real LLM
- Test query flow end-to-end
- Verify citations in response

**Acceptance**:
- [ ] Real LLM generates answer
- [ ] Citations present and verifiable

---

## Dependency Matrix

| Task | Depends On |
|------|------------|
| M3-1 | - |
| M3-2 | M3-1 |
| M3-3 | M3-2 |
| M3-4 | - |
| M3-5 | M3-4 |
| M3-6 | M3-5 |
| M3-7 | M3-6, M3-2 |
| M3-8 | M3-3, M3-7 |
| M3-9 | M3-8 |
| M3-10 | M3-9 |

---

## Configuration Reference

### Required Environment Variables

```bash
# LLM Configuration
RAG_ENABLE_LLM=true
OPENAI_API_KEY=sk-...  # Or use RAG_LLM_BASE_URL for alternatives

# Vector Configuration  
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSION=1536
```

### Alternative LLM Providers

```bash
# OpenAI
RAG_LLM_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=sk-...

# Ollama (local)
RAG_LLM_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama

# Other OpenAI-compatible
RAG_LLM_BASE_URL=<custom endpoint>
OPENAI_API_KEY=<key>
```

---

## Acceptance Criteria

### LLM Integration
- [ ] With `RAG_ENABLE_LLM=true` and valid API key, real LLM generates answers
- [ ] Without API key, falls back to mock (no crash)
- [ ] Every LLM-generated answer includes citations
- [ ] Abstention still triggers on insufficient evidence

### Vector Search
- [ ] Vector search returns results (not empty) when configured
- [ ] Embeddings generated and stored for text units
- [ ] Similarity search works with pgvector

### Hybrid Retrieval
- [ ] Combines lexical and vector results
- [ ] Configurable weighting
- [ ] Better results than lexical-only

### Overall
- [ ] All tests pass
- [ ] Eval suite passes thresholds
- [ ] No regression in existing functionality
- [ ] No API keys in logs

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| API key missing | Fallback to mock - no crash |
| Vector slow | Use caching, limit result set |
| LLM hallucination | Citation verification still enforced |
| Performance | Add timeouts, limit tokens |

---

## Commit Strategy

Each task should be atomic:
- `feat(config): add vector configuration env vars`
- `feat(llm): enable real LLM generation`
- `feat(vector): add pgvector similarity search`
- `feat(retrieval): implement hybrid search`
- `test: add LLM and vector integration tests`
