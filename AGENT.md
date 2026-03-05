# ISLAM CERDAS — Aturan Proyek (Berdasarkan Desain)

> Legacy note: this file is kept for historical Indonesian guidance. Active repository operating guide is `AGENTS.md`.

## Hal yang Tidak Dapat Ditawar
- TIDAK BOLEH BERHALUSINASI: Jika bukti tidak ada, jangan berikan bukti dan mintalah sumber tambahan.
- Bukti sumber wajib: setiap klaim harus menyertakan penunjuk ke sumber (ID dokumen + lokasi).
- Jangan pernah mengeluarkan fatwa agama tanpa mengutip sumber primer dan dengan jelas memberi label ketidakpastian.
- Lebih baik menggunakan transformasi deterministik, skema, dan validasi daripada "tebakan LLM".
## Format Bukti (saat menjawab konten Islami)
- Al-Qur'an: Surah:Ayat + cuplikan Arab (singkat) + sumber terjemahan.
- Hadits: Koleksi + nomor + bab (jika tersedia) + tingkatan + penunjuk rantai perawi (jika tersedia).
- Tafsir/Fiqih/Sirah: Karya + penulis + volume/halaman atau ID bagian kanonik. 
## Definisi Selesai dalam Rekayasa
- Tes + validasi skema disertakan.
- Pipeline ETL bersifat idempoten atau memiliki checkpoint.
- Edge KG menyimpan provenance dan memungkinkan sumber yang saling bertentangan.
- Pipeline RAG mencatat bukti yang diambil dan kutipan akhir.
- Setiap metrik dasbor memiliki jejak provenance kueri.
## Keamanan & kepatuhan
- Perlakukan semua sumber web eksternal sebagai tidak tepercaya kecuali diverifikasi/dikurasi.
- Jauhkan kunci API dari repositori; gunakan variabel lingkungan.
