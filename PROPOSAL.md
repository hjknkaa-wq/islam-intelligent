# ISLAM INTELLIGENT — Project Proposal

**Tanggal / Date:** 2026-03-03  
**Versi / Version:** 1.0  
**Status:** Draft

---

## Ringkasan Eksekutif / Executive Summary

**ISLAM INTELLIGENT** adalah platform intelijen pengetahuan Islam berbasis data yang dirancang seperti Palantir — menggabungkan ingesti teks primer (Al-Quran, Hadits, Tafsir, Fiqh, Sirah) dengan pipeline deterministik yang menjamin setiap klaim terikat pada sumber primer dengan kutipan eksplisit.

**ISLAM INTELLIGENT** is a Palantir-inspired Islamic knowledge intelligence platform that combines ingestion of primary texts (Quran, Hadith, Tafsir, Fiqh, Sirah) with deterministic pipelines ensuring every claim is tied to a primary source with an explicit citation.

---

## 1. Latar Belakang / Background

Permintaan akan informasi keislaman yang akurat dan terverifikasi terus meningkat, namun banyak platform AI yang ada masih berpotensi menghasilkan jawaban tanpa sumber yang jelas (halusinasi). Proyek ini dibangun di atas prinsip **accuracy-first**: tidak ada klaim tanpa penunjuk eksplisit ke dokumen sumber.

The demand for accurate, verifiable Islamic information continues to grow, yet many existing AI platforms risk generating answers without clear provenance (hallucination). This project is built on the **accuracy-first** principle: no claim without an explicit pointer to a source document.

---

## 2. Tujuan / Objectives

1. **Ingesti sumber primer** — Muat seluruh Al-Quran (6.236 ayat), koleksi Hadits utama (Bukhari, Muslim, Abu Dawud, Tirmidhi, Nasāʾī, Ibn Majah), dan Tafsir pilihan ke dalam basis data terverifikasi.
2. **Penelusuran berbasis bukti** — Setiap jawaban dikembalikan bersama ID sumber, lokasi (ayat, nomor hadits, halaman), dan hash SHA-256 untuk integritas.
3. **Abstain bila bukti kurang** — Sistem menolak menjawab jika bukti tidak mencukupi, daripada berspekulasi.
4. **Knowledge Graph (KG)** — Bangun KG yang menghubungkan entitas Islam dengan edge yang mengandung provenance.
5. **RAG berbasis LLM** — Integrasikan LLM untuk menghasilkan jawaban yang mengutip bukti secara transparan.
6. **UI dasbor** — Visualisasikan rantai provenance sehingga pengguna dapat memverifikasi setiap klaim.

---

## 3. Arsitektur / Architecture

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
             ┌─────────────┼─────────────┐
             ▼             ▼             ▼
       ┌──────────┐  ┌──────────┐  ┌──────────┐
       │  Ingest  │  │   RAG    │  │    KG    │
       │ Pipeline │  │ Pipeline │  │  Manager │
       └──────────┘  └──────────┘  └──────────┘
             │             │
             ▼             ▼
       ┌───────────────────────────┐
       │     Evidence Spans        │
       │  (byte offsets + SHA-256) │
       └───────────────────────────┘
