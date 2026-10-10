# VoxGuard — Project Charter

## 1. Document Information

| Atribut | Nilai |
|---|---|
| Nama dokumen | Project Charter / Project Brief |
| Nama proyek | VoxGuard — Verifiable Digital Election System (*Every Vote. Protected. Verifiable.*) |
| Versi | 0.1 |
| Status | **Draft — belum disetujui** |
| Tanggal pembuatan | 2026-10-10 |
| Pemilik dokumen | `[PEMILIK-DOKUMEN]` (placeholder; diisi tim) |
| Dokumen seri ini | `01_PROJECT_CHARTER.md`, `02_SOFTWARE_REQUIREMENTS_SPECIFICATION.md` (SRS), `03_SYSTEM_ARCHITECTURE_DOCUMENT.md` (SAD) |

**Legenda placeholder:** `[ANGGOTA-1]`, `[ANGGOTA-2]`, `[ANGGOTA-3]` = anggota tim (nama belum diketahui); `[DOSEN-PEMBIMBING]` = dosen pembimbing; `[INSTITUSI]` = institusi. Semuanya harus diisi tim sebelum dokumen dianggap final.

**Riwayat perubahan**

| Versi | Tanggal | Perubahan | Penulis |
|---|---|---|---|
| 0.1 | 2026-10-10 | Draf awal | `[PEMILIK-DOKUMEN]` |

**Kondisi repository saat dokumen disusun.** Tidak ada kode aplikasi atau konfigurasi. Folder `docs/` berisi empat dokumen hasil tugas sebelumnya: `PROJECT_BRIEF.md`, `ARCHITECTURE.md`, `SECURITY_AND_TEST_PLAN.md`, `API_CONTRACTS.md`. Dokumen tersebut **tidak diubah**. Isinya dipakai sebagai baseline rancangan dan tidak bertentangan dengan seri 01–03. Tumpang tindih peran keduanya dicatat sebagai **OPEN DECISION OD-14** (Bagian 14). Semua mekanisme di seri ini berstatus **direncanakan**; belum ada yang diimplementasikan atau diuji.

---

## 2. Executive Summary

VoxGuard adalah prototipe akademik sistem pemilihan digital berbasis web untuk pemilihan skala kecil: ketua kelas, ketua organisasi mahasiswa, ketua BEM, dan pemilihan internal komunitas. Sistem ini bukan sistem pemilu resmi dan tidak boleh diklaim memenuhi persyaratan pemilu nasional.

Masalah yang dituju: pemilihan daring sederhana sulit membuktikan bahwa satu pemilih hanya memberi satu suara, bahwa catatan tidak diubah diam-diam, bahwa hasil sesuai dengan suara sah, dan bahwa aktivitas mencurigakan terdeteksi. VoxGuard menjadikan hal-hal itu sebagai kebutuhan yang dapat diuji.

Pendekatan teknis: satu API Gateway dan enam layanan backend (Auth, Voter, Ballot, Audit, Result, Security) berbahasa Python/FastAPI dengan PostgreSQL (database terpisah per layanan), RabbitMQ, Redis, dan frontend React/Vite/Tailwind, dijalankan lokal dengan Docker Compose. Kontrol utama: pencegahan suara ganda yang aman terhadap request paralel, pemisahan identitas pemilih dari pilihan suara, audit *tamper-evident* (hash chain), rekonsiliasi hasil, deteksi anomali berbasis aturan, dan Attack Lab pada lingkungan uji.

Hasil yang diharapkan: prototipe yang berjalan lokal, test suite otomatis, simulasi serangan terdokumentasi, dan dokumentasi yang jujur tentang batas keamanannya. Keberhasilan diukur dari **pengujian yang dijalankan**, bukan dari klaim rancangan.

---

## 3. Background and Problem Statement

Pada pemilihan organisasi, pemungutan suara sering memakai formulir daring umum atau pemungutan manual. Pendekatan itu dapat cukup untuk keperluan informal, tetapi memunculkan pertanyaan berikut. Dokumen ini tidak memuat statistik atau klaim penelitian; masalah dirumuskan sebagai kebutuhan rekayasa yang akan diuji.

