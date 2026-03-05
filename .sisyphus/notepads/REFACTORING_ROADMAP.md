# REFACTORING ROADMAP: core.py

**File**: `apps/api/src/islam_intelligent/rag/pipeline/core.py`  
**Total Lines**: 825  
**Issue**: Mega function generate_answer() (310+ lines)  
**Status**: 🔄 PARTIAL REFACTORING

---

## 🎯 REFACTORING STRATEGY

### Method 1: Incremental Extraction (Recommended)
Extract helper methods satu per satu, verifikasi setiap perubahan.

**Method baru yang sudah ditambahkan:**

1. ✅ `_execute_retrieval_with_metrics()` (lines 826-875)
   - Mengekstrak logika retrieval
   - Mencatat metrics
   - Handle backward compatibility

2. ✅ `_execute_reranking_with_metrics()` (lines 877-905)
   - Mengekstrak logika reranking
   - Update metrics dengan reranker info

3. ✅ `_build_abstention_response()` (lines 907-941)
   - Build abstention response
   - Record RAGAS scores
   - Finalize metrics

4. ✅ `_build_success_response()` (lines 943-972)
   - Build success response
   - Record verdict
   - Finalize metrics

---

## 🔄 NEXT STEPS (Untuk dilanjutkan)

### Step 1: Refactor generate_answer() menggunakan method baru

**Current structure (lines 370-680):**
```python
def generate_answer(self, query, retrieved=None):
    # 1. Initialize metrics (lines 380-384)
    # 2. Define _record_ragas_scores (lines 386-405)
    # 3. Step 1: Retrieve (lines 407-446) -> PINDAH ke _execute_retrieval_with_metrics()
    # 4. Step 2: Rerank (lines 448-457) -> PINDAH ke _execute_reranking_with_metrics()
    # 5. Step 3: Filter trusted (line 459)
    # 6. Step 4: Validate sufficiency (lines 484-504)
    # 7. Step 5: Cost governance (lines 506-540)
    # 8. Step 6: Generate (lines 542-575)
    # 9. Step 7: Verify (lines 577-680)
    #    - 7a: Basic verification
    #    - 7b: Citation verification
    #    - 7c: Faithfulness verification
    # 10. Build response (various places)
```

**Target structure:**
```python
def generate_answer(self, query, retrieved=None):
    # 1. Initialize
    metrics_collector = create_metrics_collector(...)
    
    # 2. Execute steps using extracted methods
    raw_retrieved, metadata = self._execute_retrieval_with_metrics(
        query, retrieved, metrics_collector
    )
    reranked = self._execute_reranking_with_metrics(
        query, raw_retrieved, metrics_collector
    )
    trusted = self._filter_trusted(reranked)
    
    # 3. Validation gates
    if not self._validate_trusted_sources(trusted, ...):
        return self._build_abstention_response(...)
    
    if not self._validate_sufficiency(trusted, ...):
        return self._build_abstention_response(...)
    
    cost_ok, cost_estimate, msg = self._apply_cost_governance(query)
    if not cost_ok:
        return self._build_abstention_response(...)
    
    # 4. Generate and verify
    statements = self._generate_and_verify(query, trusted, metrics_collector)
    if not statements:
        return self._build_abstention_response(...)
    
    # 5. Success
    return self._build_success_response(...)
```

### Step 2: Extract additional helper methods

```python
def _validate_trusted_sources(self, trusted, raw, metrics, ragas_fn):
    """Validate that we have trusted sources."""
    if raw and not trusted:
        return False
    return True

def _validate_sufficiency(self, trusted, metrics, ragas_fn):
    """Validate evidence sufficiency."""
    is_sufficient, score = self.validate_sufficiency(trusted)
    if not is_sufficient:
        return False, score
    return True, score

def _generate_and_verify(
    self, 
    query: str, 
    trusted: list[dict], 
    metrics_collector: MetricsCollector
) -> list[Statement] | None:
    """Generate statements and verify them."""
    # Step 6: Generate
    # Step 7a: Basic verification
    # Step 7b: Citation verification
    # Step 7c: Faithfulness verification
    # Return statements or None if verification fails
```

---

## 📊 IMPACT ANALYSIS

### Method yang perlu diubah di generate_answer():

| Line Range | Current Code | Action |
|------------|--------------|--------|
| 407-446 | Retrieval logic | Replace dengan `_execute_retrieval_with_metrics()` |
| 448-457 | Reranking logic | Replace dengan `_execute_reranking_with_metrics()` |
| 462-479 | Abstention (untrusted) | Replace dengan `_build_abstention_response()` |
| 484-504 | Abstention (insufficient) | Replace dengan `_build_abstention_response()` |
| 506-540 | Cost governance + abstention | Replace dengan helper |
| 542-575 | Generation | Extract ke method baru |
| 577-680 | Verification | Extract ke method baru |
| 682-739 | Success response | Replace dengan `_build_success_response()` |

---

## ⚠️ RISKS

1. **Logic Changes**: Perlu hati-hati agar tidak mengubah behavior
2. **Metrics Collection**: Pastikan metrics tetap terekam dengan benar
3. **Error Handling**: Jangan merusak error handling yang ada
4. **Test Coverage**: Semua 57 tests harus tetap pass

---

## ✅ VERIFICATION CHECKLIST

- [ ] All 57 tests pass
- [ ] No syntax errors
- [ ] Metrics collected correctly
- [ ] Abstention reasons preserved
- [ ] RAGAS scores calculated
- [ ] Cost tracking works

---

## 📝 ESTIMATED EFFORT

- **Complete refactoring**: 4-6 hours
- **Incremental (2-3 methods)**: 2 hours
- **Testing & verification**: 1-2 hours
- **Total**: 6-8 hours

---

## 🎯 CURRENT STATUS

**Progress**: 20% (4 helper methods extracted, belum diintegrasikan)
**Next Action**: Integrate extracted methods ke generate_answer()
**Risk**: Medium (complex function, many dependencies)

---

## 💡 ALTERNATIVE APPROACH

Jika refactoring penuh terlalu risky, consider:

1. **Extract coordinators** (seperti yang diusulkan di CODEMAP):
   - `RetrievalCoordinator`
   - `GenerationCoordinator`
   - `VerificationCoordinator`

2. **Gunakan State Machine**:
   ```python
   class PipelineState(Enum):
       INIT = auto()
       RETRIEVED = auto()
       RERANKED = auto()
       VALIDATED = auto()
       GENERATED = auto()
       VERIFIED = auto()
       COMPLETE = auto()
       ABSTAINED = auto()
   ```

3. **Chain of Responsibility pattern** untuk validation gates

---

*Dokumentasi ini untuk melanjutkan refactoring di sesi berikutnya*
