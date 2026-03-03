# ISLAM INTELLIGENT - REMEDIATION PLAN

**Plan Date:** 2026-03-02  
**Objective:** Fix all critical bugs, complete core features, ingest Islamic data  
**Estimated Duration:** 2-3 weeks  

---

## 🎯 PHASE 1: CRITICAL BUG FIXES (Week 1)

### Task 1.1: Fix Foreign Key Constraint Bug
**Priority:** P0 - Critical  
**Estimated Time:** 2-3 hours  
**Assignee:** Database Architect  

**Problem:**
Self-referential FK in SourceDocument references non-unique column

**Solution:**
1. Add composite unique constraint on `(source_id, version)`
2. Change FK to reference the composite constraint
3. OR remove FK constraint and keep only relationship logic

**Implementation:**
```python
# Option A: Composite unique constraint (Recommended)
class SourceDocument(Base):
    __tablename__ = "source_document"
    __table_args__ = (
        UniqueConstraint('source_id', 'version', name='uq_source_version'),
    )
    
    # Change FK to reference composite constraint
    supersedes_source_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )
    supersedes_version: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    
    # Use CheckConstraint instead of FK for self-reference
    # OR use composite FK if SQLite supports it
```

**Files to Modify:**
- `apps/api/src/islam_intelligent/domain/models.py`
- `apps/api/tests/test_kg_edge_requires_evidence.py` (if needed)

**Acceptance Criteria:**
- [ ] All KG tests pass
- [ ] SourceDocument can be inserted with supersedes_source_id
- [ ] Version chain works correctly

---

### Task 1.2: Align Database Schema
**Priority:** P0 - Critical  
**Estimated Time:** 4-6 hours  
**Assignee:** Database Architect  

**Problem:**
SQL schema (PostgreSQL) doesn't match SQLAlchemy models (SQLite)

**Solution:**
Choose one approach and commit to it:

**Option A: SQLAlchemy-Only (Recommended for MVP)**
1. Remove `packages/schemas/sql/0001_init.sql`
2. Use SQLAlchemy models as source of truth
3. Add Alembic for migrations

**Option B: SQL-First**
1. Update SQLAlchemy models to match SQL schema
2. Use UUID primary keys
3. Update all code for UUID handling

**Recommended: Option A** (simpler for current stage)

**Implementation:**
```bash
# 1. Remove conflicting SQL schema
mv packages/schemas/sql/0001_init.sql packages/schemas/sql/0001_init.sql.deprecated

# 2. Add Alembic
pip install alembic
alembic init alembic

# 3. Create initial migration
alembic revision --autogenerate -m "Initial schema"
```

**Files to Modify:**
- `packages/schemas/sql/0001_init.sql` (deprecate)
- Add `alembic/` directory
- `apps/api/pyproject.toml` (add alembic dependency)

**Acceptance Criteria:**
- [ ] Single source of truth for schema
- [ ] Alembic migrations working
- [ ] All tests pass

---

### Task 1.3: Fix Pydantic Deprecation Warnings
**Priority:** P1 - High  
**Estimated Time:** 1 hour  
**Assignee:** Backend Developer  

**Problem:**
```
PydanticDeprecatedSince20: Support for class-based `config` is deprecated
```

**Solution:**
Update all Pydantic models to use `ConfigDict`:

```python
# Before (deprecated)
class SourceResponse(BaseModel):
    class Config:
        from_attributes = True

# After (correct)
from pydantic import ConfigDict

class SourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
```

**Files to Modify:**
- `apps/api/src/islam_intelligent/api/routes/sources.py`
- `apps/api/src/islam_intelligent/api/routes/spans.py`
- Any other files with Pydantic models

**Acceptance Criteria:**
- [ ] No deprecation warnings in test output
- [ ] All tests pass

---

## 🎯 PHASE 2: CORE FEATURE COMPLETION (Week 1-2)

### Task 2.1: Integrate LLM for RAG
**Priority:** P0 - Critical  
**Estimated Time:** 8-12 hours  
**Assignee:** AI/ML Engineer  

**Problem:**
RAG uses mock generator instead of real LLM

**Solution:**
Integrate OpenAI API for answer generation