| ID | Masalah | Dampak pada pemilihan |
|---|---|---|
| P-01 | Risiko pemungutan suara ganda, termasuk lewat request bersamaan atau retry | Hasil tidak mencerminkan satu orang satu suara |
| P-02 | Sulit membuktikan integritas catatan | Perubahan data suara/audit tanpa jejak |
| P-03 | Kesalahan atau keterlambatan penghitungan | Hasil tidak konsisten dengan suara tersimpan |
| P-04 | Transparansi proses terbatas | Peserta tidak punya bukti penerimaan dan pemeriksaan yang aman dipublikasikan |
| P-05 | Pendeteksian aktivitas mencurigakan terbatas | Brute force, lonjakan penolakan, atau akses terlarang tidak diketahui |
| P-06 | Kegagalan komunikasi antarlayanan | Audit dan hasil tidak sinkron saat pesan hilang atau duplikat |
| P-07 | Pengaitan identitas dengan pilihan | Kerahasiaan pilihan terancam |

---

## 4. Project Objectives

**Tujuan utama.** Membangun prototipe sistem pemilihan digital berbasis microservices yang menunjukkan pengamanan suara, pencegahan suara ganda, audit yang dapat mendeteksi perubahan, penghitungan yang dapat direkonsiliasi, dan deteksi anomali — dengan batas keamanan yang dinyatakan jujur.

**Tujuan khusus.** Semua target di bawah adalah **kriteria yang harus diuji, bukan hasil yang sudah terbukti.**

| ID | Tujuan khusus | Cara diuji (rencana) |
|---|---|---|
| OBJ-01 | Mencegah lebih dari satu suara sah untuk satu kelayakan pemilih | Uji double voting dan konkurensi |
| OBJ-02 | Mendeteksi percobaan pemungutan suara ganda | Aturan anomali + Attack Lab |
| OBJ-03 | Menyediakan pemeriksaan integritas audit | Uji manipulasi record audit pada DB uji |
| OBJ-04 | Menguji konsistensi penghitungan | Rekonsiliasi dan hitung ulang independen |
| OBJ-05 | Mendemonstrasikan deteksi anomali | Skenario Attack Lab |
| OBJ-06 | Mendemonstrasikan komunikasi antarmicroservice (sinkron dan asinkron) yang tahan gangguan | Uji duplikasi event dan gangguan broker |
| OBJ-07 | Menegakkan otorisasi per peran di backend | Uji matriks role × endpoint |
| OBJ-08 | Menjaga kerahasiaan hubungan identitas–pilihan sejauh rancangan prototipe | Uji pemindaian data publik, log, dan event |

---

## 5. Project Scope

### In Scope

- Pengelolaan pemilihan dan kandidat.
- Autentikasi dan otorisasi berbasis peran.
- Pengelolaan kelayakan pemilih.
- Pemungutan suara dan pencegahan suara ganda.
- Audit dan pemeriksaan integritas.
- Penghitungan, rekonsiliasi, dan finalisasi hasil.
- Deteksi anomali berbasis aturan dan alert.
- Attack Lab (hanya lingkungan uji).
- Automated testing.
- Docker Compose untuk pengembangan lokal.

### Out of Scope

- Pemilu nasional atau pemerintah; integrasi resmi dengan lembaga pemerintah.
- Jaminan anonimitas kriptografis sempurna.
- Klaim *end-to-end verifiability* tanpa protokol dan pembuktian memadai.
- Audit keamanan independen bersertifikasi.
- Infrastruktur produksi berskala besar, *high availability*.
- Blockchain, biometrik, AI generatif/machine learning.
- Verifikasi identitas dunia nyata (KYC).

---

## 6. Stakeholders and User Roles

| Pihak | Peran dalam proyek | Batas kewenangan |
|---|---|---|
| **Admin** (`ADMIN`) | Mengelola konfigurasi pemilihan: membuat pemilihan, kandidat, daftar pemilih; menjadwalkan, membuka, menutup; menjalankan penghitungan dan finalisasi; melihat audit/alert | Tidak dapat mengubah/menghapus suara, mengubah hasil final, atau mengedit catatan audit lewat API; tidak otomatis menjadi pemilih |
| **Voter** (`VOTER`) | Memberikan satu suara pada pemilihan yang ia berhak ikuti; membaca receipt; melihat hasil setelah FINALIZED | Tidak mengakses fungsi administrasi, daftar pemilih, alert, atau hasil sementara |
| **Auditor** (`AUDITOR`) | Memeriksa integritas audit, bukti, hasil, alert (hanya baca) | Tidak melihat identitas atau pilihan individu; tidak mengubah apa pun |
| **Development Team** | Merancang, membangun, menguji, mendokumentasikan | Tidak memakai akses database untuk mengubah data pemilihan nyata; Attack Lab hanya data simulasi |
| **Project Supervisor / Lecturer** (`[DOSEN-PEMBIMBING]`) | Mengarahkan dan mengevaluasi hasil akademik | Menyetujui keputusan terbuka (Bagian 14) |

