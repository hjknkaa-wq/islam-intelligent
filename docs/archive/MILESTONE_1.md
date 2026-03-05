# Milestone 1: Foundation Implementation

**Completed**: 2026-03-02  
**Status**: ✅ COMPLETE

> Update note (2026-03-04): This document records Milestone 1 only. Full Quran ingestion pathway was added later via `scripts/ingest_quran_tanzil.py` and `make ingest:quran_full`; full hadith ingestion is still pending.

## Deliverables

### 1. Documentation (Wave 1)
- ✅ `docs/TECH_STACK.md` - MVP stack decisions (Python/FastAPI, Next.js, PostgreSQL+pgvector)
- ✅ `docs/CANONICAL_IDS.md` - Quran and Hadith canonical ID specifications
- ✅ `sources/LICENSE_AUDIT.md` - Source licensing audit with SAFE/RESTRICTED/UNKNOWN status

### 2. Repository Scaffold
- ✅ `apps/api/` - Python FastAPI project with pytest
- ✅ `apps/ui/` - Next.js 14+ with TypeScript, Tailwind, Playwright
- ✅ `packages/schemas/` - JSON schemas and SQL migrations
- ✅ `docker-compose.yml` - Development stack (Postgres+pgvector, API, UI)

### 3. Data Schemas (Task 5)
- ✅ `packages/schemas/sql/0001_init.sql` - 7 core tables + views
  - source_document (registry with license)
  - text_unit (Quran ayah, hadith items)
  - evidence_span (byte offsets + hash)
  - kg_entity, kg_edge, kg_edge_evidence (knowledge graph)
  - rag_query, rag_retrieval_result, rag_validation, rag_answer (pipeline logs)
- ✅ `packages/schemas/json/*.json` - 6 JSON schemas for validation
  - source_document.json, text_unit.json, evidence_span.json
  - kg_entity.json, kg_edge.json, rag_answer.json

### 4. Tests & Validation
- ✅ `scripts/validate_schemas.py` - Schema validation script (passes)
- ✅ `eval/cases/golden.yaml` - 11 evaluation cases (7 answerable, 4 abstention)
- ✅ `scripts/validate_eval_cases.py` - Eval case validator (passes)
- ✅ `apps/api/tests/` - pytest scaffold with placeholder test

### 5. Quran Ingestion (Minimal)
- ✅ `data/fixtures/quran_minimal.yaml` - 23 ayahs from 5 surahs
  - Surah Al-Fatiha (1:1-7) - 7 ayahs
  - Ayat al-Kursi (2:255) - 1 ayah
  - Surah Al-Ikhlas (112) - 4 ayahs
  - Surah Al-Falaq (113) - 5 ayahs
  - Surah An-Nas (114) - 6 ayahs
- ✅ `scripts/load_fixtures.py` - Fixture loader with hash computation
- ✅ `data/curated/manifests/quran_minimal_manifest.json` - Generated manifest

### 6. Evidence & Provenance
- ✅ Every text unit has SHA-256 hash
- ✅ Source document with full attribution (Tanzil Project, CC-BY-3.0)
- ✅ Canonical IDs with locator JSON
- ✅ License audit compliance

## Evidence/Provenance Examples

### Source Document Record
```json
{
  "source_id": "d23fe651-93a3-590a-8e56-06404aee4ed7",
  "source_type": "quran_text",
  "work_title": "The Quran - Uthmani Script",
  "license_id": "CC-BY-3.0",
  "license_url": "https://tanzil.net/docs/text_license",
  "rights_holder": "Tanzil Project",
  "attribution_text": "Tanzil Quran Text Copyright (C) 2007-2021 Tanzil Project...",
  "content_hash_sha256": "6950b816384705899ab27375e20d9124140a7bcbf37cd14c13e9887aae5fb26b",
  "trust_status": "trusted"
}
```

### Text Unit Record (Evidence)
```json
{
  "text_unit_id": "f8b1c759-077d-50ba-9ed0-26631d96b1db",
  "canonical_id": "quran:1:1",
  "text_canonical": "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ",
  "text_canonical_utf8_sha256": "a83ca7b2c2b3d1ef0c5dd0a0d10ae2704707602ed48cfca8268df5453a69cb34",
  "canonical_locator_json": {
    "surah": 1, "ayah": 1,
    "surah_name_ar": "الفاتحة",
    "surah_name_en": "Al-Fatiha",
    "juz": 1
  }
}
```

### Example Query with Expected Citation
**Query**: "What is the first verse of the Quran?"  
**Expected Citation**: `quran:1:1`  
**Evidence Hash**: `a83ca7b2c2b3d1ef0c5dd0a0d10ae2704707602ed48cfca8268df5453a69cb34`  
**License**: CC-BY-3.0 (Tanzil Project)

## Verification Commands

```bash
# Validate schemas
python scripts/validate_schemas.py
# Output: SUCCESS: ALL VALIDATIONS PASSED

# Validate eval cases
python scripts/validate_eval_cases.py
# Output: SUCCESS: All cases valid

# Run backend tests
cd apps/api && python -m pytest -q
# Output: 1 passed

# Load fixtures
python scripts/load_fixtures.py
# Output: SUCCESS: Fixtures loaded (23 text units)
```

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     ISLAM INTELLIGENT                        │
│              Evidence-First Knowledge Platform               │
└─────────────────────────────────────────────────────────────┘

┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   apps/ui    │────▶│   apps/api   │────▶│  PostgreSQL  │
│  Next.js 14  │     │  FastAPI     │     │  + pgvector  │
└──────────────┘     └──────────────┘     └──────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │   packages   │
                    │   schemas    │
                    │  (JSON/SQL)  │
                    └──────────────┘

Evidence Flow:
1. Query → 2. Retrieve Evidence Spans → 3. Validate Sufficiency
                              ↓
                    ┌──────────────────┐
                    │ Evidence Span    │
                    │ - text_unit_id   │
                    │ - start/end byte │
                    │ - sha256 hash    │
                    └──────────────────┘
                              ↓
4. Generate Answer with Citations → 5. Verify Citations → 6. Return
```

## Next Steps (Milestone 2+)

- Implement provenance recorder (PROV-DM)
- Build RAG pipeline (retrieve → validate → answer)
- Add evidence span creation API
- Implement KG builder
- UI provenance visualization
- Full eval harness execution

## License Compliance

All Quran fixtures use Tanzil.net text (CC BY 3.0):
- ✅ Verbatim preservation (no modifications)
- ✅ Attribution included in source_document
- ✅ Link to tanzil.net in license_url
- ✅ Copyright notice preserved

---
**Milestone 1 Complete** - Ready for Milestone 2 (Provenance + Pipeline)