**Implementation:**
```python
# apps/api/src/islam_intelligent/rag/generator.py
import openai
from typing import List

class LLMGenerator:
    def __init__(self, api_key: str = None):
        self.client = openai.OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
    
    def generate_answer(
        self, 
        query: str, 
        evidence: List[dict],
        model: str = "gpt-4"
    ) -> str:
        # Create prompt with evidence
        evidence_text = "\n\n".join([
            f"[{i+1}] {e['canonical_id']}: {e['snippet']}"
            for i, e in enumerate(evidence)
        ])
        
        prompt = f"""You are an Islamic knowledge assistant. Answer the question based ONLY on the provided evidence.

Question: {query}

Evidence:
{evidence_text}

Provide a clear, accurate answer citing the evidence numbers. If the evidence is insufficient, say so."""

        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful Islamic knowledge assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=500
        )
        
        return response.choices[0].message.content
```

**Files to Modify:**
- Create `apps/api/src/islam_intelligent/rag/generator.py`
- Update `apps/api/src/islam_intelligent/rag/pipeline/core.py`
- Add OPENAI_API_KEY to environment configuration

**Dependencies:**
```bash
pip install openai
```

**Acceptance Criteria:**
- [ ] LLM generates real answers
- [ ] Answers cite evidence correctly
- [ ] Abstention still works when evidence insufficient
- [ ] Tests updated to mock LLM

---

### Task 2.2: Enable Vector Search
**Priority:** P1 - High  
**Estimated Time:** 6-8 hours  
**Assignee:** Backend Developer  

**Problem:**
Vector search is disabled

**Solution:**
Implement embeddings and vector similarity search

**Implementation:**
```python
# apps/api/src/islam_intelligent/rag/retrieval/vector.py
import os
from typing import List
import numpy as np

class EmbeddingService:
    def __init__(self):
        self.client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    def embed(self, text: str) -> List[float]:
        response = self.client.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )
        return response.data[0].embedding

def search_vector(query: str, limit: int = 10) -> List[dict]:
    """Search using vector similarity."""
    # Get query embedding
    embedder = EmbeddingService()
    query_embedding = embedder.embed(query)
    
    # Search in database (using pgvector or in-memory for now)
    # Implementation depends on database
    ...
```

**Database Setup:**
```sql
-- Add vector column to text_unit
ALTER TABLE text_unit ADD COLUMN embedding VECTOR(1536);

-- Create index
CREATE INDEX ON text_unit USING ivfflat (embedding vector_cosine_ops);
```

**Files to Modify:**
- `apps/api/src/islam_intelligent/rag/retrieval/vector.py`
- `apps/api/src/islam_intelligent/domain/models.py` (add embedding column)

**Acceptance Criteria:**
- [ ] Vector search returns results
- [ ] Hybrid search uses both lexical and vector
- [ ] Embeddings cached/precomputed

---

### Task 2.3: Add Comprehensive Error Handling
**Priority:** P1 - High  
**Estimated Time:** 4-6 hours  
**Assignee:** Backend Developer  

**Problem:**
Generic exception handling, missing specific error types

**Solution:**
Create custom exception hierarchy

**Implementation:**
```python
# apps/api/src/islam_intelligent/exceptions.py

class IslamIntelligentError(Exception):
    """Base exception."""
    pass

class ValidationError(IslamIntelligentError):
    """Data validation error."""
    pass

class IngestionError(IslamIntelligentError):
    """Data ingestion error."""
    pass

class RAGError(IslamIntelligentError):
    """RAG pipeline error."""
    pass

class InsufficientEvidenceError(RAGError):
    """Not enough evidence to answer."""
    pass

class CitationError(RAGError):
    """Citation verification failed."""
    pass
```

**Files to Modify:**
- Create `apps/api/src/islam_intelligent/exceptions.py`
- Update all modules to use specific exceptions
- Update API routes to handle exceptions properly

**Acceptance Criteria:**
- [ ] Custom exceptions defined
- [ ] All modules use appropriate exceptions
- [ ] API returns proper error responses
- [ ] Error messages are user-friendly

---

## 🎯 PHASE 3: DATA INGESTION (Week 2)

### Task 3.1: Ingest Full Quran
**Priority:** P0 - Critical  
**Estimated Time:** 8-12 hours  
**Assignee:** Data Engineer  

**Problem:**
Only 7 ayat in fixtures, need all 6236 ayat

**Solution:**
1. Download complete Quran text (Tanzil project)
2. Parse and normalize
3. Ingest into database

**Data Source:**
- Tanzil Project (tanzil.net)
- Format: Text with surah/ayah markers
- License: Public domain

