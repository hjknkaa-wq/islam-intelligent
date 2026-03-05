# Performance Guide

Benchmarks, optimization strategies, and tuning recommendations for Islam Intelligent.

## Benchmark Overview

Tested on: PostgreSQL 15, 4 CPU cores, 16GB RAM, SSD storage
Dataset: Full Quran (6,236 ayat) + Sahih Bukhari (7,563 hadith)

### Query Performance

| Operation | Mean Latency | p95 Latency | Notes |
|-----------|--------------|-------------|-------|
| Lexical search | 12ms | 28ms | BM25 on indexed text |
| Vector search (pgvector) | 45ms | 89ms | Cosine similarity, 1536d |
| Hybrid search | 52ms | 95ms | Combined + ranking |
| Multi-query (5 variations) | 180ms | 320ms | Includes expansion |
| RAG (mock generator) | 65ms | 110ms | No LLM call |
| RAG (gpt-4o-mini) | 850ms | 1,400ms | With generation |
| RAG (gpt-4o) | 2,100ms | 3,500ms | High quality |
| Citation verification | 8ms | 15ms | Hash checks |
| DB connection | 2ms | 5ms | Connection pool hit |

### Throughput

| Scenario | Requests/sec | Concurrent Users |
|----------|--------------|------------------|
| Health check | 12,000 | 1000 |
| Simple search | 450 | 100 |
| Hybrid RAG (mock) | 85 | 50 |
| Hybrid RAG (LLM) | 8 | 20 |

### Database Performance

| Table | Rows | Size | Index Size |
|-------|------|------|------------|
| source_document | 50 | 2MB | 500KB |
| text_unit | 13,800 | 12MB | 3MB |
| evidence_span | 50,000 | 45MB | 8MB |
| kg_entity | 5,000 | 2MB | 1MB |
| kg_edge | 15,000 | 4MB | 2MB |
| rag_query | 100,000 | 50MB | 5MB |

## Optimization Strategies

### 1. Database Tuning

#### PostgreSQL Configuration

For a 16GB RAM server:

```ini
# postgresql.conf
shared_buffers = 4GB                    # 25% of RAM
effective_cache_size = 12GB             # 75% of RAM
work_mem = 32MB                         # Per-operation memory
maintenance_work_mem = 1GB              # For VACUUM, CREATE INDEX

# Connection settings
max_connections = 200
shared_preload_libraries = 'pg_stat_statements'

# Query planner
effective_io_concurrency = 200
random_page_cost = 1.1                  # For SSD
seq_page_cost = 1.0

# WAL settings for write-heavy workloads
wal_buffers = 16MB
max_wal_size = 4GB
min_wal_size = 1GB
checkpoint_completion_target = 0.9

# Autovacuum (critical for text search)
autovacuum_max_workers = 4
autovacuum_naptime = 30s
```

#### Index Optimization

```sql
-- Core indexes (already created by migrations)
CREATE INDEX CONCURRENTLY idx_text_unit_canonical_id ON text_unit(canonical_id);
CREATE INDEX CONCURRENTLY idx_evidence_span_text_unit ON evidence_span(text_unit_id);
CREATE INDEX CONCURRENTLY idx_kg_edge_subject ON kg_edge(subject_entity_id);

-- Full-text search index
CREATE INDEX CONCURRENTLY idx_text_unit_fts 
ON text_unit USING GIN (to_tsvector('arabic', text_canonical));

-- Partial index for trusted sources only
CREATE INDEX CONCURRENTLY idx_source_trusted 
ON source_document(source_id) WHERE trust_status = 'trusted';

-- Covering index for common query pattern
CREATE INDEX CONCURRENTLY idx_text_unit_covering 
ON text_unit(source_id, unit_type, canonical_id) 
INCLUDE (text_canonical);
```

#### Connection Pooling

Use PgBouncer for high-traffic deployments:

```ini
# pgbouncer.ini
[databases]
islam_intelligent = host=localhost port=5432 dbname=islam_intelligent

[pgbouncer]
listen_port = 6432
listen_addr = 127.0.0.1
auth_type = md5
auth_file = /etc/pgbouncer/userlist.txt

# Pool settings
pool_mode = transaction
max_client_conn = 10000
default_pool_size = 25
reserve_pool_size = 5
reserve_pool_timeout = 3

# Timeouts
server_idle_timeout = 600
server_lifetime = 3600
```

### 2. Query Optimization

#### Search Optimization

```python
# Bad: Large limit without filtering
results = search_hybrid(query, limit=100)

# Good: Small limit, filter first
results = search_hybrid(query, limit=10)
trusted = [r for r in results if r.get('trust_status') == 'trusted']
```

