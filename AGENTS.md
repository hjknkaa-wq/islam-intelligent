# ISLAM INTELLIGENT - AGENT KNOWLEDGE BASE

**Project:** Provenance-first Islamic knowledge intelligence platform
**Focus:** Deterministic pipelines, explicit citations, no hallucinated sources
**Updated:** 2026-03-04

---

## OVERVIEW

This repository contains a working monorepo scaffold with:
- Backend API (`apps/api`) for ingestion, provenance, KG, and RAG pipeline logic
- Frontend UI (`apps/ui`) for query, answer, citation, and evidence rendering
- Shared schema package (`packages/schemas`) for JSON and SQL contracts
- Verification scripts (`scripts`) and CI workflow (`.github/workflows/ci.yml`)

Core principle: no claim without explicit source pointer.

---

## STRUCTURE

```text
islam-intelligent/
├── README.md
├── AGENTS.md
├── AGENT.md                          # Legacy Indonesian rule sheet
├── Makefile
├── docker-compose.yml
├── .github/
│   └── workflows/
│       └── ci.yml
├── apps/
│   ├── api/
│   │   ├── src/islam_intelligent/
│   │   └── tests/
│   └── ui/
│       ├── src/
│       └── tests/
├── packages/
│   └── schemas/
│       ├── json/
│       └── sql/
├── scripts/
├── data/
│   ├── fixtures/
│   └── curated/
├── eval/
│   ├── cases/
│   └── report.json
├── docs/
│   ├── CANONICAL_IDS.md
│   ├── CI.md
│   ├── TECH_STACK.md
│   └── archive/
├── sources/
│   └── LICENSE_AUDIT.md
└── .sisyphus/
    ├── evidence/
    ├── plans/
    └── tasks/
```

---

## WHERE TO LOOK

| Need | Location | Notes |
|------|----------|-------|
| API routes and contracts | `apps/api/src/islam_intelligent/api/routes/` | FastAPI endpoints |
| RAG flow | `apps/api/src/islam_intelligent/rag/pipeline/core.py` | Retrieve -> verify -> answer |
| Provenance logic | `apps/api/src/islam_intelligent/provenance/` | Hash chain and record models |
| UI rendering | `apps/ui/src/components/` | Answer, citations, evidence display |
| Shared schemas | `packages/schemas/json/`, `packages/schemas/sql/` | Canonical data contracts |
| Verification scripts | `scripts/verify_all.py` + `scripts/verify_*.py` | CI and local checks |
| CI pipeline | `.github/workflows/ci.yml` | `verify-all` and `ui-tests` jobs |
| Archived planning docs | `docs/archive/` | Historical plans/status docs |
| Local OpenCode config | `opencode.json` (gitignored) | Optional local runtime config |

---

## CITATION REQUIREMENTS (HARD RULES)

- **Quran:** surah:ayah + Arabic snippet + translation source
- **Hadith:** collection + number + chapter + grading (+ sanad when available)
- **Tafsir/Fiqh/Sirah:** work + author + volume/page or canonical section ID
- **Engineering claims:** file path + symbol + precise location

Evidence format:

```text
Claim -> Source ID + Location -> Provenance chain
No claim without explicit pointer to source material
```

---

## ENGINEERING STANDARDS

- ETL pipelines must be idempotent or checkpointed.
- Every transformation must preserve provenance fields.
- KG edges must support conflicting-source coexistence.
- RAG responses must log retrieved evidence and final citations.
- Abstain when evidence is insufficient.

---

## COMMANDS (CURRENT REPOSITORY)

### Project-level checks

```bash
python scripts/verify_all.py
PYTHONPATH=apps/api/src python -m pytest apps/api/tests -q
npm --prefix apps/ui ci
npm --prefix apps/ui test -- --run
npm --prefix apps/ui run test:e2e
```

### Make targets

```bash
make up
make down
make migrate
make ingest:quran_sample
make ingest:quran_full
make ingest:hadith_full
make test
make logs
```

---

## NOTES

- This is **not** a configuration-only repository; it contains active API/UI/code/tests.
- Root planning/status docs were archived under `docs/archive/` during cleanup.
- `faithful_rag_repo/` and `ground_cite_repo/` are local external clones and are gitignored.
- Keep secrets out of git; use environment variables.

### When evidence is missing

```text
Insufficient sources. I do not have enough citations to answer safely.
Please provide Quran references (surah:ayah), hadith references
(collection + number), or scholarly sources with bibliographic detail.
```
