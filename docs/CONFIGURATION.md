# Configuration Guide

Complete reference for all Islam Intelligent configuration options.

## Configuration Sources

Configuration is loaded from (in order of precedence):

1. **Environment variables** (highest priority)
2. **`.env` file** in project root
3. **Default values** (lowest priority)

## Core Configuration

### Application Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `Islam Intelligent API` | Application name displayed in API docs |
| `APP_ENV` | `development` | Environment: `development`, `staging`, `production` |
| `DEBUG` | `false` | Enable debug mode (auto-enabled in development) |
| `LOG_LEVEL` | `info` | Logging level: `debug`, `info`, `warning`, `error` |

### Database Configuration

#### PostgreSQL

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes* | - | Full PostgreSQL connection string |
| `POSTGRES_HOST` | No | `localhost` | Database host |
| `POSTGRES_PORT` | No | `5432` | Database port |
| `POSTGRES_DB` | No | `islam_intelligent` | Database name |
| `POSTGRES_USER` | No | - | Database user |
| `POSTGRES_PASSWORD` | No | - | Database password |

*Either `DATABASE_URL` or individual `POSTGRES_*` variables required.

**Connection String Format:**
```
postgresql://user:password@host:port/database
```

**Examples:**

```bash
# Local development
DATABASE_URL=postgresql://islam_user:password@localhost:5432/islam_intelligent

# Docker Compose
DATABASE_URL=postgresql://islam_user:password@postgres:5432/islam_intelligent

# With SSL
DATABASE_URL=postgresql://user:password@host:5432/db?sslmode=require

# Connection pooling (via PgBouncer)
DATABASE_URL=postgresql://user:password@pgbouncer:6432/db
```

#### SQLite (Development Only)

```bash
# In-memory (testing)
DATABASE_URL=sqlite+pysqlite:///:memory:

# File-based
DATABASE_URL=sqlite+pysqlite:///./.local/dev.db
```

### Neo4j Configuration (Optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection URI |
| `NEO4J_AUTH` | `neo4j/change-me` | Username/password combo |
| `NEO4J_HTTP_PORT` | `7474` | HTTP API port |
| `NEO4J_BOLT_PORT` | `7687` | Bolt protocol port |

## RAG Pipeline Configuration

### LLM Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `RAG_ENABLE_LLM` | `false` | Enable LLM generation (requires API key) |
| `RAG_LLM_MODEL` | `gpt-4o-mini` | LLM model to use |
| `RAG_LLM_TEMPERATURE` | `0.2` | Sampling temperature (0.0-2.0) |
| `RAG_LLM_SEED` | `42` | Random seed for reproducibility |
| `RAG_LLM_BASE_URL` | - | Custom base URL for LLM API |
| `RAG_LLM_MAX_TOKENS` | `1000` | Maximum tokens per response |
| `OPENAI_API_KEY` | - | OpenAI API key |

**Supported Models:**

| Model | Description | Cost |
|-------|-------------|------|
| `gpt-4o-mini` | Fast, cheap, good quality | $0.15/$0.60 per 1M tokens |
| `gpt-4.1-mini` | Balanced performance | $0.40/$1.60 per 1M tokens |
| `gpt-4o` | Best quality, slower | $2.50/$10.00 per 1M tokens |

**Temperature Guidelines:**

- `0.0-0.2`: Factual, deterministic answers (recommended)
- `0.3-0.7`: Balanced creativity
- `0.8-1.0`: High creativity, less factual
- `1.1-2.0`: Very creative, may hallucinate

### Retrieval Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |
| `EMBEDDING_DIMENSION` | `1536` | Vector dimension |
| `RAG_ENABLE_RERANKER` | `true` | Enable cross-encoder reranking |
| `RAG_RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Reranker model |
| `RAG_RERANKER_TOP_K` | `10` | Number of results to rerank |
| `RAG_LEXICAL_WEIGHT` | `0.7` | Weight for lexical search (0.0-1.0) |
| `RAG_VECTOR_WEIGHT` | `0.3` | Weight for vector search (0.0-1.0) |

**Embedding Models:**

| Model | Dimension | Description |
|-------|-----------|-------------|
| `text-embedding-3-small` | 1536 | Fast, cheap, good quality |
| `text-embedding-3-large` | 3072 | Higher quality, slower |
| `text-embedding-ada-002` | 1536 | Legacy model |

**Hybrid Search Weights:**

```bash
# Lexical-heavy (good for exact keyword matches)
RAG_LEXICAL_WEIGHT=0.8
RAG_VECTOR_WEIGHT=0.2