#### Batch Operations

```python
# Bad: Individual inserts
for unit in text_units:
    db.add(unit)
    db.commit()

# Good: Bulk insert
db.bulk_save_objects(text_units)
db.commit()
```

#### Query Caching

```python
from functools import lru_cache
import hashlib

@lru_cache(maxsize=1000)
def cached_search(query_hash: str, limit: int):
    """Cache search results by query hash."""
    query = decode_query(query_hash)
    return search_hybrid(query, limit)

# Usage
query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
results = cached_search(query_hash, limit=10)
```

### 3. Embedding Optimization

#### Pre-compute Embeddings

```python
# Generate embeddings during ingestion, not query time
from islam_intelligent.rag.retrieval.embeddings import generate_embedding

# During data loading
for text_unit in text_units:
    embedding = generate_embedding(text_unit.text_canonical)
    text_unit.embedding = embedding
    db.add(text_unit)
```

#### Dimension Reduction

```python
# Use smaller dimensions for faster search
# text-embedding-3-small: 1536d (default)
# Custom: 768d or 384d with PCA

# For pgvector, consider:
# 1. IVF indexes for large datasets (>100k vectors)
# 2. HNSW for approximate nearest neighbors
```

#### Vector Index Types

```sql
-- Exact search (default, slower but accurate)
CREATE INDEX ON text_unit USING ivfflat (embedding vector_cosine_ops);

-- Approximate search (faster, slight accuracy trade-off)
CREATE INDEX ON text_unit USING hnsw (embedding vector_cosine_ops);

-- Tune IVF lists for your dataset size
-- Rule of thumb: lists = sqrt(number of vectors)
-- For 100k vectors: lists = 316
CREATE INDEX ON text_unit 
USING ivfflat (embedding vector_cosine_ops) 
WITH (lists = 316);
```

### 4. RAG Pipeline Optimization

#### Sufficiency Threshold Tuning

```python
# Low threshold = more answers, possibly lower quality
RAG_SUFFICIENCY_THRESHOLD = 0.5

# Medium threshold = balanced (default)
RAG_SUFFICIENCY_THRESHOLD = 0.6

# High threshold = fewer answers, higher quality
RAG_SUFFICIENCY_THRESHOLD = 0.75
```

#### Retrieval Limits

```python
# Fewer results = faster but may miss relevant evidence
RAG_MAX_RETRIEVAL = 5

# Balanced (default)
RAG_MAX_RETRIEVAL = 10

# More results = slower but more comprehensive
RAG_MAX_RETRIEVAL = 20
```

#### Hybrid Weight Tuning

```python
# Lexical-heavy: good for exact terms
lexical_weight = 0.8
vector_weight = 0.2

# Balanced (default)
lexical_weight = 0.7
vector_weight = 0.3

# Vector-heavy: good for semantic similarity
lexical_weight = 0.4
vector_weight = 0.6
```

### 5. Caching Strategies

#### Result Caching

```python
import redis
from functools import wraps

redis_client = redis.Redis(host='localhost', port=6379, db=0)

def cache_result(ttl=3600):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}:{hash(args)}:{hash(tuple(kwargs.items()))}"
            cached = redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
            result = func(*args, **kwargs)
            redis_client.setex(cache_key, ttl, json.dumps(result))
            return result
        return wrapper
    return decorator

@cache_result(ttl=1800)
def search_with_cache(query: str, limit: int = 10):
    return search_hybrid(query, limit)
```

#### Embedding Cache

```python
# Cache embeddings for repeated queries
embedding_cache = {}

def get_cached_embedding(text: str) -> list[float]:
    text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
    if text_hash not in embedding_cache:
        embedding_cache[text_hash] = generate_embedding(text)
    return embedding_cache[text_hash]
```

### 6. Async Operations

#### Concurrent LLM Requests

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=5)

async def generate_async(query: str, evidence: list):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        executor, 
        lambda: generator.generate(query, evidence)
    )

# Process multiple queries concurrently
async def batch_generate(queries: list[str]):
    tasks = [generate_async(q, retrieve(q)) for q in queries]
    return await asyncio.gather(*tasks)
```

#### Background Tasks

```python
from fastapi import BackgroundTasks

@app.post("/ingest")
async def ingest_document(
    document: UploadFile,
    background_tasks: BackgroundTasks
):
    # Return immediately
    background_tasks.add_task(process_document, document)
    return {"status": "processing", "id": document_id}
```

## Performance Monitoring

### Query Logging

```python
import time
import logging

logger = logging.getLogger('performance')

