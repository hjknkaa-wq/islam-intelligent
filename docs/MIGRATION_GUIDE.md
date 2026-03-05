# Migration Guide: v1 to v2

Step-by-step guide for migrating from Islam Intelligent v1 to v2.

## What's New in v2

### Major Changes

1. **PostgreSQL + pgvector**: Replaced SQLite with PostgreSQL for production use
2. **W3C PROV-DM Provenance**: Complete audit trail with hash chains
3. **Trust Gating**: Explicit source trust status for answer generation
4. **Cost Governance**: Budget management and model routing
5. **Knowledge Graph**: Optional Neo4j integration for entity relationships
6. **Docker Compose**: Simplified deployment with `make up`
7. **Verification Suite**: Comprehensive integrity checking

### Breaking Changes

| Feature | v1 | v2 |
|---------|-----|-----|
| Database | SQLite only | PostgreSQL (production), SQLite (dev) |
| Provenance | Basic | W3C PROV-DM with hash chains |
| Trust System | Implicit | Explicit `trust_status` column |
| Cost Control | None | Full budget management |
| Deployment | Manual | Docker Compose |
| API | Unstable | Versioned contracts |

## Pre-Migration Checklist

Before starting migration:

- [ ] Backup v1 database: `cp .local/dev.db .local/dev.db.backup`
- [ ] Document current sources and their IDs
- [ ] Export any custom configurations
- [ ] Note any API integrations using v1 endpoints
- [ ] Check disk space (need 5GB+ free)
- [ ] Verify PostgreSQL 15+ availability

## Migration Steps

### Step 1: Install Dependencies

```bash
# Install PostgreSQL 15 and pgvector
# Ubuntu/Debian:
sudo apt-get update
sudo apt-get install postgresql-15 postgresql-15-pgvector

# macOS:
brew install postgresql@15
brew install pgvector

# Start PostgreSQL
sudo systemctl start postgresql  # Linux
brew services start postgresql@15  # macOS
```

### Step 2: Create v2 Database

```bash
# Create database and user
sudo -u postgres psql << EOF
CREATE DATABASE islam_intelligent_v2;
CREATE USER islam_v2 WITH ENCRYPTED PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE islam_intelligent_v2 TO islam_v2;
\c islam_intelligent_v2
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
EOF
```

### Step 3: Export v1 Data

```bash
# Export sources
python scripts/export_v1_data.py \
    --db .local/dev.db \
    --output v1_export.json

# This creates a structured export with:
# - source_documents
# - text_units
# - evidence_spans
# - custom configurations
```

### Step 4: Set Up v2 Environment

```bash
# Clone or update to v2
git checkout v2.0.0  # or main branch

# Create v2 environment file
cat > .env.v2 << EOF
APP_ENV=migration
DATABASE_URL=postgresql://islam_v2:your_secure_password@localhost:5432/islam_intelligent_v2
RAG_ENABLE_LLM=false
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=islam_intelligent_v2
POSTGRES_USER=islam_v2
POSTGRES_PASSWORD=your_secure_password
EOF

# Install v2 dependencies
cd apps/api
python -m venv venv_v2
source venv_v2/bin/activate
pip install -e ".[dev]"
```

### Step 5: Initialize v2 Schema

```bash
# Run v2 migrations
export DATABASE_URL="postgresql://islam_v2:your_secure_password@localhost:5432/islam_intelligent_v2"
python scripts/db_init.py --postgres

# Verify schema
psql $DATABASE_URL -c "\dt"
# Should show: source_document, text_unit, evidence_span, kg_entity, kg_edge, etc.
```

### Step 6: Migrate Data

```bash
# Import v1 data into v2
python scripts/migrate_v1_to_v2.py \
    --input v1_export.json \
    --db-url "$DATABASE_URL"

# This script:
# - Transforms v1 schema to v2 schema
# - Assigns trust_status (defaults to 'untrusted')
# - Creates provenance records for migration activity
# - Validates canonical IDs
# - Generates missing hashes
```

### Step 7: Validate Migration

```bash
# Run v2 verification suite
python scripts/verify_all.py --db-path .local/migration_check.db

# Check data counts
psql $DATABASE_URL -c "SELECT 'Sources' as type, COUNT(*) FROM source_document;"
psql $DATABASE_URL -c "SELECT 'Text Units' as type, COUNT(*) FROM text_unit;"
psql $DATABASE_URL -c "SELECT 'Evidence Spans' as type, COUNT(*) FROM evidence_span;"

# Compare with v1 counts (should match)
sqlite3 .local/dev.db "SELECT 'Sources' as type, COUNT(*) FROM source_document;"
```

### Step 8: Promote Trusted Sources

