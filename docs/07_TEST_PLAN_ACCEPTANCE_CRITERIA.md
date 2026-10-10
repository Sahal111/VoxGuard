# VoxGuard — Test Plan and Acceptance Criteria

## 1. Document Information

| Atribut | Nilai |
|---|---|
| Nama dokumen | Test Plan & Acceptance Criteria |
| Proyek | VoxGuard — Verifiable Digital Election System |
| Versi / Status | 0.1 / **Draft — rencana; belum ada test yang dibuat atau dijalankan** |
| Tanggal | 2026-10-10 |
| Pemilik | `[PEMILIK-DOKUMEN]` (placeholder) |
| Acuan | SRS (`02_…`), SAD (`03_…`), `04_…` (constraint DBC-01..15), `05_…` (kontrak), `06_…` (threat TH-01..23). Pendamping lama (tidak diubah): `SECURITY_AND_TEST_PLAN.md` |

| Versi | Tanggal | Perubahan |
|---|---|---|
| 0.1 | 2026-10-10 | Draf awal. **Dokumen ini menjadi acuan kanonik ID test dan AC** (lihat Bagian 17 untuk rekonsiliasi dengan dokumen lama) |

**Aturan status.** Semua test berstatus `PLANNED`. Status `PASSED` hanya boleh diisi setelah test benar-benar dijalankan dengan bukti (Bagian 5, 15). Dokumen ini tidak memuat hasil aktual, angka performa hasil ukur, atau klaim lulus.

---

## 2. Test Objectives and Scope

**Tujuan.** Memverifikasi bahwa VoxGuard memenuhi requirement SRS, menegakkan kontrol pada threat model, dan mematuhi constraint database — dengan bukti yang dapat diulang — sebelum demonstrasi/penyerahan.

| Jenis pengujian | Cakupan | Tingkat |
|---|---|---|
| Functional | Perilaku fitur sesuai FR | API/integrasi |
| Unit | Fungsi murni: hash, ticket, lifecycle, aturan anomali | UT |
| Integration | Layanan + PostgreSQL + RabbitMQ (+ Redis) | IT |
| API contract | Skema, status, error, RBAC | API, CT |
| Database constraint | Unique/CHECK/trigger/hak | DB, MIG |
| Concurrency | Voting paralel, idempotency, batas close | CC |
| Security | Tamper, privasi, konfigurasi, injeksi, Attack Lab | SEC, ATK |
| Event processing | Outbox, duplikat, DLQ | IT-OUT, REC, ATK-07 |
| Recovery | Broker/layanan/Redis mati, restore | REC |
| End-to-end | Alur lengkap | E2E |
| Usability | Alur pemilih, pesan error, responsif, aksesibilitas dasar | UX |
| Performance | Pengamatan latensi (target PROPOSED) | PERF |

**Di luar cakupan:** uji penetrasi pihak ketiga, uji beban produksi, sertifikasi, pengujian terhadap sistem eksternal.

---

## 3. Test Environment

| Komponen | Spesifikasi (rancangan) |
|---|---|
| Orkestrasi | Docker Compose profil `test` (database uji terpisah; Attack Lab aktif; port Ballot ke `127.0.0.1` untuk CC jalur langsung) |
| Infrastruktur | PostgreSQL (6 database uji), RabbitMQ, Redis |
| Aplikasi | FastAPI (Gateway + 6 layanan) |
| Test runner | Pytest; HTTPX (sync/async) untuk API dan konkurensi; Docker CLI untuk uji pemulihan |
| Versi dependency | OPEN DECISION OD-19 (di-*pin* saat implementasi) |
| Data uji | Sintetis (Bagian 13) |
| Variabel konfigurasi uji | `APP_ENV=test`, `ATTACK_LAB_ENABLED=true`, `RATE_LIMIT_*` rendah untuk ATK-09, `ACCESS_TOKEN_TTL_MIN` pendek untuk uji kedaluwarsa, secret uji acak per run (tidak di repo), `INTERNAL_API_KEY` uji. Tidak ada secret nyata di dokumen |
| Isolasi | Lingkungan uji tidak berbagi database/volume dengan lingkungan demo; reset penuh antar suite |

---

## 4. Test Levels and Responsibilities

Pemilik adalah role/placeholder (usulan; lihat `08_…` Bagian 5).

| Level | Tujuan | Tools | Pemilik | Kriteria lulus | Bukti yang disimpan |
|---|---|---|---|---|---|
| Unit | Logika murni benar | Pytest | Pemilik komponen | Seluruh UT Must lulus | EV-1 |
| Integration | Layanan+DB+broker bekerja benar | Pytest, Compose test | Pemilik layanan | IT Must lulus | EV-1, EV-2 |
| API/Contract | Kontrak dan RBAC terpenuhi | Pytest+HTTPX | Pemilik layanan + FE | API/CT Must lulus | EV-1, EV-6 |
| Database | Constraint ada dan efektif | Pytest+SQL | Pemilik DB | DB-01..15, MIG-01..04 lulus | EV-1, EV-2 |
| Concurrency | Tidak ada suara ganda | Pytest+asyncio | Pemilik Ballot | CC-01..05 lulus | EV-1, EV-2 |
| Security | Kontrol ancaman efektif | Pytest, SQL uji | Pemilik Security + semua | SEC/ATK Must lulus | EV-1, EV-2, EV-3 |
| Recovery | Pemulihan sesuai rancangan | Pytest+Docker CLI | Pemilik infrastruktur | REC Must lulus | EV-1, EV-4 |
| E2E | Alur penuh | Pytest (opsional Playwright) | Bersama | E2E Must lulus | EV-1, EV-5 |
| Usability | Alur dapat dipakai | Uji manual berskrip | Pemilik frontend | UX sesuai kriteria | EV-5 |
| Performance | Pengamatan | Skrip HTTPX | Bersama | Terukur dan tercatat (tanpa ambang wajib) | EV-1 |

---

## 5. Test Case Format

Setiap test case memuat: **Test ID, Requirement ID, Threat ID, Nama, Prioritas (Must/Should/Could), Prasyarat dan data, Langkah, Expected result, Evidence, Status**. Kolom **Pass/fail** berlaku seragam: **PASS** bila *seluruh* butir Expected terpenuhi dan terbukti oleh Evidence; **FAIL** bila ada satu butir tidak terpenuhi; **BLOCKED** bila prasyarat tidak dapat dipenuhi. Status: `PLANNED`, `IMPLEMENTED`, `PASSED`, `FAILED`, `BLOCKED` — semua awalnya `PLANNED`; **tidak boleh `PASSED` tanpa dijalankan**.

