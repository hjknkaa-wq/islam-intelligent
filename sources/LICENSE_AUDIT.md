# License Audit (Islamic Text Sources)

Hard gate: no ingestion unless a source is explicitly SAFE here.

Last reviewed: 2026-03-04

## Status definitions

- SAFE: Explicit license/terms allow redistribution for our use-case; requirements are recorded here.
- RESTRICTED: Explicitly limited (e.g., non-commercial, no-derivatives, no scraping, excerpt-only, written-permission required, copyleft constraints we cannot meet).
- UNKNOWN: No authoritative license/terms found (or conflicting terms). Treat as not ingestible.

## SAFE sources (recommended MVP fixtures)

These are the only sources in this list that are safe to use for MVP fixtures without additional legal review.

1) tanzil_quran_text_uthmani (verbatim only)
2) tanzil_quran_text_simple (verbatim only)
3) tanzil_quran_text_simple_clean (verbatim only)
4) hadith_api_fawazahmed_v1 (Unlicense; pinned API ref)

## Source inventory

Each entry documents: source_id, status, license_url, attribution_text, rights_holder.

### Quran - Arabic text

#### tanzil_quran_text_uthmani

- status: SAFE (verbatim only; no modifications)
- license_url: https://tanzil.net/docs/text_license
- license_url_alt: https://tanzil.net/pub/download/v1.0/
- rights_holder: Tanzil Project
- attribution_text (must include verbatim):

```text
Tanzil Quran Text Copyright (C) 2007-2021 Tanzil Project
License: Creative Commons Attribution 3.0
This copy of the Quran text is carefully produced, highly verified and continuously monitored by a group of specialists in Tanzil Project.
TERMS OF USE:
- Permission is granted to copy and distribute verbatim copies of this text, but CHANGING IT IS NOT ALLOWED.
- This Quran text can be used in any website or application, provided that its source (Tanzil Project) is clearly indicated, and a link is made to tanzil.net to enable users to keep track of changes.
- This copyright notice shall be included in all verbatim copies of the text, and shall be reproduced appropriately in all files derived from or containing substantial portion of this text.
Please check updates at: http://tanzil.net/updates/
```

- notes:
  - Any normalization (even whitespace/diacritics edits) is a modification; do not do it if distributing the resulting text.
  - OK for fixtures if we store verbatim text + include the full notice.

#### tanzil_quran_text_simple

- status: SAFE (verbatim only; no modifications)
- license_url: https://tanzil.net/docs/text_license
- license_url_alt: https://tanzil.net/pub/download/v1.0/
- rights_holder: Tanzil Project
- attribution_text: same as `tanzil_quran_text_uthmani`
- notes: Same terms; this is a different script/type from the same licensed dataset.

#### tanzil_quran_text_simple_clean

- status: SAFE (verbatim only; no modifications)
- license_url: https://tanzil.net/docs/text_license
- license_url_alt: https://tanzil.net/pub/download/v1.0/
- rights_holder: Tanzil Project
- attribution_text: same as `tanzil_quran_text_uthmani`
- notes: Same terms; this is a different text variant offered by Tanzil.

### Quran - translations (major candidates)

#### clear_quran_en_mustafa_khattab

- status: RESTRICTED
- license_url: https://theclearquran.org/copyright-information/
- rights_holder: Al-Furqaan Foundation (Furqaan Institute of Quranic Education / Book of Signs Foundation) with exclusive license; translator Dr. Mustafa Khattab
- attribution_text: Per the publisher terms; includes citing translator + publisher and linking to https://theclearquran.org/
- restrictions:
  - Explicit permission required for reproduction beyond narrow excerpt allowances; not suitable for ingestion/redistribution as a dataset.

#### sahih_international_en

- status: UNKNOWN
- license_url: (no authoritative license page captured during this audit)
- rights_holder: UNKNOWN (typically published via Abul-Qasim Publishing House; verify)
- attribution_text: UNKNOWN
- notes:
  - Frequently redistributed online, but that is not a license.
  - Do not ingest until an official permission/license statement is captured.