Matriks role × endpoint terperinci: `API_CONTRACTS.md` B.0 (akan ditautkan ke SRS Bagian 8).

---

## 7. Deliverables

| ID | Deliverable | Status saat ini |
|---|---|---|
| D-01 | Project Charter (dokumen ini) | Draft |
| D-02 | Software Requirements Specification | Draft |
| D-03 | System Architecture Document | Draft |
| D-04 | Implementasi prototipe (frontend, gateway, enam layanan) | Belum dimulai |
| D-05 | Test suite otomatis (Pytest + HTTPX) | Belum dimulai |
| D-06 | Attack Lab | Belum dimulai |
| D-07 | Dokumentasi API (OpenAPI 3.1; kontrak awal di `API_CONTRACTS.md`) | Kontrak draft ada |
| D-08 | Petunjuk instalasi dan menjalankan sistem | Belum dimulai |
| D-09 | Demo hasil pengujian | Belum dimulai |

Deliverable tambahan boleh ditambahkan tim kemudian; tugas dokumentasi ini tidak membuat file di luar tiga dokumen seri.

---

## 8. Assumptions and Constraints

| ID | Asumsi/batasan | Status |
|---|---|---|
| AS-01 | Waktu pengerjaan ±8 minggu | Asumsi awal — **perlu konfirmasi `[DOSEN-PEMBIMBING]`** |
| AS-02 | Tim 2–3 orang | Perlu konfirmasi anggota |
| AS-03 | Fokus prototipe akademik, bukan produksi | Ditetapkan oleh prompt proyek |
| AS-04 | Dijalankan dengan Docker Compose pada perangkat lokal; satu instance PostgreSQL dengan database per layanan | Ditetapkan |
| AS-05 | Satu bahasa backend (Python/FastAPI); tidak ada teknologi tambahan tanpa alasan teknis | Ditetapkan |
| AS-06 | Skala MVP ≤ 1.000 pemilih per pemilihan | **PROPOSED TARGET** — perlu konfirmasi |
| AS-07 | Kelayakan memilih berasal dari daftar yang diimpor Admin; verifikasi identitas dunia nyata tidak dijamin | Batasan |
| AS-08 | Data uji fiktif; tidak ada data pribadi sungguhan | Ditetapkan |
| AS-09 | Integrasi antarlayanan menuntut kontrak API/event yang stabil sejak awal | Batasan kerja |
| AS-10 | Sumber daya perangkat dan waktu terbatas; prioritas pada requirement Must | Batasan |

---

## 9. High-Level Milestones

Rencana awal delapan minggu. **Pembagian waktu ini belum disetujui** (OD-15).

| Minggu | Milestone | Hasil | Kriteria selesai |
|---|---|---|---|
| 1 | Analisis kebutuhan dan desain | Dokumen 01–03 direview; kontrak API/event disepakati | Review tim selesai; OD prioritas diputuskan |
| 2 | Fondasi repository, database, gateway | Struktur repo, Compose dasar, migrasi, gateway + health | `docker compose up` menjalankan infrastruktur dan gateway sehat |
| 3 | Auth dan Voter Service | Akun, token, RBAC, election, kandidat, daftar pemilih, lifecycle | Uji API Auth dan Voter lulus |
| 4 | Ballot Service | Ballot, ticket, penerimaan suara, idempotency, outbox | Uji double vote dan konkurensi lulus |
| 5 | Audit dan Result Service | Hash chain, verifikasi, checkpoint, tally, rekonsiliasi, finalisasi | Uji tamper audit dan rekonsiliasi lulus |
| 6 | Security Service dan integrasi | Aturan anomali, alert, metrik, frontend inti | Alur end-to-end berjalan |
| 7 | Pengujian integrasi dan simulasi serangan | Attack Lab, uji pemulihan broker | Skenario Attack Lab dijalankan dan dicatat |
| 8 | Perbaikan, dokumentasi, demonstrasi | Perbaikan temuan, petunjuk instalasi, demo | Definition of Done (Bagian 13) terpenuhi |

