# Canonical ID Reference

This document defines the canonical identifier formats for all primary Islamic sources used throughout the knowledge graph, RAG system, and citation infrastructure.

## Overview

Every primary source item must have a deterministic, unambiguous canonical ID. These IDs are:

- **Stable**: Do not change across system versions
- **Unique**: One ID maps to exactly one source item
- **Parsable**: Can be decomposed programmatically
- **Verifiable**: Include validation rules

---

## Qur'an Canonical IDs

### Format

```
quran:{surah}:{ayah}
```

### Components

| Component | Range | Description |
|-----------|-------|-------------|
| `surah` | 1-114 | Chapter number |
| `ayah` | 1-286 | Verse number within chapter |

### Canonical Locator JSON

```json
{
  "type": "quran",
  "canonical_id": "quran:2:255",
  "surah": 2,
  "ayah": 255,
  "surah_name_ar": "البقرة",
  "surah_name_en": "Al-Baqarah",
  "juz": 3,
  "hizb": 5,
  "rub": 1
}
```

### Validation Rules

| Rule | Pattern | Example Valid | Example Invalid |
|------|---------|---------------|-----------------|
| Surah range | 1-114 | `quran:1:1`, `quran:114:6` | `quran:0:1`, `quran:115:1` |
| Ayah max by surah | Varies | `quran:2:286` (valid) | `quran:2:287` (invalid) |
| Format | `^quran:([1-9]\d{0,2}):([1-9]\d{0,2})$` | `quran:112:1` | `quran:112`, `quran:abc:1` |
| No leading zeros | No `0` prefix | `quran:2:5` | `quran:02:05` |

### Ayah Counts by Surah