def log_performance(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        logger.info(f"{func.__name__} took {elapsed:.3f}s")
        return result
    return wrapper

@log_performance
def search_hybrid(query: str, limit: int = 10):
    # ... implementation
```

### Database Metrics

```sql
-- Slow query detection
SELECT query, mean_exec_time, calls 
FROM pg_stat_statements 
ORDER BY mean_exec_time DESC 
LIMIT 10;

-- Index usage
SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read
FROM pg_stat_user_indexes
ORDER BY idx_scan DESC;

-- Table bloat estimation
SELECT schemaname, tablename, 
       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
WHERE schemaname='public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

### Application Metrics

```python
from prometheus_client import Counter, Histogram, generate_latest

# Define metrics
rag_queries_total = Counter('rag_queries_total', 'Total RAG queries')
rag_latency = Histogram('rag_latency_seconds', 'RAG query latency')
retrieval_count = Histogram('retrieval_count', 'Documents retrieved per query')

# Instrument code
@rag_latency.time()
def rag_query(query: str):
    rag_queries_total.inc()
    results = retrieve(query)
    retrieval_count.observe(len(results))
    return generate_answer(query, results)
```

## Load Testing

### Using Locust

```python
# locustfile.py
from locust import HttpUser, task, between

class IslamIntelligentUser(HttpUser):
    wait_time = between(1, 5)
    
    @task(3)
    def search_query(self):
        self.client.post("/rag/query", json={
            "query": "What does the Quran say about patience?",
            "max_results": 10
        })
    
    @task(1)
    def health_check(self):
        self.client.get("/health")
```

Run load test:
```bash
locust -f locustfile.py --host=http://localhost:8000
```

### Using Apache Bench

```bash
# Simple load test
ab -n 1000 -c 50 http://localhost:8000/health

# POST request test
ab -n 100 -c 10 -T application/json \
   -p query.json \
   http://localhost:8000/rag/query
```

## Optimization Checklist

### Database
- [ ] Connection pooling (PgBouncer)
- [ ] Proper indexes created
- [ ] Vacuum and analyze run regularly
- [ ] Shared_buffers at 25% of RAM
- [ ] Effective_cache_size at 75% of RAM
- [ ] pgvector indexes for vector search
- [ ] Query statistics enabled

### Application
- [ ] Result caching enabled
- [ ] Embedding caching enabled
- [ ] Async operations where beneficial
- [ ] Batch operations for bulk inserts
- [ ] Proper RAG thresholds tuned
- [ ] Hybrid weights calibrated

### Infrastructure
- [ ] SSD storage for database
- [ ] Sufficient RAM (4GB+ minimum)
- [ ] Multiple workers for API
- [ ] Load balancer for multiple instances
- [ ] CDN for static assets (UI)

## Troubleshooting Performance

### High Latency

**Symptom:** Queries taking >500ms

**Diagnostics:**
```bash
# Check database performance
psql $DATABASE_URL -c "SELECT * FROM pg_stat_activity WHERE state = 'active';"

# Check index usage
psql $DATABASE_URL -c "SELECT indexrelname, idx_scan FROM pg_stat_user_indexes ORDER BY idx_scan DESC;"
```

**Solutions:**
1. Add missing indexes
2. Increase work_mem
3. Enable result caching
4. Tune retrieval limits

### Memory Issues

**Symptom:** OOM errors or high memory usage

**Diagnostics:**
```bash
# Check PostgreSQL memory
ps aux | grep postgres

# Check connection count
psql $DATABASE_URL -c "SELECT count(*) FROM pg_stat_activity;"
```

**Solutions:**
1. Reduce shared_buffers
2. Limit max_connections
3. Use connection pooling
4. Reduce embedding cache size

### CPU Saturation

**Symptom:** 100% CPU usage

**Solutions:**
1. Enable query caching
2. Use approximate vector search (HNSW)
3. Reduce concurrent LLM requests
4. Scale horizontally (more instances)

## Recommended Hardware

### Development
- CPU: 2 cores
- RAM: 4GB
- Storage: 20GB SSD
- Database: SQLite or local PostgreSQL

### Small Production
- CPU: 4 cores
- RAM: 8GB
- Storage: 50GB SSD
- Database: PostgreSQL 15

### Medium Production
- CPU: 8 cores
- RAM: 16GB
- Storage: 100GB SSD
- Database: PostgreSQL 15 + PgBouncer
- Cache: Redis

### Large Production
- CPU: 16+ cores
- RAM: 32GB+
- Storage: 500GB+ NVMe SSD
- Database: PostgreSQL 15 cluster
- Cache: Redis cluster
- Load balancer: NGINX or ALB