**Implementation:**
```python
# scripts/ingest_quran.py
import requests
from pathlib import Path

def download_quran():
    url = "https://tanzil.net/pub/download/index.php?marks=true&sajdah=true&tatweel=false&pauseMarks=true&recitation=husary&outType=txt-uthmani&aggressive=true"
    response = requests.get(url)
    return response.text

def parse_quran(text: str) -> List[dict]:
    """Parse Quran text into ayat."""
    ayat = []
    current_surah = 1
    current_ayah = 1
    
    for line in text.split('\n'):
        if line.startswith('#'):
            continue
        if '|' in line:
            ref, text = line.split('|', 1)
            current_surah, current_ayah = map(int, ref.split(':'))
            ayat.append({
                'surah': current_surah,
                'ayah': current_ayah,
                'text': text.strip()
            })
    
    return ayat

def ingest_quran():
    text = download_quran()
    ayat = parse_quran(text)
    
    # Create source document
    source_id = create_source_document(
        source_type='quran',
        title='Al-Quran Al-Kareem',
        author='Allah (Revelation)',
        language='ar'
    )
    
    # Ingest each ayah
    for ayah_data in ayat:
        create_quran_ayah(
            source_id=source_id,
            surah=ayah_data['surah'],
            ayah=ayah_data['ayah'],
            text=ayah_data['text']
        )
```

**Files to Create:**
- `scripts/ingest_quran.py`

**Acceptance Criteria:**
- [ ] All 6236 ayat ingested
- [ ] Canonical IDs correct (quran:1:1 to quran:114:6)
- [ ] Text NFC normalized
- [ ] Hashes computed
- [ ] Source document created

---

### Task 3.2: Ingest Major Hadith Collections
**Priority:** P0 - Critical  
**Estimated Time:** 12-16 hours  
**Assignee:** Data Engineer  

**Problem:**
Only 3 hadith in fixtures, need major collections

**Collections to Ingest:**
1. Sahih Bukhari (~7000 hadith)
2. Sahih Muslim (~7500 hadith)
3. Sunan Abu Dawud (~4800 hadith)
4. Jami' at-Tirmidhi (~3900 hadith)
5. Sunan an-Nasa'i (~5700 hadith)
6. Sunan Ibn Majah (~4300 hadith)

**Data Sources:**
- Sunnah.com API
- OpenHadith datasets
- Manual curation if needed

**Implementation:**
```python
# scripts/ingest_hadith.py
HADITH_COLLECTIONS = {
    'bukhari': {'name': 'Sahih al-Bukhari', 'author': 'Imam Bukhari'},
    'muslim': {'name': 'Sahih Muslim', 'author': 'Imam Muslim'},
    # ... more collections
}

def ingest_collection(collection_id: str):
    """Ingest a hadith collection."""
    collection_info = HADITH_COLLECTIONS[collection_id]
    
    # Create source document
    source_id = create_source_document(
        source_type='hadith',
        title=collection_info['name'],
        author=collection_info['author'],
        language='ar'
    )
    
    # Fetch hadith data
    hadith_list = fetch_hadith_collection(collection_id)
    
    # Ingest each hadith
    for hadith_data in hadith_list:
        create_hadith_item(
            source_id=source_id,
            collection=collection_id,
            numbering_system='sahih',
            hadith_number=hadith_data['number'],
            text_ar=hadith_data['arabic'],
            text_en=hadith_data['english'],
            book_name=hadith_data.get('book'),
            chapter_name=hadith_data.get('chapter'),
            grading=hadith_data.get('grade', 'sahih')
        )
```

**Files to Create:**
- `scripts/ingest_hadith.py`
- `scripts/fetch_hadith_data.py`

**Acceptance Criteria:**
- [ ] Major collections ingested
- [ ] Canonical IDs correct
- [ ] Translations included where available
- [ ] Grading information preserved

---

### Task 3.3: Add Tafsir Data
**Priority:** P1 - High  
**Estimated Time:** 8-12 hours  
**Assignee:** Data Engineer  

**Tafsir to Ingest:**
1. Tafsir Ibn Kathir (English)
2. Tafsir al-Jalalayn (Arabic)
3. Ma'ariful Quran (Urdu/English)

**Implementation:**
Similar to hadith ingestion

---

## 🎯 PHASE 4: TESTING & HARDENING (Week 2-3)

### Task 4.1: Achieve 90%+ Test Coverage
**Priority:** P1 - High  
**Estimated Time:** 8-12 hours  
**Assignee:** QA Engineer  

