# Deployment Guide

Complete deployment instructions for Islam Intelligent with PostgreSQL.

## Deployment Options

1. **Docker Compose (Recommended)**: Full stack with one command
2. **Manual Setup**: Custom installation for production
3. **Production Cluster**: Kubernetes/ECS configuration

## Quick Start (Docker Compose)

The fastest way to get started with a complete development environment.

### Prerequisites

- Docker 24.0+
- Docker Compose 2.20+
- 4GB RAM minimum (8GB recommended)
- 10GB free disk space

### 1. Clone and Configure

```bash
git clone <repository-url>
cd islam-intelligent

# Copy and edit environment file
cp .env.example .env
```

### 2. Environment Configuration

Edit `.env` with your settings:

```bash
# Database Configuration
POSTGRES_DB=islam_intelligent
POSTGRES_USER=islam_user
POSTGRES_PASSWORD=your_secure_password_here
POSTGRES_PORT=5432
DATABASE_URL=postgresql://islam_user:your_secure_password_here@postgres:5432/islam_intelligent

# API Configuration
APP_ENV=development
API_PORT=8000

# UI Configuration
UI_PORT=3000
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000

# LLM Configuration (optional)
OPENAI_API_KEY=sk-your-key-here
RAG_ENABLE_LLM=false
RAG_LLM_MODEL=gpt-4o-mini

# Neo4j Configuration (optional)
NEO4J_AUTH=neo4j/change-me
NEO4J_HTTP_PORT=7474
NEO4J_BOLT_PORT=7687
```

### 3. Start Services

```bash
# Build and start all services
make up

# Wait for services to be healthy (usually 30-60 seconds)
docker-compose ps
```

### 4. Initialize Database

```bash
# Run database migrations
make migrate

# Or manually:
docker-compose exec api python /workspace/scripts/db_init.py --postgres
```

### 5. Ingest Data

```bash
# Option A: Minimal sample data (fast, for testing)
make ingest:quran_sample

# Option B: Full Quran only
make ingest:quran_full

# Option C: Full Quran + Hadith (complete dataset)
make ingest:hadith_full
```

### 6. Verify Deployment

```bash
# Check all services are running
make test

# Or run verification script
python scripts/verify_all.py

# Access services:
# API: http://localhost:8000/docs
# UI: http://localhost:3000
# Neo4j Browser: http://localhost:7474
```

## Manual PostgreSQL Setup

For production deployments or custom configurations.

### 1. Install PostgreSQL 15+

**Ubuntu/Debian:**
```bash
# Add PostgreSQL repository
sudo sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'
wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -
sudo apt-get update

# Install PostgreSQL and pgvector
sudo apt-get install -y postgresql-15 postgresql-15-pgvector
```

**macOS:**
```bash
brew install postgresql@15
brew install pgvector
```

### 2. Create Database

```bash
# Switch to postgres user
sudo -u postgres psql

# Create database and user
CREATE DATABASE islam_intelligent;
CREATE USER islam_user WITH ENCRYPTED PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE islam_intelligent TO islam_user;

# Enable pgvector extension
\c islam_intelligent
CREATE EXTENSION IF NOT EXISTS vector;

# Exit
\q
```

### 3. Configure PostgreSQL

Edit `postgresql.conf` for performance:

```bash
# Find config file
sudo -u postgres psql -c "SHOW config_file;"

# Edit settings
sudo nano /etc/postgresql/15/main/postgresql.conf
```

Recommended settings:

```ini
# Connection Settings
listen_addresses = '*'
max_connections = 200

# Memory Settings (adjust based on RAM)
shared_buffers = 2GB                    # 25% of RAM
effective_cache_size = 6GB              # 75% of RAM
work_mem = 16MB
maintenance_work_mem = 512MB

# Query Planner
effective_io_concurrency = 200
random_page_cost = 1.1                  # For SSD storage

# WAL Settings
wal_buffers = 16MB
max_wal_size = 2GB
min_wal_size = 512MB

# Logging
log_destination = 'stderr'
logging_collector = on
log_directory = 'log'
log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'
log_min_duration_statement = 1000       # Log slow queries (>1s)
```

