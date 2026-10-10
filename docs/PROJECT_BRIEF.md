# VoxGuard — Project Brief

| Atribut | Nilai |
|---|---|
| Dokumen | `docs/PROJECT_BRIEF.md` (1 dari 4 dokumen engineering inti) |
| Versi | 0.1 — draft untuk review tim |
| Tanggal | 2026-10-10 |
| Status | **Rancangan.** Belum ada kode. Semua mekanisme ditulis sebagai rancangan/rekomendasi sampai benar-benar dibuat dan diuji. |
| Dokumen terkait | `ARCHITECTURE.md`, `SECURITY_AND_TEST_PLAN.md`, `API_CONTRACTS.md` |

**Konvensi ID (dipakai konsisten di keempat dokumen)**

| Prefix | Arti | Didefinisikan di |
|---|---|---|
| `FR-xx` / `NFR-xxx-xx` | Functional / Non-functional requirement | PROJECT_BRIEF |
| `SM-xx` | Success metric | PROJECT_BRIEF |
| `KD-xx` / `OD-xx` | Keputusan teknis / **OPEN DECISION** | ARCHITECTURE |
| `TH-xx` | Threat | SECURITY_AND_TEST_PLAN |
| `ATK-xx` | Skenario Attack Lab | SECURITY_AND_TEST_PLAN |
| `UT/IT/API/E2E/CC/SEC/REC/PERF-…` | Test case | SECURITY_AND_TEST_PLAN |
| `AC-xx` | Acceptance criteria | SECURITY_AND_TEST_PLAN |
| `R-xx` | Aturan deteksi anomali | SECURITY_AND_TEST_PLAN |

---

## A. Project Identity

| Item | Isi |
|---|---|
| Nama | **VoxGuard** — Verifiable Digital Election System |
| Tagline | *Every Vote. Protected. Verifiable.* |
| Jenis | Aplikasi web platform pemilu digital |
| Status | **Prototipe edukasi.** Bukan sistem pemilu resmi, belum diaudit pihak independen, belum tersertifikasi. |
| Target pengguna | Panitia pemilihan (ADMIN), pemilih (VOTER), pemeriksa independen (AUDITOR) |
| Konteks penggunaan | Simulasi pemilihan ketua kelas, ketua BEM, organisasi kampus, dan pemilihan internal komunitas; peragaan teknik pertahanan lewat Attack Lab |
| Penerapan | Lokal (Docker Compose, satu mesin) |

**Ringkasan konsep.** VoxGuard memisahkan enam hal yang sering tercampur dalam sistem pemilu sederhana: (1) identitas akun, (2) hak/kelayakan memilih, (3) isi suara, (4) bukti penerimaan suara, (5) catatan audit, dan (6) hasil penghitungan. Pemisahan ini diwujudkan lewat tujuh komponen (API Gateway + enam service), masing-masing memiliki datanya sendiri. Integritas catatan audit dijaga dengan hash chain yang *tamper-evident* (perubahan terdeteksi, bukan dicegah mutlak). Penerimaan suara dirancang aman terhadap request paralel dan retry melalui transaksi atomik, unique constraint, idempotency key, dan transactional outbox. **Attack Lab** menjalankan skenario serangan terhadap lingkungan uji lokal untuk memverifikasi bahwa mekanisme pertahanan bekerja sesuai rancangan.

---

## B. Problem Statement

Pemilu skala kecil (kelas, BEM, komunitas) umumnya berjalan lewat formulir daring atau pemungutan manual. Pendekatan tersebut dapat cukup untuk keperluan informal, tetapi sulit memberi bukti terstruktur atas hal-hal berikut. Dokumen ini **tidak** menyatakan bahwa sistem pemilu digital lain pasti tidak aman; ia hanya mendefinisikan masalah yang ingin dipelajari dan dipertahankan oleh prototipe ini.

| ID | Masalah | Risiko konkret |
|---|---|---|
| P-01 | **Double voting** | Satu pemilih mengirim suara lebih dari satu kali, termasuk lewat request bersamaan atau retry jaringan |
| P-02 | **Manipulasi/pengubahan data suara atau catatan** | Perubahan diam-diam pada tabel suara atau audit tanpa jejak |
| P-03 | **Sulit memverifikasi integritas hasil** | Hasil tidak dapat dicocokkan ulang dengan suara sah dan catatan audit |
| P-04 | **Transparansi proses terbatas** | Peserta tidak punya bukti penerimaan dan bukti proses yang aman dipublikasikan |
| P-05 | **Aktivitas tidak normal tidak terdeteksi** | Brute force, lonjakan penolakan, percobaan akses terlarang berlalu tanpa alert |
| P-06 | **Kegagalan komunikasi antarservice** | Broker mati atau pesan hilang/duplikat membuat audit dan hasil tidak konsisten |
| P-07 | **Hubungan identitas–pilihan bocor** | Operator atau log dapat mengaitkan siapa memilih siapa |