# Balanced (recommended for most use cases)
RAG_LEXICAL_WEIGHT=0.7
RAG_VECTOR_WEIGHT=0.3

# Vector-heavy (good for semantic similarity)
RAG_LEXICAL_WEIGHT=0.3
RAG_VECTOR_WEIGHT=0.7
```

### Query Expansion

| Variable | Default | Description |
|----------|---------|-------------|
| `RAG_ENABLE_QUERY_EXPANSION` | `false` | Enable multi-query expansion |
| `RAG_QUERY_EXPANSION_VARIATIONS` | `5` | Number of query variations |

### Pipeline Thresholds

| Variable | Default | Description |
|----------|---------|-------------|
| `RAG_SUFFICIENCY_THRESHOLD` | `0.6` | Minimum score to proceed (0.0-1.0) |
| `RAG_MAX_RETRIEVAL` | `10` | Maximum documents to retrieve |
| `RAG_MIN_CITATIONS` | `1` | Minimum citations per statement |

## Cost Governance Configuration

### Budget Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `COST_DAILY_BUDGET_USD` | `10.0` | Daily spend limit in USD |
| `COST_WEEKLY_BUDGET_USD` | `50.0` | Weekly spend limit in USD |
| `COST_ALERT_THRESHOLDS` | `0.8,0.9,1.0` | Alert thresholds (comma-separated) |

### Model Routing

| Variable | Default | Description |
|----------|---------|-------------|
| `COST_CHEAP_MODEL` | `gpt-4o-mini` | Low-cost model tier |
| `COST_STANDARD_MODEL` | `gpt-4.1-mini` | Standard model tier |
| `COST_EXPENSIVE_MODEL` | `gpt-4o` | High-quality model tier |
| `COST_LOW_COMPLEXITY_THRESHOLD` | `0.35` | Threshold for cheap routing |
| `COST_HIGH_COMPLEXITY_THRESHOLD` | `0.72` | Threshold for expensive routing |

### Pricing Overrides

Override default model pricing:

```bash
# Format: model_name:price_per_1k_prompt:price_per_1k_completion
COST_LLM_PRICING="gpt-4o-mini:0.00015:0.0006,gpt-4o:0.0025:0.01"

# Embedding pricing: model_name:price_per_1k
COST_EMBEDDING_PRICING="text-embedding-3-small:0.00002"
```

## API Server Configuration

### Uvicorn Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `API_HOST` | `0.0.0.0` | Bind address |
| `API_PORT` | `8000` | Server port |
| `API_WORKERS` | `1` | Number of worker processes |
| `API_RELOAD` | `false` | Auto-reload on code changes |
| `API_TIMEOUT_KEEP_ALIVE` | `5` | Keep-alive timeout (seconds) |

### Security Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `API_SECRET_KEY` | - | Secret for JWT/signing |
| `API_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Token expiration time |
| `API_RATE_LIMIT_PER_MINUTE` | `60` | Rate limit per IP |
| `API_CORS_ORIGINS` | `*` | Allowed CORS origins |

**CORS Configuration:**

```bash
# Single origin
API_CORS_ORIGINS="https://yourdomain.com"

# Multiple origins (comma-separated)
API_CORS_ORIGINS="https://app1.com,https://app2.com"

# Development (allow all)
API_CORS_ORIGINS="*"
```

## UI Configuration

### Next.js Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `NODE_ENV` | `development` | Node environment |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | API base URL |
| `UI_PORT` | `3000` | UI server port |

### Build Settings

```bash
# Static export (for CDN deployment)
NEXT_OUTPUT=export

# Standalone output (for Docker)
NEXT_OUTPUT=standalone

# Production optimization
NEXT_TELEMETRY_DISABLED=1
```

## Ingestion Configuration

### Quran Ingestion

| Variable | Default | Description |
|----------|---------|-------------|
| `QURAN_VARIANT` | `uthmani` | Text variant: `uthmani`, `simple` |
| `QURAN_TRANSLATION` | - | Include translation (e.g., `en.sahih`) |

### Hadith Ingestion

| Variable | Default | Description |
|----------|---------|-------------|
| `HADITH_COLLECTIONS` | `bukhari,muslim` | Comma-separated list |
| `HADITH_API_KEY` | - | API key for hadith data source |
| `HADITH_API_URL` | - | Custom hadith API endpoint |

### Data Paths

| Variable | Default | Description |
|----------|---------|-------------|
| `DATA_DIR` | `./data` | Data directory |
| `FIXTURES_DIR` | `./data/fixtures` | Fixture files directory |
| `CURATED_DIR` | `./data/curated` | Curated data directory |
| `LOGS_DIR` | `./logs` | Log files directory |

## Advanced Configuration