Kode **Evidence**: EV-1 laporan Pytest (junit/log run); EV-2 keluaran query database; EV-3 hasil pemindaian log/respons; EV-4 status RabbitMQ/Compose; EV-5 rekaman/tangkapan layar; EV-6 respons HTTP tersimpan.

Prasyarat umum (kecuali dinyatakan lain): stack profil `test` hidup dan sehat, database kosong lalu *seed* sintetis, akun ADMIN/VOTER/AUDITOR uji.

---

## 6. Functional Test Cases

| ID | Req | Threat | Nama | Pri | Prasyarat/data | Langkah | Expected | Evid. | Status |
|---|---|---|---|---|---|---|---|---|---|
| API-AUTH-01 | FR-AUTH-001 | TH-04 | Registrasi aman | Must | Email baru | Register tanpa role; dengan `role=ADMIN` sebagai anon dan VOTER; email duplikat | `201` role `VOTER`; role tinggi → `403`; duplikat → `409`; tanpa password di respons | EV-1, EV-6 | PLANNED |
| API-AUTH-02 | FR-AUTH-002 | — | Login valid | Must | Akun uji | Login benar | `200`, token + refresh, `role` benar | EV-1 | PLANNED |
| API-AUTH-03 | FR-AUTH-002 | TH-10 | Login tidak valid | Must | — | Email tak ada; password salah | `401 UNAUTHORIZED`; body dan waktu tidak membedakan kedua kasus | EV-1, EV-6 | PLANNED |
| API-AUTH-04 | FR-AUTH-003 | TH-13 | Refresh dan reuse | Must | Sesi login | Refresh; pakai token lama lagi | Pasangan baru; reuse → `401` dan seluruh `family_id` dicabut | EV-1, EV-2 | PLANNED |
| API-AUTH-05 | FR-AUTH-004 | TH-13 | Logout | Must | Sesi login | Logout; pakai access token lama | `204`; token ditolak `401` (selama denylist tersedia) | EV-1 | PLANNED |
| API-AUTH-06 | FR-AUTH-005 | — | `me` | Must | Login | `GET /auth/me` | Data pengguna tanpa hash/token | EV-6 | PLANNED |
| API-AUTH-07 | FR-AUTH-007 | TH-10 | Lockout | Should | Konfigurasi ambang | Login gagal berulang | `423 ACCOUNT_LOCKED` setelah ambang; sinyal keamanan terkirim | EV-1 | PLANNED |
| API-AUTH-08 | FR-AUTH-006 | TH-03 | Token invalid | Must | — | Tanpa token; tanda tangan diubah; kedaluwarsa; `aud` salah | `401 UNAUTHORIZED` pada semua | EV-1, EV-6 | PLANNED |
| API-RBAC-01 | FR-AUTH-006 | TH-04, TH-17 | Matriks role × endpoint | Must | Token anon/VOTER/AUDITOR/ADMIN | Panggil setiap endpoint (`05_…` Bagian 3.2) per role | Diizinkan/ditolak sesuai matriks (`401`/`403`); parametrik dari `x-roles` | EV-1 | PLANNED |
| IT-VOT-01 | FR-ELEC-001, 002 | — | Buat, daftar, detail pemilihan | Must | ADMIN, VOTER terdaftar/tidak | Buat election; daftar sebagai tiap role | `DRAFT`; VOTER tak terdaftar tidak melihat; `DRAFT` tak terlihat VOTER/AUDITOR | EV-1 | PLANNED |
| IT-VOT-02 | FR-ELEC-003, 004 | — | Kandidat dan impor pemilih | Must | `DRAFT` | Tambah kandidat (ganda), impor pemilih (duplikat, format salah) | `201`; duplikat `409`/`422`; all-or-nothing | EV-1, EV-2 | PLANNED |
| IT-VOT-03 | FR-ELEC-005..008 | TH-17 | Lifecycle dan pembekuan | Must | Kandidat ≥ 2, pemilih ≥ 1 | schedule → open → close; ulang transisi; ubah kandidat/pemilih setelah schedule | Transisi sah; ulang/ubah → `409 ELECTION_INVALID_STATE`; event `ElectionOpened/Closed` di outbox | EV-1, EV-2 | PLANNED |
| IT-VOT-04 | FR-ELIG-001 | TH-14 | Penerbitan ticket | Must | Election `OPEN`, pemilih terdaftar | `GET …/ballot` | Ticket tanpa `user_id`/email; status `TICKET_ISSUED` | EV-1, EV-2 | PLANNED |
| IT-VOT-05 | FR-ELIG-002 | TH-14 | Pemilih tidak terdaftar | Must | Akun VOTER tak terdaftar | `GET …/ballot` | `403 VOTER_NOT_ELIGIBLE`; tanpa ticket | EV-1 | PLANNED |
| IT-VOT-06 | FR-ELIG-003 | TH-14 | Cabut kelayakan sebelum `OPEN` | Could | `SCHEDULED` | Revoke pemilih | `REVOKED` ditolak ticket | EV-1 | PLANNED |
| API-BAL-01 | FR-BALL-001 | — | Ballot view | Must | `OPEN`, eligible | `GET …/ballot` | Kandidat + ticket + `ticket_expires_at` | EV-6 | PLANNED |
| API-BAL-02 | FR-BALL-002, 005 | TH-02 | Suara sah dan replay | Must | Ticket valid | `POST /ballots`; ulang dengan key sama | `201` receipt; replay `200` + `Idempotent-Replayed` | EV-1, EV-2 | PLANNED |
| API-BAL-03 | FR-BALL-003 | TH-01 | Suara ganda | Must | Sudah memilih | Kirim lagi, key baru | `409 VOTER_ALREADY_VOTED`; 1 baris | EV-1, EV-2 | PLANNED |
| API-BAL-04 | FR-BALL-007 | TH-12 | Receipt | Must | Suara diterima | Lookup dengan kode benar/salah/id salah | `200` tanpa pilihan/identitas; salah → `404 RECEIPT_NOT_FOUND` (sama untuk keduanya) | EV-6 | PLANNED |
| IT-BAL-01 | FR-BALL-002, 008 | — | Penerimaan atomik | Must | Ticket valid | Kirim suara | `ballots`, `idempotency_records`, `outbox_events` terisi sekaligus; tanpa `user_id` | EV-2 | PLANNED |
| IT-BAL-02 | FR-BALL-003 | TH-01 | Suara kedua | Must | Suara pertama ada | Kirim dengan `eligibility_ref` sama | `VOTER_ALREADY_VOTED`; `COUNT=1` | EV-2 | PLANNED |
| IT-BAL-03 | FR-BALL-005 | TH-02 | Replay idempotency | Must | Key K | Ulang K, payload sama | Respons sama; tanpa baris baru | EV-2 | PLANNED |
| IT-BAL-04 | FR-BALL-005 | TH-02 | Key sama payload beda | Must | Key K | Ulang K dengan `candidate_id` lain | `409 IDEMPOTENCY_CONFLICT` | EV-1 | PLANNED |
| IT-BAL-05 | FR-BALL-008 | TH-08 | Atomisitas outbox | Must | Fault injection setelah insert `ballots` | Picu kegagalan sebelum COMMIT | Rollback: tidak ada `ballots` tanpa `outbox_events` | EV-2 | PLANNED |
| IT-BAL-06 | FR-BALL-006 | TH-07 | Di luar waktu | Must | Election `CLOSED`/lewat `end_at` | Kirim suara | `409 ELECTION_NOT_OPEN`; tidak tersimpan | EV-2 | PLANNED |
| IT-BAL-07 | FR-BALL-006 | TH-16 | Voter mati (fail-closed) | Must | Hentikan voter-service | Kirim suara | `503 SERVICE_UNAVAILABLE`; tidak tersimpan | EV-1, EV-2 | PLANNED |
| IT-OUT-01 | FR-BALL-008, FR-SYSO-005 | TH-09 | Relay outbox | Must | Baris `PENDING` | Jalankan relay; matikan broker | Terkirim → `PUBLISHED`; gagal → `attempts` naik, backoff | EV-2, EV-4 | PLANNED |
| IT-AUD-01 | FR-AUDT-001, 002 | TH-06 | Chain dari event | Must | `VoteAccepted` terkirim | Konsumsi | Entri dengan `prev_hash` benar; `payload_public` ter-allowlist (tanpa `eligibility_ref`) | EV-2 | PLANNED |
| IT-AUD-02 | FR-AUDT-001 | TH-08 | Dedup audit | Must | Event sama 5× | Kirim ulang | Satu entri | EV-2 | PLANNED |
| IT-AUD-03 | FR-AUDT-003, 004 | TH-06 | `verify` dan `proof` | Must | Chain valid | Panggil endpoint | `VALID`; proof tanpa data sensitif | EV-6 | PLANNED |
| IT-RES-01 | FR-RSLT-001 | TH-19 | Tally benar | Must | Election `CLOSED`, suara diketahui | Tally | Hitungan = hitung ulang independen dari data uji | EV-1, EV-2 | PLANNED |
| IT-RES-02 | FR-RSLT-002, 003 | TH-19 | Rekonsiliasi gagal | Must | B ≠ A atau V | Tally | `RECONCILIATION_FAILED`; finalisasi ditolak; tally ulang menghasilkan run baru | EV-2 | PLANNED |
| IT-RES-03 | FR-RSLT-004 | TH-05, TH-19 | Finalisasi immutable | Must | Tally `MATCH`, audit `VALID` | Finalize; coba UPDATE/DELETE via role aplikasi | `final_results` dibuat; UPDATE/DELETE gagal; finalize ulang → `409` | EV-2 | PLANNED |
| IT-RES-04 | FR-RSLT-002 | TH-05 | Commitment | Must | Ubah `candidate_id` di `ballots` uji | Tally | `INTEGRITY_FAILED` / `BALLOT_INTEGRITY_FAILED` | EV-2 | PLANNED |
| IT-RES-05 | FR-RSLT-005 | TH-06, TH-19 | Finalisasi ditolak prasyarat | Must | Chain dirusak pada DB uji | Finalize | `409 AUDIT_VERIFICATION_FAILED` | EV-1 | PLANNED |
| IT-SEC-01 | FR-SECM-002, 003 | TH-01 | R-01 | Must | Ambang lab | 3 `VoteRejected(VOTER_ALREADY_VOTED)` sama fingerprint | Alert R-01 MEDIUM + `SecurityAlertRaised` | EV-2 | PLANNED |
| IT-SEC-02 | FR-SECM-002 | TH-02 | R-02 | Must | — | ≥ 20 penolakan/menit | Alert R-02 | EV-2 | PLANNED |
| IT-SEC-03 | FR-SECM-002 | TH-03, TH-10 | R-03 | Must | — | ≥ 10 sinyal gagal | Alert R-03 | EV-2 | PLANNED |
| IT-SEC-04 | FR-SECM-002 | TH-10 | R-04 | Should | — | ≥ 5 sinyal rate limit | Alert R-04 | EV-2 | PLANNED |
| IT-SEC-05 | FR-SECM-002 | TH-09 | R-06 | Should | Broker mati | Outbox `PENDING` > ambang | Alert R-06 HIGH | EV-2 | PLANNED |
| IT-SEC-06 | FR-SECM-002 | TH-19 | R-10 | Must | Tally mismatch | `TallyCompleted` mismatch | Alert R-10 | EV-2 | PLANNED |
| SEC-LAB-01 | FR-SECM-005 | TH-18 | Pembatasan Attack Lab | Must | Role VOTER/AUDITOR; flag nonaktif; election non-lab | `POST /security/attacks/run` berbagai kondisi | `403`/`409`; tidak ada aksi pada election non-lab | EV-1, EV-2 | PLANNED |
| IT-ARCH-01 | NFR-MNT-001, SO-10 | TH-05 | Ownership DB | Must | Role DB per layanan | Coba akses lintas database dan pindai konfigurasi | Setiap role hanya mengakses databasenya | EV-1, EV-2 | PLANNED |