```

### Komponen Utama / Key Components

| Komponen | Teknologi | Status |
|----------|-----------|--------|
| Backend API | Python 3.12 + FastAPI | ✅ Berjalan |
| Frontend UI | Next.js 14 + TypeScript | ✅ Berjalan |
| Database | SQLite (dev) / PostgreSQL + pgvector (prod) | ✅ Dev aktif |
| Ingesti | Python ETL idempoten | ✅ Quran minimal (23 ayat) |
| RAG | Lexical retrieval + mock LLM | ⚠️ Mock only |
| Vector Search | pgvector (dinonaktifkan) | ❌ Belum aktif |
| Knowledge Graph | SQLAlchemy + provenance | ✅ Berjalan |

---

## 4. Format Bukti Wajib / Mandatory Evidence Format

Setiap klaim yang dihasilkan sistem **harus** menyertakan:

- **Al-Quran:** `surah:ayat` + cuplikan Arab + sumber terjemahan  
  _Contoh: quran:2:255 — "اللَّهُ لَا إِلَٰهَ إِلَّا هُوَ..." (Tanzil Project, CC-BY-3.0)_

- **Hadits:** Koleksi + nomor + bab + tingkatan (sahih/hasan/daif) + penunjuk sanad  
  _Contoh: bukhari:1 — bab:Badaʾ al-Wahy — Sahih_

- **Tafsir/Fiqh/Sirah:** Karya + penulis + volume/halaman atau ID bagian kanonik  
  _Contoh: tafsir-ibn-kathir:2:255 — Ibn Kathir, Vol. 1_

---

## 5. Tonggak Pencapaian / Milestones

| Fase | Deskripsi | Durasi | Status |
|------|-----------|--------|--------|
| **Milestone 1** | Foundation: schemas, fixtures (23 ayat), API scaffold, UI | Selesai | ✅ DONE |
| **Milestone 2** | Perbaikan bug kritis, migrasi DB, sinkronisasi UI-API | Selesai | ✅ DONE |
| **Milestone 3** | Integrasi LLM nyata + vector search | 1-2 minggu | 🔲 TODO |
| **Milestone 4** | Ingesti penuh Al-Quran (6.236 ayat) + Hadits utama | 2 minggu | 🔲 TODO |
| **Milestone 5** | Cakupan uji 90%+, hardening keamanan, dokumentasi | 1 minggu | 🔲 TODO |
| **Milestone 6** | Deployment produksi + CI/CD | 1 minggu | 🔲 TODO |

Rincian lengkap tersedia di [`REMEDIATION_PLAN.md`](./REMEDIATION_PLAN.md) dan [`PROJECT_STATUS.md`](./PROJECT_STATUS.md).

---

## 6. Sumber Data / Data Sources

| Sumber | Lisensi | Jumlah | Status |
|--------|---------|--------|--------|
| Al-Quran (Tanzil Project) | CC-BY-3.0 | 6.236 ayat | ⚠️ 23 ayat tersedia |
| Sahih Bukhari (sunnah.com API) | Terbuka | ~7.000 hadits | 🔲 Belum diingesti |
| Sahih Muslim | Terbuka | ~7.500 hadits | 🔲 Belum diingesti |
| Sunan Abu Dawud | Terbuka | ~4.800 hadits | 🔲 Belum diingesti |
| Jāmiʿ at-Tirmidhī | Terbuka | ~3.900 hadits | 🔲 Belum diingesti |
| Sunan an-Nasāʾī | Terbuka | ~5.700 hadits | 🔲 Belum diingesti |
| Sunan Ibn Mājah | Terbuka | ~4.300 hadits | 🔲 Belum diingesti |
| Tafsir Ibn Kathir (en) | Domain publik | Per surah | 🔲 Belum diimplementasi |

Semua sumber eksternal diperlakukan sebagai **tidak tepercaya** hingga dikurasi dan diverifikasi. Lihat [`sources/LICENSE_AUDIT.md`](./sources/LICENSE_AUDIT.md) untuk audit lengkap.

---

## 7. Kriteria Keberhasilan / Success Criteria

- [ ] Semua 6.236 ayat Al-Quran berhasil diingesti dengan canonical ID benar (`quran:1:1` — `quran:114:6`)
- [ ] Koleksi Hadits utama diingesti dengan grading dan sanad tersedia
- [ ] LLM menghasilkan jawaban nyata dengan kutipan bukti yang terverifikasi
- [ ] Vector search aktif dan hybrid search berfungsi
- [ ] Cakupan uji ≥ 90%
- [ ] Sistem abstain dengan benar saat bukti tidak mencukupi
- [ ] Audit keamanan lulus (tidak ada rahasia di kode, tidak ada injeksi SQL, rate limiting aktif)
- [ ] Dokumentasi API lengkap (OpenAPI/Swagger)
- [ ] Waktu respons query < 2 detik

---

## 8. Pantangan / Anti-Patterns

| Pantangan | Alasan | Pendekatan Benar |
|-----------|--------|-----------------|
| Halusinasi sumber | Melanggar prinsip accuracy-first | Abstain + minta retrieval |
| Fatwa tanpa kutipan primer | Tanggung jawab agama | Wajib surah:ayat atau ref hadits + label ketidakpastian |
| Hilangkan field provenance | Merusak jejak audit | Setiap transformasi menyimpan penunjuk sumber |
| "Keajaiban LLM" tanpa verifikasi | Non-deterministik | Skema + validasi + spot check |
| Percaya sumber web tanpa verifikasi | Data tidak terverifikasi | Perlakukan sebagai tidak tepercaya kecuali dikurasi |
| Kunci API di kode | Risiko keamanan | Gunakan variabel lingkungan |

---

## 9. Aturan Tidak Dapat Ditawar / Non-Negotiable Rules

_(Diambil dari [`AGENT.md`](./AGENT.md) dan [`AGENTS.md`](./AGENTS.md))_

1. **TIDAK BOLEH BERHALUSINASI** — Jika bukti tidak ada, jangan berikan jawaban; minta sumber tambahan.
2. **Bukti sumber wajib** — Setiap klaim harus menyertakan penunjuk ke sumber (ID dokumen + lokasi).
3. **Jangan keluarkan fatwa** tanpa kutipan sumber primer dan label ketidakpastian yang jelas.
4. **Transformasi deterministik** — Gunakan skema dan validasi daripada tebakan LLM.
5. **Pipeline ETL idempoten** — Dengan checkpoint.
6. **Edge KG menyimpan provenance** — Izinkan sumber yang saling bertentangan.
7. **Pipeline RAG mencatat bukti** — Log bukti yang diambil dan kutipan akhir.
8. **Tidak ada kunci API di repo** — Gunakan variabel lingkungan.

---

## 10. Cara Menjalankan / Getting Started

```bash
# 1. Start development stack (PostgreSQL + API + UI)
make up