### 4. Setup Environment

```bash
export DATABASE_URL="postgresql://islam_user:your_secure_password@localhost:5432/islam_intelligent"
export APP_ENV=production
export RAG_ENABLE_LLM=false
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_DB=islam_intelligent
export POSTGRES_USER=islam_user
export POSTGRES_PASSWORD=your_secure_password
```

### 5. Install API Dependencies

```bash
cd apps/api
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e ".[dev]"
```

### 6. Run Migrations

```bash
# Initialize database schema
python scripts/db_init.py --postgres

# Verify connection
python scripts/db_smoke.py
```

### 7. Start API Server

```bash
# Development mode with auto-reload
uvicorn islam_intelligent.api.main:app --reload --host 0.0.0.0 --port 8000

# Production mode
uvicorn islam_intelligent.api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## Production Deployment

### Docker Compose Production

Create `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init-scripts:/docker-entrypoint-initdb.d
    command: >
      postgres
      -c shared_buffers=2GB
      -c effective_cache_size=6GB
      -c work_mem=16MB
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  api:
    build:
      context: ./apps/api
      dockerfile: Dockerfile.prod
    environment:
      APP_ENV: production
      DATABASE_URL: ${DATABASE_URL}
      RAG_ENABLE_LLM: ${RAG_ENABLE_LLM:-false}
      RAG_LLM_MODEL: ${RAG_LLM_MODEL:-gpt-4o-mini}
    command: >
      uvicorn islam_intelligent.api.main:app
      --host 0.0.0.0
      --port 8000
      --workers 4
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 2G

  ui:
    build:
      context: ./apps/ui
      dockerfile: Dockerfile.prod
    environment:
      NODE_ENV: production
      NEXT_PUBLIC_API_BASE_URL: ${NEXT_PUBLIC_API_BASE_URL}
    depends_on:
      - api
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
    depends_on:
      - api
      - ui
    restart: unless-stopped

volumes:
  postgres_data:
```

### Environment-Specific Configuration

#### Development

```bash
APP_ENV=development
RAG_ENABLE_LLM=false
LOG_LEVEL=debug
```

#### Staging

```bash
APP_ENV=staging
RAG_ENABLE_LLM=true
RAG_LLM_MODEL=gpt-4o-mini
LOG_LEVEL=info
```

#### Production

```bash
APP_ENV=production
RAG_ENABLE_LLM=true
RAG_LLM_MODEL=gpt-4o
LOG_LEVEL=warning
# Disable reload, enable workers
```

## SSL/TLS Configuration

### Using Let's Encrypt

```bash
# Install certbot
sudo apt-get install certbot

# Obtain certificate
sudo certbot certonly --standalone -d your-domain.com

# Certificates will be at:
# /etc/letsencrypt/live/your-domain.com/fullchain.pem
# /etc/letsencrypt/live/your-domain.com/privkey.pem
```

### Nginx Configuration

```nginx
upstream api {
    server api:8000;
}

upstream ui {
    server ui:3000;
}