---

## 7. Concurrency and Idempotency Tests

Beban uji (50 request) adalah **target usulan (PROPOSED)**, bukan hasil. **Kriteria wajib:** untuk satu `(election_id, eligibility_ref)`, paling banyak **satu** baris `ballots`.

| ID | Req | Threat | Nama | Pri | Prasyarat/data | Langkah | Expected | Evid. | Status |
|---|---|---|---|---|---|---|---|---|---|
| CC-01 | FR-BALL-003/004, NFR-PRF-002 | TH-02 | Paralel, key berbeda | Must | 1 pemilih, 1 ticket; 50 key berbeda; jalur langsung dan via Gateway | 50 `POST /ballots` bersamaan | Tepat 1×`201`; sisanya `409 VOTER_ALREADY_VOTED` (atau `429` via Gateway); tanpa `5xx`; `COUNT(ballots)=1`, `COUNT(outbox VoteAccepted)=1` | EV-1, EV-2 | PLANNED |
| CC-02 | FR-BALL-005 | TH-02 | Paralel, key sama | Must | Key tunggal, payload sama | 50 request bersamaan | 1×`201` + 49×`200` replay dengan `receipt_id` identik; `COUNT=1` | EV-1, EV-2 | PLANNED |
| CC-03 | FR-BALL-006 | TH-07 | Voting paralel saat `close` | Must | Banyak pemilih | Kirim suara sambil memanggil `close` | Tidak ada suara dengan `accepted_at > closed_at` dihitung; B/A/V cocok atau mismatch dilaporkan | EV-2 | PLANNED |
| CC-04 | FR-BALL-005 | TH-02 | Timeout setelah commit | Must | Putuskan koneksi klien setelah COMMIT sebelum respons | Retry key sama | `200` replay; satu suara | EV-1, EV-2 | PLANNED |
| CC-05 | NFR-REL-003 | TH-08 | Restart consumer setelah menerima event | Must | Consumer dihentikan sebelum ack | Naikkan lagi | Pesan di-redeliver; efek bisnis sekali (satu entri audit) | EV-2, EV-4 | PLANNED |
| (kasus lain) | | | Key berbeda untuk kelayakan sama (sekuensial); event duplikat | Must | — | Lihat IT-BAL-02, ATK-07, IT-AUD-02 | Lihat masing-masing | — | PLANNED |