# 2. Run database migrations
make migrate

# 3. Load Quran fixture data
make ingest:quran_sample

# 4. Run tests
make test

# 5. View logs
make logs
```

Untuk pengembangan lokal tanpa Docker:

```bash
# Backend
cd apps/api
pip install -e ".[dev]"
PYTHONPATH=src pytest tests/ -q

# Frontend
cd apps/ui
npm install
npm run dev
```

---

## 11. Referensi Dokumen / Related Documents

| Dokumen | Deskripsi |
|---------|-----------|
| [`AGENTS.md`](./AGENTS.md) | Aturan agen, standar kutipan, anti-pola |
| [`AGENT.md`](./AGENT.md) | Aturan proyek (Bahasa Indonesia) |
| [`MILESTONE_1.md`](./MILESTONE_1.md) | Detail Milestone 1 yang sudah selesai |
| [`CODEBASE_ASSESSMENT.md`](./CODEBASE_ASSESSMENT.md) | Analisis komprehensif codebase |
| [`REMEDIATION_PLAN.md`](./REMEDIATION_PLAN.md) | Rencana perbaikan 2-3 minggu |
| [`PROJECT_STATUS.md`](./PROJECT_STATUS.md) | Status proyek terkini |
| [`docs/TECH_STACK.md`](./docs/TECH_STACK.md) | Keputusan tumpukan teknologi MVP |
| [`docs/CANONICAL_IDS.md`](./docs/CANONICAL_IDS.md) | Spesifikasi ID kanonik Quran dan Hadits |
| [`sources/LICENSE_AUDIT.md`](./sources/LICENSE_AUDIT.md) | Audit lisensi sumber data |
| [`eval/cases/golden.yaml`](./eval/cases/golden.yaml) | 11 kasus evaluasi emas |

---

*End of Proposal — ISLAM INTELLIGENT v1.0*