---

## 10. Success Criteria

Semua indikator berikut adalah **kriteria yang harus diuji**. Angka bertanda PROPOSED TARGET menunggu persetujuan.

| ID | Indikator | Tujuan terkait |
|---|---|---|
| SC-01 | Pemilih yang tidak memenuhi syarat ditolak | OBJ-01, OBJ-07 |
| SC-02 | Percobaan suara ganda ditolak | OBJ-01, OBJ-02 |
| SC-03 | Request paralel (**PROPOSED TARGET:** 50 request) tidak menghasilkan lebih dari satu suara sah per kelayakan | OBJ-01 |
| SC-04 | Perubahan record audit pada pengujian manipulasi terdeteksi | OBJ-03 |
| SC-05 | Hasil penghitungan sesuai dengan kumpulan suara sah (rekonsiliasi cocok) | OBJ-04 |
| SC-06 | Event duplikat tidak menggandakan efek bisnis | OBJ-06 |
| SC-07 | Gangguan message broker ditangani sesuai kebijakan pemulihan tanpa suara hilang atau ganda | OBJ-06 |
| SC-08 | Peran tidak berwenang ditolak oleh backend | OBJ-07 |
| SC-09 | Skenario anomali yang didefinisikan menghasilkan alert | OBJ-05 |
| SC-10 | Data publik, log, dan event non-Voter tidak memuat identitas atau pilihan individu | OBJ-08 |
| SC-11 | Pengujian otomatis dapat dijalankan mengikuti instruksi tertulis | Seluruh tujuan |

Metode verifikasi terperinci: SRS Bagian 14.

---

## 11. Risks and Mitigation

Probabilitas dan dampak adalah **penilaian awal** yang perlu ditinjau tim.

| ID | Risiko | Probabilitas | Dampak | Strategi mitigasi | Pemilik risiko |
|---|---|---|---|---|---|
| RK-01 | *Scope creep* (fitur tambahan menggeser Must) | Sedang | Tinggi | Prioritas Must/Should/Could; fitur tambahan hanya setelah Must lulus | `[ANGGOTA-1]` |
| RK-02 | Keterlambatan integrasi antarlayanan | Tinggi | Tinggi | Kontrak API/event dibekukan minggu 1; integrasi bertahap tiap minggu | `[ANGGOTA-2]` |
| RK-03 | Konflik kontrak API antar anggota | Sedang | Sedang | Satu sumber kontrak (`API_CONTRACTS.md`); perubahan lewat PR dokumen | `[ANGGOTA-1]` |
| RK-04 | Kehilangan atau duplikasi event | Sedang | Tinggi | Outbox, consumer idempotent, DLQ, uji pemulihan | pemilik Ballot/Audit |
| RK-05 | Race condition pada pemungutan suara | Sedang | Tinggi | Unique constraint + transaksi; uji konkurensi sejak minggu 4 | pemilik Ballot |
| RK-06 | Kebocoran data pemilih | Rendah–Sedang | Tinggi | Pemisahan data, allowlist event, kebijakan log, uji pemindaian | pemilik Voter/Auth |
| RK-07 | Kegagalan penghitungan / hasil tidak cocok | Sedang | Tinggi | Rekonsiliasi tiga arah; hitung ulang independen; uji E2E | pemilik Result |
| RK-08 | Klaim keamanan melampaui bukti pengujian | Sedang | Tinggi | Pisahkan direncanakan/diimplementasikan/diuji; catat hasil aktual | seluruh tim |
| RK-09 | Beban kerja melebihi kapasitas tim 2 orang | Tinggi | Sedang | Pembagian kerja Bagian 12; potong Should/Could lebih awal | `[ANGGOTA-1]` |
| RK-10 | Perubahan teknologi/versi dependency menghambat build | Rendah | Sedang | Pin versi saat implementasi; `docker compose` reproducible | pemilik infrastruktur |

---

## 12. Team Organization

Pembagian di bawah adalah **usulan**, belum disepakati. Setiap komponen punya satu pemilik; integrasi dan pengujian menjadi tanggung jawab bersama.