Verifikasi hasil selalu dari **API dan database** (query `COUNT` dan konten `outbox_events`).

---

## 8. Security Test Cases

Semua pengujian pada sistem/data milik tim. Skenario Attack Lab ATK-01..10 selengkapnya (langkah, expected response/DB/audit/alert) ada di `SECURITY_AND_TEST_PLAN.md` D.2; ringkasannya di bawah dan harus dijalankan ulang dengan hasil dicatat di dokumen ini.

| ID | Req | Threat | Nama | Pri | Prasyarat/data | Langkah | Expected | Evid. | Status |
|---|---|---|---|---|---|---|---|---|---|
| ATK-01 | FR-BALL-003, FR-SECM-002 | TH-01 | Double voting | Must | Election lab `OPEN` | Suara 1; suara 2 (key/kandidat berbeda) | 2: `409 VOTER_ALREADY_VOTED`; 1 baris; R-01 | EV-1, EV-2 | PLANNED |
| ATK-02 | FR-BALL-004 | TH-02 | 50 request paralel | Must | Varian A (langsung), B (Gateway), C (key sama) | Lihat CC-01/CC-02 | Sama dengan CC-01/CC-02; R-01/R-02 | EV-1, EV-2 | PLANNED |
| ATK-03 | FR-AUTH-006 | TH-03, TH-13 | Token invalid/kedaluwarsa | Must | Token uji | Tanpa token, tanda tangan salah, kedaluwarsa, pasca-logout, ticket rusak | `401`/`403 VOTE_TICKET_INVALID`; tanpa efek; R-03 | EV-1 | PLANNED |
| ATK-04 | FR-RSLT-006 | TH-04, TH-17, TH-19 | Ubah hasil tanpa izin | Must | Election `FINALIZED` | VOTER/AUDITOR/anon panggil tally/finalize; ADMIN ulang; PUT/PATCH/DELETE | `403`/`401`/`409`/`404`; `result_hash` tidak berubah; R-08 | EV-1, EV-2 | PLANNED |
| ATK-05 | FR-BALL-006 | TH-07 | Suara setelah penutupan | Must | Ticket valid lalu `close` | Kirim suara | `409 ELECTION_NOT_OPEN`; R-07 | EV-1, EV-2 | PLANNED |
| ATK-06 | FR-AUDT-006 | TH-06 | Manipulasi audit (DB uji) | Must | ≥ 10 entri valid; checkpoint | Ubah, hapus, sisip, potong ekor, lalu `verify` | `INVALID` dengan `first_failure.sequence` benar; R-05 | EV-1, EV-2 | PLANNED |
| ATK-07 | NFR-REL-003 | TH-08 | Event duplikat | Must | Publish ulang event | Publish 5× `VoteAccepted`, `ElectionClosed`, `ResultFinalized` | Tanpa efek ganda; metrik duplikat naik | EV-2, EV-4 | PLANNED |
| ATK-08 | NFR-REL-001, 006 | TH-09 | RabbitMQ downtime | Must | `OPEN`; outbox kosong | Matikan broker, kirim N suara, nyalakan | Suara tetap `201`; receipt `PENDING`→`RECORDED`; backlog 0; R-06 | EV-2, EV-4 | PLANNED |
| ATK-09 | NFR-SEC-003 | TH-10 | Rate limiting | Must | Batas lab | Banjir login/GET; gagal login berulang | `429` + `Retry-After`; lockout; R-03/R-04 | EV-1 | PLANNED |
| ATK-10 | NFR-PRV-001, 005 | TH-12 | Akses identitas/pilihan | Must | Election lab terisi | Periksa semua respons, event, log; coba endpoint tak ada/internal | Tanpa field terlarang; `404`/`403` | EV-3, EV-6 | PLANNED |
| SEC-AUD-01 | FR-AUDT-003 | TH-06 | Ubah `payload_public` | Must | Chain valid | Ubah satu entri (DB uji), `verify` | `INVALID`, `EVENT_HASH_MISMATCH` pada `sequence` itu | EV-1 | PLANNED |
| SEC-AUD-02 | FR-AUDT-003 | TH-06 | Hapus entri tengah | Must | idem | Hapus, `verify` | `INVALID` (`SEQUENCE_GAP`/`PREV_HASH_MISMATCH`) | EV-1 | PLANNED |
| SEC-AUD-03 | FR-AUDT-003 | TH-06 | Sisip/susun ulang | Must | idem | Sisip entri palsu / tukar urutan | `INVALID` | EV-1 | PLANNED |
| SEC-AUD-04 | FR-AUDT-005 | TH-06 | Potong ekor rantai | Should | Checkpoint ada | Hapus entri terakhir | `INVALID` (`CHECKPOINT_MISMATCH`/`HEAD_MISMATCH`) | EV-1 | PLANNED |
| SEC-DB-01 | NFR-SEC-009 | TH-05 | `ballots` append-only | Must | Role `ballot_app` | Coba UPDATE/DELETE | Ditolak | EV-2 | PLANNED |
| SEC-DB-02 | NFR-SEC-009 | TH-05 | `audit_events` append-only | Must | Role `audit_app` | Coba UPDATE/DELETE | Ditolak | EV-2 | PLANNED |
| SEC-DB-03 | NFR-SEC-009 | TH-05 | `final_results` immutable | Must | Role `result_app` | Coba UPDATE/DELETE | Ditolak | EV-2 | PLANNED |
| SEC-DB-04 | NFR-SEC-009 | TH-11 | Batas superuser | Should | Superuser uji | Ubah data sebagai superuser | Dapat diubah; perubahan **terdeteksi** oleh verify/commitment bila relevan; dicatat sebagai residual | EV-2 | PLANNED |
| SEC-PRV-01 | NFR-PRV-001 | TH-12 | Audit/proof/receipt bersih | Must | Data uji terisi | Pindai respons audit, proof, receipt, hasil | Tanpa `user_id`, email, `eligibility_ref`, `candidate_id`, nonce, token | EV-3 | PLANNED |
| SEC-PRV-02 | NFR-PRV-003 | TH-15 | Log bersih | Must | Jalankan alur lengkap | Pindai log semua kontainer | Tanpa password, token, ticket, kode receipt, `candidate_id`, nonce | EV-3 | PLANNED |
| SEC-PRV-03 | NFR-PRV-001 | TH-12 | Event bersih | Must | Alur voting | Periksa pesan di broker/DLQ | Tidak ada `candidate_id`/identitas; `eligibility_ref` hanya pada `VoteAccepted` | EV-3, EV-4 | PLANNED |
| SEC-PRV-04 | NFR-PRV-002 | TH-12 | `ballots` tanpa identitas | Must | Skema | Inspeksi kolom/query | Tidak ada kolom identitas pada `ballots`/`idempotency_records` | EV-2 | PLANNED |
| SEC-CFG-01 | NFR-SEC-006 | TH-15, TH-21 | Tanpa secret di repo | Must | Repo | Pindai secret | Tidak ada secret nyata | EV-3 | PLANNED |
| SEC-CFG-02 | NFR-SEC-008 | TH-21 | Port internal tertutup | Must | Compose | Pindai port host | Hanya Gateway/frontend (+loopback management) | EV-4 | PLANNED |
| SEC-CFG-03 | NFR-SEC-008 | TH-18, TH-21 | Endpoint uji terkunci | Must | `ATTACK_LAB_ENABLED=false` | Panggil `/internal/v1/test/*` | Tidak tersedia/ditolak | EV-1 | PLANNED |
| SEC-INJ-01 | NFR-SEC-004 | TH-03 | Validasi input | Must | — | Kirim payload SQL/JSON aneh, field ekstra | `422`; tanpa efek | EV-1 | PLANNED |
| SEC-TKN-01 | NFR-SEC-005 | TH-13 | Replay token/ticket | Should | Ticket pemilik A | Pakai ticket dari klien lain; ticket kedaluwarsa | Ticket valid hanya memberi satu suara; kedaluwarsa ditolak | EV-1, EV-2 | PLANNED |
| SEC-ADM-01 | FR-AUTH-006, FR-AUDT-001 | TH-17 | Aksi admin tercatat | Must | Admin menjalankan lifecycle | schedule/open/close/finalize | Aksi tercatat di chain; tidak ada endpoint ubah suara/hasil | EV-2 | PLANNED |
| SEC-EVT-01 | NFR-REL-003 | TH-20 | Event tidak valid | Must | Akses broker uji | Publish event dengan skema salah/`producer` tak dikenal/field terlarang | Ditolak ke DLQ; tanpa efek | EV-2, EV-4 | PLANNED |
| SEC-BKP-01 | NFR-SEC-006 | TH-23 | Keamanan backup | Should | Berkas backup uji | Periksa lokasi/izin/riwayat repo | Di luar repo; izin terbatas | EV-3 | PLANNED |

