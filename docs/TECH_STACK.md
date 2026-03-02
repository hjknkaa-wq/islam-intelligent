# MVP Tech Stack

## Overview

This document locks the technology decisions for the Islam Intelligent MVP. Every choice is deliberate, serving the core requirement of provenance-backed accuracy with minimal moving parts.

---

## Backend Stack

| Component | Technology | Version |
|-----------|------------|---------|
| Language | Python | 3.12+ |
| Framework | FastAPI | Latest stable |
| ORM | SQLAlchemy | 2.0+ |
| Validation | Pydantic | 2.x |
| Migrations | Alembic | Latest stable |

### Why These Choices

**Python 3.12+**
- Mature ecosystem for Arabic text processing
- Excellent libraries for data pipelines (pandas, numpy)
- Type hints enable static analysis and safer refactors
- Native support for improved pattern matching and error messages

**FastAPI**
- Automatic OpenAPI spec generation for frontend contracts
- Native async support for concurrent processing
- Built-in request/response validation via Pydantic
- Minimal boilerplate, maximal clarity

**SQLAlchemy 2.0+**
- Modern async ORM with explicit session management
- Type-safe query building
- Proven track record for data integrity
- Excellent migration support via Alembic

**Pydantic 2.x**
- Runtime validation of all data contracts
- JSON Schema generation for API documentation
- Integration with FastAPI for automatic validation
- Type safety across the stack

**Alembic**
- Database migration versioning
- Schema change tracking with full history
- Support for reversible migrations
- Programmatic migration execution for CI/CD

---

## Database Stack

| Component | Technology | Version |
|-----------|------------|---------|
| Primary DB | PostgreSQL | 15+ |
| Vector Extension | pgvector | 0.5+ |
| Full-Text Search | tsvector + pg_trgm | Built-in |

### Why PostgreSQL as Single Store

**Single Source of Truth**
- One database to backup, monitor, and optimize
- ACID guarantees for all data (relational + vector + text)
- Single connection pool, single query language
- No synchronization complexity between stores

**pgvector Extension**
- Stores embeddings alongside source text
- Supports cosine similarity and L2 distance
- Integrates with SQLAlchemy via pgvector-python
- Enables semantic search within same transaction as metadata queries

**tsvector + pg_trgm**
- Native full-text search for Arabic content
- Trigram similarity for fuzzy matching
- No external dependencies (Elasticsearch, Meilisearch)
- Indexable and queryable via standard SQL

### Why NOT Neo4j/Qdrant/Pinecone for v1

**Neo4j**
- Graph queries valuable for sanad chains, but add operational complexity
- Requires separate deployment and expertise
- Deferred to post-MVP when knowledge graph relationships mature

**Qdrant/Pinecone**
- Purpose-built vector stores offer marginal gains
- Add network latency and operational burden
- pgvector handles our expected scale (thousands of texts, millions of embeddings)
- Migration path exists if we hit scale limits

---

## Frontend Stack

| Component | Technology | Version |
|-----------|------------|---------|
| Framework | Next.js | 14+ |
| Language | TypeScript | 5.x |
| Styling | TailwindCSS | 3.4+ |
| Components | shadcn/ui | Latest |

### Why These Choices

**Next.js 14+**
- App Router for server components and streaming
- Static generation for read-heavy content (Quran, Hadith)
- API routes for backend-for-frontend patterns
- Vercel deployment target for zero-config hosting

**TypeScript**
- End-to-end type safety with backend Pydantic schemas
- IntelliSense and refactoring support
- Compile-time catching of API contract mismatches

**TailwindCSS**
- Utility-first for rapid UI iteration
- Small bundle size via purge
- RTL (right-to-left) support for Arabic interfaces
- Consistent design tokens via configuration

**shadcn/ui**
- Copy-paste components, zero dependency bloat
- Built on Radix primitives for accessibility
- Tailwind-first styling approach
- Easy to customize and extend

---

## Testing Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Backend Tests | pytest | Unit and integration tests |
| Frontend Tests | Vitest | Component and unit tests |
| E2E Tests | Playwright | Full user journey validation |

### Why These Choices

**pytest**
- Industry standard for Python testing
- Async test support via pytest-asyncio
- Fixtures for database state management
- Coverage reporting and parallel execution

**Vitest**
- Fast, Vite-native test runner
- TypeScript support out of the box
- Jest-compatible API for familiar patterns

**Playwright**
- Cross-browser testing (Chromium, Firefox, WebKit)
- Arabic text rendering validation
- Visual regression testing for UI consistency
- Trace viewer for debugging flaky tests

---

## Deployment Targets

| Environment | Target | Notes |
|-------------|--------|-------|
| Development | Docker Compose | Single command local stack |
| Staging | Vercel + Supabase | Serverless frontend, managed Postgres |
| Production | Vercel + AWS RDS | CDN edge, managed database with backups |

### Rationale

**Vercel for Frontend**
- Zero-config deployment from Git
- Automatic preview deployments for PRs
- Edge network for global low-latency
- Built-in analytics and monitoring

**Managed PostgreSQL**
- Automated backups and point-in-time recovery
- Connection pooling via PgBouncer
- Read replicas if query load requires
- Monitoring and alerting via provider dashboards

---

## Excluded from MVP

The following technologies are intentionally deferred. They may be valuable post-MVP but add complexity we do not need yet.

| Technology | Reason Deferred |
|------------|-----------------|
| Neo4j | Graph relationships can be modeled in Postgres JSONB; add if query complexity justifies |
| Qdrant/Pinecone | pgvector handles current scale; migrate if embedding count exceeds 10M |
| Redis | Session storage and caching unnecessary with stateless JWT auth |
| Kafka/RabbitMQ | Event streaming overkill for single-node ingestion |
| Elasticsearch | tsvector/pg_trgm sufficient for Arabic search at current scale |
| Kubernetes | Docker Compose + managed services simpler for single-tenant MVP |

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-02 | PostgreSQL as single store | Operational simplicity, proven reliability, pgvector maturity |
| 2026-03-02 | FastAPI over Django/Flask | Modern async, automatic API docs, type safety |
| 2026-03-02 | Next.js over vanilla React | Server components, static generation, Vercel integration |
| 2026-03-02 | No dedicated vector store | pgvector sufficient for MVP scale, simpler stack |
| 2026-03-02 | shadcn/ui over MUI/Chakra | Zero runtime deps, full control, Tailwind-native |

---

## Migration Path

When we outgrow any component:

1. **Database Scale**: Add read replicas, then consider Qdrant if vector queries bottleneck
2. **Search Complexity**: Migrate to Meilisearch if tsvector performance degrades
3. **Graph Queries**: Add Neo4j alongside Postgres for relationship-heavy features
4. **Frontend Scale**: Split to micro-frontends or edge functions

Every migration decision requires load testing data and explicit performance thresholds.

---

## Operational Requirements

| Requirement | Implementation |
|-------------|----------------|
| Backups | Daily automated + point-in-time recovery |
| Monitoring | Application logs + database metrics + error tracking |
| CI/CD | GitHub Actions for test + build + deploy |
| Secrets | Environment variables, never committed |
| Migrations | Automated in CI, reversible, tested against staging data |

---

## Summary

The MVP stack prioritizes operational simplicity and correctness over theoretical performance. A single PostgreSQL instance with pgvector handles relational, vector, and text search needs. Python/FastAPI provides type-safe API development. Next.js delivers server-rendered, fast UIs. This stack supports the core mission: accurate, provenance-backed Islamic knowledge retrieval without infrastructure distractions.