Surah 1 (Al-Fatihah): 7 ayat
Surah 2 (Al-Baqarah): 286 ayat
Surah 3 (Ali Imran): 200 ayat
Surah 4 (An-Nisa): 176 ayat
Surah 5 (Al-Ma'idah): 120 ayat
Surah 6 (Al-An'am): 165 ayat
Surah 7 (Al-A'raf): 206 ayat
Surah 8 (Al-Anfal): 75 ayat
Surah 9 (At-Tawbah): 129 ayat
Surah 10 (Yunus): 109 ayat
Surah 11 (Hud): 123 ayat
Surah 12 (Yusuf): 111 ayat
Surah 13 (Ar-Ra'd): 43 ayat
Surah 14 (Ibrahim): 52 ayat
Surah 15 (Al-Hijr): 99 ayat
Surah 16 (An-Nahl): 128 ayat
Surah 17 (Al-Isra): 111 ayat
Surah 18 (Al-Kahf): 110 ayat
Surah 19 (Maryam): 98 ayat
Surah 20 (Ta-Ha): 135 ayat
Surah 21 (Al-Anbiya): 112 ayat
Surah 22 (Al-Hajj): 78 ayat
Surah 23 (Al-Mu'minun): 118 ayat
Surah 24 (An-Nur): 64 ayat
Surah 25 (Al-Furqan): 77 ayat
Surah 26 (Ash-Shu'ara): 227 ayat
Surah 27 (An-Naml): 93 ayat
Surah 28 (Al-Qasas): 88 ayat
Surah 29 (Al-Ankabut): 69 ayat
Surah 30 (Ar-Rum): 60 ayat
Surah 31 (Luqman): 34 ayat
Surah 32 (As-Sajda): 30 ayat
Surah 33 (Al-Ahzab): 73 ayat
Surah 34 (Saba): 54 ayat
Surah 35 (Fatir): 45 ayat
Surah 36 (Ya-Sin): 83 ayat
Surah 37 (As-Saffat): 182 ayat
Surah 38 (Sad): 88 ayat
Surah 39 (Az-Zumar): 75 ayat
Surah 40 (Ghafir): 85 ayat
Surah 41 (Fussilat): 54 ayat
Surah 42 (Ash-Shura): 53 ayat
Surah 43 (Az-Zukhruf): 89 ayat
Surah 44 (Ad-Dukhan): 59 ayat
Surah 45 (Al-Jathiya): 37 ayat
Surah 46 (Al-Ahqaf): 35 ayat
Surah 47 (Muhammad): 38 ayat
Surah 48 (Al-Fath): 29 ayat
Surah 49 (Al-Hujurat): 18 ayat
Surah 50 (Qaf): 45 ayat
Surah 51 (Adh-Dhariyat): 60 ayat
Surah 52 (At-Tur): 49 ayat
Surah 53 (An-Najm): 62 ayat
Surah 54 (Al-Qamar): 55 ayat
Surah 55 (Ar-Rahman): 78 ayat
Surah 56 (Al-Waqi'a): 96 ayat
Surah 57 (Al-Hadid): 29 ayat
Surah 58 (Al-Mujadila): 22 ayat
Surah 59 (Al-Hashr): 24 ayat
Surah 60 (Al-Mumtahanah): 13 ayat
Surah 61 (As-Saff): 14 ayat
Surah 62 (Al-Jumu'ah): 11 ayat
Surah 63 (Al-Munafiqun): 11 ayat
Surah 64 (At-Taghabun): 18 ayat
Surah 65 (At-Talaq): 12 ayat
Surah 66 (At-Tahrim): 12 ayat
Surah 67 (Al-Mulk): 30 ayat
Surah 68 (Al-Qalam): 52 ayat
Surah 69 (Al-Haqqah): 52 ayat
Surah 70 (Al-Ma'arij): 44 ayat
Surah 71 (Nuh): 28 ayat
Surah 72 (Al-Jinn): 28 ayat
Surah 73 (Al-Muzzammil): 20 ayat
Surah 74 (Al-Muddaththir): 56 ayat
Surah 75 (Al-Qiyamah): 40 ayat
Surah 76 (Al-Insan): 31 ayat
Surah 77 (Al-Mursalat): 50 ayat
Surah 78 (An-Naba): 40 ayat
Surah 79 (An-Nazi'at): 46 ayat
Surah 80 ('Abasa): 42 ayat
Surah 81 (At-Takwir): 29 ayat
Surah 82 (Al-Infitar): 19 ayat
Surah 83 (Al-Mutaffifin): 36 ayat
Surah 84 (Al-Inshiqaq): 25 ayat
Surah 85 (Al-Buruj): 22 ayat
Surah 86 (At-Tariq): 17 ayat
Surah 87 (Al-A'la): 19 ayat
Surah 88 (Al-Ghashiyah): 26 ayat
Surah 89 (Al-Fajr): 30 ayat
Surah 90 (Al-Balad): 20 ayat
Surah 91 (Ash-Shams): 15 ayat
Surah 92 (Al-Layl): 21 ayat
Surah 93 (Ad-Duha): 11 ayat
Surah 94 (Ash-Sharh): 8 ayat
Surah 95 (At-Tin): 8 ayat
Surah 96 (Al-'Alaq): 19 ayat
Surah 97 (Al-Qadr): 5 ayat
Surah 98 (Al-Bayyinah): 8 ayat
Surah 99 (Az-Zalzalah): 8 ayat
Surah 100 (Al-'Adiyat): 11 ayat
Surah 101 (Al-Qari'ah): 11 ayat
Surah 102 (At-Takathur): 8 ayat
Surah 103 (Al-'Asr): 3 ayat
Surah 104 (Al-Humazah): 9 ayat
Surah 105 (Al-Fil): 5 ayat
Surah 106 (Quraysh): 4 ayat
Surah 107 (Al-Ma'un): 7 ayat
Surah 108 (Al-Kawthar): 3 ayat
Surah 109 (Al-Kafirun): 6 ayat
Surah 110 (An-Nasr): 3 ayat
Surah 111 (Al-Masad): 5 ayat
Surah 112 (Al-Ikhlas): 4 ayat
Surah 113 (Al-Falaq): 5 ayat
Surah 114 (An-Nas): 6 ayat

### Regex Pattern

```regex
^quran:([1-9]|[1-9][0-9]|1[0-1][0-9]|11[0-4]):([1-9]|[1-9][0-9]|[1-2][0-9]{2})$
```

Note: Full validation requires checking ayah count against surah-specific maximum.

---

## Hadith Canonical IDs

### Format

```
hadith:{collection}:{numbering_system}:{hadith_number}
```

### Components

| Component | Description | Example |
|-----------|-------------|---------|
| `collection` | Short code for hadith collection | `bukhari`, `muslim` |
| `numbering_system` | Specific numbering scheme used | `sahih`, `international` |
| `hadith_number` | The hadith number in that system | `1`, `340`, `2567` |

### Critical Rule: Numbering System is Required

Hadith numbering varies by collection AND by edition. The `numbering_system` component is **mandatory**, not optional. This ensures unambiguous identification.

### Canonical Locator JSON

```json
{
  "type": "hadith",
  "canonical_id": "hadith:bukhari:sahih:1",
  "collection": "bukhari",
  "collection_name_ar": "صحيح البخاري",
  "collection_name_en": "Sahih al-Bukhari",
  "numbering_system": "sahih",
  "hadith_number": 1,
  "book_number": 1,
  "book_name_ar": "بدء الوحي",
  "book_name_en": "Revelation",
  "chapter_number": 1,
  "chapter_name_ar": "بدء الوحي",
  "chapter_name_en": "How the Divine Revelation started",
  "grade": "sahih",
  "narrator_chain": ["Umar ibn al-Khattab", "Al-Bukhari"],
  "text_ar": "...",
  "text_en": "..."
}
```

### Major Hadith Collections

#### Sahih al-Bukhari

| Attribute | Value |
|-----------|-------|
| Canonical code | `bukhari` |
| Arabic name | صحيح البخاري |
| Compiler | Muhammad ibn Ismail al-Bukhari (d. 256 AH) |
| Total hadith | 7,563 (including repetitions) / ~2,600 unique |

**Numbering Systems:**

| System | Description | Range | Notes |
|--------|-------------|-------|-------|
| `sahih` | Traditional numbering (Fath al-Bari) | 1-7563 | Most widely used |
| `in_book` | Book-based numbering (e.g., 1.1, 2.15) | 1.1-97.144 | Chapter.hadith format |
| `darussalam` | Darussalam edition | 1-7563 | Modern edition |

**Example IDs:**
- `hadith:bukhari:sahih:1` - First hadith (revelation)
- `hadith:bukhari:sahih:7563` - Last hadith

---

#### Sahih Muslim

| Attribute | Value |
|-----------|-------|
| Canonical code | `muslim` |
| Arabic name | صحيح مسلم |
| Compiler | Muslim ibn al-Hajjaj al-Naysaburi (d. 261 AH) |
| Total hadith | ~3,000 (with repetitions) / ~2,200 unique |

**Numbering Systems:**

| System | Description | Range | Notes |
|--------|-------------|-------|-------|
| `sahih` | Traditional numbering | 1-3033 | Standard reference |
| `in_book` | Book-based numbering | 1.1-56.110 | Chapter.hadith format |

**Example IDs:**
- `hadith:muslim:sahih:1` - First hadith
- `hadith:muslim:sahih:3033` - Last hadith

---

#### Sunan Abu Dawud

| Attribute | Value |
|-----------|-------|
| Canonical code | `abudawud` |
| Arabic name | سنن أبي داود |
| Compiler | Abu Dawud al-Sijistani (d. 275 AH) |
| Total hadith | ~4,800 |

**Numbering Systems:**

| System | Description | Range | Notes |
|--------|-------------|-------|-------|
| `standard` | Traditional numbering | 1-4590 | Most common |
| `in_book` | Book-based numbering | 1.1-43.525 | Chapter.hadith format |

**Example IDs:**
- `hadith:abudawud:standard:1`
- `hadith:abudawud:standard:4590`

---

#### Jami' al-Tirmidhi

| Attribute | Value |
|-----------|-------|
| Canonical code | `tirmidhi` |
| Arabic name | جامع الترمذي |
| Compiler | Muhammad ibn Isa al-Tirmidhi (d. 279 AH) |
| Total hadith | ~3,956 |

**Numbering Systems:**

| System | Description | Range | Notes |
|--------|-------------|-------|-------|
| `standard` | Traditional numbering | 1-3956 | Standard reference |
| `in_book` | Book-based numbering | 1.1-49.431 | Chapter.hadith format |

**Example IDs:**
- `hadith:tirmidhi:standard:1`
- `hadith:tirmidhi:standard:3956`

---

#### Sunan al-Nasa'i

| Attribute | Value |
|-----------|-------|
| Canonical code | `nasai` |
| Arabic name | سنن النسائي |
| Compiler | Ahmad ibn Shuayb al-Nasa'i (d. 303 AH) |
| Total hadith | ~5,700 |

**Numbering Systems:**

| System | Description | Range | Notes |
|--------|-------------|-------|-------|
| `standard` | Traditional numbering | 1-5760 | Standard reference |
| `in_book` | Book-based numbering | 1.1-52.461 | Chapter.hadith format |
| `kubra` | Al-Sunan al-Kubra (larger collection) | 1-11415 | Larger Nasa'i collection |

**Example IDs:**
- `hadith:nasai:standard:1`
- `hadith:nasai:standard:5760`
- `hadith:nasai:kubra:1`

---

#### Sunan Ibn Majah

| Attribute | Value |
|-----------|-------|
| Canonical code | `ibnmajah` |
| Arabic name | سنن ابن ماجه |
| Compiler | Muhammad ibn Yazid Ibn Majah (d. 273 AH) |
| Total hadith | ~4,341 |

**Numbering Systems:**

| System | Description | Range | Notes |
|--------|-------------|-------|-------|
| `standard` | Traditional numbering | 1-4341 | Standard reference |
| `in_book` | Book-based numbering | 1.1-37.574 | Chapter.hadith format |

**Example IDs:**
- `hadith:ibnmajah:standard:1`
- `hadith:ibnmajah:standard:4341`

---

#### Muwatta Malik

| Attribute | Value |
|-----------|-------|
| Canonical code | `malik` |
| Arabic name | موطأ مالك |
| Compiler | Malik ibn Anas (d. 179 AH) |
| Total hadith | ~1,720 |

**Numbering Systems:**

| System | Description | Range | Notes |
|--------|-------------|-------|-------|
| `standard` | Traditional numbering | 1-1720 | Standard reference |
| `in_book` | Book-based numbering | 1.1-61.1804 | Chapter.hadith format |
| `rahman` | Shaykh Rahman edition | 1-1594 | Revised ordering |

**Example IDs:**
- `hadith:malik:standard:1`
- `hadith:malik:standard:1720`

---

#### Musnad Ahmad

| Attribute | Value |
|-----------|-------|
| Canonical code | `ahmad` |
| Arabic name | مسند أحمد |
| Compiler | Ahmad ibn Hanbal (d. 241 AH) |
| Total hadith | ~30,000 |

**Numbering Systems:**

| System | Description | Range | Notes |
|--------|-------------|-------|-------|
| `standard` | Traditional numbering | 1-30000+ | Standard reference |
| `narrator` | Organized by narrator | varies | Ibn Abbas section, etc. |

**Example IDs:**
- `hadith:ahmad:standard:1`
- `hadith:ahmad:standard:30000`

---

#### Riyad al-Salihin

| Attribute | Value |
|-----------|-------|
| Canonical code | `riyadussalihin` |
| Arabic name | رياض الصالحين |
| Compiler | Yahya ibn Sharaf al-Nawawi (d. 676 AH) |
| Total hadith | 1,896 |

**Numbering Systems:**

| System | Description | Range | Notes |
|--------|-------------|-------|-------|
| `standard` | Traditional numbering | 1-1896 | Standard reference |
| `in_book` | Book-based numbering | 1.1-19.388 | Chapter.hadith format |

**Example IDs:**
- `hadith:riyadussalihin:standard:1`
- `hadith:riyadussalihin:standard:1896`

---

#### Al-Arba'in al-Nawawiyyah

| Attribute | Value |
|-----------|-------|
| Canonical code | `nawawi40` |
| Arabic name | الأربعون النووية |
| Compiler | Yahya ibn Sharaf al-Nawawi (d. 676 AH) |
| Total hadith | 42 (2 bonus hadith) |

**Numbering Systems:**

| System | Description | Range | Notes |
|--------|-------------|-------|-------|
| `standard` | Traditional numbering | 1-42 | Standard reference |

**Example IDs:**
- `hadith:nawawi40:standard:1`
- `hadith:nawawi40:standard:42`

---

### Collection Registry

| Collection Code | Collection Name | Numbering Systems |
|-----------------|-----------------|-------------------|
| `bukhari` | Sahih al-Bukhari | `sahih`, `in_book`, `darussalam` |
| `muslim` | Sahih Muslim | `sahih`, `in_book` |
| `abudawud` | Sunan Abu Dawud | `standard`, `in_book` |
| `tirmidhi` | Jami' al-Tirmidhi | `standard`, `in_book` |
| `nasai` | Sunan al-Nasa'i | `standard`, `in_book`, `kubra` |
| `ibnmajah` | Sunan Ibn Majah | `standard`, `in_book` |
| `malik` | Muwatta Malik | `standard`, `in_book`, `rahman` |
| `ahmad` | Musnad Ahmad | `standard`, `narrator` |
| `riyadussalihin` | Riyad al-Salihin | `standard`, `in_book` |
| `nawawi40` | Al-Arba'in al-Nawawiyyah | `standard` |
| `qudsi40` | Al-Arba'in al-Qudsiyyah | `standard` |
| `shahwaliullah40` | Al-Arba'in Shah Waliullah | `standard` |

### Validation Rules

| Rule | Pattern | Example Valid | Example Invalid |
|------|---------|---------------|-----------------|
| Collection code | lowercase, a-z | `bukhari`, `muslim` | `Bukhari`, `sunan_nasai` |
| Numbering system | lowercase, a-z, underscore | `sahih`, `in_book` | `Sahih`, `book-number` |
| Hadith number | positive integer | `1`, `7563` | `0`, `1.5`, `001` |
| Format | `^hadith:([a-z]+):([a-z_]+):([1-9]\d*)$` | `hadith:bukhari:sahih:1` | `hadith:bukhari:1` |
| No leading zeros | No `0` prefix | `hadith:bukhari:sahih:5` | `hadith:bukhari:sahih:05` |

### Regex Pattern

```regex
^hadith:([a-z]+):([a-z_]+):([1-9]\d*)$
```

Note: Full validation requires checking against collection-specific numbering systems and ranges.

---

## Validation Implementation

### TypeScript Interface

```typescript
interface QuranLocator {
  type: 'quran';
  canonical_id: string;
  surah: number;        // 1-114
  ayah: number;         // 1-max (surah-specific)
  surah_name_ar: string;
  surah_name_en: string;
  juz?: number;         // 1-30
  hizb?: number;        // 1-60
  rub?: number;         // 1-4 (within hizb)
}

interface HadithLocator {
  type: 'hadith';
  canonical_id: string;
  collection: string;        // e.g., 'bukhari'
  numbering_system: string;  // e.g., 'sahih', 'in_book'
  hadith_number: number;
  collection_name_ar?: string;
  collection_name_en?: string;
  book_number?: number;
  book_name_ar?: string;
  book_name_en?: string;
  chapter_number?: number;
  chapter_name_ar?: string;
  chapter_name_en?: string;
  grade?: 'sahih' | 'hasan' | 'daif' | 'mawdu' | 'unknown';
  narrator_chain?: string[];
  text_ar?: string;
  text_en?: string;
}

type CanonicalLocator = QuranLocator | HadithLocator;
```

### Validation Functions

```typescript
// Quran validation
function isValidQuranId(id: string): boolean {
  const match = id.match(/^quran:([1-9]\d*):([1-9]\d*)$/);
  if (!match) return false;
  
  const surah = parseInt(match[1], 10);
  const ayah = parseInt(match[2], 10);
  
  if (surah < 1 || surah > 114) return false;
  
  const maxAyah = getMaxAyahForSurah(surah); // Lookup table
  return ayah >= 1 && ayah <= maxAyah;
}

// Hadith validation
function isValidHadithId(id: string): boolean {
  const match = id.match(/^hadith:([a-z]+):([a-z_]+):([1-9]\d*)$/);
  if (!match) return false;
  
  const collection = match[1];
  const numberingSystem = match[2];
  const hadithNumber = parseInt(match[3], 10);
  
  // Check collection exists
  if (!COLLECTION_REGISTRY[collection]) return false;
  
  // Check numbering system valid for collection
  if (!COLLECTION_REGISTRY[collection].numbering_systems.includes(numberingSystem)) {
    return false;
  }
  
  // Check number in range
  const maxNumber = COLLECTION_REGISTRY[collection].numbering_systems[numberingSystem].max;
  return hadithNumber >= 1 && hadithNumber <= maxNumber;
}
```

---

## Examples Summary

### Valid Qur'an IDs

```
quran:1:1       (Surah 1, Ayah 1)
quran:2:255     (Ayat al-Kursi)
quran:112:1     (Surah Al-Ikhlas, Ayah 1)
quran:114:6     (Last ayah of Qur'an)
```

### Invalid Qur'an IDs

```
quran:0:1       (Surah 0 invalid)
quran:115:1     (Surah 115 invalid)
quran:2:287     (Ayah exceeds surah max)
quran:02:05     (Leading zeros)
quran:2         (Missing ayah)
quran:abc:1     (Non-numeric)
```

### Valid Hadith IDs

```
hadith:bukhari:sahih:1
hadith:muslim:sahih:3033
hadith:tirmidhi:standard:3956
hadith:nasai:in_book:1.15
hadith:abudawud:standard:4590
```

### Invalid Hadith IDs

```
hadith:bukhari:1              (Missing numbering_system)
hadith:Bukhari:sahih:1        (Uppercase collection)
hadith:bukhari:Sahih:1        (Uppercase numbering_system)
hadith:bukhari:sahih:0        (Hadith 0 invalid)
hadith:bukhari:sahih:7564     (Exceeds collection max)
hadith:unknown:sahih:1        (Unknown collection)
hadith:bukhari:unknown:1      (Invalid numbering system)
```

---

## Migration and Compatibility

### From Legacy Formats

| Legacy Format | Canonical Format | Notes |
|---------------|------------------|-------|
| `2:255` | `quran:2:255` | Always include prefix |
| `Bukhari 1` | `hadith:bukhari:sahih:1` | Lowercase, explicit numbering |
| `Muslim 1` | `hadith:muslim:sahih:1` | Lowercase, explicit numbering |
| `Tirmidhi 1` | `hadith:tirmidhi:standard:1` | Specify numbering system |

### API Endpoints

All API endpoints must accept and return canonical IDs. Legacy formats may be accepted as input with conversion, but output must always be canonical.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-03-02 | Initial specification |

---

## References

- Qur'an ayah counts: Standard Uthmani script (Hafs 'an Asim)
- Hadith numbering: Based on major published editions (Darussalam, Al-Maktaba al-Shamela)
- Collection metadata: Derived from classical biographical sources