---

## 9. Event Reliability Tests

| ID | Req | Threat | Nama | Pri | Prasyarat | Langkah | Expected | Evid. | Status |
|---|---|---|---|---|---|---|---|---|---|
| REC-01 | NFR-REL-001, 006, FR-SYSO-005 | TH-09 | Broker mati lalu aktif | Must | `OPEN` | Lihat ATK-08 | Tidak ada suara hilang/ganda; outbox `PENDING`→`PUBLISHED`; receipt `RECORDED`; `verify` `VALID` | EV-2, EV-4 | PLANNED |
| REC-02 | NFR-REL-001 | TH-16 | `audit-service` mati lalu aktif | Must | Suara masuk saat Audit mati | Matikan/nyalakan Audit | Suara tetap diterima; antrean diproses setelah aktif; B = A tercapai | EV-2, EV-4 | PLANNED |
| REC-03 | NFR-REL-003 | TH-08 | Retry, DLQ, replay | Must | Consumer dibuat gagal | Gagal 4×; perbaiki; replay DLQ | Retry 5/30/120 s (PROPOSED) lalu `.dlq`; replay → efek sekali; R-09 | EV-2, EV-4 | PLANNED |
| REC-04 | NFR-REL-003 | TH-08 | Event duplikat/terlambat | Must | — | Lihat ATK-07; tunda event lalu tally | Tanpa efek ganda; tally sebelum event diproses → `RECONCILIATION_FAILED`, sesudah → `MATCH` | EV-2 | PLANNED |
| REC-05 | NFR-REL-006 | TH-23 | Backup dan restore | Should | Backup per DB | Restore semua DB; jalankan `verify` dan tally | `MATCH`; restore parsial → mismatch terdeteksi | EV-2 | PLANNED |
| REC-06 | NFR-SEC-003 | TH-22 | Redis mati | Should | Redis dihentikan | Panggil rute voting/login/baca | Perilaku sesuai OD-25 (usulan: gagal-tertutup rute sensitif); tidak ada suara ganda | EV-1 | PLANNED |

**Bukti yang dikumpulkan:** status antrean/DLQ (EV-4), query `COUNT` outbox/ballots/audit (EV-2), log run (EV-1).

---

## 10. Audit and Result Verification Tests

| Uji | ID | Expected |
|---|---|---|
| Audit chain valid | IT-AUD-03, UT-HASH-01 | `VALID`; hash deterministik |
| Satu catatan diubah | SEC-AUD-01, ATK-06 | `INVALID` di `sequence` terdampak |
| Urutan berubah | SEC-AUD-03 | `INVALID` |
| Catatan dihapus (DB uji) | SEC-AUD-02 | `INVALID` |
| Ekor dipotong | SEC-AUD-04 | `INVALID` terhadap checkpoint |
| Penghitungan sesuai suara sah | IT-RES-01, E2E-03 | Hitungan = hitung ulang independen |
| Jumlah tidak cocok | IT-RES-02, IT-RES-04 | `RECONCILIATION_FAILED`/`INTEGRITY_FAILED` |
| Penghitungan ulang | IT-RES-02 | Run baru; riwayat tersimpan |
| Finalisasi ditolak bila prasyarat belum | IT-RES-05, IT-RES-02 | `409` sesuai penyebab |