---

## C. Objectives

**Tujuan umum.** Merancang dan membangun prototipe pemilu digital berbasis microservices yang mendemonstrasikan pencegahan double voting, pemisahan identitas dari isi suara, audit tamper-evident, penghitungan yang dapat direkonsiliasi, deteksi anomali berbasis aturan, dan pengujian pertahanan melalui Attack Lab — dengan batas keamanan yang dinyatakan jujur.

**Tujuan khusus (dapat diuji).**

| ID | Tujuan khusus | Diuji oleh (lihat SECURITY_AND_TEST_PLAN) |
|---|---|---|
| SO-01 | Satu hak memilih menghasilkan maksimal satu suara diterima | ATK-01, ATK-02, CC-01, IT-BAL-02 |
| SO-02 | Retry request yang sama tidak menambah suara | CC-02, IT-BAL-03 |
| SO-03 | Suara hanya diterima saat election berstatus OPEN dan sebelum `end_at` | ATK-05, IT-BAL-06 |
| SO-04 | Hak akses diverifikasi di backend per role | ATK-03, ATK-04, API-RBAC-01 |
| SO-05 | Perubahan pada record audit uji terdeteksi oleh audit checker | ATK-06, SEC-AUD-01..04 |
| SO-06 | Hasil final berasal dari suara sah, terekonsiliasi, dan tidak dapat diubah lewat endpoint | E2E-03, IT-RES-01..05 |
| SO-07 | Event tertunda/gagal dapat dipulihkan tanpa menggandakan efek bisnis | ATK-07, ATK-08, REC-01..04 |
| SO-08 | Skenario anomali yang didefinisikan menghasilkan alert | IT-SEC-01..06, ATK-01/02/05/09 |
| SO-09 | Data audit publik tidak memuat identitas pemilih maupun pilihan kandidat | ATK-10, SEC-PRV-01..03 |
| SO-10 | Arsitektur menerapkan batas service dan kepemilikan data yang benar | IT-ARCH-01 (cek tidak ada akses DB lintas service) |

---

## D. Scope

### D.1 Fitur MVP wajib

| Kelompok | Fitur |
|---|---|
| Akun & akses | Register, login, refresh, logout, `me`; JWT access token + refresh rotation; RBAC di backend (FR-01..03) |
| Election | Buat election, kandidat, impor daftar pemilih, siklus hidup `DRAFT→SCHEDULED→OPEN→CLOSED→FINALIZED` (FR-04, FR-05) |
| Voting | Ballot view + vote ticket, pengiriman suara, idempotency, receipt (FR-06..11) |
| Konsistensi | Transactional outbox, idempotent consumer, retry, DLQ (FR-12, FR-21) |
| Audit | Hash chain per election, verifikasi, proof, checkpoint audit di luar database (FR-13, FR-14) |
| Hasil | Tally, rekonsiliasi tiga arah, finalisasi immutable, verifikasi hasil (FR-15..17) |
| Keamanan | Rate limiting, anomaly rules, alert, metrik, Attack Lab 10 skenario (FR-18..20, FR-23) |
| UI | Halaman minimal per role (FR-22) |

### D.2 Fitur tambahan (jika waktu memungkinkan)

| ID | Fitur | Catatan |
|---|---|---|
| ADD-01 | Scheduler otomatis open/close berdasarkan `start_at`/`end_at` | Lihat OD-02 |
| ADD-02 | Klaim kelayakan lewat `voter_code` sekali pakai | Lihat OD-01 |
| ADD-03 | Aturan dua orang (two-person rule) untuk finalisasi | Lihat OD-07 |
| ADD-04 | Acknowledge/resolve alert, notifikasi realtime | Di luar MVP |
| ADD-05 | JWT asimetris (RS256/EdDSA) | Lihat OD-04 |
| ADD-06 | Ekspor proof audit sebagai berkas unduhan | — |
| ADD-07 | Endpoint `/metrics` format Prometheus | — |

### D.3 Sengaja tidak dikerjakan

