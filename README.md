# Islam Intelligent

Islam Intelligent is a provenance-first Islamic knowledge intelligence platform.

The repository is a working monorepo with backend, frontend, shared schemas, and verification tooling. Every claim in the system must be traceable to explicit source evidence.

## Repository layout

```text
islam-intelligent/
├── apps/
│   ├── api/                  # FastAPI backend (ingest, provenance, KG, RAG)
│   └── ui/                   # Next.js frontend (query, citations, evidence)
├── packages/
│   └── schemas/              # Shared JSON + SQL contracts
├── scripts/                  # Verification, DB, eval, and utility scripts
├── data/                     # Fixtures and curated manifests
├── eval/                     # Golden cases and eval report artifacts
├── docs/                     # Technical docs
│   └── archive/              # Historical planning/status documents
├── sources/                  # Source licensing audit
├── .github/workflows/ci.yml  # CI pipeline
├── Makefile
└── docker-compose.yml
```

## Quick start (Docker)

```bash
make up
make migrate
make ingest:hadith_full
make test
make logs
```

To seed only minimal local fixtures instead of full Quran+hadith ingestion:

```bash
make ingest:quran_sample
```

To ingest only full Quran (Tanzil) while keeping minimal hadith fixtures:

```bash
make ingest:quran_full
```

Stop services:

```bash
make down
```

## Local checks

```bash
python scripts/verify_all.py
PYTHONPATH=apps/api/src python -m pytest apps/api/tests -q
npm --prefix apps/ui ci
npm --prefix apps/ui test -- --run
npm --prefix apps/ui run test:e2e
```

## CI

GitHub Actions workflow: `.github/workflows/ci.yml`

- `verify-all`: Python setup + `python scripts/verify_all.py`
- `ui-tests`: Node setup + Vitest + Playwright E2E

## Documentation

- `AGENTS.md` - agent operating knowledge for this repository
- `docs/CI.md` - CI details and local reproduction
- `docs/TECH_STACK.md` - MVP stack decisions
- `docs/CANONICAL_IDS.md` - Quran/Hadith canonical ID rules
- `docs/archive/` - archived planning and status documents

## Notes

- Local runtime config file `opencode.json` is ignored by git.
- External local research clones `faithful_rag_repo/` and `ground_cite_repo/` are ignored by git.
- Keep all secrets in environment variables, never in committed files.