**Catatan:** keberhasilan mendeteksi manipulasi **bergantung pada rancangan hash, checkpoint, dan asumsi keamanan yang benar-benar diimplementasikan**. Uji ini tidak membuktikan ketahanan terhadap penyerang yang menguasai seluruh database **dan** kunci/checkpoint (`06_…` Bagian 11, 14).

---

## 11. End-to-End Scenarios

| ID | Req | Threat | Nama | Pri | Langkah | Expected | Evid. | Status |
|---|---|---|---|---|---|---|---|---|
| E2E-01 | FR-BALL-*, FR-UI-001 | TH-01 | Alur pemilih | Must | Login → ballot → vote → receipt `PENDING` → `RECORDED` | Selesai; receipt tanpa pilihan | EV-1, EV-5 | PLANNED |
| E2E-02 | FR-ELEC-*, FR-RSLT-*, FR-AUDT-* | TH-17, TH-19 | **Skenario utama (1–10)** | Must | 1 Admin menyiapkan pemilihan; 2 kandidat dan daftar pemilih; 3 schedule+open; 4 pemilih sah memberi suara; 5 percobaan suara ganda ditolak; 6 event diproses (receipt `RECORDED`, `A = B = V`); 7 `verify` audit `VALID`; 8 tally `MATCH`; 9 finalize; 10 Auditor memverifikasi proof/hasil tanpa melihat identitas/pilihan | Setiap langkah sesuai kontrak; `final_results` ada; `GET …/verify` `MATCH` | EV-1, EV-5 | PLANNED |
| E2E-03 | SM-04, NFR-REL-005 | TH-19 | Hasil sama dengan suara sah | Must | Gunakan data uji berhitungan diketahui | Bandingkan hasil final dengan hitungan manual dari data uji | Sama | EV-1, EV-2 | PLANNED |
| E2E-04 | FR-SYSO-005, FR-RSLT-005 | TH-09, TH-19 | Skenario kegagalan penting | Must | (a) matikan broker saat voting lalu tally segera; (b) rusak chain DB uji lalu finalize; (c) coba suara setelah close; (d) VOTER akses hasil sebelum final | (a) `RECONCILIATION_FAILED` lalu `MATCH` setelah pulih; (b) `AUDIT_VERIFICATION_FAILED`; (c) `ELECTION_NOT_OPEN`; (d) `RESULT_NOT_FINALIZED` | EV-1, EV-2 | PLANNED |

---

## 12. Acceptance Criteria

Kriteria penerimaan MVP. Status: **NOT VERIFIED** untuk semuanya; diubah menjadi `MET` hanya dengan bukti (Bagian 15).

| ID | Kriteria | Dibuktikan oleh | Status |
|---|---|---|---|
| AC-01 | Role dan permission ditegakkan backend: setiap endpoint sesuai matriks `05_…` Bagian 3 | API-RBAC-01, ATK-03, ATK-04 | NOT VERIFIED |
| AC-02 | Pemilih tidak memenuhi syarat ditolak (`VOTER_NOT_ELIGIBLE`) dan tidak mendapat ticket | IT-VOT-05, DB-03 | NOT VERIFIED |
| AC-03 | Satu kelayakan tidak menghasilkan lebih dari satu suara sah: `COUNT(ballots)≤1` per `(election_id, eligibility_ref)` | IT-BAL-02, DB-05, ATK-01 | NOT VERIFIED |
| AC-04 | Request paralel tidak melewati aturan one person, one vote (tanpa `5xx`) | CC-01, CC-02, ATK-02 | NOT VERIFIED |
| AC-05 | Pilihan suara tidak bocor ke receipt, audit, event, log, atau alert yang tidak memerlukannya | SEC-PRV-01..04, ATK-10, API-BAL-04 | NOT VERIFIED |
| AC-06 | Audit verification mendeteksi manipulasi yang diuji (ubah, hapus, sisip, susun ulang, potong ekor) | SEC-AUD-01..04, ATK-06 | NOT VERIFIED |
| AC-07 | Hasil dapat direkonsiliasi dengan suara sah (B = A = V, digest, commitment) dan sama dengan hitungan independen | IT-RES-01..05, E2E-03 | NOT VERIFIED |
| AC-08 | Duplicate event tidak menggandakan efek bisnis | ATK-07, IT-AUD-02, REC-04, CC-05 | NOT VERIFIED |
| AC-09 | Gangguan broker ditangani sesuai rancangan: suara tidak hilang/ganda; backlog pulih; R-06 muncul | ATK-08, REC-01..03 | NOT VERIFIED |
| AC-10 | Attack Lab dibatasi pada lingkungan pengujian dan election lab | SEC-LAB-01, SEC-CFG-03 | NOT VERIFIED |
| AC-11 | Dokumentasi setup dan test dapat diikuti anggota tim dari repository bersih | E2E-02 (dijalankan anggota lain), prosedur instalasi | NOT VERIFIED |
| AC-12 | Suara tidak diterima di luar `OPEN`/`end_at`; hasil final tidak dapat diubah lewat API | ATK-05, IT-BAL-06, ATK-04, IT-RES-03 | NOT VERIFIED |
| AC-13 | Setiap constraint DBC-01..15 ada dan diuji | DB-01..15, MIG-01..04 | NOT VERIFIED |

### DB dan Migration (pelengkap AC-13)