- **Blockchain publik** (tidak diperlukan untuk tujuan tamper-evidence skala ini; menambah kompleksitas dan biaya).
- **Biometrik** (risiko privasi tinggi, di luar tujuan).
- **AI generatif** dalam alur voting, audit, atau deteksi anomali.
- **Protokol end-to-end verifiable voting** (blind signature, mixnet, homomorphic tally, zero-knowledge) — sistem **tidak** boleh diklaim E2E-verifiable.
- Ketahanan terhadap paksaan/jual-beli suara (coercion/vote-buying resistance) yang kuat.
- Verifikasi identitas dunia nyata (KYC), high availability multi-node, sertifikasi pemilu resmi, aplikasi mobile native.

---

## E. User Roles

| Role | Hak akses | Batas kewenangan |
|---|---|---|
| **ADMIN** | Membuat election, kandidat, impor pemilih; schedule/open/close; menjalankan tally dan finalize; melihat audit, alert, metrik; menjalankan Attack Lab (hanya lingkungan lokal/uji) | **Tidak** dapat mengubah/menghapus suara diterima, mengubah hasil final, atau mengedit record audit lewat API. Tidak otomatis menjadi pemilih. Tidak dapat memilih atas nama orang lain |
| **VOTER** | Melihat election yang ia berhak ikuti; meminta ballot + vote ticket; mengirim satu suara; membaca receipt; membaca hasil **setelah FINALIZED**; verifikasi hasil dan proof audit | Tidak dapat mengakses fungsi administrasi, daftar pemilih, alert, atau hasil sementara |
| **AUDITOR** | Read-only: audit events, verifikasi chain, proof, hasil (termasuk sementara), alert dan metrik | Tidak dapat membuat/mengubah election, mengirim suara, menjalankan tally/finalize/Attack Lab |

Aturan umum: satu akun memiliki tepat satu role; matriks lengkap role × endpoint ada di `API_CONTRACTS.md` (Bagian B.0). Pemisahan tugas ADMIN (misalnya dua orang untuk finalisasi) adalah **OD-07**.

---

## F. Functional Requirements

| ID | Kebutuhan | Prioritas | Service pemilik |
|---|---|---|---|
| FR-01 | Registrasi akun; self-registration hanya menghasilkan role VOTER; akun ADMIN/AUDITOR dibuat oleh ADMIN atau seed lokal | MUST | auth-service |
| FR-02 | Login, refresh dengan rotasi + deteksi reuse, logout (revokasi sesi), `GET /auth/me` | MUST | auth-service |
| FR-03 | RBAC divalidasi di backend setiap request (Gateway + tiap service) | MUST | api-gateway, semua service |
| FR-04 | ADMIN membuat election (DRAFT), menambah kandidat, mengimpor daftar pemilih | MUST | voter-service |
| FR-05 | Transisi lifecycle dengan guard dan otoritas jelas; tidak ada transisi mundur | MUST | voter-service |
| FR-06 | Penerbitan vote ticket berpseudonim hanya untuk pemilih sah saat election OPEN | MUST | voter-service |
| FR-07 | Ballot view: daftar kandidat + vote ticket | MUST | ballot-service |
| FR-08 | Penerimaan suara: validasi ticket, status election, kandidat valid | MUST | ballot-service |
| FR-09 | One person one vote, aman terhadap request paralel | MUST | ballot-service |
| FR-10 | Idempotency: retry dengan `Idempotency-Key` sama mengembalikan hasil yang sama tanpa suara baru | MUST | ballot-service |
| FR-11 | Receipt penerimaan suara yang tidak memuat pilihan; status audit `PENDING`/`RECORDED` dilaporkan jujur | MUST | ballot-service |
| FR-12 | Transactional outbox dan relay ke RabbitMQ untuk setiap event bisnis | MUST | voter, ballot, audit, result, security |
| FR-13 | Pencatatan audit per election dengan hash chain; payload audit publik di-allowlist | MUST | audit-service |
| FR-14 | Verifikasi chain, proof audit, checkpoint audit di luar database | MUST | audit-service |
| FR-15 | Tally dari ekspor Ballot + rekonsiliasi tiga arah + pemeriksaan ballot commitment | MUST | result-service |
| FR-16 | Finalisasi hasil immutable (snapshot + `result_hash`), tanpa endpoint edit | MUST | result-service |
| FR-17 | Akses hasil sesuai role/status; verifikasi ulang hasil final | MUST | result-service |
| FR-18 | Deteksi anomali berbasis aturan (R-01..R-10) dan alert | MUST | security-service |
| FR-19 | Attack Lab: jalankan ATK-01..ATK-10 hanya pada election lab di lingkungan lokal/uji | MUST | security-service |
| FR-20 | Rate limiting, request ID, correlation ID, validasi awal request | MUST | api-gateway |
| FR-21 | Idempotent consumer, retry bertahap, dead-letter queue, prosedur replay | MUST | semua consumer |
| FR-22 | Frontend minimal: login, daftar election, ballot, receipt, hasil; admin; auditor; security/Attack Lab | MUST | frontend |
| FR-23 | Endpoint metrik keamanan dan operasional | SHOULD | security-service |