### Provenance Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `PROV_ENABLE_HASH_CHAIN` | `true` | Enable hash chain verification |
| `PROV_INCLUDE_GIT_SHA` | `true` | Include Git SHA in activities |
| `PROV_RETENTION_DAYS` | `365` | Provenance data retention |

### Cache Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `CACHE_TYPE` | `memory` | Cache backend: `memory`, `redis` |
| `CACHE_REDIS_URL` | - | Redis connection URL |
| `CACHE_TTL_SECONDS` | `3600` | Default cache TTL |

### Async Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_CONCURRENT_REQUESTS` | `10` | Max concurrent LLM requests |
| `REQUEST_TIMEOUT_SECONDS` | `30` | Request timeout |

## Configuration Examples

### Minimal Development Setup

```bash
# .env
APP_ENV=development
DATABASE_URL=sqlite+pysqlite:///./.local/dev.db
RAG_ENABLE_LLM=false
```

### Production with LLM

```bash
# .env
APP_ENV=production
DATABASE_URL=postgresql://user:pass@postgres:5432/islam_intelligent
RAG_ENABLE_LLM=true
OPENAI_API_KEY=sk-...
RAG_LLM_MODEL=gpt-4o-mini
COST_DAILY_BUDGET_USD=50
API_WORKERS=4
API_RELOAD=false
```

### High-Performance Setup

```bash
# .env
APP_ENV=production
DATABASE_URL=postgresql://user:pass@postgres:5432/islam_intelligent
RAG_ENABLE_LLM=true
RAG_ENABLE_RERANKER=true
RAG_ENABLE_QUERY_EXPANSION=true
RAG_QUERY_EXPANSION_VARIATIONS=5
RAG_LLM_MODEL=gpt-4o
EMBEDDING_MODEL=text-embedding-3-large
COST_DAILY_BUDGET_USD=100
API_WORKERS=8
```

### Cost-Optimized Setup

```bash
# .env
APP_ENV=production
DATABASE_URL=postgresql://user:pass@postgres:5432/islam_intelligent
RAG_ENABLE_LLM=true
RAG_LLM_MODEL=gpt-4o-mini
RAG_ENABLE_RERANKER=false
EMBEDDING_MODEL=text-embedding-3-small
COST_DAILY_BUDGET_USD=5
COST_CHEAP_MODEL=gpt-4o-mini
COST_STANDARD_MODEL=gpt-4o-mini
COST_EXPENSIVE_MODEL=gpt-4.1-mini
```

## Environment-Specific Files

Create separate files for different environments:

```
.env.development    # Development defaults
.env.staging        # Staging overrides
.env.production     # Production overrides
```

Load the appropriate file:

```bash
# Development
export APP_ENV=development
source .env.development

# Production
export APP_ENV=production
source .env.production
```

## Configuration Validation

Validate your configuration:

```bash
# Check required variables
python scripts/verify_all.py --check-invariants

# Test database connection
python scripts/db_smoke.py

# Validate schemas
python scripts/validate_schemas.py
```

## Troubleshooting Configuration

### Common Issues

**Database connection fails:**
```bash
# Check DATABASE_URL format
echo $DATABASE_URL
# Should be: postgresql://user:password@host:port/database

# Test connection
psql $DATABASE_URL -c "SELECT 1;"
```

**LLM not working:**
```bash
# Verify API key is set
echo $OPENAI_API_KEY

# Check LLM is enabled
echo $RAG_ENABLE_LLM  # Should be: true

# Test with curl
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

**Embeddings fail:**
```bash
# Check pgvector extension
psql $DATABASE_URL -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Verify embedding dimension matches
psql $DATABASE_URL -c "\d text_unit"  # Check embedding column type
```

## Configuration Reference Table

| Category | Variables | Priority |
|----------|-----------|----------|
| Core | `APP_*`, `LOG_*`, `DEBUG` | High |
| Database | `DATABASE_URL`, `POSTGRES_*` | Critical |
| RAG | `RAG_*`, `EMBEDDING_*` | High |
| Cost | `COST_*` | Medium |
| API | `API_*` | High |
| UI | `NEXT_*`, `UI_*` | Medium |
| Security | `API_SECRET_KEY`, `*_API_KEY` | Critical |

## Best Practices

1. **Use `.env` files** for local development
2. **Set `APP_ENV`** explicitly in each environment
3. **Use secrets management** (Vault, AWS Secrets Manager) in production
4. **Rotate API keys** regularly
5. **Monitor `COST_*` budgets** to prevent unexpected charges
6. **Test configuration** with `verify_all.py` before deployment
7. **Document custom settings** in your deployment notes