| ID | Req | Threat | Pengujian | Pri | Expected | Evid. | Status |
|---|---|---|---|---|---|---|---|
| DB-01 | NFR-SEC-009 | TH-10 | Email duplikat (beda huruf besar/kecil) di `users` | Must | `unique_violation`/CHECK gagal | EV-2 | PLANNED |
| DB-02 | FR-ELEC-004 | TH-14 | Duplikat `email_normalized`/`external_ref` per pemilihan | Must | Ditolak | EV-2 | PLANNED |
| DB-03 | BR-001 | TH-14 | Satu `user_id` mengikat dua `voters` pada pemilihan sama | Must | Ditolak (UNIQUE parsial) | EV-2 | PLANNED |
| DB-04 | BR-001 | TH-01 | Dua `voting_eligibility` untuk pemilih yang sama; `eligibility_ref` ganda; election tak cocok (FK komposit) | Must | Ditolak | EV-2 | PLANNED |
| DB-05 | BR-001 | TH-01, TH-02 | Dua `INSERT ballots` untuk `(election_id, eligibility_ref)` sama | Must | Kedua ditolak/satu saja; `23505` | EV-2 | PLANNED |
| DB-06 | FR-BALL-005 | TH-02 | Duplikat `(eligibility_ref, idempotency_key)` | Must | Ditolak | EV-2 | PLANNED |
| DB-07 | NFR-REL-003 | TH-08 | Duplikat `source_event_id`, `event_id`, `processed_events` | Must | Ditolak | EV-2 | PLANNED |
| DB-08 | FR-ELEC-003 | — | Kandidat duplikat nama/urutan; FK election tak ada | Must | Ditolak | EV-2 | PLANNED |
| DB-09 | BR-003 | TH-17 | Nilai status di luar enum; `start_at ≥ end_at` | Must | CHECK menolak | EV-2 | PLANNED |
| DB-10 | BR-009 | TH-05 | UPDATE/DELETE `ballots` (trigger + hak) | Must | Ditolak | EV-2 | PLANNED |
| DB-11 | FR-AUDT-002 | TH-06 | UPDATE/DELETE `audit_events` | Must | Ditolak | EV-2 | PLANNED |
| DB-12 | BR-009 | TH-05 | UPDATE/DELETE/duplikat `final_results` | Must | Ditolak | EV-2 | PLANNED |
| DB-13 | FR-RSLT-003 | — | Duplikat `(election_id, run_number)`, `(tally_run_id, candidate_id)` | Must | Ditolak | EV-2 | PLANNED |
| DB-14 | FR-SECM-003 | — | Dua alert aktif `dedupe_key` sama | Should | Ditolak; boleh setelah resolved | EV-2 | PLANNED |
| DB-15 | FR-AUDT-002 | TH-06 | Dua entri `(scope_id, sequence)` sama | Must | Ditolak | EV-2 | PLANNED |
| MIG-01 | NFR-MNT-003 | — | Upgrade dari DB kosong ke `head` (tiap layanan) | Must | Sukses | EV-1 | PLANNED |
| MIG-02 | NFR-MNT-003 | — | Model SQLAlchemy vs migration (tanpa drift) | Must | Diff kosong | EV-1 | PLANNED |
| MIG-03 | NFR-MNT-003 | — | Upgrade dari revisi sebelumnya dengan data seed | Should | Data utuh | EV-1, EV-2 | PLANNED |
| MIG-04 | NFR-MNT-003 | — | Downgrade satu langkah (dev) | Could | Sukses | EV-1 | PLANNED |

---

## 13. Test Data and Privacy

- **Data sintetis saja:** email `*@example.test`, nama dan `external_ref` fiktif (`NIM-0001`…), dibangkitkan oleh skrip seed deterministik; tidak ada data pribadi nyata, tidak ada data produksi.
- **Reset:** database uji dibuat ulang (drop/create + migrasi) di awal setiap suite; volume checkpoint dan antrean RabbitMQ dibersihkan.
- **Pemisahan lingkungan:** profil `test` memakai database, volume, dan secret terpisah dari demo; data election lab ditandai `is_attack_lab=true`.
- **Larangan:** tidak menggunakan data pribadi nyata tanpa dasar yang sah dan persetujuan; tidak menyalin data uji ke repo selain seed sintetis; tidak mengarahkan uji ke sistem pihak ketiga.
- **Artefak bukti** (log, dump query) dibersihkan dari secret/data sensitif sebelum disimpan atau dibagikan.

---

## 14. Defect Management

| Severity | Definisi | Contoh |
|---|---|---|
| S1 Kritis | Melanggar aturan inti atau kerahasiaan | Dua suara tersimpan; pilihan bocor di audit; hasil berubah lewat API |
| S2 Tinggi | Fitur utama gagal/akses salah | RBAC bocor; verifikasi audit tak mendeteksi manipulasi |
| S3 Sedang | Fitur sekunder gagal / workaround ada | Alert tidak muncul untuk satu aturan |
| S4 Rendah | Kosmetik/dokumentasi | Teks pesan error |

| Prioritas | Aturan |
|---|---|
| P0 | Selesai sebelum test berikutnya pada area itu; memblokir demo |
| P1 | Selesai sebelum demo |
| P2 | Dijadwalkan; boleh ditunda dengan persetujuan |

**Proses:** (1) pelapor mencatat ID defect, test ID terkait, langkah reproduksi, expected vs actual, bukti; (2) triage mingguan oleh tim (S1 segera); (3) penanggung jawab = pemilik komponen; (4) perbaikan lewat PR dengan test regresi; (5) *retest* oleh orang selain pengembang; status test kembali `PASSED` hanya setelah berjalan lagi dengan bukti. Defect S1/S2 tidak ditutup tanpa test regresi.

---

## 15. Test Reporting

Format ringkasan per run (**kosong; diisi hanya setelah test dijalankan**):

| Tanggal | Commit/versi | Lingkungan | Total test | Passed | Failed | Blocked | Not executed | Defect terbuka (S1/S2/S3/S4) | Risiko tersisa |
|---|---|---|---|---|---|---|---|---|---|
| — | — | — | *belum dijalankan* | — | — | — | — | — | — |

Tabel hasil per test: `Test ID | Status | Tanggal | Penjalan | Bukti (path/tautan) | Catatan`. Angka performa dicatat sebagai pengamatan (PERF) bersama konteks perangkat; tidak ada ambang wajib.

**Pengukuran performa (PERF, target PROPOSED):**

| ID | Req | Pengamatan | Target usulan |
|---|---|---|---|
| PERF-01 | NFR-PRF-001 | Latensi `POST /ballots` p95 dengan 50 paralel | ≤ 500 ms (PROPOSED) |
| PERF-02 | NFR-PRF-003 | Lag outbox→audit p95 | ≤ 10 s (PROPOSED) |
| PERF-03 | NFR-PRF-005 | Waktu `verify` untuk 10.000 entri | ≤ 60 s (PROPOSED) |
| PERF-04 | NFR-PRF-004 | Waktu tally 1.000 suara | ≤ 10 s (PROPOSED) |

---

## 16. Exit Criteria

Pengujian dianggap cukup untuk demonstrasi akademik bila:

