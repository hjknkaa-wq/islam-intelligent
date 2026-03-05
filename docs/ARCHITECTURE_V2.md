# Architecture v2

A provenance-first Islamic knowledge intelligence platform with deterministic pipelines, explicit citations, and no hallucinated sources.

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture Layers](#architecture-layers)
3. [Component Details](#component-details)
4. [Data Flow](#data-flow)
5. [Database Schema](#database-schema)
6. [API Structure](#api-structure)
7. [Verification System](#verification-system)
8. [Security Considerations](#security-considerations)
9. [Performance Characteristics](#performance-characteristics)
10. [Future Extensions](#future-extensions)

## System Overview

Islam Intelligent is built on a simple principle: every claim must be traceable to explicit source evidence. The system combines a FastAPI backend, Next.js frontend, PostgreSQL database with pgvector, and optional Neo4j for knowledge graph storage.

### Core Design Principles

1. **Provenance-First**: Every piece of data has a complete audit trail from ingestion to answer generation
2. **Evidence-Based Abstention**: The system abstains when evidence is insufficient rather than hallucinating answers
3. **Trust Gating**: Only sources marked as `trusted` can be cited in answers
4. **Hash Verification**: All evidence spans include SHA-256 hashes for cryptographic verification
5. **Append-Only Versioning**: Source documents use append-only updates with complete version history

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend Layer                       │
│  Next.js + React + TypeScript                              │
│  - Query interface                                          │
│  - Citation display                                         │
│  - Evidence highlighting                                    │
│  - RTL support for Arabic                                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                         API Layer                           │
│  FastAPI + SQLAlchemy + Pydantic                           │
│  - REST endpoints                                           │
│  - OpenAPI/Swagger docs                                     │
│  - RAG pipeline orchestration                              │
│  - Request/response validation                              │
│  - Authentication (future)                                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Pipeline Layer                         │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   RAG Core   │  │  Retrieval   │  │  Verification│     │
│  │  - Abstain   │  │  - Hybrid    │  │  - Citations │     │
│  │  - Generate  │  │  - Vector    │  │  - Hashes    │     │
│  │  - Validate  │  │  - Lexical   │  │  - Links     │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Provenance │  │      KG      │  │  Cost Gov    │     │
│  │  - Hash chain│  │  - Entities  │  │  - Budget    │     │
│  │  - W3C PROV  │  │  - Edges     │  │  - Routing   │     │
│  │  - Activities│  │  - Evidence  │  │  - Tracking  │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              Advanced Retrieval                       │  │
│  │  - Cross-Encoder Reranking                           │  │
│  │  - HyDE (Hypothetical Document Embeddings)          │  │
│  │  - Query Expansion                                   │  │
│  │  - Multi-Query Search                                │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Storage Layer                          │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  PostgreSQL  │  │   pgvector   │  │    Neo4j     │     │
│  │  - Sources   │  │  - Embeddings│  │  - KG graph  │     │
│  │  - Text units│  │  - Similarity│  │  - Relations │     │
│  │  - Evidence  │  │  - Search    │  │  - Queries   │     │
│  │  - Provenance│  │  - HNSW index│  │              │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. RAG Pipeline (`apps/api/src/islam_intelligent/rag/`)

The core RAG (Retrieval-Augmented Generation) pipeline follows a strict evidence-first flow:

#### Pipeline Stages

```
┌─────────────┐    ┌──────────────┐    ┌──────────────┐
│   Query     │───▶│   Retrieve   │───▶│    Filter    │
│   Input     │    │   (Hybrid)   │    │   Trusted    │
└─────────────┘    └──────────────┘    └──────────────┘
                                              │
                                              ▼
┌─────────────┐    ┌──────────────┐    ┌──────────────┐
│   Answer    │◄───│   Generate   │◄───│   Validate   │
│  (Output)   │    │  (Optional)  │    │ Sufficiency  │
└─────────────┘    └──────────────┘    └──────────────┘
                                              │
                                              ▼
                                       ┌──────────────┐
                                       │   Abstain    │
                                       │ (If needed)  │
                                       └──────────────┘
```

1. **Retrieve**: Hybrid search combining lexical (BM25) and vector similarity
2. **Filter Trusted**: Only `trust_status='trusted'` sources pass through
3. **Validate Sufficiency**: Check if evidence meets quality thresholds
4. **Generate**: Create answer with citations (or abstain)
5. **Verify**: Post-generation citation and hash verification

```python
# Simplified pipeline flow
class RAGPipeline:
    def query(self, query: str) -> AnswerContract:
        retrieved = self.retrieve(query)           # Stage 1
        trusted = self._filter_trusted(retrieved)  # Stage 2
        is_sufficient, score = self.validate_sufficiency(trusted)  # Stage 3
        if not is_sufficient:
            return AnswerContract(verdict="abstain", ...)
        statements = self._generate_statements(query, trusted)     # Stage 4
        if not self._verify_statements(statements, trusted):        # Stage 5
            return AnswerContract(verdict="abstain", ...)
        return AnswerContract(verdict="answer", statements=statements, ...)
```

#### Abstention Conditions

The pipeline abstains (returns `verdict="abstain"`) when:

- **Insufficient Evidence**: Fewer than 2 results or low confidence scores
- **Untrusted Sources**: Retrieved results are from untrusted sources
- **Verification Failed**: Post-generation checks fail
- **Citation Mismatch**: Generated citations don't match retrieved evidence

### 2. Retrieval System (`apps/api/src/islam_intelligent/rag/retrieval/`)

#### Hybrid Search

Combines lexical and vector retrieval with configurable weights:

```python
results = search_hybrid(
    query="What does the Quran say about patience?",
    limit=10,
    lexical_weight=0.7,  # 70% lexical, 30% vector
    vector_weight=0.3
)
```

**Lexical Search**: BM25-style full-text search on canonical text

**Vector Search**: Cosine similarity on embeddings (requires pgvector)

#### Cross-Encoder Reranking

Optional second-stage reranking for improved result quality:

```python
from islam_intelligent.rag.rerank import CrossEncoderReranker

reranker = CrossEncoderReranker(model_name="cross-encoder/ms-marco-MiniLM-L-6-v2")
reranked = reranker.rerank(query="question", results=initial_results, top_k=5)
```

#### Multi-Query Expansion

Optional query expansion generates variations to improve recall:

```python
results = search_hybrid_multi_query(
    query="patience in Islam",
    limit=10,
    num_variations=5  # Generate 5 query variations
)
```

#### HyDE (Hypothetical Document Embeddings)

Uses LLM to generate hypothetical documents for better semantic matching:

```python
from islam_intelligent.rag.retrieval.hyde import HyDEGenerator

hyde = HyDEGenerator(model="gpt-4o-mini")
hypothetical_doc = hyde.generate("What is the concept of sabr in Islam?")
# Use hypothetical_doc for vector search
```

### 3. Provenance System (`apps/api/src/islam_intelligent/provenance/`)

Implements W3C PROV-DM (PROV Data Model) for complete audit trails:

#### Core Entities

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  ProvEntity  │────▶│ ProvActivity │────▶│  ProvAgent   │
│  (Document)  │     │ (Process)    │     │ (Software)   │
└──────────────┘     └──────────────┘     └──────────────┘
        │                    │
        │                    │
        ▼                    ▼
┌──────────────┐     ┌──────────────┐
│ProvGeneration│     │  ProvUsage   │
│  (Created)   │     │  (Consumed)  │
└──────────────┘     └──────────────┘
```

- **ProvEntity**: Things in the world (documents, text units, spans)
- **ProvActivity**: Processes that occur over time (ingestion, transformation)
- **ProvAgent**: Responsible parties (software, users, organizations)
- **ProvGeneration**: When an entity was created
- **ProvUsage**: When an activity used an entity
- **ProvDerivation**: Transformation lineage

#### Hash Chain

Activities maintain a tamper-evident hash chain:

```python
activity_hash = SHA256(prev_activity_hash + activity_params + git_sha)
```

This allows verification that the provenance chain hasn't been altered:

```python
from islam_intelligent.provenance.hash_chain import verify_hash_chain

is_valid, message = verify_hash_chain(session)
# Returns: (True, "verified") or (False, "mismatch explanation")
```

### 4. Knowledge Graph (`apps/api/src/islam_intelligent/kg/`)

A lightweight knowledge graph for entity relationships:

#### Entity Model

```python
class KgEntity:
    entity_id: UUID          # Primary key
    entity_type: str         # "person", "concept", "event", "location"
    canonical_name: str      # Standard name
    aliases_json: str        # Alternative names [JSON array]
    description: str         # Optional description
```

#### Edge Model with Evidence

Every edge MUST link to at least one evidence span:

```python
class KgEdge:
    edge_id: UUID
    subject_entity_id: UUID
    predicate: str           # e.g., "authored", "mentions", "is_a"
    object_entity_id: UUID   # Either entity or literal
    object_literal: str
    confidence_score: float  # 0.0 to 1.0

class KgEdgeEvidence:
    edge_id: UUID
    evidence_span_id: UUID   # REQUIRED - every edge needs evidence
    relevance_score: float
```

The `v_kg_edges_without_evidence` view finds any edges violating this constraint (should always be empty).

#### Graph Query Example

```python
# Get all edges for an entity
GET /kg/edges?entity_id=abc123

# Response
{
  "edges": [
    {
      "edge_id": "edge_001",
      "subject_entity_id": "entity_abc",
      "predicate": "authored",
      "object_entity_id": "entity_def",
      "evidence_span_ids": ["span_001", "span_002"],
      "confidence": 0.95
    }
  ]
}
```

### 5. Source Registry (`apps/api/src/islam_intelligent/ingest/`)

Append-only versioning for source documents:

#### Version Chain

```
Version 1 (source_id="quran_tanzil")
    ↓ supersedes_source_id
Version 2 (source_id="quran_tanzil", supersedes_version=1)
    ↓ supersedes_source_id
Version 3 (source_id="quran_tanzil", supersedes_version=2)
```

Old versions remain accessible forever. This enables:

- Complete audit history
- Reproducible research
- Safe updates without data loss

#### Trust Status

Sources have a `trust_status` field:

- `untrusted`: Default, cannot be cited in answers
- `trusted`: Can be cited (requires explicit promotion)

```python
# Promote a source to trusted
python scripts/set_source_trust.py <source_id> --trust

# Retract a source
python scripts/retract_source.py <source_id> --reason "erroneous data"
```

### 6. Cost Governance (`apps/api/src/islam_intelligent/cost_governance.py`)

Comprehensive cost control for LLM and embedding usage:

#### Features

- **Budget Enforcement**: Daily and weekly spend caps
- **Cost Estimation**: Pre-execution cost prediction
- **Model Routing**: Automatic tier selection based on query complexity
- **Alerting**: Threshold-based notifications
- **Persistence**: All usage logged to database

#### Model Tiers

| Tier | Model | Use Case |
|------|-------|----------|
| Cheap | gpt-4o-mini | Simple queries, budget pressure |
| Standard | gpt-4.1-mini | Normal complexity |
| Expensive | gpt-4o | Complex analysis, high accuracy needed |

#### Complexity Scoring

```python
complexity = assess_complexity("Compare the tafsir of Ibn Kathir and Al-Tabari")
# Returns: 0.0 to 1.0 based on token count, hint words, structure
```

#### Usage Example

```python
from islam_intelligent.cost_governance import CostGovernanceService, BudgetManager

budget_mgr = BudgetManager(daily_budget=10.0, weekly_budget=50.0)
governance = CostGovernanceService(budget_manager=budget_mgr)

plan = governance.plan_query(query="What is zakat?")
if plan.allowed:
    # Execute query with plan.route.model
    # ... after execution ...
    governance.record_usage(query=query, estimate=plan.estimate, route=plan.route)
else:
    # Handle budget exceeded
    print(plan.degradation_message)
```

## Data Flow

### Ingestion Flow

```
Raw Source (JSON/XML/Text)
    ↓
Text Unit Builder
    ↓
Canonical ID Assignment (quran:1:1, hadith:bukhari:sahih:1)
    ↓
Unicode NFC Normalization
    ↓
Hash Computation (SHA-256)
    ↓
Source Registry (append-only)
    ↓
Provenance Recording (activity + generation)
    ↓
Text Unit Storage
    ↓
Evidence Span Creation (optional)
    ↓
Embedding Generation (optional, if vector enabled)
```

### Query Flow

```
User Query
    ↓
Query Expansion (optional)
    ↓
Hybrid Retrieval (lexical + vector)
    ↓
Cross-Encoder Reranking (optional)
    ↓
Trust Filtering (trusted sources only)
    ↓
Sufficiency Validation
    ↓
┌──────────────────────────────────────┐
│  Evidence Sufficient?                │
│  Yes → Generate Answer               │
│  No  → Abstain                       │
└──────────────────────────────────────┘
    ↓
Citation Verification
    ↓
Answer with Citations
    ↓
Provenance Recording (rag_query, rag_retrieval_result, rag_answer)
```

## Database Schema

### Core Tables

| Table | Purpose |
|-------|---------|
| `source_document` | Source registry with versioning |
| `text_unit` | Canonical text units (ayat, hadith) |
| `evidence_span` | Byte-offset evidence with hash verification |
| `kg_entity` | Knowledge graph entities |
| `kg_edge` | Relationships between entities |
| `kg_edge_evidence` | Junction: edges to evidence spans |
| `prov_entity` | W3C PROV entities |
| `prov_activity` | W3C PROV activities with hash chain |
| `prov_generation` | Entity creation events |
| `rag_query` | Query audit log |
| `rag_retrieval_result` | Retrieved evidence per query |
| `rag_answer` | Generated answers or abstentions |
| `cost_usage_log` | Cost tracking records |
| `cost_alert_event` | Budget alert history |

### Key Constraints

- **Canonical IDs**: Enforced regex patterns (quran:X:Y, hadith:collection:system:number)
- **Evidence Requirement**: Every KG edge must have >= 1 evidence span
- **Trust Gating**: RAG only uses `trust_status='trusted'` sources
- **Hash Verification**: Evidence spans include SHA-256 for cryptographic integrity

### Entity Relationship Diagram

```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│ source_document │       │    text_unit    │       │  evidence_span  │
├─────────────────┤       ├─────────────────┤       ├─────────────────┤
│ source_id (PK)  │──────▶│ text_unit_id    │──────▶│ span_id (PK)    │
│ version         │       │ source_id (FK)  │       │ text_unit_id(FK)│
│ content_sha256  │       │ canonical_id    │       │ start_byte      │
│ trust_status    │       │ content         │       │ end_byte        │
└─────────────────┘       │ content_sha256  │       │ snippet_sha256  │
                          └─────────────────┘       └─────────────────┘
                                   │                         │
                                   │                         │
                                   ▼                         ▼
                          ┌─────────────────┐       ┌─────────────────┐
                          │  kg_entity      │       │  kg_edge        │
                          ├─────────────────┤       ├─────────────────┤
                          │ entity_id (PK)  │       │ edge_id (PK)    │
                          │ entity_type     │       │ subject_id (FK) │
                          │ canonical_name  │       │ predicate       │
                          └─────────────────┘       │ object_id (FK)  │
                                                    └─────────────────┘
```

## API Structure

### Main Routes (`apps/api/src/islam_intelligent/api/routes/`)

| Route | Purpose | Methods |
|-------|---------|---------|
| `/sources` | Source document CRUD | GET, POST, PUT |
| `/spans` | Evidence span management | GET, POST |
| `/kg/entities` | Knowledge graph entities | GET, POST |
| `/kg/edges` | Knowledge graph relationships | GET, POST |
| `/rag/query` | Query the RAG pipeline | POST |
| `/evidence` | Evidence lookup and verification | GET |
| `/health` | Health check endpoint | GET |

### Example: RAG Query

Request:

```bash
curl -X POST http://localhost:8000/rag/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What does the Quran say about patience?",
    "max_results": 10
  }'
```

Response:

```json
{
  "verdict": "answer",
  "statements": [
    {
      "text": "The Quran mentions patience (sabr) in many verses, particularly emphasizing its importance during difficult times.",
      "citations": [
        {
          "evidence_span_id": "span_abc123",
          "canonical_id": "quran:2:153",
          "snippet": "O you who have believed, seek help through patience and prayer..."
        },
        {
          "evidence_span_id": "span_def456",
          "canonical_id": "quran:3:200",
          "snippet": "O you who have believed, persevere and endure..."
        }
      ]
    }
  ],
  "retrieved_count": 8,
  "sufficiency_score": 0.85,
  "abstain_reason": null,
  "fail_reason": null
}
```

### Example: Source Management

```bash
# Create a source
curl -X POST http://localhost:8000/sources \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "tafsir",
    "title": "Tafsir Ibn Kathir",
    "author": "Ibn Kathir",
    "content": {"text": "..."}
  }'

# Get source manifest
curl http://localhost:8000/sources/quran_tanzil/manifest
```

## Verification System

The `scripts/verify_all.py` script provides comprehensive verification:

1. **Schema Validation**: SQL and JSON schema compliance
2. **Security Audit**: Check for secrets, unsafe patterns
3. **Database Integrity**: FK constraints, orphan records
4. **Provenance Verification**: Hash chain integrity
5. **Manifest Verification**: Source document hashes
6. **Invariant Checking**: Evidence requirements, trust status

Run: `python scripts/verify_all.py`

### Individual Verification Scripts

```bash
# Verify provenance hash chain
python scripts/verify_hash_chain.py

# Verify RAG logs
python scripts/verify_rag_logs.py

# Verify license gate
python scripts/verify_license_gate.py

# Security audit
python scripts/security_audit.py

# Database smoke test
python scripts/db_smoke.py
```

## Security Considerations

- **No Secrets in Code**: All credentials via environment variables
- **Hash Verification**: Cryptographic integrity for all evidence
- **Trust Gating**: Untrusted sources cannot affect answers
- **Input Validation**: Strict limits on query length, result counts
- **SQL Injection Protection**: Parameterized queries throughout
- **Append-Only Data**: Immutable audit trail
- **License Compliance**: Automated license gate verification

## Performance Characteristics

| Operation | Latency | Notes |
|-----------|---------|-------|
| Lexical search | ~10-50ms | BM25 on indexed text |
| Vector search | ~20-100ms | Cosine similarity with pgvector |
| Hybrid search | ~30-150ms | Combined + ranking |
| Reranking | ~50-200ms | Cross-encoder scoring |
| RAG query (mock) | ~50-200ms | No LLM call |
| RAG query (LLM) | ~500-2000ms | With gpt-4o-mini |
| Citation verification | ~5-20ms | Hash checks |

### Scalability Targets

- **Sources**: 1,000+ source documents
- **Text Units**: 100,000+ ayat and hadith
- **Embeddings**: 1M+ vectors (pgvector limit)
- **Concurrent Queries**: 50+ QPS
- **Storage**: ~10GB for full dataset

## Future Extensions

- **Multi-language Support**: Beyond Arabic and English
- **Advanced NER**: Named entity recognition for KG population
- **Sanad Analysis**: Hadith chain verification
- **Cross-reference Engine**: Automatic linking between sources
- **Real-time Ingestion**: Streaming updates from external sources
- **Graph Database**: Full Neo4j integration for complex queries
- **Distributed Deployment**: Kubernetes and horizontal scaling