#### noble_quran_hilali_khan_en

- status: UNKNOWN
- license_url: (no authoritative license page captured during this audit)
- rights_holder: UNKNOWN (often associated with King Fahd Complex; verify)
- attribution_text: UNKNOWN
- notes:
  - PDFs often state "Not for sale" / "Free distribution" which is not a clear open license.
  - Treat as UNKNOWN unless an explicit redistribution license is obtained from the rights holder.

#### pickthall_en_meaning_of_the_glorious_koran

- status: UNKNOWN
- license_url: https://www.sacred-texts.com/isl/pick/ (non-authoritative; informational)
- rights_holder: UNKNOWN (original translator Mohammed Marmaduke Pickthall; verify public-domain status per jurisdiction)
- attribution_text: UNKNOWN
- notes:
  - Public-domain status depends on jurisdiction/publication details; requires legal review.

#### yusuf_ali_en

- status: UNKNOWN
- license_url: https://quranyusufali.com/ (not an authoritative license statement)
- rights_holder: UNKNOWN (original translator Abdullah Yusuf Ali; verify public-domain status per jurisdiction and edition)
- attribution_text: UNKNOWN
- notes:
  - Conflicting claims exist across the internet; do not ingest without an authoritative rights statement.

#### chandia_en_englishqurantranslation_org

- status: RESTRICTED
- license_url: http://englishqurantranslation.org/open-copy-licence-and-terms-and-conditions
- rights_holder: Dr. M. Chandia (and other contributors for fonts/graphics)
- attribution_text (required, per license page):

```text
Qur'an Translation taken by open licence from the English Translation of the Holy Qur'an by Dr. M. Chandia, available from www.englishqurantranslation.org
```

- restrictions:
  - Non-commercial only.
  - No changes/modifications.

### Quran - linguistic annotation / word-by-word resources

#### quranic_arabic_corpus

- status: RESTRICTED
- license_url: https://corpus.quran.com/license.jsp
- terms_url: https://corpus.quran.com/faq.jsp
- rights_holder: Kais Dukes (site footer) / Quran.com team maintenance; see site for details
- attribution_text: (not explicitly provided as a required notice; cite project in publications per FAQ)
- restrictions (from FAQ):
  - "Do not use the data for commercial purposes"; described as made available for research.
  - Provided under GNU GPL, which imposes copyleft conditions; combined with non-commercial constraint this is not suitable for broad redistribution in this repo.

### Hadith / Sunnah collections

#### hadith_api_fawazahmed_v1

- status: SAFE
- license_url: https://raw.githubusercontent.com/fawazahmed0/hadith-api/1/LICENSE
- license_url_alt: https://github.com/fawazahmed0/hadith-api/blob/a07cb47397dc36d0a238bfad9419c725b268a38c/LICENSE
- rights_holder: hadith-api contributors (public domain dedication via The Unlicense)
- attribution_text: Optional attribution recommended - "Source: fawazahmed0/hadith-api"
- notes:
  - API endpoint format: `https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@{ref}/...`
  - Ingestion MUST pin `ref` to a stable tag/commit and store retrieved content hash.
  - This source entry approves ingestion of hadith-api distributions under the declared repository license.

#### sunnah_com_hadith_collections

- status: RESTRICTED
- license_url: https://sunnah.com/about
- rights_holder: Sunnah.com
- attribution_text: Not specified as a formal license notice.
- restrictions (from "Reproduction, Copying, Scraping" section):
  - Scraping and mass reproduction of entire books/collections is not permitted.
  - Individual hadith or selections for teaching/didactic/presentation is permitted.

## Intake policy

- Only ingest sources marked SAFE.
- If a source is SAFE but forbids modification (e.g., Tanzil), the pipeline must preserve verbatim text and store any normalized/derived representations separately without redistributing the modified original.
- UNKNOWN stays UNKNOWN until we capture an authoritative license/permission statement from the rights holder.
