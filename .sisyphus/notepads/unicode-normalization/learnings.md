# Unicode Normalization Learnings

## Implementation Summary

### Files Created
1. `apps/api/src/islam_intelligent/normalize/normalizer.py` - Core normalization module
2. `apps/api/src/islam_intelligent/normalize/__init__.py` - Package exports
3. `apps/api/tests/test_normalization_nfc.py` - Comprehensive test suite
4. `scripts/verify_normalization.py` - CLI verification tool

## Key Design Decisions

### NFC for Storage
- NFC (Canonical Composition) preserves canonical equivalence
- Most compact normalized form
- Used for all `text_canonical` fields
- Required for all stored text

### NFKC for Search
- NFKC (Compatibility Composition) handles compatibility characters
- Better matching for user queries (e.g., fullwidth digits → ASCII)
- ONLY for indexing - never stored as source-of-truth

### SHA-256 Hashing
- All storage text must have SHA-256 hash
- Hash computed on NFC-normalized UTF-8 bytes
- Enables content-addressable storage
- Integrity verification via `hmac.compare_digest()` (constant-time)

## Technical Notes

### Python Type Checking
- Used `Optional[str]` for backward compatibility
- LSP shows deprecation warnings for Python 3.10+ but code works fine
- Consider updating to `| None` syntax when dropping Python 3.9 support

### Windows Compatibility
- Replaced Unicode checkmarks (✓✗⚠) with ASCII equivalents ([OK], [FAIL], [WARN])
- Windows console may not display Unicode properly
- All non-ASCII characters in code are in string literals only

### Hash Comparison
- Use `hmac.compare_digest()` not `hashlib.compare_digest()`
- Former is available across Python versions
- Provides timing-attack resistant comparison

## Test Coverage

42 tests covering:
- NFC normalization (combining characters, Arabic text, edge cases)
- NFKC normalization (compatibility characters, Arabic differences)
- Hash computation (consistency, empty strings, None handling)
- Hash verification (success, failure, timing safety)
- Round-trip integrity (idempotency)
- Arabic-specific cases (Quranic text, tashkeel, ligatures, kashida)
- Edge cases (mixed scripts, emojis, whitespace, long text, special chars)

## Verification Script

The verification script supports:
- `--check nfc`: Verifies all text_unit.text_canonical is NFC
- `--check nfkc_not_stored`: Verifies no NFKC in storage
- `--mock`: Run with test data for validation
- Returns 0 on success, 1 on failure, 2 on error

## References
- Unicode TR15: https://unicode.org/reports/tr15/
- Python unicodedata module documentation