**Implementation:**
```bash
# Run tests with coverage
pytest --cov=islam_intelligent --cov-report=html --cov-report=term-missing

# Identify uncovered code
# Add tests for:
# - Error conditions
# - Edge cases
# - Integration scenarios
```

**Acceptance Criteria:**
- [ ] 90%+ line coverage
- [ ] 100% coverage for critical paths
- [ ] All error conditions tested

---

### Task 4.2: Performance Testing
**Priority:** P1 - High  
**Estimated Time:** 4-6 hours  
**Assignee:** Performance Engineer  

**Tests:**
1. Query response time < 2 seconds
2. Ingestion throughput > 100 items/second
3. Concurrent user handling
4. Memory usage profiling

**Implementation:**
```python
# tests/performance/test_rag_performance.py
import time
import pytest

@pytest.mark.performance
def test_rag_query_performance():
    """RAG query should complete within 2 seconds."""
    start = time.time()
    result = pipeline.query("What is the meaning of life?")
    elapsed = time.time() - start
    assert elapsed < 2.0, f"Query took {elapsed}s, expected < 2s"
```

---

### Task 4.3: End-to-End Testing
**Priority:** P1 - High  
**Estimated Time:** 6-8 hours  
**Assignee:** QA Engineer  

**Test Scenarios:**
1. Full flow: Ingest → Query → Answer with citations
2. Abstention flow: Query with no evidence → Abstain
3. Multi-source: Query spanning Quran + Hadith
4. Error handling: Invalid query → Proper error

**Implementation:**
Use Playwright for E2E testing (already configured)

---

## 🎯 PHASE 5: PRODUCTION READINESS (Week 3)

### Task 5.1: Security Audit
**Priority:** P0 - Critical  
**Estimated Time:** 4-6 hours  
**Assignee:** Security Engineer  

**Checks:**
- [ ] No hardcoded secrets
- [ ] API authentication
- [ ] SQL injection prevention
- [ ] XSS prevention in UI
- [ ] Rate limiting

---

### Task 5.2: Documentation
**Priority:** P1 - High  
**Estimated Time:** 8-12 hours  
**Assignee:** Technical Writer  

**Documents:**
- [ ] API documentation (OpenAPI/Swagger)
- [ ] Architecture decision records
- [ ] Deployment guide
- [ ] User guide
- [ ] Developer onboarding

---

### Task 5.3: CI/CD Setup
**Priority:** P1 - High  
**Estimated Time:** 4-6 hours  
**Assignee:** DevOps Engineer  

**Setup:**
- [ ] GitHub Actions workflow
- [ ] Automated testing
- [ ] Linting (ruff, mypy)
- [ ] Security scanning
- [ ] Deployment automation

---

## 📊 TIMELINE SUMMARY

| Week | Phase | Tasks | Deliverables |
|------|-------|-------|--------------|
| Week 1 | Critical Fixes | 1.1, 1.2, 1.3 | Bug-free foundation |
| Week 1-2 | Core Features | 2.1, 2.2, 2.3 | Working LLM, Vector search |
| Week 2 | Data Ingestion | 3.1, 3.2, 3.3 | Full Quran + Hadith |
| Week 2-3 | Testing | 4.1, 4.2, 4.3 | 90%+ coverage, E2E tests |
| Week 3 | Production | 5.1, 5.2, 5.3 | Secure, documented, deployable |

---

## ✅ SUCCESS CRITERIA

**Definition of Done:**
1. All critical bugs fixed ✅
2. LLM integration working ✅
3. Vector search enabled ✅
4. Full Quran ingested (6236 ayat) ✅
5. Major Hadith collections ingested ✅
6. 90%+ test coverage ✅
7. All tests passing ✅
8. Performance benchmarks met ✅
9. Security audit passed ✅
10. Documentation complete ✅

---

## 🚀 EXECUTION STRATEGY

### Parallel Workstreams
1. **Backend Team:** Tasks 1.1, 1.2, 2.1, 2.2, 2.3
2. **Data Team:** Tasks 3.1, 3.2, 3.3
3. **QA Team:** Tasks 4.1, 4.2, 4.3
4. **DevOps Team:** Tasks 5.1, 5.2, 5.3

### Daily Standup Questions
1. What did you complete yesterday?
2. What are you working on today?
3. Any blockers?

### Weekly Review
- Demo completed features
- Review test results
- Adjust timeline if needed

---

*End of Remediation Plan*