In v2, sources must be explicitly marked as trusted:

```bash
# List all sources
python scripts/list_sources.py --db-url "$DATABASE_URL"

# Promote trusted sources
python scripts/set_source_trust.py quran_tanzil --trust
python scripts/set_source_trust.py hadith_bukhari --trust

# Verify trust status
psql $DATABASE_URL -c "SELECT source_id, source_type, trust_status FROM source_document;"
```

### Step 9: Test RAG Pipeline

```bash
# Start v2 API
uvicorn islam_intelligent.api.main:app --reload --port 8001

# Test health
curl http://localhost:8001/health

# Test RAG query
curl -X POST http://localhost:8001/rag/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What does the Quran say about patience?"}'

# Should return answer with citations from trusted sources
```

### Step 10: Update Integrations

#### API Endpoint Changes

| v1 Endpoint | v2 Endpoint | Change |
|-------------|-------------|--------|
| `GET /sources` | `GET /sources` | Added trust_status filter |
| `POST /query` | `POST /rag/query` | New path, different response format |
| `GET /health` | `GET /health` | Unchanged |
| - | `GET /evidence/{id}` | New: evidence lookup |
| - | `GET /kg/entities` | New: knowledge graph |

#### Response Format Changes

**v1 Response:**
```json
{
  "answer": "The Quran mentions patience...",
  "sources": ["quran:2:153"]
}
```

**v2 Response:**
```json
{
  "verdict": "answer",
  "statements": [
    {
      "text": "The Quran mentions patience (sabr) in many verses...",
      "citations": [
        {
          "evidence_span_id": "span_abc123",
          "canonical_id": "quran:2:153",
          "snippet": "O you who have believed, seek help through patience..."
        }
      ]
    }
  ],
  "retrieved_count": 8,
  "sufficiency_score": 0.85
}
```

### Step 11: Configure Cost Governance (Optional)

```bash
# Set budget limits
export COST_DAILY_BUDGET_USD=10
export COST_WEEKLY_BUDGET_USD=50

# Enable LLM with cost control
export RAG_ENABLE_LLM=true
export RAG_LLM_MODEL=gpt-4o-mini
```

### Step 12: Switch to Production

```bash
# Stop v1 API
pkill -f "uvicorn.*v1"  # or however you run v1

# Update environment to production
export APP_ENV=production
export DATABASE_URL="postgresql://islam_v2:your_secure_password@localhost:5432/islam_intelligent_v2"

# Start v2 API (production mode)
uvicorn islam_intelligent.api.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4

# Update any reverse proxy configs to point to v2
```

### Step 13: Post-Migration Verification

```bash
# Run full verification
python scripts/verify_all.py

# Test with sample queries
curl -X POST http://localhost:8000/rag/query \
  -H "Content-Type: application/json" \
  -d '{"query": "test query"}'

# Check logs for errors
tail -f logs/islam_intelligent.log

# Verify cost tracking (if LLM enabled)
psql $DATABASE_URL -c "SELECT COUNT(*) FROM cost_usage_log;"
```

## Data Transformations

### Source Document Mapping

| v1 Field | v2 Field | Transform |
|----------|----------|-----------|
| `id` | `source_id` | Keep as string |
| `type` | `source_type` | Rename, validate enum |
| `content` | `content_json` | JSON stringify |
| `hash` | `content_sha256` | Verify format |
| - | `trust_status` | Default 'untrusted' |
| - | `manifest_sha256` | Compute new hash |

### Text Unit Mapping

| v1 Field | v2 Field | Transform |
|----------|----------|-----------|
| `id` | `text_unit_id` | Convert to UUID |
| `canonical_id` | `canonical_id` | Validate pattern |
| `text` | `text_canonical` | NFC normalize |
| - | `text_canonical_utf8_sha256` | Compute new hash |

### Provenance Migration

v1 had basic activity logging. v2 requires full PROV-DM:

```python
# Migration creates a single "migration" activity
migration_activity = ProvActivity(
    activity_id="act_migration_v1_to_v2",
    activity_type="migration",
    started_at=datetime.now(),
    ended_at=datetime.now(),
    git_sha="abc123...",
)

# Links all imported entities to this activity
```

## Rollback Procedure

If migration fails:

```bash
# Stop v2 API
pkill -f uvicorn

# Drop v2 database (careful!)
sudo -u postgres psql -c "DROP DATABASE islam_intelligent_v2;"

# Restore v1 database from backup
cp .local/dev.db.backup .local/dev.db

# Restart v1 API
# (your original v1 startup command)
```

## Troubleshooting

### "trust_status column not found"

**Cause:** Running v1 code against v2 database

