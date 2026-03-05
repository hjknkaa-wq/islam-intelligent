# Features Guide

Complete guide to all features in Islam Intelligent with descriptions, examples, and best practices.

## Table of Contents

1. [Core Features](#core-features)
2. [RAG Pipeline](#rag-pipeline)
3. [Provenance System](#provenance-system)
4. [Knowledge Graph](#knowledge-graph)
5. [Cost Governance](#cost-governance)
6. [Retrieval System](#retrieval-system)
7. [Source Management](#source-management)
8. [Verification Tools](#verification-tools)
9. [Advanced Features](#advanced-features)

## Core Features

### Evidence-First Architecture

Every answer in Islam Intelligent is backed by explicit source evidence. The system refuses to hallucinate answers when evidence is insufficient.

**Key Principles:**
- Every statement requires at least one citation
- Citations point to specific evidence spans with byte offsets
- SHA-256 hashes verify content integrity
- Trust gating ensures only verified sources are used

**Example:**
```json
{
  "verdict": "answer",
  "statements": [{
    "text": "The Quran mentions patience (sabr) as a virtue...",
    "citations": [{
      "evidence_span_id": "span_abc123",
      "canonical_id": "quran:2:153",
      "snippet": "O you who have believed, seek help through patience...",
      "snippet_utf8_sha256": "a1b2c3..."
    }]
  }]
}
```

### Abstention Mechanism

When evidence is insufficient, the system abstains rather than providing potentially incorrect information.

**Abstention Reasons:**
- `insufficient_evidence`: Not enough relevant sources found
- `untrusted_sources`: Found sources but none are marked trusted
- `citation_verification_failed`: Generated citations don't match evidence
- `verification_failed`: Post-generation checks failed

**Example Response:**
```json
{
  "verdict": "abstain",
  "statements": [],
  "abstain_reason": "insufficient_evidence",
  "abstain_details": "Found only 1 relevant passage. Minimum 2 required.",
  "retrieved_count": 1,
  "sufficiency_score": 0.35
}
```

## RAG Pipeline

### Pipeline Stages

The RAG (Retrieval-Augmented Generation) pipeline processes queries through multiple stages:

```
Query Input
    ↓
Query Expansion (optional)
    ↓
Hybrid Retrieval (lexical + vector)
    ↓
Cross-Encoder Reranking (optional)
    ↓
Trust Filtering
    ↓
Sufficiency Validation
    ↓
Answer Generation (or Abstention)
    ↓
Citation Verification
    ↓
Answer Output
```

### Query API

**Endpoint:** `POST /rag/query`

**Request:**
```json
{
  "query": "What does Islam say about charity?",
  "max_results": 10
}
```

**Response:**
```json
{
  "verdict": "answer",
  "statements": [
    {
      "text": "Charity (zakat and sadaqah) is one of the Five Pillars of Islam...",
      "citations": [
        {
          "evidence_span_id": "span_001",
          "canonical_id": "quran:2:110",
          "snippet": "And establish prayer and give zakat..."
        },
        {
          "evidence_span_id": "span_002",
          "canonical_id": "hadith:bukhari:sahih:1",
          "snippet": "The Prophet said: Charity does not decrease wealth..."
        }
      ]
    }
  ],
  "retrieved_count": 8,
  "sufficiency_score": 0.85
}
```

### Configuration Options

```python
# Pipeline configuration
RAGConfig(
    sufficiency_threshold=0.6,      # Minimum score to proceed
    max_retrieval=10,                # Maximum documents to retrieve
    min_citations_per_statement=1,   # Required citations per statement
    enable_llm=True,                 # Enable LLM generation
    llm_model="gpt-4o-mini",         # Model to use
    llm_temperature=0.2,             # Sampling temperature
    enable_query_expansion=True,     # Enable multi-query
    query_expansion_variations=5     # Number of query variations
)
```

## Provenance System

### W3C PROV-DM Implementation

Complete audit trail tracking all data transformations from source to answer.

**Core Entities:**
- **ProvEntity**: Things in the world (documents, text units, spans)
- **ProvActivity**: Processes that occur over time
- **ProvAgent**: Responsible parties (software, users)
- **ProvGeneration**: When an entity was created
- **ProvUsage**: When an activity used an entity

### Hash Chain Verification

Tamper-evident chain of SHA-256 hashes linking all provenance activities.

```python
from islam_intelligent.provenance.hash_chain import verify_hash_chain

is_valid, message = verify_hash_chain(session)
if is_valid:
    print("Provenance chain verified - no tampering detected")
else:
    print(f"Chain verification failed: {message}")
```

**How it works:**
```
Activity 1: hash_a = SHA256(activity_params + git_sha)
Activity 2: hash_b = SHA256(hash_a + activity_params + git_sha)
Activity 3: hash_c = SHA256(hash_b + activity_params + git_sha)
```

### Viewing Provenance

**API:** `GET /evidence/{span_id}/provenance`

**Response:**
```json
{
  "evidence_span_id": "span_abc123",
  "created_by_activity": "act_ingest_001",
  "derived_from": [
    {
      "entity_id": "text_unit_xyz",
      "entity_type": "text_unit",
      "activity": "act_segment_001"
    }
  ],
  "hash_chain": {
    "verified": true,
    "activities_in_chain": 5
  }
}
```

## Knowledge Graph

### Entity Management

Create and manage entities in the knowledge graph.

**Create Entity:**
```bash
POST /kg/entities
{
  "entity_type": "person",
  "canonical_name": "Prophet Muhammad",
  "aliases": ["Muhammad", "Rasulullah", "The Prophet"],
  "description": "The final prophet in Islam"
}
```

**Response:**
```json
{
  "entity_id": "ent_abc123",
  "entity_type": "person",
  "canonical_name": "Prophet Muhammad",
  "aliases": ["Muhammad", "Rasulullah", "The Prophet"],
  "description": "The final prophet in Islam",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### Edge Creation with Evidence

Every relationship (edge) must be backed by evidence.

**Create Edge:**
```bash
POST /kg/edges
{
  "subject_entity_id": "ent_abc123",
  "predicate": "authored",
  "object_entity_id": "ent_def456",
  "evidence_span_ids": ["span_001", "span_002"],
  "confidence": 0.95
}
```

**Required:** At least one `evidence_span_id` must be provided.

### Graph Queries

**List All Edges for an Entity:**
```bash
GET /kg/edges?entity_id=ent_abc123
```

**Search Entities:**
```bash
GET /kg/entities?query=muhammad
```

**Filter by Type:**
```bash
GET /kg/entities?entity_type=person
```

## Cost Governance

### Budget Management

Set daily and weekly spending limits for LLM and embedding API usage.

**Configuration:**
```bash
DAILY_BUDGET_USD=10.0
WEEKLY_BUDGET_USD=50.0
```

**How it works:**
- Pre-execution cost estimation
- Automatic model routing based on remaining budget
- Graceful degradation when approaching limits
- All usage persisted to database

### Model Routing

Automatic selection of LLM model based on query complexity and budget pressure.

**Tiers:**
| Tier | Model | Use Case |
|------|-------|----------|
| Cheap | gpt-4o-mini | Budget pressure, simple queries |
| Standard | gpt-4.1-mini | Normal complexity |
| Expensive | gpt-4o | Complex analysis, high accuracy |

**Complexity Scoring:**
```python
complexity = assess_complexity(query)
# Based on:
# - Token count
# - Complexity hint words ("compare", "analyze", "synthesize")
# - Question structure (multiple questions, newlines)
```

### Cost Alerts

Automatic alerts when approaching budget thresholds.

**Configuration:**
```bash
COST_ALERT_THRESHOLDS=0.8,0.9,1.0  # Alert at 80%, 90%, 100%
```

**Alert Example:**
```
WARNING:cost alert [daily/budget_threshold] 80.0% used
(spend=$8.000000 budget=$10.000000): Daily budget reached 80.0%
```

### Viewing Cost Usage

**Database Query:**
```sql
-- Daily spend
SELECT DATE(created_at), SUM(total_cost_usd)
FROM cost_usage_log
GROUP BY DATE(created_at)
ORDER BY DATE(created_at) DESC;

-- By model
SELECT llm_model, COUNT(*), SUM(total_cost_usd)
FROM cost_usage_log
GROUP BY llm_model;
```

## Retrieval System

### Hybrid Search

Combines lexical (BM25) and vector (cosine similarity) search.

**API:** Built into RAG pipeline, or use directly:

```python
from islam_intelligent.rag.retrieval.hybrid import search_hybrid

results = search_hybrid(
    query="What is the ruling on fasting?",
    limit=10,
    lexical_weight=0.7,  # 70% lexical, 30% vector
    vector_weight=0.3
)
```

### Cross-Encoder Reranking

Second-stage reranking for improved result quality.

**Usage:**
```python
from islam_intelligent.rag.rerank import CrossEncoderReranker

reranker = CrossEncoderReranker(
    model_name="cross-encoder/ms-marco-MiniLM-L-6-v2"
)

# Rerank initial results
reranked = reranker.rerank(
    query="question",
    results=initial_results,
    top_k=5
)
```

### Query Expansion

Generate query variations to improve recall.

**Configuration:**
```bash
QUERY_EXPANSION_ENABLED=true
QUERY_EXPANSION_COUNT=3
```

**Example:**
```
Original: "patience in Islam"
Expanded:
  1. "What does Islam teach about patience?"
  2. "Quranic verses about sabr"
  3. "Hadith on being patient"
```

### HyDE (Hypothetical Document Embeddings)

Generate hypothetical documents for better semantic matching.

**Usage:**
```python
from islam_intelligent.rag.retrieval.hyde import HyDEGenerator

hyde = HyDEGenerator(model="gpt-4o-mini")
hypothetical_doc = hyde.generate(
    "What is the concept of tawakkul?"
)
# Use hypothetical_doc for vector search
```

## Source Management

### Source Registry

Manage Islamic texts and their metadata.

**Create Source:**
```bash
POST /sources
{
  "source_type": "tafsir",
  "title": "Tafsir Ibn Kathir",
  "author": "Ibn Kathir",
  "language": "ar",
  "content": {
    "text": "...",
    "metadata": {...}
  }
}
```

### Versioning

Append-only versioning with complete history.

**Update Source:**
```bash
PUT /sources/{source_id}
{
  "content": {"text": "...updated..."}
}
```

This creates a new version, keeping the old one accessible.

**View Version History:**
```bash
GET /sources/{source_id}/versions
```

### Trust Management

Sources must be explicitly marked as trusted before being used in answers.

**Promote to Trusted:**
```bash
python scripts/set_source_trust.py quran_tanzil --trust
```

**Retract Source:**
```bash
python scripts/retract_source.py {source_id} \
  --reason "Found errors in transcription"
```

**Check Trust Status:**
```bash
GET /sources?q=trust_status:trusted
```

### Manifest System

Every source has a manifest with cryptographic hashes for verification.

**Get Manifest:**
```bash
GET /sources/{source_id}/manifest
```

**Response:**
```json
{
  "source_id": "quran_tanzil",
  "version": 1,
  "content_sha256": "a1b2c3...",
  "manifest_sha256": "d4e5f6...",
  "hash_verified": true
}
```

## Verification Tools

### Comprehensive Verification

Run all verification checks:

```bash
python scripts/verify_all.py
```

**Checks:**
1. Schema validation
2. Security audit
3. Database integrity
4. Provenance hash chain
5. Manifest verification
6. License compliance
7. Evidence requirement invariants

### Individual Verifiers

**Provenance Verification:**
```bash
python scripts/verify_hash_chain.py
```

**RAG Log Verification:**
```bash
python scripts/verify_rag_logs.py
```

**License Gate:**
```bash
python scripts/verify_license_gate.py
```

**Security Audit:**
```bash
python scripts/security_audit.py
```

**Database Smoke Test:**
```bash
python scripts/db_smoke.py
```

### Continuous Verification

Add to CI/CD pipeline:

```yaml
# .github/workflows/ci.yml
- name: Verify All
  run: python scripts/verify_all.py
```

## Advanced Features

### Canonical ID System

Standardized identifiers for all Islamic sources.

**Quran IDs:**
```
quran:{surah}:{ayah}
Examples:
  quran:2:255      (Ayat al-Kursi)
  quran:112:1      (Surah Al-Ikhlas)
```

**Hadith IDs:**
```
hadith:{collection}:{numbering_system}:{number}
Examples:
  hadith:bukhari:sahih:1
  hadith:muslim:sahih:3033
```

### Evidence Spans

Byte-offset ranges within text units for precise citation.

**Create Span:**
```bash
POST /spans
{
  "text_unit_id": "unit_abc123",
  "start_byte": 150,
  "end_byte": 280,
  "context_before": "...",
  "context_after": "..."
}
```

**Features:**
- SHA-256 hash of snippet for verification
- Context padding for display
- Linkable to multiple KG edges

### Unicode Normalization

All text is NFC-normalized for consistent processing.

```python
from islam_intelligent.normalize import normalize_text

normalized = normalize_text("بِسْمِ")  # NFC form
```

### Text Unit Builder

During ingestion, text is split into canonical units.

```python
from islam_intelligent.ingest.text_unit_builder import TextUnitBuilder

builder = TextUnitBuilder()
units = builder.build_units(
    text=raw_text,
    source_id="source_001",
    unit_type="ayah"
)
```

### Cost Governance Service

Full programmatic control over costs.

```python
from islam_intelligent.cost_governance import (
    CostGovernanceService,
    BudgetManager
)

budget_mgr = BudgetManager(
    daily_budget=10.0,
    weekly_budget=50.0
)

governance = CostGovernanceService(
    budget_manager=budget_mgr
)

# Plan query
plan = governance.plan_query(query="What is zakat?")
if plan.allowed:
    print(f"Using model: {plan.route.model}")
    print(f"Estimated cost: ${plan.estimate.total_cost_usd}")
else:
    print("Budget exceeded - operation blocked")
```

### Custom Embeddings

Use custom embedding models.

```python
from islam_intelligent.rag.retrieval.embeddings import EmbeddingGenerator

generator = EmbeddingGenerator(
    provider="sentence-transformers",
    model_name="BAAI/bge-large-en-v1.5"
)

embedding = generator.generate("text to embed")
```

### Database Migrations

Schema evolution with Alembic.

```bash
# Create migration
alembic revision --autogenerate -m "Add new table"

# Run migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

### Ingestion Scripts

**Quran (Tanzil):**
```bash
python scripts/ingest_quran_tanzil.py \
  --variant uthmani \
  --translation en.sahih
```

**Hadith (API):**
```bash
python scripts/ingest_hadith_api.py \
  --collections bukhari,muslim \
  --all-supported-arabic
```

**Load Fixtures:**
```bash
python scripts/load_fixtures.py \
  --fixtures-dir ./data/fixtures
```

## Feature Comparison

| Feature | Free Tier | Standard Tier | Enterprise Tier |
|---------|-----------|---------------|-----------------|
| RAG Queries | 100/day | 1000/day | Unlimited |
| LLM Generation | No | Yes | Yes |
| Knowledge Graph | Read-only | Full | Full |
| Custom Sources | 5 | 50 | Unlimited |
| API Rate Limit | 10/min | 100/min | Custom |
| Cost Governance | Basic | Full | Advanced |
| Support | Community | Email | Dedicated |

## Best Practices

### For Users

1. **Start with trusted sources only** - Verify trust status before querying
2. **Understand abstention** - It's a feature, not a bug
3. **Check citations** - Always verify the evidence behind answers
4. **Use specific queries** - Better retrieval with detailed questions

### For Administrators

1. **Regular verification** - Run `verify_all.py` weekly
2. **Monitor costs** - Set up budget alerts
3. **Backup strategy** - Daily automated backups
4. **Trust carefully** - Only mark verified sources as trusted
5. **Review logs** - Check RAG logs for quality issues

### For Developers

1. **Use evidence spans** - Always link to specific text
2. **Hash verification** - Verify content integrity
3. **Handle abstention** - Design UI to handle "no answer" gracefully
4. **Test with verify** - Run verification before deploying changes

## Troubleshooting Features

### "No sources found"

**Cause:** No sources marked as trusted

**Fix:**
```bash
python scripts/set_source_trust.py {source_id} --trust
```

### "LLM not responding"

**Cause:** LLM disabled or API key issue

**Fix:**
```bash
export RAG_ENABLE_LLM=true
export OPENAI_API_KEY=sk-...
```

### "High costs"

**Cause:** Expensive model, no budget limits

**Fix:**
```bash
export RAG_LLM_MODEL=gpt-4o-mini
export DAILY_BUDGET_USD=5.0
```

### "Slow queries"

**Cause:** No vector index, large retrieval limit

**Fix:**
```sql
-- Create vector index
CREATE INDEX ON text_unit USING ivfflat (embedding vector_cosine_ops);

-- Reduce retrieval limit
export RAG_MAX_RETRIEVAL=5
```

## Future Features

Planned enhancements:

- **Multi-language support** - Beyond Arabic and English
- **Advanced NER** - Named entity recognition for KG auto-population
- **Sanad analysis** - Hadith chain verification
- **Cross-reference engine** - Automatic linking between sources
- **Real-time ingestion** - Streaming updates
- **Graph queries** - Complex Cypher queries on Neo4j
- **Semantic caching** - Cache similar queries
- **A/B testing** - Compare RAG configurations
