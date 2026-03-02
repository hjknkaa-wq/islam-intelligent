# Wave 1 Foundation Learnings

## 2026-03-02: Canonical ID Specification

### Task Completed
Created comprehensive canonical ID specification at `docs/CANONICAL_IDS.md`.

### Key Patterns Established

1. **Qur'an Format**: `quran:{surah}:{ayah}`
   - Surah: 1-114
   - Ayah: 1-286 (surah-specific max)
   - No leading zeros allowed
   - Full ayah count table included for validation

2. **Hadith Format**: `hadith:{collection}:{numbering_system}:{hadith_number}`
   - **Critical**: numbering_system is mandatory, not optional
   - Collection codes: lowercase only (bukhari, muslim, etc.)
   - Each collection has multiple numbering systems documented
   - Major collections covered: Bukhari, Muslim, Abu Dawud, Tirmidhi, Nasa'i, Ibn Majah, Malik, Ahmad, Riyad al-Salihin, Nawawi's 40

3. **Validation Rules**
   - Regex patterns provided for both types
   - Full validation requires lookup tables (ayah counts, collection ranges)
   - TypeScript interfaces defined

4. **Canonical Locator JSON Schema**
   - Complete JSON structure documented for both Quran and Hadith
   - Includes metadata fields (book names, chapter info, grades)

### Sources Consulted
- Qur'an ayah counts: Standard Uthmani script (Hafs 'an Asim)
- Hadith numbering: Based on major published editions (Darussalam, Al-Maktaba al-Shamela)
- Collection metadata: Classical biographical sources

### Decisions Made
1. Used colon (`:`) as delimiter for consistency
2. Required lowercase throughout for normalization
3. Explicit numbering_system prevents ambiguity across editions
4. JSON schema includes both Arabic and English names for internationalization

### Files Created
- `docs/CANONICAL_IDS.md` (646 lines, 17,887 bytes)