| Komponen | Tim 2 orang | Tim 3 orang |
|---|---|---|
| api-gateway, infrastruktur Compose | `[ANGGOTA-1]` | `[ANGGOTA-1]` |
| auth-service | `[ANGGOTA-1]` | `[ANGGOTA-1]` |
| voter-service | `[ANGGOTA-1]` | `[ANGGOTA-1]` |
| ballot-service | `[ANGGOTA-1]` | `[ANGGOTA-2]` |
| audit-service | `[ANGGOTA-2]` | `[ANGGOTA-2]` |
| result-service | `[ANGGOTA-2]` | `[ANGGOTA-3]` |
| security-service dan Attack Lab | `[ANGGOTA-2]` | `[ANGGOTA-3]` |
| frontend React | `[ANGGOTA-2]` | `[ANGGOTA-3]` |
| Integrasi, uji konkurensi/pemulihan, Attack Lab (eksekusi), dokumentasi | Bersama | Bersama |

Aturan kerja: perubahan kontrak API/event wajib *review* oleh pemilik komponen terdampak; PR yang menyentuh voting, audit, atau hasil direview minimal satu anggota lain.

---

## 13. Definition of Done

Proyek dianggap selesai bila:

1. Dokumentasi 01–03 (dan dokumen pendamping) konsisten dan dimutakhirkan terhadap implementasi.
2. Semua layanan berjalan di lingkungan pengembangan lewat Docker Compose.
3. Endpoint utama berfungsi sesuai kontrak.
4. Seluruh pengujian kritis (requirement Must) lulus dan hasilnya tercatat dengan bukti.
5. Simulasi serangan dijalankan dan hasil aktual terdokumentasi.
6. Instruksi instalasi dapat diikuti orang lain dari repository kosong.
7. Keterbatasan sistem (anonimitas, hash chain, deteksi berbasis aturan, bukan E2E-verifiable) dijelaskan.
8. Tidak ada secret, token, atau data pribadi sungguhan di repository.

---

## 14. Approval and Open Decisions

Tidak ada persetujuan atau tanda tangan yang tercatat. Kolom status diisi tim.

| ID | Keputusan | Opsi / usulan | Pemutus | Status |
|---|---|---|---|---|
| OD-01 | Cara memastikan pemilik akun adalah pemilih sah | Cocokkan email terimpor (usulan MVP); `voter_code`; verifikasi email | Tim | OPEN DECISION |
| OD-02 | Open/close otomatis | Manual di MVP (usulan); scheduler sebagai tambahan | Tim | OPEN DECISION |
| OD-07 | Aturan dua orang untuk finalisasi | Satu Admin (usulan MVP); dua Admin | Tim, dosen | OPEN DECISION |
| OD-11 | Kebijakan registrasi | Registrasi mandiri hanya menghasilkan VOTER, Admin/Auditor dibuat Admin (usulan) vs provisioning penuh oleh Admin | Tim, dosen | OPEN DECISION |
| OD-12 | Visibilitas jumlah suara bagi Auditor sebelum penutupan | Tidak ada hasil sebelum `CLOSED` (usulan; tally hanya setelah ditutup) | Tim, dosen | OPEN DECISION |
| OD-13 | Penghitungan ulang | Boleh sebelum finalisasi (run baru); tidak boleh setelah `FINALIZED` (usulan) | Tim, dosen | OPEN DECISION |
| OD-14 | Dokumen sumber kebenaran: seri 01–03 vs empat dokumen lama | Seri 01–03 untuk kebutuhan dan narasi arsitektur; dokumen lama sebagai detail kontrak dan rencana uji (usulan) | Tim | OPEN DECISION |
| OD-15 | Persetujuan jadwal 8 minggu dan pembagian kerja | Tinjau di minggu 1 | Tim, dosen | OPEN DECISION |
| OD-16 | Target peserta dan beban concurrent | PROPOSED TARGET: ≤ 1.000 pemilih, 50 request paralel | Tim, dosen | OPEN DECISION |
| OD-17 | Retensi data audit dan data pemilihan | Usulan: disimpan selama masa penilaian akademik lalu dihapus | Tim, dosen | OPEN DECISION |
| OD-18 | Nama anggota dan identitas institusi di dokumen | Isi placeholder | Tim | OPEN DECISION |
