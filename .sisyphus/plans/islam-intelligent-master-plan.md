# ISLAM INTELLIGENT Master Plan (End-to-End)

## TL;DR
> **Summary**: Bangun platform Islamic Knowledge Intelligence yang evidence-first: sistem hanya menjawab bila setiap klaim terikat ke bukti (evidence spans) dengan provenance lengkap; jika bukti kurang -> abstain.
> **Deliverables**: repo scaffold + skema data minimal (registry/text units/spans/KG/RAG/eval) + pipeline retrieve->validate->answer + provenance-first UI + eval harness (citation-required + abstention).
> **Effort**: XL
> **Parallel**: YES - 5 waves
> **Critical Path**: Foundation -> Ingestion+Normalization -> KG -> RAG -> Eval -> Hardening

## Context

### Original Request
- Buat master plan end-to-end untuk ISLAM INTELLIGENT (Palantir-like Islamic Knowledge Intelligence Platform).
- Wajib: evidence-first, provenance selalu tampil, no hallucination (abstain jika bukti kurang).
- Output: milestone berurutan + deliverables + acceptance criteria + struktur folder repo + skema data minimal:
  - Source registry (work/edition/license/checksum)
  - Text units (Qur'an ayat, hadith item)
  - Evidence spans (offset pointers)
  - KG entities/edges + provenance per edge
  - RAG pipeline (retrieve->validate->answer)
  - Eval harness (citation-required tests + abstention tests)

### Interview Summary
- Repo saat ini bersifat config-only (OpenCode/Oh-My-OpenCode). Tidak ada application code. Plan ini mencakup scaffolding end-to-end dari nol.

### Metis Review (gaps addressed)
- Ditetapkan Wave 0 (Foundation) sebelum ingestion.
- Ditambahkan: license audit sebagai gate sebelum ingest sumber nyata.
- Ditambahkan: canonical ID spec (khusus hadith numbering system) sebagai gate.
- Ditambahkan: golden eval dataset + abstention cases sebelum RAG.
- Risiko utama di-address: Unicode Arabic normalization/offsets, licensing, hadith numbering, abstention reliability, scope creep.

## Work Objectives

### Core Objective
Menyediakan sistem yang:
1) selalu menampilkan provenance (API + UI),
2) hanya menghasilkan jawaban jika bukti cukup dan tervalidasi, dan
3) abstain secara deterministik bila bukti kurang.