---

## G. Non-Functional Requirements

> Target performa di bawah adalah **usulan target awal yang harus divalidasi** lewat pengukuran (PERF-01..PERF-04). Belum ada angka hasil pengujian.

| ID | Area | Persyaratan |
|---|---|---|
| NFR-SEC-01 | Security | Password di-hash dengan Argon2id; tidak pernah dicatat |
| NFR-SEC-02 | Security | Semua endpoint non-publik menuntut token valid; otorisasi role di backend |
| NFR-SEC-03 | Security | Service internal tidak dapat dijangkau dari luar jaringan Docker; hanya Gateway (dan frontend) yang dipublikasikan |
| NFR-SEC-04 | Security | Setiap service memakai role database dengan hak minimum; `ballot_app` hanya `INSERT/SELECT` pada tabel `ballots` |
| NFR-SEC-05 | Security | Secret hanya lewat environment/secret store lokal, tidak masuk repo atau dokumen |
| NFR-PRV-01 | Privacy | `ballots` tidak memuat `user_id`/email; audit dan event tidak memuat identitas maupun `candidate_id` |
| NFR-PRV-02 | Privacy | Log tidak memuat password, token, `receipt_code`, `vote_ticket`, atau `candidate_id` |
| NFR-PRV-03 | Privacy | Dokumentasikan batas privasi: pseudonimisasi bukan anonimitas sempurna |
| NFR-REL-01 | Reliability | Penerimaan suara tidak bergantung pada ketersediaan RabbitMQ atau Audit Service |
| NFR-REL-02 | Reliability | Event bersifat at-least-once; konsumen idempotent; pesan gagal masuk DLQ dan dapat di-replay |
| NFR-REL-03 | Reliability | Ketergantungan sinkron kritis (Voter dari Ballot) bersifat fail-closed: 503, bukan menerima suara tanpa validasi |
| NFR-MNT-01 | Maintainability | Satu bahasa backend (Python/FastAPI); pustaka bersama `voxguard_common` hanya berisi utilitas non-domain |
| NFR-MNT-02 | Maintainability | Migrasi skema via Alembic per service; kontrak API ditulis agar dapat diterjemahkan ke OpenAPI 3.1/Pydantic |
| NFR-TST-01 | Testability | Setiap klaim keamanan memiliki mitigasi dan minimal satu skenario uji |
| NFR-TST-02 | Testability | Lingkungan uji dapat dibuat ulang dengan satu perintah Compose (profil `test`) |
| NFR-PRF-01 | Performa | 50 request voting paralel untuk satu hak memilih selesai tanpa HTTP 5xx dan menghasilkan tepat satu suara (kriteria fungsional) |
| NFR-PRF-02 | Performa | **Target awal (validasi):** p95 latensi `POST /ballots` ≤ 500 ms pada laptop pengembangan dengan 50 request paralel |
| NFR-PRF-03 | Performa | **Target awal (validasi):** lag outbox→audit p95 ≤ 10 detik saat broker sehat |
| NFR-PRF-04 | Performa | **Target awal (validasi):** verifikasi chain 10.000 event ≤ 60 detik |
| NFR-PRF-05 | Performa | **Asumsi skala MVP:** ≤ 1.000 pemilih per election, ≤ 5 election aktif bersamaan |

---

## H. Success Metrics