server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/nginx/ssl/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # API routes
    location /api/ {
        proxy_pass http://api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Health check
    location /health {
        proxy_pass http://api/health;
    }

    # UI
    location / {
        proxy_pass http://ui;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Backup and Recovery

### Database Backup

```bash
# Full backup
pg_dump -h localhost -U islam_user -d islam_intelligent > backup_$(date +%Y%m%d).sql

# Compressed backup
pg_dump -h localhost -U islam_user -d islam_intelligent | gzip > backup_$(date +%Y%m%d).sql.gz

# With custom format (for pg_restore)
pg_dump -h localhost -U islam_user -F c -d islam_intelligent > backup_$(date +%Y%m%d).dump
```

### Automated Backups

Create `/etc/cron.daily/islam-intelligent-backup`:

```bash
#!/bin/bash
BACKUP_DIR="/var/backups/islam-intelligent"
DB_NAME="islam_intelligent"
DB_USER="islam_user"
RETENTION_DAYS=30

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup database
pg_dump -h localhost -U $DB_USER $DB_NAME | gzip > $BACKUP_DIR/backup_$(date +%Y%m%d_%H%M%S).sql.gz

# Clean old backups
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +$RETENTION_DAYS -delete
```

Make executable:
```bash
chmod +x /etc/cron.daily/islam-intelligent-backup
```

### Restore from Backup

```bash
# From SQL dump
psql -h localhost -U islam_user -d islam_intelligent < backup_20240101.sql

# From compressed backup
gunzip -c backup_20240101.sql.gz | psql -h localhost -U islam_user -d islam_intelligent

# From custom format
pg_restore -h localhost -U islam_user -d islam_intelligent backup_20240101.dump
```

## Monitoring and Logging

### Health Checks

The API provides health endpoints:

```bash
# Basic health
curl http://localhost:8000/health

# Detailed health (if implemented)
curl http://localhost:8000/health/detailed
```

### Log Aggregation

```bash
# View API logs
docker-compose logs -f api

# View PostgreSQL logs
docker-compose logs -f postgres

# View all logs
docker-compose logs -f
```

### Prometheus Metrics (Future)

Add to `docker-compose.yml`:

```yaml
  prometheus:
    image: prom/prometheus
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana
    ports:
      - "3001:3000"
    volumes:
      - grafana_data:/var/lib/grafana
```

## Troubleshooting

### Database Connection Issues

```bash
# Check if PostgreSQL is running
sudo systemctl status postgresql

# Check connection
psql -h localhost -U islam_user -d islam_intelligent -c "SELECT 1;"

# Check pgvector extension
psql -h localhost -U islam_user -d islam_intelligent -c "SELECT * FROM pg_extension WHERE extname = 'vector';"
```

### Container Issues

```bash
# Check container status
docker-compose ps

# View logs
docker-compose logs <service-name>

# Restart service
docker-compose restart <service-name>

# Rebuild and restart
docker-compose up -d --build <service-name>
```

### Performance Issues

```bash
# Check database performance
psql -h localhost -U islam_user -d islam_intelligent -c "
SELECT pid, state, query_start, query 
FROM pg_stat_activity 
WHERE state != 'idle' 
ORDER BY query_start;
"

# Check table sizes
psql -h localhost -U islam_user -d islam_intelligent -c "
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) 
FROM pg_tables 
WHERE schemaname='public' 
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"
```

## Security Checklist

- [ ] Change default passwords
- [ ] Enable SSL/TLS
- [ ] Configure firewall rules
- [ ] Set up regular backups
- [ ] Enable database logging
- [ ] Restrict network access
- [ ] Use secrets management (Vault, AWS Secrets Manager)
- [ ] Regular security updates
- [ ] Enable audit logging
- [ ] Implement rate limiting

## Resource Requirements

| Component | CPU | Memory | Storage |
|-----------|-----|--------|---------|
| PostgreSQL | 2 cores | 4GB | 50GB SSD |
| API | 1 core | 2GB | 5GB |
| UI | 0.5 core | 1GB | 1GB |
| Neo4j (optional) | 2 cores | 4GB | 20GB SSD |

## Next Steps

After deployment:

1. **Configure Sources**: Add and trust your source documents
2. **Set Up Backups**: Automated daily backups
3. **Configure Monitoring**: Set up alerts and dashboards
4. **Test Recovery**: Verify backup restoration process
5. **Load Test**: Test with expected query volume
6. **Review Logs**: Check for errors or warnings

See also:
- [Configuration Guide](CONFIGURATION.md) - All configuration options
- [Performance Guide](PERFORMANCE.md) - Optimization and tuning