### Deliverables
- Repo scaffold yang siap dev: `apps/api` (pipeline + API), `apps/ui` (UI), `packages/schemas` (JSON Schemas + SQL), `eval/` (cases), `scripts/`.
- Skema minimal (relational + JSON schema) untuk:
  - Source registry
  - Text units (Qur'an ayat, hadith item)
  - Evidence spans (UTF-8 byte offsets + hash)
  - KG entities/edges + evidence per edge
  - RAG logs + Answer contract (statement-level citations)
  - Eval harness (citation-required + abstention)
- Pipeline retrieve->validate->answer dengan guardrails:
  - retrieval gated (tanpa evidence -> tidak panggil LLM)
  - validation gate (sufficiency threshold) + citation verification
  - output selalu menyertakan citations dan provenance
- UI provenance-first: setiap citation clickable ke span (highlight) dan source registry detail (work/edition/license).
- Eval harness: test suite (citation-required + abstention correctness) + laporan JSON.

### Definition of Done (agent-executable)
- `python -m pytest -q` lulus (backend + pipelines + eval checks).
- `python scripts/run_eval.py --suite golden --output eval/report.json` menghasilkan metrik:
  - `citation_required_pass_rate == 1.0`
  - `abstention_f1 >= 0.95` (untuk subset unanswerable)
  - `locator_resolve_pass_rate == 1.0`
- `node -v` + `pnpm -v` (atau `npm -v`) tersedia dan `apps/ui` build lulus.
- UI E2E (Playwright) lulus: provenance selalu tampil; tidak ada jawaban dirender tanpa citations.

### Must Have
- Evidence-first contract enforced di server: tidak ada mode untuk bypass.
- Provenance always-on (API + UI).
- Immutability/versioning untuk data mentah dan hasil transform (append-only + content-hash).
- Skema data minimal + validator.
- Logging RAG lengkap: retrieval -> validation -> answer (termasuk abstain reason).

### Must NOT Have (guardrails)
- Tidak ada klaim Islami tanpa pointer ke sumber (surah:ayah / hadith ref / tafsir ref) dan EvidenceSpan.
- Tidak ada "jawaban dari ingatan"; jika evidence kurang -> abstain.
- Tidak ada ingestion sumber yang lisensinya belum terverifikasi sebagai redistributable.
- Tidak ada penghapusan data; hanya versioned retraction/supersede.
- Tidak membangun graph visualization Palantir-like pada v1 (UI fokus search + citations + provenance trail).
- Tidak meng-encode fatwa/ijtihad otomatis.

## Verification Strategy
> ZERO HUMAN INTERVENTION.
- Test decision: tests-after (tapi setiap task wajib menambah tes/validator yang bisa dijalankan otomatis).
- QA policy: setiap task punya skenario happy + failure yang menghasilkan evidence file di `.sisyphus/evidence/`.

## Execution Strategy

### Target Repo Folder Structure
Executor MUST create struktur berikut (MVP):

```
  AGENTS.md
  opencode.jsonc
  .opencode/
  .sisyphus/

  docs/
  sources/

  apps/
    api/
      pyproject.toml
      src/islam_intelligent/
        __init__.py
        config.py
        db/
          engine.py
          migrations/
        domain/
          models.py
          schemas.py
        provenance/
          prov_models.py
          recorder.py
        ingest/
          __init__.py
          sources/
        normalize/
          __init__.py
        kg/
          __init__.py
        rag/
          __init__.py
        api/
          main.py
          routes/
        eval/
          __init__.py
      tests/
        test_schema_validation.py
        test_span_roundtrip.py
        test_citation_required.py
        test_abstention.py

    ui/
      package.json
      playwright.config.ts
      src/
        app/
        components/
        lib/
        tests/e2e/

  packages/
    schemas/
      json/
      sql/
      docs/

  data/
    raw/           # append-only, content-hash addressed
    curated/       # manifests + checksums + license notes
    fixtures/      # tiny license-safe fixtures for tests

  eval/
    cases/

  scripts/
```

### Parallel Execution Waves

Wave 1 (Foundation: decisions + scaffold)
- In parallel: 1, 2, 3
- Then: 4 -> 5
- After 5: 6

Wave 2 (Provenance + fixtures ingestion + spans)
- 7 -> 8 -> 9 -> 10 -> 11

Wave 3 (KG + retrieval)
- 12 and 13

Wave 4 (RAG + API + UI)
- 14 -> 15 -> 16 -> 17

Wave 5 (Eval + hardening)
- 18 -> 19 -> 20 -> 21 -> 22 -> 23 -> 24 -> 25 -> 26 -> 27 -> 28 -> 29 -> 30

### Dependency Matrix (decision-complete)

| Task | Depends On |
|------|------------|
| 1 | - |
| 2 | - |
| 3 | - |
| 4 | 1 |
| 5 | 2, 4 |
| 6 | 3 |
| 7 | 5 |
| 8 | 7 |
| 9 | 8 |
| 10 | 2, 9 |
| 11 | 10 |
| 12 | 11 |
| 13 | 10, 5 |
| 14 | 12, 13 |
| 15 | 14 |
| 16 | 15 |
| 17 | 16 |
| 18 | 6, 15 |
| 19 | 18 |
| 20 | 5, 8 |
| 21 | 20 |
| 22 | 14 |
| 23 | 15, 22 |
| 24 | 23 |
| 25 | 18, 24 |
| 26 | 16, 18 |
| 27 | 3, 15 |
| 28 | 19 |
| 29 | 28 |
| 30 | 25, 26, 29 |

## Minimal Data Schemas (Decision-Complete)

### Canonical Text + Span Addressing (MVP)
- Canonical storage for text units: Unicode NFC string in DB (`text_canonical`).
- Canonical offsets for EvidenceSpan: UTF-8 byte offsets (`start_byte`, `end_byte`) into `text_canonical.encode('utf-8')`.
- Span verification: store `snippet_text` (optional) + `snippet_utf8_sha256` + optional `prefix_text`/`suffix_text` for fuzzy re-anchor.
- UI must convert: JS UTF-16 indices <-> UTF-8 bytes using `TextEncoder`/`TextDecoder` (never assume `string.length`).

References:
- UAX #15 (Normalization): https://unicode.org/reports/tr15/
- UAX #29 (Grapheme clusters for UI selection): https://unicode.org/reports/tr29/
- W3C Web Annotation Model (TextPositionSelector concepts): https://www.w3.org/TR/annotation-model/
- Unicode source spans: https://totbwf.github.io/posts/unicode-source-spans.html

### 1) Source Registry
Table: `source_document`

Minimal fields:
- `source_id` (UUID, PK)
- `source_type` (enum; e.g. `quran_text`, `hadith_collection`, `tafsir`, `translation`, `other`)
- `work_title`
- `author` (nullable)
- `edition` (nullable)
- `language` (BCP-47-like short; `ar`, `en`, `id`)
- `canonical_ref` (string: bibliographic ref / URL)
- `license_id` (string)
- `license_url` (string)
- `rights_holder` (string, nullable)
- `attribution_text` (string, nullable)
- `retrieved_at` (timestamp)
- `content_hash_sha256` (string)
- `content_mime` (string)
- `content_length_bytes` (int)
- `storage_path` (string)
- `trust_status` (enum: `untrusted`, `trusted`)
- `supersedes_source_id` (UUID, nullable)
- `retraction_reason` (string, nullable)

Acceptance invariant:
- Tidak ada ingestion tanpa `source_document`.

### 2) Text Units
Table: `text_unit`

Minimal fields:
- `text_unit_id` (UUID, PK)
- `source_id` (FK)
- `unit_type` (enum: `quran_ayah`, `hadith_item`)
- `canonical_id` (string)
  - Quran: `quran:{surah}:{ayah}`
  - Hadith: `hadith:{collection}:{numbering_system}:{hadith_number}`
- `canonical_locator_json` (JSON)
- `text_canonical` (string, NFC)
- `text_canonical_utf8_sha256` (string)
- `created_at` (timestamp)

Acceptance invariant:
- `text_canonical_utf8_sha256 == sha256(utf8(text_canonical))`.

### 3) Evidence Spans
Table: `evidence_span`

Minimal fields:
- `evidence_span_id` (UUID, PK)
- `text_unit_id` (FK)
- `start_byte` (int, inclusive)
- `end_byte` (int, exclusive)
- `snippet_text` (string, nullable)
- `snippet_utf8_sha256` (string)
- `prefix_text` (string, nullable)
- `suffix_text` (string, nullable)
- `created_at` (timestamp)

Validation:
- range valid; slice exact match by hash; optional prefix/suffix used only for re-anchor.

### 4) KG Entities/Edges + provenance per edge
Tables:
- `kg_entity(entity_id, entity_type, canonical_name, aliases_json, created_at)`
- `kg_edge(edge_id, subject_entity_id, predicate, object_entity_id, object_literal, created_at)`
- `kg_edge_evidence(edge_id, evidence_span_id, relevance_score, asserted_activity_id)`

Acceptance invariant:
- setiap `kg_edge` memiliki >= 1 row di `kg_edge_evidence`.

### 5) RAG pipeline logs + answer contract
Tables:
- `rag_query(rag_query_id, query_text, created_at)`
- `rag_retrieval_result(rag_query_id, evidence_span_id, rank, score_lexical, score_vector, score_final)`
- `rag_validation(rag_query_id, sufficiency_score, threshold_tau, verdict, fail_reason)`
- `rag_answer(rag_query_id, verdict, answer_json, created_at)`

Answer JSON contract (MVP):
```json
{
  "verdict": "answer",
  "statements": [
    {
      "text": "...",
      "citations": [
        {
          "evidence_span_id": "...",
          "source_id": "...",
          "canonical_id": "quran:2:255",
          "start_byte": 0,
          "end_byte": 10,
          "snippet_text": "...",
          "snippet_utf8_sha256": "sha256:...",
          "license_id": "...",
          "work_title": "...",
          "edition": "..."
        }
      ]
    }
  ],
  "retrieved_evidence": [ ... ],
  "validation": { "sufficiency_score": 0.9, "threshold_tau": 0.8, "verdict": "pass" }
}
```

Invariants:
- `verdict=answer` => setiap `statements[i].citations.length >= 1`.
- Jika invariant gagal => server harus mengubah menjadi `verdict=abstain`.

### 6) Eval harness
Eval case format (YAML/JSON):
- `case_id`
- `query`
- `expected_verdict` (`answer`/`abstain`)
- `required_citations` (list canonical_id; optional)
- `notes`

Required tests:
- citation-required tests: fail jika statement tanpa citations.
- abstention tests: case unanswerable harus abstain.

References:
- RAGAS: https://github.com/vibrantlabsai/ragas
- ARES: https://github.com/stanford-futuredata/ARES
- AbstentionBench: https://github.com/facebookresearch/AbstentionBench

## TODOs
> Implementation + Test = ONE task.

- [x] 1. Create `docs/TECH_STACK.md` (decision-lock) ✅ COMPLETED

  **What to do**:
  - Putuskan stack MVP (tanpa memperluas): Python 3.12 + FastAPI + Postgres + Alembic + SQLAlchemy + Pydantic; UI Next.js + Playwright.
  - Dokumentasikan mengapa memilih Postgres + pgvector + tsvector/pg_trgm (single store, auditability).

  **Must NOT do**:
  - Jangan menambah infra tambahan (Neo4j/Qdrant) pada MVP.

  **Recommended Agent Profile**:
  - Category: `writing` — Reason: pure decision doc.
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 4 | Blocked By: []

  **References**:
  - Project rules: `AGENTS.md`

  **Acceptance Criteria**:
  - [ ] `docs/TECH_STACK.md` ada dan menetapkan stack final (no TODO placeholders).

  **QA Scenarios**:
  ```
  Scenario: Doc completeness
    Tool: Bash
    Steps: rg -n "TBD|TODO" docs/TECH_STACK.md
    Expected: no matches
    Evidence: .sisyphus/evidence/task-1-tech-stack-rg.txt

  Scenario: Forbidden infra creep
    Tool: Bash
    Steps: rg -n "Neo4j|Qdrant|Pinecone" docs/TECH_STACK.md
    Expected: either absent OR explicitly marked "v2" only
    Evidence: .sisyphus/evidence/task-1-tech-stack-infra.txt
  ```

  **Commit**: YES | Message: `docs(tech-stack): lock MVP stack decisions` | Files: [docs/TECH_STACK.md]

- [x] 2. Create `docs/CANONICAL_IDS.md` (ID spec) ✅ COMPLETED

  **What to do**:
  - Tetapkan canonical ID format untuk Quran ayah, hadith item (wajib mencantumkan `numbering_system`).
  - Tetapkan canonical locator JSON untuk masing-masing tipe.

  **Must NOT do**:
  - Jangan mengasumsikan hadith numbering universal.

  **Recommended Agent Profile**:
  - Category: `writing`
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 5, 10-13 | Blocked By: []

  **References**:
  - Project rules: `AGENTS.md`

  **Acceptance Criteria**:
  - [ ] `docs/CANONICAL_IDS.md` mencakup: `quran:{surah}:{ayah}`, `hadith:{collection}:{numbering_system}:{hadith_number}`, dan aturan validasi.

  **QA Scenarios**:
  ```
  Scenario: No ambiguous hadith IDs
    Tool: Bash
    Steps: rg -n "hadith:.*\{collection\}.*\{hadith_number\}" docs/CANONICAL_IDS.md
    Expected: spec includes numbering_system explicitly
    Evidence: .sisyphus/evidence/task-2-canonical-ids.txt
  
  Scenario: No TODO markers
    Tool: Bash
    Steps: rg -n "TBD|TODO" docs/CANONICAL_IDS.md
    Expected: no matches
    Evidence: .sisyphus/evidence/task-2-canonical-ids-todo.txt
  ```

  **Commit**: YES | Message: `docs(ids): define canonical IDs and locators` | Files: [docs/CANONICAL_IDS.md]

- [x] 3. Create `sources/LICENSE_AUDIT.md` + enforce license gate ✅ COMPLETED

  **What to do**:
  - Buat daftar source candidates + status (SAFE/RESTRICTED/UNKNOWN) + bukti license (link + ringkasan kewajiban atribusi).
  - Tambahkan rule: ingestion job hanya boleh jalan untuk sources berstatus SAFE.

  **Must NOT do**:
  - Jangan memasukkan sumber dengan status UNKNOWN ke fixture/prod.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: policy + research.
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 11-13 | Blocked By: []

  **References**:
  - Project rules: `AGENTS.md`

  **Acceptance Criteria**:
  - [ ] `sources/LICENSE_AUDIT.md` exists dan setiap source punya status + license link.
  - [ ] Ada skrip/validator yang gagal bila ada ingestion untuk source non-SAFE.

  **QA Scenarios**:
  ```
  Scenario: License audit has no UNKNOWN for v1 fixtures
    Tool: Bash
    Steps: rg -n "fixtures.*UNKNOWN" sources/LICENSE_AUDIT.md
    Expected: no matches
    Evidence: .sisyphus/evidence/task-3-license-audit.txt
  
  Scenario: Gate triggers on non-safe
    Tool: Bash
    Steps: python scripts/verify_license_gate.py --expect-fail-on UNKNOWN
    Expected: exit code 0 (script proves it blocks)
    Evidence: .sisyphus/evidence/task-3-license-gate.txt
  ```

  **Commit**: YES | Message: `docs(licensing): add license audit and ingestion gate` | Files: [sources/LICENSE_AUDIT.md, scripts/verify_license_gate.py]

- [x] 4. Scaffold repo code (apps/api + apps/ui + packages/schemas) ✅ COMPLETED

  **What to do**:
  - Buat struktur folder target.
  - Setup Python project (`pyproject.toml`) + FastAPI skeleton + pytest.
  - Setup UI project (Next.js) + Playwright skeleton.
  - Setup `packages/schemas` (JSON schemas + SQL migration files).

  **Must NOT do**:
  - Jangan menambah fitur selain scaffold + test runners.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: multi-module scaffolding.
  - Skills: []

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: 5-30 | Blocked By: 1

  **References**:
  - Orchestrator config: `opencode.jsonc`
  - Agent categories: `.opencode/oh-my-opencode.jsonc`

  **Acceptance Criteria**:
  - [ ] `python -m pytest -q` runs (even if 0 tests initially) and exits 0.
  - [ ] `apps/ui` can run `npm test` or `pnpm test` (or Playwright) without config errors.

  **QA Scenarios**:
  ```
  Scenario: Backend test runner works
    Tool: Bash
    Steps: (cd apps/api && python -m pytest -q)
    Expected: exit code 0
    Evidence: .sisyphus/evidence/task-4-pytest.txt

  Scenario: UI Playwright config loads
    Tool: Bash
    Steps: (cd apps/ui && npx playwright --version)
    Expected: prints version
    Evidence: .sisyphus/evidence/task-4-playwright.txt
  ```

  **Commit**: YES | Message: `chore(scaffold): add api/ui/schemas skeleton` | Files: [apps/api/*, apps/ui/*, packages/schemas/*]

- [x] 5. Lock minimal schemas (JSON + SQL) for required entities ✅ COMPLETED

  **What to do**:
  - Create SQL migration `packages/schemas/sql/0001_init.sql` untuk tables minimal (source_document, text_unit, evidence_span, kg_entity, kg_edge, kg_edge_evidence, rag_*).
  - Create JSON Schemas di `packages/schemas/json/` yang mirror domain contracts.

  **Must NOT do**:
  - Jangan menambah tabel di luar kebutuhan minimal request.

  **Recommended Agent Profile**:
  - Category: `islam-etl` — Reason: schema + provenance strict.
  - Skills: []

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: 7-30 | Blocked By: 2, 4

  **References**:
  - W3C PROV-DM: https://www.w3.org/TR/prov-dm/

  **Acceptance Criteria**:
  - [ ] Migration file exists and includes all required tables.
  - [ ] Schema validator script exists and passes on sample records.

  **QA Scenarios**:
  ```
  Scenario: Schema files exist
    Tool: Bash
    Steps: ls packages/schemas/json && ls packages/schemas/sql
    Expected: includes required schema filenames + 0001_init.sql
    Evidence: .sisyphus/evidence/task-5-schema-ls.txt

  Scenario: JSON schemas validate samples
    Tool: Bash
    Steps: python scripts/validate_schemas.py
    Expected: exit code 0
    Evidence: .sisyphus/evidence/task-5-schema-validate.txt
  ```

  **Commit**: YES | Message: `feat(schema): add minimal data model for evidence-first system` | Files: [packages/schemas/*, scripts/validate_schemas.py]

- [x] 6. Create golden eval cases + unanswerable abstention cases ✅ COMPLETED

  **What to do**:
  - Create `eval/cases/golden.yaml` with:
    - answerable cases that map to fixtures (Quran ayat + hadith items)
    - unanswerable cases that MUST abstain
  - Ensure cases only reference fixture data IDs (not external sources).

  **Must NOT do**:
  - Jangan memasukkan klaim Islami tanpa bukti fixture.

  **Recommended Agent Profile**:
  - Category: `islam-eval`
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 25-30 | Blocked By: 3

  **References**:
  - AbstentionBench patterns: https://github.com/facebookresearch/AbstentionBench

  **Acceptance Criteria**:
  - [ ] `python scripts/validate_eval_cases.py` passes.

  **QA Scenarios**:
  ```
  Scenario: Cases validate
    Tool: Bash
    Steps: python scripts/validate_eval_cases.py
    Expected: exit code 0
    Evidence: .sisyphus/evidence/task-6-eval-validate.txt

  Scenario: Unanswerable present
    Tool: Bash
    Steps: rg -n "expected_verdict: abstain" eval/cases/golden.yaml
    Expected: >= 1 match
    Evidence: .sisyphus/evidence/task-6-eval-abstain.txt
  ```

  **Commit**: YES | Message: `test(eval): add golden and abstention cases` | Files: [eval/cases/golden.yaml, scripts/validate_eval_cases.py]

- [x] 7. Implement provenance core (PROV-like) + recorder ✅ COMPLETED

  **What to do**:
  - Implement minimal PROV tables or models: `prov_entity`, `prov_activity`, `prov_agent`, and relations (generated_by, used, derived_from, attributed_to).
  - Provide helper `recorder.py` to record activities with `git_sha`, params hash, timestamps.

  **Must NOT do**:
  - Jangan membuat provenance opsional; semua pipeline steps wajib mencatat.

  **Recommended Agent Profile**:
  - Category: `islam-etl`
  - Skills: []

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: 8-30 | Blocked By: 5

  **References**:
  - W3C PROV constraints: https://www.w3.org/TR/prov-constraints/

  **Acceptance Criteria**:
  - [ ] Unit test proves each domain entity has generation activity recorded.

  **QA Scenarios**:
  ```
  Scenario: Provenance link exists
    Tool: Bash
    Steps: python -m pytest -q apps/api/tests/test_provenance_links.py
    Expected: pass
    Evidence: .sisyphus/evidence/task-7-provenance-tests.txt

  Scenario: No orphan entities
    Tool: Bash
    Steps: python scripts/verify_provenance.py --check no_orphans
    Expected: 0 violations
    Evidence: .sisyphus/evidence/task-7-provenance-verify.txt
  ```

  **Commit**: YES | Message: `feat(provenance): add PROV-like core and recorder` | Files: [apps/api/src/islam_intelligent/provenance/*, scripts/verify_provenance.py]

- [x] 8. Implement source registry + raw manifest (append-only) ✅ COMPLETED

  **What to do**:
  - Implement create/read APIs and ingestion utilities for `source_document`.
  - Implement manifest generator: sha256 for raw files + store manifest in `data/curated/manifests/`.
  - Enforce append-only: any update creates new version row with `supersedes_source_id`.

  **Must NOT do**:
  - Jangan overwrite file raw.

  **Recommended Agent Profile**:
  - Category: `islam-etl`
  - Skills: []

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: 9-30 | Blocked By: 7

  **Acceptance Criteria**:
  - [ ] `python scripts/verify_manifest.py --all` passes.

  **QA Scenarios**:
  ```
  Scenario: Manifest verification
    Tool: Bash
    Steps: python scripts/verify_manifest.py --all
    Expected: exit code 0
    Evidence: .sisyphus/evidence/task-8-manifest.txt

  Scenario: Append-only behavior
    Tool: Bash
    Steps: python scripts/test_append_only.py
    Expected: new source version created, old remains
    Evidence: .sisyphus/evidence/task-8-append-only.txt
  ```

  **Commit**: YES | Message: `feat(source): add registry, manifests, append-only versioning` | Files: [apps/api/src/islam_intelligent/ingest/*, scripts/*]

- [x] 9. Implement text normalization (NFC storage; NFKC search index only) ✅ COMPLETED

  **What to do**:
  - Normalize all ingested text to NFC for storage.
  - Create derived search text (NFKC) strictly for indexing/search.
  - Store `text_canonical_utf8_sha256`.

  **Must NOT do**:
  - Jangan menyimpan NFKC sebagai source-of-truth.

  **Recommended Agent Profile**:
  - Category: `islam-etl`
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 10-30 | Blocked By: 8

  **References**:
  - Unicode normalization: https://unicode.org/reports/tr15/

  **Acceptance Criteria**:
  - [ ] `python -m pytest -q apps/api/tests/test_normalization_nfc.py` passes.

  **QA Scenarios**:
  ```
  Scenario: NFC enforced
    Tool: Bash
    Steps: python scripts/verify_normalization.py --check nfc
    Expected: 0 violations
    Evidence: .sisyphus/evidence/task-9-nfc.txt

  Scenario: NFKC only in index
    Tool: Bash
    Steps: python scripts/verify_normalization.py --check nfkc_not_stored
    Expected: 0 violations
    Evidence: .sisyphus/evidence/task-9-nfkc.txt
  ```

  **Commit**: YES | Message: `feat(normalize): enforce NFC canonical text and hashes` | Files: [apps/api/src/islam_intelligent/normalize/*, scripts/verify_normalization.py]

- [x] 10. Implement TextUnit builders for fixtures (Quran ayat + hadith item) ✅ COMPLETED

  **What to do**:
  - Create tiny license-safe fixtures in `data/fixtures/`.
  - Build ingestion-to-text_unit for both unit types, using canonical IDs from `docs/CANONICAL_IDS.md`.

  **Must NOT do**:
  - Jangan mengambil dataset online tanpa license audit SAFE.

  **Recommended Agent Profile**:
  - Category: `islam-etl`
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 11-30 | Blocked By: 9

  **Acceptance Criteria**:
  - [ ] Fixture ingestion populates `text_unit` with both unit types.

  **QA Scenarios**:
  ```
  Scenario: Fixture load
    Tool: Bash
    Steps: python scripts/load_fixtures.py && python scripts/db_smoke.py --check text_unit_counts
    Expected: counts > 0 for quran_ayah and hadith_item
    Evidence: .sisyphus/evidence/task-10-fixtures.txt

  Scenario: Canonical IDs validate
    Tool: Bash
    Steps: python scripts/validate_canonical_ids.py --from-db
    Expected: 0 invalid IDs
    Evidence: .sisyphus/evidence/task-10-ids.txt
  ```

  **Commit**: YES | Message: `feat(text-unit): build Quran/hadith units from fixtures` | Files: [data/fixtures/*, apps/api/src/islam_intelligent/ingest/*, scripts/*]

- [x] 11. Implement EvidenceSpan creation + round-trip validator (UTF-8 byte offsets) ✅ COMPLETED

  **What to do**:
  - Provide API/util to create spans with `start_byte/end_byte`.
  - Validate boundaries and `snippet_utf8_sha256` against canonical bytes.
  - Add optional prefix/suffix fields for fuzzy anchoring (do not use for primary validation).

  **Must NOT do**:
  - Jangan menerima span yang tidak bisa diverifikasi hash.

  **Recommended Agent Profile**:
  - Category: `islam-etl`
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 12-30 | Blocked By: 10

  **References**:
  - Byte offset best practice: https://totbwf.github.io/posts/unicode-source-spans.html

  **Acceptance Criteria**:
  - [ ] `python -m pytest -q apps/api/tests/test_span_roundtrip.py` passes.

  **QA Scenarios**:
  ```
  Scenario: Happy span round-trip
    Tool: Bash
    Steps: python -m pytest -q apps/api/tests/test_span_roundtrip.py
    Expected: pass
    Evidence: .sisyphus/evidence/task-11-span-roundtrip.txt

  Scenario: Reject invalid offsets
    Tool: Bash
    Steps: python -m pytest -q apps/api/tests/test_span_reject_invalid.py
    Expected: pass
    Evidence: .sisyphus/evidence/task-11-span-invalid.txt
  ```

  **Commit**: YES | Message: `feat(evidence): add evidence spans with byte offsets and validation` | Files: [apps/api/src/islam_intelligent/domain/*, apps/api/tests/*]

- [x] 12. Build KG minimal (entities + edges) with evidence enforcement ✅ COMPLETED

  **What to do**:
  - Implement CRUD for `kg_entity`.
  - Implement `kg_edge` creation only if attaches >=1 `evidence_span_id`.
  - Add integrity script: no edge without evidence.

  **Must NOT do**:
  - Jangan auto-merge entitas agresif; MVP gunakan manual mapping/fixtures.

  **Recommended Agent Profile**:
  - Category: `islam-kg`
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: 13-30 | Blocked By: 11

  **Acceptance Criteria**:
  - [ ] `python scripts/kg_integrity.py` returns 0 violations.

  **QA Scenarios**:
  ```
  Scenario: Edge without evidence is rejected
    Tool: Bash
    Steps: python -m pytest -q apps/api/tests/test_kg_edge_requires_evidence.py
    Expected: pass
    Evidence: .sisyphus/evidence/task-12-kg-require-evidence.txt

  Scenario: Integrity check
    Tool: Bash
    Steps: python scripts/kg_integrity.py
    Expected: 0 violations
    Evidence: .sisyphus/evidence/task-12-kg-integrity.txt
  ```

  **Commit**: YES | Message: `feat(kg): add entities/edges with per-edge evidence` | Files: [apps/api/src/islam_intelligent/kg/*, scripts/kg_integrity.py]

- [x] 13. Implement retrieval indexes (lexical + vector-ready) ✅ COMPLETED

  **What to do**:
  - Implement lexical search over `text_unit.text_canonical` (tsvector/pg_trgm) for fixtures.
  - Implement embedding storage column (pgvector) but allow no-op if embeddings not configured yet.

  **Must NOT do**:
  - Jangan menambah external vector DB.

  **Recommended Agent Profile**:
  - Category: `islam-rag`
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: 14-30 | Blocked By: 10

  **Acceptance Criteria**:
  - [ ] `python -m pytest -q apps/api/tests/test_lexical_retrieval.py` passes.

  **QA Scenarios**:
  ```
  Scenario: Lexical retrieval returns evidence
    Tool: Bash
    Steps: python -m pytest -q apps/api/tests/test_lexical_retrieval.py
    Expected: pass
    Evidence: .sisyphus/evidence/task-13-lexical.txt

  Scenario: Vector layer disabled gracefully
    Tool: Bash
    Steps: python -m pytest -q apps/api/tests/test_vector_disabled.py
    Expected: pass
    Evidence: .sisyphus/evidence/task-13-vector-disabled.txt
  ```

  **Commit**: YES | Message: `feat(retrieval): add lexical index and vector-ready storage` | Files: [apps/api/src/islam_intelligent/rag/retrieval/*]

- [x] 14. Implement RAG pipeline: retrieve -> validate -> answer (abstain) ✅ COMPLETED

  **What to do**:
  - Retrieval returns candidate EvidenceSpan list.
  - Validation gate computes `sufficiency_score` and compares to `tau`.
  - If insufficient -> abstain without calling generator.
  - If sufficient -> generator produces statement list with citations.
  - Post-generation verifier checks: every statement has citations; every citation resolves; every span hash matches.

  **Must NOT do**:
  - Jangan allow output text tanpa citations.

  **Recommended Agent Profile**:
  - Category: `islam-rag`
  - Skills: []

  **Parallelization**: Can Parallel: NO | Wave 4 | Blocks: 15-30 | Blocked By: 13, 12

  **References**:
  - Evidence-first gating concepts: (see plan notes) + internal invariants.

  **Acceptance Criteria**:
  - [ ] `python -m pytest -q apps/api/tests/test_rag_citation_required.py` passes.
  - [ ] `python -m pytest -q apps/api/tests/test_rag_abstain_gate.py` passes.

  **QA Scenarios**:
  ```
  Scenario: Answerable case returns answer with citations
    Tool: Bash
    Steps: python -m pytest -q apps/api/tests/test_rag_answerable.py
    Expected: pass
    Evidence: .sisyphus/evidence/task-14-rag-answerable.txt

  Scenario: Unanswerable case abstains
    Tool: Bash
    Steps: python -m pytest -q apps/api/tests/test_rag_unanswerable_abstain.py
    Expected: pass
    Evidence: .sisyphus/evidence/task-14-rag-abstain.txt
  ```

  **Commit**: YES | Message: `feat(rag): enforce retrieve-validate-answer with abstention` | Files: [apps/api/src/islam_intelligent/rag/*, apps/api/tests/*]

- [x] 15. Add API endpoints (provenance always-on) ✅ COMPLETED

  **What to do**:
  - Add endpoints:
    - `POST /rag/query` returns answer contract.
    - `GET /sources/{source_id}` returns registry + license.
    - `GET /evidence/{evidence_span_id}` returns snippet + locator + hashes.
  - Ensure OpenAPI generated.

  **Must NOT do**:
  - Jangan membuat endpoint yang bisa mematikan provenance.

  **Recommended Agent Profile**:
  - Category: `deep`
  - Skills: []

  **Parallelization**: Can Parallel: NO | Wave 4 | Blocks: 16-30 | Blocked By: 14

  **Acceptance Criteria**:
  - [ ] `python -m pytest -q apps/api/tests/test_api_contracts.py` passes.

  **QA Scenarios**:
  ```
  Scenario: API returns citations always
    Tool: Bash
    Steps: python -m pytest -q apps/api/tests/test_api_returns_citations.py
    Expected: pass
    Evidence: .sisyphus/evidence/task-15-api-citations.txt

  Scenario: Evidence endpoint resolves span
    Tool: Bash
    Steps: python -m pytest -q apps/api/tests/test_api_evidence_resolve.py
    Expected: pass
    Evidence: .sisyphus/evidence/task-15-api-evidence.txt
  ```

  **Commit**: YES | Message: `feat(api): expose rag + evidence + source endpoints` | Files: [apps/api/src/islam_intelligent/api/*]

- [x] 16. Implement UI: query + answer rendering (citation-required) ✅ COMPLETED

  **What to do**:
  - Build UI page: query input, submit, render verdict.
  - If verdict=answer: render statements and citations.
  - If verdict=abstain: render abstain message + retrieved evidence + missing requirements.
  - Add strict rendering guard: UI refuses to render statement text if citations missing.

  **Must NOT do**:
  - Jangan menyembunyikan citations di UI.

  **Recommended Agent Profile**:
  - Category: `visual-engineering` — Reason: UI + accessibility.
  - Skills: [`frontend-ui-ux`, `playwright`]

  **Parallelization**: Can Parallel: NO | Wave 4 | Blocks: 17-30 | Blocked By: 15

  **Acceptance Criteria**:
  - [ ] Playwright E2E test proves citations always visible.

  **QA Scenarios**:
  ```
  Scenario: Answer view shows citations
    Tool: Playwright
    Steps: Open UI -> submit fixture answerable query -> click first citation
    Expected: Evidence panel opens and shows source work_title + license_id
    Evidence: .sisyphus/evidence/task-16-ui-citations.png

  Scenario: UI refuses to render uncited statement
    Tool: Playwright
    Steps: Mock API response with statement missing citations
    Expected: UI shows error + does not show statement text
    Evidence: .sisyphus/evidence/task-16-ui-refuse.png
  ```

  **Commit**: YES | Message: `feat(ui): provenance-first answer rendering with citations` | Files: [apps/ui/src/*, apps/ui/tests/e2e/*]

- [x] 17. Implement UI span highlighting (byte offsets) ✅ COMPLETED

  **What to do**:
  - Implement conversion util to highlight span by UTF-8 byte offsets.
  - Ensure Arabic RTL rendering is stable.

  **Must NOT do**:
  - Jangan gunakan `string.slice(start_byte, end_byte)` langsung.

  **Recommended Agent Profile**:
  - Category: `visual-engineering`
  - Skills: [`frontend-ui-ux`, `playwright`]

  **Parallelization**: Can Parallel: YES | Wave 4 | Blocks: 18-30 | Blocked By: 16

  **Acceptance Criteria**:
  - [ ] E2E: clicking citation highlights correct span and passes hash check display.

  **QA Scenarios**:
  ```
  Scenario: Byte-offset highlight works
    Tool: Playwright
    Steps: open evidence panel -> highlight span
    Expected: highlighted text equals snippet_text and hash badge is "verified"
    Evidence: .sisyphus/evidence/task-17-highlight.png

  Scenario: Mismatch detection
    Tool: Playwright
    Steps: simulate wrong offsets
    Expected: UI shows "span verification failed" and no highlight
    Evidence: .sisyphus/evidence/task-17-highlight-fail.png
  ```

  **Commit**: YES | Message: `feat(ui): highlight evidence spans using utf8 byte offsets` | Files: [apps/ui/src/lib/*, apps/ui/tests/e2e/*]

- [x] 18. Implement eval runner: citation-required + abstention metrics ✅ COMPLETED

  **What to do**:
  - Implement `scripts/run_eval.py` to run `eval/cases/golden.yaml` against API/pipeline.
  - Metrics:
    - citation_required_pass_rate
    - locator_resolve_pass_rate
    - abstention precision/recall/F1 for unanswerable subset
  - Emit `eval/report.json`.

  **Must NOT do**:
  - Jangan gunakan penilaian manual.

  **Recommended Agent Profile**:
  - Category: `islam-eval`
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 5 | Blocks: 19-30 | Blocked By: 14, 6

  **References**:
  - AbstentionBench: https://github.com/facebookresearch/AbstentionBench

  **Acceptance Criteria**:
  - [ ] `python scripts/run_eval.py --suite golden --output eval/report.json` exits 0 and writes report.

  **QA Scenarios**:
  ```
  Scenario: Eval report produced
    Tool: Bash
    Steps: python scripts/run_eval.py --suite golden --output eval/report.json
    Expected: exit 0 and file exists
    Evidence: .sisyphus/evidence/task-18-eval-run.txt

  Scenario: Citation-required enforced
    Tool: Bash
    Steps: python scripts/run_eval.py --suite golden --assert citation_required_pass_rate==1.0
    Expected: exit 0
    Evidence: .sisyphus/evidence/task-18-eval-assert.txt
  ```

  **Commit**: YES | Message: `feat(eval): add runner for citation-required and abstention tests` | Files: [scripts/run_eval.py, eval/*]

- [x] 19. Add hardening: integrity + audit + retraction workflow ✅ COMPLETED

  **What to do**:
  - Add scripts:
    - `scripts/verify_manifest.py` (already)
    - `scripts/verify_provenance.py` (no broken links; no orphan entities)
    - `scripts/retract_source.py` (creates new version + reason)
  - Ensure services never delete rows/files.

  **Must NOT do**:
  - Jangan implement delete endpoints.

  **Recommended Agent Profile**:
  - Category: `islam-security`
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 5 | Blocks: 20-30 | Blocked By: 18

  **Acceptance Criteria**:
  - [ ] `python scripts/verify_provenance.py --check no_broken_links` returns 0.
  - [ ] Retraction creates new version without deleting.

  **QA Scenarios**:
  ```
  Scenario: Provenance integrity
    Tool: Bash
    Steps: python scripts/verify_provenance.py --check no_broken_links
    Expected: 0 violations
    Evidence: .sisyphus/evidence/task-19-prov-integrity.txt

  Scenario: Retraction is versioned
    Tool: Bash
    Steps: python scripts/retract_source.py --first-fixture --reason "test" && python scripts/test_append_only.py
    Expected: old still exists; new version exists; status retracted
    Evidence: .sisyphus/evidence/task-19-retract.txt
  ```

  **Commit**: YES | Message: `feat(hardening): add integrity checks and versioned retraction` | Files: [scripts/*, apps/api/src/islam_intelligent/*]

- [x] 20. Add DB bootstrap + migration apply (SQLite default; Postgres optional) ✅ COMPLETED

  **What to do**:
  - Implement `DATABASE_URL` config.
  - Implement `scripts/db_init.py`:
    - creates DB (SQLite file) if missing
    - applies migrations (from `packages/schemas/sql/0001_init.sql` or Alembic, but must be deterministic)
    - runs schema sanity checks
  - Ensure tests run on SQLite without external services.

  **Must NOT do**:
  - Jangan mewajibkan Docker/Postgres untuk test suite.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: plumbing + repeatable local verification.
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 5 | Blocks: 21-30 | Blocked By: 5, 8

  **Acceptance Criteria**:
  - [ ] `python scripts/db_init.py --sqlite ./.local/dev.db` exits 0.
  - [ ] `python -m pytest -q` still passes using SQLite.

  **QA Scenarios**:
  ```
  Scenario: DB init idempotent
    Tool: Bash
    Steps: python scripts/db_init.py --sqlite ./.local/dev.db && python scripts/db_init.py --sqlite ./.local/dev.db
    Expected: exit 0 both runs; no duplicate schema errors
    Evidence: .sisyphus/evidence/task-20-db-init.txt

  Scenario: Postgres optional path (skipped safely)
    Tool: Bash
    Steps: python scripts/db_init.py --postgres "" --expect-skip
    Expected: exits 0 and prints "skipped"
    Evidence: .sisyphus/evidence/task-20-db-init-pg-skip.txt
  ```

  **Commit**: YES | Message: `feat(db): add deterministic db bootstrap and migrations` | Files: [scripts/db_init.py, apps/api/src/islam_intelligent/db/*]

- [x] 21. Single-command local reset+seed for fixtures ✅ COMPLETED

  **What to do**:
  - Implement `scripts/dev_reset_and_seed.py` to:
    - wipe local SQLite DB (delete file)
    - run `scripts/db_init.py`
    - run `scripts/load_fixtures.py`
    - run smoke checks (counts + span validators)

  **Must NOT do**:
  - Jangan menyentuh data non-local atau remote.

  **Recommended Agent Profile**:
  - Category: `islam-etl`
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 5 | Blocks: 22-30 | Blocked By: 20

  **Acceptance Criteria**:
  - [ ] `python scripts/dev_reset_and_seed.py` exits 0 and leaves DB ready.

  **QA Scenarios**:
  ```
  Scenario: Reset+seed reproducible
    Tool: Bash
    Steps: python scripts/dev_reset_and_seed.py && python scripts/dev_reset_and_seed.py
    Expected: exit 0 both runs; row counts identical
    Evidence: .sisyphus/evidence/task-21-reset-seed.txt

  Scenario: Seed includes both unit types
    Tool: Bash
    Steps: python scripts/db_smoke.py --check text_unit_counts
    Expected: quran_ayah>0 and hadith_item>0
    Evidence: .sisyphus/evidence/task-21-seed-counts.txt
  ```

  **Commit**: YES | Message: `chore(dev): add deterministic reset+seed for fixtures` | Files: [scripts/dev_reset_and_seed.py, scripts/db_smoke.py]

- [x] 22. Enforce trusted-only answering (source trust gate) ✅ COMPLETED

  **What to do**:
  - Enforce: retrieval and answering MUST ignore `source_document.trust_status != trusted`.
  - If all retrieved evidence is untrusted -> abstain with `fail_reason=untrusted_sources`.
  - Add a minimal curator-only mechanism (MVP): allow toggling trust status via CLI script (not UI).

  **Must NOT do**:
  - Jangan menjawab dari untrusted sources.

  **Recommended Agent Profile**:
  - Category: `islam-security`
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 5 | Blocks: 23-30 | Blocked By: 14

  **Acceptance Criteria**:
  - [ ] Test proves untrusted evidence triggers abstain.

  **QA Scenarios**:
  ```
  Scenario: Untrusted evidence causes abstain
    Tool: Bash
    Steps: python -m pytest -q apps/api/tests/test_untrusted_sources_abstain.py
    Expected: pass
    Evidence: .sisyphus/evidence/task-22-untrusted-abstain.txt

  Scenario: Curator script toggles trust
    Tool: Bash
    Steps: python scripts/set_source_trust.py --first-fixture --trusted true
    Expected: exit 0 and DB shows trust_status=trusted
    Evidence: .sisyphus/evidence/task-22-trust-toggle.txt
  ```

  **Commit**: YES | Message: `feat(security): gate answering on trusted sources only` | Files: [apps/api/src/islam_intelligent/*, scripts/set_source_trust.py]

- [x] 23. RAG logging completeness (audit trail) ✅ COMPLETED

  **What to do**:
  - Guarantee that every `POST /rag/query` writes:
    - `rag_query`
    - >=0 `rag_retrieval_result`
    - `rag_validation`
    - `rag_answer`
  - Add verifier script `scripts/verify_rag_logs.py`.

  **Must NOT do**:
  - Jangan ada path yang return response tanpa logging.

  **Recommended Agent Profile**:
  - Category: `islam-rag`
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 5 | Blocks: 24-30 | Blocked By: 15, 22

  **Acceptance Criteria**:
  - [ ] `python scripts/verify_rag_logs.py` returns 0 violations after running eval suite.

  **QA Scenarios**:
  ```
  Scenario: Logs exist for answer and abstain
    Tool: Bash
    Steps: python scripts/run_eval.py --suite golden --output eval/report.json && python scripts/verify_rag_logs.py
    Expected: 0 violations
    Evidence: .sisyphus/evidence/task-23-rag-logs.txt

  Scenario: Missing log is detected
    Tool: Bash
    Steps: python scripts/verify_rag_logs.py --simulate-missing --expect-fail
    Expected: exit 0 (script proves it detects)
    Evidence: .sisyphus/evidence/task-23-rag-logs-detect.txt
  ```

  **Commit**: YES | Message: `feat(rag): enforce complete logging for auditability` | Files: [scripts/verify_rag_logs.py, apps/api/src/islam_intelligent/rag/*]

- [x] 24. Strict citation verifier (no fabricated citations) ✅ COMPLETED

  **What to do**:
  - Implement a server-side verifier that checks for every citation:
    - evidence_span_id exists
    - span resolves to text_unit + source_document
    - byte slice hash matches `snippet_utf8_sha256`
    - citation belongs to retrieved evidence set for that query (or is provably derivable from it)
  - If any check fails -> force abstain with `fail_reason=citation_verification_failed`.

  **Must NOT do**:
  - Jangan leak partially verified answers.

  **Recommended Agent Profile**:
  - Category: `islam-rag`
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 5 | Blocks: 25-30 | Blocked By: 14

  **Acceptance Criteria**:
  - [ ] Unit tests cover fabricated citation and hash mismatch cases.

  **QA Scenarios**:
  ```
  Scenario: Fabricated citation is rejected
    Tool: Bash
    Steps: python -m pytest -q apps/api/tests/test_citation_verifier_rejects_fabrication.py
    Expected: pass
    Evidence: .sisyphus/evidence/task-24-citation-fabrication.txt

  Scenario: Hash mismatch triggers abstain
    Tool: Bash
    Steps: python -m pytest -q apps/api/tests/test_citation_verifier_hash_mismatch.py
    Expected: pass
    Evidence: .sisyphus/evidence/task-24-citation-hash.txt
  ```

  **Commit**: YES | Message: `feat(rag): add strict citation verification and fail-closed abstention` | Files: [apps/api/src/islam_intelligent/rag/verify/*, apps/api/tests/*]

- [x] 25. Extend eval: citation coverage + abstention F1 thresholds (gating) ✅ COMPLETED

  **What to do**:
  - Extend `scripts/run_eval.py` to compute and assert thresholds:
    - citation_required_pass_rate == 1.0
    - locator_resolve_pass_rate == 1.0
    - abstention_f1 >= 0.95
  - Emit failure taxonomy counts (missing_citations, untrusted_sources, citation_verification_failed, etc.).

  **Must NOT do**:
  - Jangan menggunakan penilaian berbasis "looks good".

  **Recommended Agent Profile**:
  - Category: `islam-eval`
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 5 | Blocks: 26-30 | Blocked By: 18, 24

  **Acceptance Criteria**:
  - [ ] `python scripts/run_eval.py --suite golden --assert citation_required_pass_rate==1.0 --assert abstention_f1>=0.95` exits 0.

  **QA Scenarios**:
  ```
  Scenario: Threshold gate passes
    Tool: Bash
    Steps: python scripts/run_eval.py --suite golden --assert citation_required_pass_rate==1.0 --assert abstention_f1>=0.95
    Expected: exit 0
    Evidence: .sisyphus/evidence/task-25-eval-thresholds.txt

  Scenario: Threshold gate fails when forced
    Tool: Bash
    Steps: python scripts/run_eval.py --suite golden --force-bad-metric --expect-fail
    Expected: exit 0 (script proves it fails correctly)
    Evidence: .sisyphus/evidence/task-25-eval-fail.txt
  ```

  **Commit**: YES | Message: `test(eval): enforce metric thresholds and failure taxonomy` | Files: [scripts/run_eval.py]

- [x] 26. UI E2E: provenance always visible (answer + abstain) ✅ COMPLETED

  **What to do**:
  - Add Playwright tests that assert:
    - answer mode: every statement has >=1 citation visible
    - abstain mode: retrieved evidence list is shown + missing requirements are shown
    - citations are clickable and open evidence panel
  - Save screenshots as evidence.

  **Must NOT do**:
  - Jangan membuat test yang bergantung pada external network.

  **Recommended Agent Profile**:
  - Category: `visual-engineering`
  - Skills: [`playwright`]

  **Parallelization**: Can Parallel: YES | Wave 5 | Blocks: 27-30 | Blocked By: 16, 18

  **Acceptance Criteria**:
  - [ ] `npx playwright test` passes.

  **QA Scenarios**:
  ```
  Scenario: Answer flow shows citations
    Tool: Playwright
    Steps: Run e2e test "answer_shows_citations"
    Expected: pass + screenshot exists
    Evidence: .sisyphus/evidence/task-26-ui-answer.png

  Scenario: Abstain flow shows missing requirements
    Tool: Playwright
    Steps: Run e2e test "abstain_shows_missing_requirements"
    Expected: pass + screenshot exists
    Evidence: .sisyphus/evidence/task-26-ui-abstain.png
  ```

  **Commit**: YES | Message: `test(ui): add e2e checks for provenance-first behavior` | Files: [apps/ui/tests/e2e/*]

- [x] 27. Security audit: secrets + forbidden destructive ops ✅ COMPLETED

  **What to do**:
  - Implement `scripts/security_audit.py`:
    - scan for accidental secrets patterns
    - assert no delete endpoints exist
    - assert raw data paths are append-only
  - Add CI-style check `python scripts/security_audit.py`.

  **Must NOT do**:
  - Jangan mengandalkan manual review.

  **Recommended Agent Profile**:
  - Category: `islam-security`
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 5 | Blocks: 28-30 | Blocked By: 3, 15

  **Acceptance Criteria**:
  - [ ] `python scripts/security_audit.py` exits 0.

  **QA Scenarios**:
  ```
  Scenario: Audit passes
    Tool: Bash
    Steps: python scripts/security_audit.py
    Expected: exit 0
    Evidence: .sisyphus/evidence/task-27-security-audit.txt

  Scenario: Audit detects injected secret
    Tool: Bash
    Steps: python scripts/security_audit.py --simulate-secret --expect-fail
    Expected: exit 0 (script proves it catches)
    Evidence: .sisyphus/evidence/task-27-security-detect.txt
  ```

  **Commit**: YES | Message: `test(security): add automated security and integrity audit` | Files: [scripts/security_audit.py]

- [x] 28. Tamper-evident provenance hash chain (minimal) ✅ COMPLETED

  **What to do**:
  - For each transform/activity, compute `activity_hash = sha256(json_canonical(activity_record + input_hashes + output_hashes))`.
  - Store `activity_hash` and link to previous activity hash for same pipeline run.
  - Implement verifier `scripts/verify_hash_chain.py`.

  **Must NOT do**:
  - Jangan mengubah aktivitas lama; append-only.

  **Recommended Agent Profile**:
  - Category: `islam-security`
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 5 | Blocks: 29-30 | Blocked By: 19

  **Acceptance Criteria**:
  - [ ] `python scripts/verify_hash_chain.py` returns 0 violations.

  **QA Scenarios**:
  ```
  Scenario: Hash chain verifies
    Tool: Bash
    Steps: python scripts/verify_hash_chain.py
    Expected: 0 violations
    Evidence: .sisyphus/evidence/task-28-hash-chain.txt

  Scenario: Tamper is detected
    Tool: Bash
    Steps: python scripts/verify_hash_chain.py --simulate-tamper --expect-fail
    Expected: exit 0 (script proves detection)
    Evidence: .sisyphus/evidence/task-28-hash-chain-tamper.txt
  ```

  **Commit**: YES | Message: `feat(integrity): add minimal tamper-evident hash chain for provenance` | Files: [apps/api/src/islam_intelligent/provenance/*, scripts/verify_hash_chain.py]

- [x] 29. End-to-end verify script (single entrypoint) ✅ COMPLETED

  **What to do**:
  - Implement `scripts/verify_all.py` to run in order:
    - db init + seed
    - pytest
    - eval suite (with thresholds)
    - UI e2e tests (optional switch)
    - provenance + manifest + hash chain verification
  - Add flag `--check-invariants` that runs only invariant checks (no full suite) and exits non-zero on first violation.
  - Ensure output is machine-readable (exit codes) and produces evidence logs.

  **Must NOT do**:
  - Jangan bergantung pada manual steps.

  **Recommended Agent Profile**:
  - Category: `islam-eval`
  - Skills: []

  **Parallelization**: Can Parallel: YES | Wave 5 | Blocks: 30 | Blocked By: 28

  **Acceptance Criteria**:
  - [ ] `python scripts/verify_all.py` exits 0 on clean run.
  - [ ] `python scripts/verify_all.py --check-invariants` exits 0 on clean run.

  **QA Scenarios**:
  ```
  Scenario: Full verification run
    Tool: Bash
    Steps: python scripts/verify_all.py
    Expected: exit 0
    Evidence: .sisyphus/evidence/task-29-verify-all.txt

  Scenario: Failure propagates
    Tool: Bash
    Steps: python scripts/verify_all.py --simulate-failure --expect-fail
    Expected: exit 0 (script proves it fails)
    Evidence: .sisyphus/evidence/task-29-verify-all-fail.txt
  ```

  **Commit**: YES | Message: `chore(verify): add single end-to-end verification entrypoint` | Files: [scripts/verify_all.py]

- [x] 30. Final acceptance run + evidence bundle ✅ COMPLETED

  **What to do**:
  - Run `scripts/verify_all.py` and commit the generated evidence artifacts path list (not the data itself).
  - Ensure the system demonstrates the three invariants:
    - citation-required
    - abstain on insufficient/untrusted evidence
    - provenance always-on

  **Must NOT do**:
  - Jangan commit raw corpora besar.

  **Recommended Agent Profile**:
  - Category: `islam-eval`
  - Skills: []

  **Parallelization**: Can Parallel: NO | Wave 5 | Blocks: [] | Blocked By: 25, 26, 29

  **Acceptance Criteria**:
  - [ ] Evidence bundle list exists in `.sisyphus/evidence/index.json` (paths + hashes).

  **QA Scenarios**:
  ```
  Scenario: Produce evidence index
    Tool: Bash
    Steps: python scripts/verify_all.py --write-evidence-index .sisyphus/evidence/index.json
    Expected: exit 0 and file exists
    Evidence: .sisyphus/evidence/task-30-evidence-index.txt

  Scenario: Sanity check invariants
    Tool: Bash
    Steps: python scripts/verify_all.py --check-invariants
    Expected: exit 0
    Evidence: .sisyphus/evidence/task-30-invariants.txt
  ```

  **Commit**: YES | Message: `test(e2e): run full verification and record evidence index` | Files: [.sisyphus/evidence/index.json]

## Final Verification Wave (4 parallel agents, ALL must APPROVE)
- [x] F1. Plan Compliance Audit — oracle ✅ COMPLETED
- [x] F2. Code Quality Review — unspecified-high ✅ COMPLETED
- [x] F3. Real QA (E2E + API) — unspecified-high (+ playwright) ✅ COMPLETED
- [x] F4. Scope Fidelity Check — deep ✅ COMPLETED

## Commit Strategy
- Atomic per milestone: `docs/*`, `schema/*`, `etl/*`, `kg/*`, `rag/*`, `ui/*`, `eval/*`, `security/*`.

## Success Criteria
- No hallucination enforced by architecture: answers only render from evidence bundle; missing evidence -> abstain.
- Provenance always displayed in API + UI, with click-through to exact span + license.
- End-to-end tests + eval suite run unattended and pass thresholds.