| ID | Indikator | Kriteria lulus | Metode verifikasi |
|---|---|---|---|
| SM-01 | Double voting ditolak | Suara kedua untuk hak memilih yang sama ditolak `409 VOTER_ALREADY_VOTED`; tepat 1 baris `ballots` | ATK-01, IT-BAL-02, API-BAL-03 |
| SM-02 | Request voting paralel menghasilkan maksimal satu suara per hak memilih | 50 request paralel → tepat 1 baris `ballots` dan 1 event `VoteAccepted` | ATK-02, CC-01, CC-02 |
| SM-03 | Perubahan data audit uji terdeteksi | `verify` mengembalikan `INVALID` dengan `sequence` pertama yang gagal | ATK-06, SEC-AUD-01..04 |
| SM-04 | Hasil penghitungan sesuai suara sah | `tally_items` = hitung ulang independen dari ekspor Ballot; rekonsiliasi `MATCH` | E2E-03, IT-RES-01..05 |
| SM-05 | Request tanpa izin ditolak | Tanpa/invalid token → 401; role salah → 403; hasil final tidak berubah | ATK-03, ATK-04, API-RBAC-01 |
| SM-06 | Event tertunda dapat diproses kembali | Setelah broker pulih, 100% baris outbox `PENDING` menjadi `PUBLISHED` dan efek bisnis tepat satu kali | ATK-08, REC-01..04 |
| SM-07 | Skenario anomali menghasilkan alert | Setiap skenario dengan alert terdefinisi memunculkan `anomaly_alerts` yang sesuai | IT-SEC-01..06, ATK-01/02/05/09 |
| SM-08 | Informasi sensitif tidak bocor lewat audit publik | Response audit/proof tidak memuat `user_id`, email, `eligibility_ref`, `candidate_id`, token | ATK-10, SEC-PRV-01..03 |

Metrik hanya dianggap tercapai bila ada **hasil eksperimen aktual** yang dicatat (template di SECURITY_AND_TEST_PLAN Bagian F.3). Dokumen ini tidak memuat hasil pengujian apa pun.

---

## I. Constraints and Assumptions

| Aspek | Batasan / asumsi |
|---|---|
| Tim | 2–3 orang; jumlah service dibatasi enam + gateway agar dapat dipelihara |
| Waktu | Rencana awal ±8 minggu, kemungkinan lebih dari satu bulan; prioritaskan FR MUST |
| Deployment | Lokal, satu mesin, Docker Compose; satu instance PostgreSQL dengan 6 database terpisah |
| Teknologi | Hanya stack yang ditetapkan; tidak ada teknologi tambahan tanpa alasan teknis |
| Skala | Lihat NFR-PRF-05 |
| Ruang lingkup keamanan | Ancaman dari klien, pengguna terautentikasi, kegagalan sistem, dan operator yang tidak mengontrol seluruh stack. **Di luar lingkup:** penyerang yang menguasai host, seluruh database, dan seluruh secret; serangan jaringan tingkat ISP; sertifikasi |
| Identitas dunia nyata | Kelayakan memilih ditetapkan dari daftar yang diimpor ADMIN. Verifikasi bahwa pemilik akun adalah orang yang sebenarnya **belum** dijamin (lihat OD-01 dan TH-14) |
| Data | Hanya data uji; tidak ada data pribadi sungguhan di dokumen maupun fixture |
| Transport | HTTP lokal pada MVP; TLS adalah rekomendasi untuk penggunaan di luar mesin lokal |

---

## J. Definition of Done

Sebuah fitur dianggap **selesai** bila seluruh poin berikut terpenuhi:

1. Perilaku sesuai FR terkait dan kontrak di `API_CONTRACTS.md` (path, role, error code, efek DB, event).
2. Migrasi Alembic ada, dapat dijalankan dari database kosong, dan tidak melanggar kepemilikan data antar-service.
3. Otorisasi role diuji di level API (termasuk kasus negatif) dan tercakup di API-RBAC-01.
4. Test yang dirujuk pada baris FR/SM terkait ada dan lulus; test keamanan/konkurensi relevan dijalankan secara aktual dan hasilnya dicatat.
5. Event baru memiliki publisher, consumer, skema versi, strategi deduplikasi, retry, dan DLQ yang terdokumentasi.
6. Tidak ada secret, token, password, `candidate_id`, atau identitas pemilih di log, event audit/keamanan, maupun response publik.
7. Dokumen terkait (ARCHITECTURE, API_CONTRACTS, SECURITY_AND_TEST_PLAN) diperbarui dalam PR yang sama jika ada perubahan kontrak.
8. OpenAPI/Swagger service menampilkan endpoint dengan skema yang sama dengan kontrak.
9. Review kode oleh minimal satu anggota tim lain; checklist keamanan di SECURITY_AND_TEST_PLAN (Bagian C) ditinjau untuk perubahan yang menyentuh voting, audit, atau hasil.
10. Klaim di dokumen memakai bahasa rancangan sampai mekanisme benar-benar diimplementasikan dan diuji.
