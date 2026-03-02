# Schema Implementation Learnings

## Created Files
- `packages/schemas/sql/0001_init.sql` - Complete SQL migration (339 lines)
- `packages/schemas/json/source_document.json` - Source registry schema
- `packages/schemas/json/text_unit.json` - Quran ayah/hadith item schema
- `packages/schemas/json/evidence_span.json` - Byte offset evidence schema
- `packages/schemas/json/kg_entity.json` - Knowledge graph entity schema
- `packages/schemas/json/kg_edge.json` - KG edge with evidence requirement
- `packages/schemas/json/rag_answer.json` - Answer contract with citations
- `scripts/validate_schemas.py` - Comprehensive validation script

## Key Design Decisions

### Evidence-First Enforcement
1. **KG Edge Evidence Requirement**: JSON schema enforces `evidence_span_ids` array with `minItems: 1`
2. **RAG Answer Contract**: Requires citations for every statement; abstain mode for insufficient evidence
3. **Hash Verification**: All text content has SHA-256 hashes for integrity

### Canonical ID Formats
- Quran: `quran:{surah}:{ayah}` where surah 1-114, ayah varies
- Hadith: `hadith:{collection}:{numbering_system}:{number}` (numbering system required!)

### UTF-8 Byte Offsets
- Evidence spans use `start_byte` and `end_byte` (not character positions)
- Critical for Arabic text with multi-byte Unicode characters
- UI must convert between UTF-16 (JavaScript) and UTF-8 (storage)

### Provenance Chain
- Every table has `source_id` FK to `source_document`
- Full chain: answer → query → retrieved evidence → span → text_unit → source
- Trust status gates answering (only `trusted` sources)

## Validation Lessons
1. SQL syntax validation must ignore comments when counting parentheses
2. Windows console has issues with Unicode checkmarks (use ASCII instead)
3. JSON Schema Draft 7 supports `if/then/else` for conditional validation
4. Sample data generation helps catch schema edge cases early

## Testing Strategy
- Validator checks SQL syntax, JSON schema validity, and sample data
- Exit codes distinguish failure types (SQL=1, JSON=2, Samples=3)
- Comprehensive error messages with line numbers


## 2026-03-02: W3C PROV-DM Provenance Implementation

### Models Created (6 tables)
1. **prov_entity**: Physical/digital/conceptual things being tracked
2. **prov_activity**: Time-bounded operations that transform/create entities
3. **prov_agent**: Responsible parties (people, software, organizations)
4. **prov_generation**: Links entity → activity (when entity was created)
5. **prov_usage**: Links activity → entity (when entity was used)
6. **prov_derivation**: Entity lineage (derived_from relationships)

### Key Functions
- `record_activity()`: Creates activity with auto-detected git SHA and param hash
- `record_generation()`: Creates entity with mandatory generation link (prevents orphans)
- `get_git_sha()`: Uses subprocess to get git HEAD, validates 40-char hex format
- `compute_params_hash()`: SHA-256 of canonical JSON (sorted keys for determinism)

### Patterns Followed
- SQLAlchemy 2.0: Mapped[] + mapped_column() with type annotations
- Proper FK relationships with back_populates for bidirectional access
- DateTime(timezone=True) for temporal fields
- Followed existing domain/models.py DeclarativeBase pattern

### Orphan Detection
- Query: LEFT OUTER JOIN prov_generation WHERE generation IS NULL
- Verification script returns 0 if clean, non-zero if violations found
- 14 pytest tests covering: activity recording, generation linking, orphan detection

### Cross-Platform Notes
- Avoided Unicode checkmarks (✓/✗) in CLI output - Windows encoding issues
- Used [PASS]/[FAIL] ASCII markers instead