1. Semua test **Must** berstatus `PASSED` dengan bukti, atau pengecualian dicatat di bawah dengan persetujuan.
2. AC-01..AC-13 berstatus `MET` dengan bukti.
3. Tidak ada defect S1 atau S2 terbuka.
4. Skenario Attack Lab ATK-01..10 dijalankan dan hasil aktualnya dicatat.
5. E2E-02 berhasil dijalankan oleh anggota selain pengembang utama dari repository bersih.
6. Laporan hasil (Bagian 15) terisi dan keterbatasan (anonimitas, hash chain, deteksi berbasis aturan) dinyatakan.

**Daftar pengecualian terbuka:** *(kosong; diisi saat pelaksanaan)*. Test Should/Could yang ditunda harus dicatat beserta alasan.

### Pengujian usability (UX)

| ID | Req | Pengujian | Pri | Expected | Evid. | Status |
|---|---|---|---|---|---|---|
| UX-01 | NFR-USA-001 | Pemilih sintetis menyelesaikan alur memilih tanpa bantuan | Should | Selesai ≤ 4 langkah utama (PROPOSED) | EV-5 | PLANNED |
| UX-02 | NFR-USA-002 | Validasi form dan pesan error | Should | Pesan Indonesia jelas; tanpa detail internal | EV-5 | PLANNED |
| UX-03 | NFR-USA-003 | Responsif ponsel/desktop | Should | Alur dapat dipakai pada kedua | EV-5 | PLANNED |
| UX-04 | NFR-USA-004 | Aksesibilitas dasar | Could | Label form, kontras, navigasi keyboard | EV-5 | PLANNED |

### Pengujian kontrak (CT)

| ID | Req | Pengujian | Pri | Expected | Evid. | Status |
|---|---|---|---|---|---|---|
| CT-01 | NFR-MNT-002 | Validasi respons/request terhadap OpenAPI | Must | Semua endpoint sesuai skema | EV-1 | PLANNED |
| CT-02 | NFR-MNT-002 | Consumer-driven (FE; Result→Ballot/Audit/Voter) | Should | Provider memenuhi harapan | EV-1 | PLANNED |
| CT-03 | NFR-MNT-002 | Kompatibilitas perubahan aditif | Should | Klien lama tidak rusak | EV-1 | PLANNED |
| CT-04 | NFR-MNT-002 | Negatif 401/403/404/409/422 per endpoint | Must | Kode dan skema error sesuai | EV-1 | PLANNED |
| CT-05 | NFR-MNT-002 | Sinkronisasi tipe FE dengan OpenAPI | Should | Tanpa selisih | EV-1 | PLANNED |
| API-VAL-01..04 | NFR-SEC-004 | UUID salah; field ekstra; body terlalu besar; `Idempotency-Key` hilang/format salah | Must | `422`/`413` sesuai kontrak | EV-1 | PLANNED |
| API-RL-01 | NFR-SEC-003 | Batas rate login/vote | Must | `429` + `Retry-After` | EV-1 | PLANNED |
| API-RL-02 | NFR-SEC-003 | Reset jendela batas | Should | Request diterima setelah jendela | EV-1 | PLANNED |
| UT-AUTH-01 | NFR-SEC-001 | Hash Argon2id: benar/salah; tanpa password di log/repr | Must | Sesuai | EV-1 | PLANNED |
| UT-TKT-01 | FR-ELIG-001 | Ticket valid/kedaluwarsa/salah tanda tangan/aud/typ/election | Must | Hanya yang valid lolos | EV-1 | PLANNED |
| UT-HASH-01 | FR-AUDT-002 | Canonical JSON dan `event_hash` deterministik | Must | Hash sama untuk urutan kunci berbeda | EV-1 | PLANNED |
| UT-HASH-02 | FR-AUDT-003 | Ubah satu field mengubah hash; verifier menemukan `sequence` pertama gagal | Must | Sesuai | EV-1 | PLANNED |
| UT-COMMIT-01 | FR-RSLT-002 | Commitment berubah bila `candidate_id` atau nonce berubah | Must | Sesuai | EV-1 | PLANNED |
| UT-LIFE-01 | BR-003 | Matriks transisi lifecycle | Must | Hanya transisi sah | EV-1 | PLANNED |
| UT-IDEM-01 | FR-BALL-005 | `request_hash` konsisten | Must | Sama untuk payload sama | EV-1 | PLANNED |
| UT-ELIG-01 | NFR-PRV-002 | `eligibility_ref` deterministik per `(election, voter)`; beda antar election/pepper | Must | Sesuai | EV-1 | PLANNED |
| UT-ANOM-01..10 | FR-SECM-002 | Satu uji per aturan R-01..R-10 pada data jendela sintetis | Must | Alert tepat di ambang, tidak di bawahnya | EV-1 | PLANNED |

(Test pada tabel kontrak/unit dikelompokkan di sini; semua memakai format dan aturan status Bagian 5.)

---

## 17. Rekonsiliasi dan Keputusan Terbuka

| ID | Catatan | Penyelesaian yang disarankan |
|---|---|---|
| C-TST-01 | `SECURITY_AND_TEST_PLAN.md` dan SRS Bagian 14 memakai rentang ID (mis. `API-AUTH-04..06`, `IT-VOT-02..03`) dengan makna yang tidak seragam | **ID di dokumen ini kanonik.** Perbarui referensi pada SRS 14 dan dokumen lama pada revisi berikutnya (pemetaan: SRS FR-AUTH-003 → API-AUTH-04; FR-AUTH-004 → API-AUTH-05; FR-AUTH-005 → API-AUTH-06; FR-ELEC-005..008 → IT-VOT-03) |
| C-TST-02 | `SECURITY_AND_TEST_PLAN.md` F.1 mendefinisikan AC-01..AC-10 dengan urutan berbeda | AC di Bagian 12 menggantikan; pemetaan: lama AC-01→AC-03, AC-02→AC-04 (+idempotency CC-02), AC-03→AC-06, AC-04→AC-07, AC-05→AC-01, AC-06→AC-09, AC-07→AC-08, AC-08→AC-05, AC-09→AC-12, AC-10→(IT-SEC-01..06, FR-SECM-002) |
| OD-19 | Versi dependency | Pin saat implementasi |
| OD-25 | Perilaku saat Redis mati | Lihat `06_…` Bagian 16 |
| OD-27 | Alat pengujian UI (manual berskrip vs Playwright) | Usulan: manual berskrip; Playwright bila waktu cukup |

Rujukan: `04_…` (DBC), `05_…` (kontrak), `06_…` (threat), `08_…` (jadwal pengujian per sprint).
