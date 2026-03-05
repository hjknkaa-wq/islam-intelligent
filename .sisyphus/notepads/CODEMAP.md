# CODEMAP: Islam Intelligent RAG System

## Module Structure

```
islam_intelligent/
├── api/
│   └── routes/
│       └── rag.py (API endpoint - imports RAGPipeline)
├── rag/
│   ├── pipeline/
│   │   └── core.py (19 methods, God Class)
│   ├── retrieval/
│   │   ├── embeddings.py (LRU cache)
│   │   ├── hybrid.py (search orchestration)
│   │   ├── hyde.py (query expansion)
│   │   ├── lexical.py (N+1 queries)
│   │   ├── query_expander.py (variations)
│   │   └── vector.py (full table scan)
│   ├── rerank/
│   │   └── cross_encoder.py (reranking)
│   ├── verify/
│   │   ├── citation_verifier.py
│   │   └── faithfulness.py (LLM verification)
│   ├── generator.py
│   └── metrics.py
├── cost_governance.py
└── config.py
```

## Dependency Graph

### High Impact Files
```
rag.py (API endpoint)
  ↓
pipeline/core.py (God Class - 19 methods)
  ↓ ←→ retrieval/hybrid.py
  ↓ ←→ retrieval/vector.py (ISSUE: full scan)
  ↓ ←→ retrieval/lexical.py (ISSUE: N+1)
  ↓ ←→ retrieval/hyde.py
  ↓ ←→ retrieval/query_expander.py
  ↓ ←→ rerank/cross_encoder.py
  ↓ ←→ verify/faithfulness.py
  ↓ ←→ cost_governance.py
  ↓ ←→ metrics.py
  ↓
generator.py
```

### Impact Zones

#### Zone 1: Critical (High Risk)
| File | Dependencies | Test Coverage |
|------|--------------|---------------|
| pipeline/core.py | 15+ | 85% |
| retrieval/vector.py | 3 | 70% |
| retrieval/lexical.py | 3 | 70% |

#### Zone 2: Medium Risk
| File | Dependencies | Test Coverage |
|------|--------------|---------------|
| cost_governance.py | 2 | 80% |
| verify/faithfulness.py | 3 | 75% |
| api/routes/rag.py | 1 | 90% |

#### Zone 3: Low Risk
| File | Dependencies | Test Coverage |
|------|--------------|---------------|
| rerank/cross_encoder.py | 2 | 85% |
| retrieval/hyde.py | 2 | 90% |
| retrieval/query_expander.py | 1 | 95% |

## Refactoring Targets

### 1. pipeline/core.py (God Class)
**Current**: 19 methods, 814 lines
**Target**: Extract to:
- RetrievalCoordinator
- GenerationCoordinator  
- VerificationCoordinator
- MetricsCoordinator

### 2. retrieval/vector.py (Performance)
**Current**: Full table scan
**Target**: Use HNSW index properly

### 3. retrieval/lexical.py (Performance)
**Current**: N+1 query pattern
**Target**: Single query with CTE

## Safe Refactoring Zones
- retrieval/query_expander.py (isolated)
- rerank/cross_encoder.py (isolated)
- retrieval/hyde.py (isolated)

## Risky Refactoring Zones
- pipeline/core.py (many dependencies)
- api/routes/rag.py (API contract)
