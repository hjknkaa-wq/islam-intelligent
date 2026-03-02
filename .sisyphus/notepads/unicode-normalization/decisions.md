# Unicode Normalization Decisions

## Date: 2026-03-02

### Storage Format: NFC
**Decision**: Use NFC (Canonical Composition) for all stored text

**Rationale**:
1. Preserves canonical equivalence per Unicode TR15
2. Most compact representation
3. Visual identity maintained
4. Industry standard for storage

### Search Format: NFKC
**Decision**: Use NFKC (Compatibility Composition) for search indexing only

**Rationale**:
1. Handles compatibility characters (fullwidth, circled, etc.)
2. Better query matching
3. MUST NOT be stored as source-of-truth

### Hash Algorithm: SHA-256
**Decision**: Use SHA-256 for content addressing

**Rationale**:
1. Industry standard
2. Fast computation
3. 256 bits = 64 hex characters
4. Easy to store and compare

### Verification Strategy
**Decision**: Create standalone verification script

**Rationale**:
1. Can run in CI/CD pipelines
2. Returns appropriate exit codes
3. Works without database (mock mode)
4. Extensible for future checks

### API Design
**Decision**: Provide both functional and class-based APIs

**Functions**: `normalize_storage()`, `normalize_search()`, `compute_hash()`, `verify_hash()`
**Class**: `TextNormalizer` with `for_storage()`, `for_search()`, `verify()` methods

**Rationale**:
1. Functions for simple use cases
2. Class for workflow management
3. Consistent interface across both