**Fix:**
```bash
# Ensure you're using v2 code
git checkout v2.0.0
pip install -e apps/api/.
```

### "Cannot connect to PostgreSQL"

**Cause:** PostgreSQL not running or wrong credentials

**Fix:**
```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Verify connection
psql "postgresql://islam_v2:password@localhost:5432/islam_intelligent_v2" -c "SELECT 1;"
```

### "pgvector extension not found"

**Cause:** pgvector not installed

**Fix:**
```bash
# Ubuntu/Debian
sudo apt-get install postgresql-15-pgvector

# Or build from source
sudo -u postgres psql -c "CREATE EXTENSION vector;"
```

### "Hash mismatch errors"

**Cause:** v1 data didn't have proper hashes

**Fix:**
```bash
# Re-compute hashes during migration
python scripts/migrate_v1_to_v2.py \
    --input v1_export.json \
    --db-url "$DATABASE_URL" \
    --recompute-hashes
```

### "Too many connections"

**Cause:** Connection pool exhaustion

**Fix:**
```bash
# Increase max_connections in PostgreSQL
sudo -u postgres psql -c "ALTER SYSTEM SET max_connections = 200;"
sudo systemctl restart postgresql
```

## Migration Script Reference

### migrate_v1_to_v2.py

```bash
python scripts/migrate_v1_to_v2.py [options]

Options:
  --input PATH          v1 export JSON file
  --db-url URL          v2 database URL
  --batch-size INT      Insert batch size (default: 1000)
  --recompute-hashes    Recompute all SHA-256 hashes
  --trust-sources       Mark all imported sources as trusted
  --dry-run             Preview changes without applying
  --verbose             Detailed logging
```

### Example: Dry Run

```bash
python scripts/migrate_v1_to_v2.py \
    --input v1_export.json \
    --db-url "$DATABASE_URL" \
    --dry-run \
    --verbose
```

### Example: Full Migration with Trust

```bash
python scripts/migrate_v1_to_v2.py \
    --input v1_export.json \
    --db-url "$DATABASE_URL" \
    --recompute-hashes \
    --trust-sources \
    --batch-size 500
```

## Post-Migration Tasks

### 1. Update Monitoring

Add new v2 metrics to your monitoring:

```python
# New metrics in v2
- rag_sufficiency_score
- cost_daily_spend
- provenance_hash_chain_valid
- kg_edge_evidence_ratio
```

### 2. Retrain Staff

Key changes for users:

- Sources must be explicitly trusted before use
- Abstention is normal when evidence is insufficient
- Citations now include evidence_span_id for verification
- Cost governance may route to cheaper models under budget pressure

### 3. Documentation Updates

Update your internal docs:

- API endpoint changes
- New required fields in requests
- Updated response formats
- Trust status management
- Cost governance policies

## Timeline Estimates

| Step | Time Estimate |
|------|---------------|
| Pre-migration prep | 30 minutes |
| Database setup | 15 minutes |
| Data export (v1) | 5-10 minutes |
| Schema migration | 10 minutes |
| Data import | 20-60 minutes (depends on data size) |
| Validation | 15 minutes |
| Trust configuration | 10 minutes |
| Testing | 30 minutes |
| Cutover | 15 minutes |
| **Total** | **2.5-4 hours** |

## Support

If you encounter issues:

1. Check the troubleshooting section above
2. Review logs: `logs/migration.log`
3. Run verification: `python scripts/verify_all.py`
4. Open an issue with:
   - Migration step you're on
   - Error message
   - Database sizes (v1 and v2)
   - Environment details

## Deprecated Features

These v1 features are removed in v2:

| Feature | Replacement |
|---------|-------------|
| SQLite in production | PostgreSQL |
| Implicit trust | Explicit trust_status |
| Basic activity log | W3C PROV-DM |
| No cost tracking | Full cost governance |
| Manual deployment | Docker Compose |

## New Features to Explore

After migration, explore these new capabilities:

1. **Provenance API**: `GET /evidence/{span_id}/provenance`
2. **Knowledge Graph**: `GET /kg/entities` and `POST /kg/query`
3. **Cost Dashboard**: Query `cost_usage_log` table
4. **Verification Suite**: `python scripts/verify_all.py`
5. **Docker Deployment**: `make up` for full stack

## Summary

Migration from v1 to v2 involves:

1. Setting up PostgreSQL with pgvector
2. Exporting v1 data
3. Running schema migrations
4. Importing and transforming data
5. Configuring trust and testing
6. Cutting over to v2

The v2 architecture provides better scalability, auditability, and cost control. Plan for 2-4 hours of migration time depending on data size.

Welcome to Islam Intelligent v2!
