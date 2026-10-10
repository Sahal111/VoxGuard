# VoxGuard — Security and Test Plan

| Atribut | Nilai |
|---|---|
| Dokumen | `docs/SECURITY_AND_TEST_PLAN.md` |
| Versi | 0.1 — draft untuk review tim |
| Status | Rancangan. **Belum ada hasil pengujian aktual.** Semua "expected" adalah hasil yang diharapkan dari rancangan, bukan hasil eksperimen |
| Terkait | `PROJECT_BRIEF.md` (SM, FR), `ARCHITECTURE.md` (service, tabel, event), `API_CONTRACTS.md` (endpoint, error code) |

---

## A. Threat Model

### A.1 Aset

| ID | Aset | Alasan penting | Pemilik data |
|---|---|---|---|
| AS-01 | Integritas suara diterima (`ballots`) | Dasar hasil | ballot-service |
| AS-02 | Hak memilih satu-kali (`voting_eligibility`, `eligibility_ref`) | One person one vote | voter-service |
| AS-03 | Kerahasiaan hubungan identitas–pilihan | Vote secrecy | voter + ballot (gabungan) |
| AS-04 | Catatan audit dan hash chain | Bukti tamper-evident | audit-service |
| AS-05 | Hasil final (`final_results`) | Output resmi | result-service |
| AS-06 | Kredensial dan sesi (`users`, `refresh_sessions`) | Identitas akun | auth-service |
| AS-07 | Secret (JWT, ticket, pepper, receipt, internal key, checkpoint key) | Akar kepercayaan | environment |
| AS-08 | Ketersediaan voting selama election OPEN | Pemilu tidak dapat diulang mudah | seluruh sistem |
| AS-09 | Antrean pesan dan outbox | Konsistensi audit/hasil | semua service |

### A.2 Aktor

| Aktor | Kemampuan | Niat |
|---|---|---|
| Pemilih curang | Akun sah, klien HTTP bebas, dapat mengirim request paralel | Memilih lebih dari sekali |
| Pengguna terautentikasi berperan salah | Token VOTER/AUDITOR valid | Mengakses fungsi ADMIN/hasil |
| Penyerang eksternal | Tanpa akun, dapat membanjiri request | Brute force, DoS, forging token |
| Pencuri ticket/token | Mendapat ticket atau token pengguna lain | Memilih atas nama orang lain |
| Administrator aplikasi (ADMIN) | Akses API admin | Memanipulasi election/hasil lewat API |
| Operator/DBA | Akses langsung database dan host | Mengubah data, menautkan identitas–pilihan |
| Gangguan sistem | Broker/service mati, pesan duplikat/terlambat | Tidak berniat jahat tetapi merusak konsistensi |

### A.3 Trust boundaries

| ID | Batas | Catatan |
|---|---|---|
| TB-1 | Browser ↔ API Gateway | Tidak dipercaya; semua input divalidasi |
| TB-2 | Gateway ↔ service internal | Dipercaya terbatas: header identitas hanya sah dengan `X-Internal-Key` dan jaringan internal |
| TB-3 | Service ↔ RabbitMQ | Pesan dianggap tidak dijamin urutan/ketunggalan; skema divalidasi konsumen |
| TB-4 | Service ↔ PostgreSQL | Role per service dengan hak minimum |
| TB-5 | Operator ↔ host/database | **Di luar** perlindungan penuh (lihat TH-11) |
| TB-6 | Audit DB ↔ volume checkpoint | Anchor terpisah; tetap di mesin yang sama pada MVP |

### A.4 Entry points

`/api/v1/*` via Gateway (publik); endpoint internal `/internal/v1/*` (hanya jaringan Docker); RabbitMQ (queue); Redis; PostgreSQL; RabbitMQ management (loopback); endpoint uji `/internal/v1/test/*` (hanya `local`/`test`).

### A.5 Dampak

Skala dampak: **Tinggi** = suara/hasil salah atau kerahasiaan pilihan terbuka; **Sedang** = integritas bukti turun atau layanan terganggu; **Rendah** = informasi/operasional terbatas.

---

## B. Threat Matrix

| Threat ID | Ancaman | Aset terdampak | Dampak | Mitigasi (rancangan) | Bukti pengujian | Residual risk |
|---|---|---|---|---|---|---|
| TH-01 | Pemilih mengirim suara dua kali berurutan | AS-01, AS-02 | Tinggi | `UNIQUE(election_id, eligibility_ref)`; cek `VOTED` saat penerbitan ticket; idempotency | ATK-01, IT-BAL-02, API-BAL-03 | Pemilik hak yang sah dengan dua akun bila daftar pemilih salah (lihat TH-14) |
| TH-02 | Request voting bersamaan (race) | AS-01, AS-02 | Tinggi | Transaksi atomik + unique constraint; insert idempotency menyerialkan konflik | ATK-02, CC-01, CC-02, CC-03 | Bug implementasi transaksi; diuji berulang |
| TH-03 | Token tidak valid/kedaluwarsa/dipalsukan; ticket palsu | AS-06, AS-01 | Tinggi | Validasi JWT (exp, iss, aud, signature), denylist `jti`, ticket bertanda tangan terpisah | ATK-03, API-AUTH-04..06, UT-TKT-01 | Kebocoran `JWT_SECRET` (HS256 bersama, OD-04) |
| TH-04 | Penyalahgunaan hak akses (VOTER/AUDITOR memanggil fungsi ADMIN, akses hasil sementara) | AS-05, AS-02 | Tinggi | RBAC di gateway **dan** tiap service; matriks diuji otomatis | ATK-04, API-RBAC-01 | Salah konfigurasi role baru |
| TH-05 | Manipulasi data uji pada `ballots`/`tally`/`final_results` langsung di DB | AS-01, AS-05 | Tinggi | Role DB tanpa UPDATE/DELETE; trigger tolak ubah; `ballot_commitment` dan `result_hash` di audit; rekonsiliasi | SEC-DB-01..03, IT-RES-04, IT-RES-05 | Superuser DB dapat melepas trigger dan role (TH-11) |
| TH-06 | Manipulasi/penghapusan record audit | AS-04 | Tinggi | Hash chain per scope; checkpoint ber-HMAC di volume terpisah; verifikasi berkala | ATK-06, SEC-AUD-01..04 | Penyerang yang menguasai DB **dan** kunci checkpoint dapat membangun ulang rantai |
| TH-07 | Election ditutup tetapi masih menerima suara | AS-01 | Tinggi | Cek status sinkron ke Voter + `election_gates` + `end_at`; tally hanya menghitung `accepted_at ≤ closed_at` | ATK-05, IT-BAL-06 | Jendela sangat sempit saat close bersamaan dengan voting; ditangani rekonsiliasi |
| TH-08 | Event duplikat atau terlambat | AS-04, AS-05, AS-09 | Sedang | `processed_events`, unique alami, tally dari ekspor (bukan event) | ATK-07, REC-04, IT-AUD-02 | Event terlambat memperlambat status `RECORDED` |
| TH-09 | RabbitMQ downtime | AS-09, AS-08 | Sedang | Outbox, relay retry, konsumen idempotent, DLQ | ATK-08, REC-01..03 | Audit tertunda selama gangguan; signal best-effort hilang |
| TH-10 | Brute force login dan request berlebihan | AS-06, AS-08 | Sedang | Rate limit Redis; lockout; Argon2id | ATK-09, API-RL-01..02, API-AUTH-07 | DoS terdistribusi tidak ditangani pada MVP |
| TH-11 | Administrator dengan akses database/host | AS-01..AS-05 | Tinggi | Pemisahan DB dan role, checkpoint, jejak audit; **tidak** dapat dicegah penuh | SEC-DB-04 (dokumentasi batas, bukan penutupan) | **Diterima sebagai residual** pada prototipe |
| TH-12 | Kebocoran hubungan identitas–pilihan | AS-03 | Tinggi | Tanpa `user_id` di Ballot; ticket berpseudonim; gateway tanpa identitas untuk `POST /ballots`; audit/event tanpa `candidate_id`/identitas | ATK-10, SEC-PRV-01..04 | Kolusi/akses ke `voter_db` + `ballot_db` + korelasi waktu |
| TH-13 | Pencurian/penggunaan ulang vote ticket atau access token | AS-01, AS-06 | Sedang | TTL pendek; ticket terikat election; unique constraint membatasi satu suara | ATK-03 (varian), UT-TKT-01 | Pencuri yang mendahului pemilik sah dapat memakai hak itu |
| TH-14 | Impersonasi kelayakan: mendaftar dengan email milik orang lain | AS-02 | Tinggi | Daftar pemilih terimpor oleh ADMIN; klaim pertama mengikat `user_id`; (opsi OD-01 `voter_code`) | IT-VOT-05 | **Belum ditutup** pada MVP tanpa verifikasi email/`voter_code` |
| TH-15 | Kebocoran secret/data sensitif lewat log atau repo | AS-07, AS-03 | Tinggi | Filter log (daftar field terlarang), `.env` di `.gitignore`, pemindaian secret | SEC-PRV-02, SEC-CFG-01 | Kesalahan manusia |
| TH-16 | Ketidaktersediaan Voter/Audit saat voting | AS-08 | Sedang | Ballot fail-closed (503) pada ketergantungan status election; Audit tidak memblokir suara | ATK-08 (varian), IT-BAL-07 | Pemilih tidak dapat memilih saat Voter mati (pilihan keamanan) |

---

## C. Security Controls

Setiap kontrol: rancangan → keterbatasan → verifikasi. Semuanya adalah **rancangan**; status implementasi belum ada.

| Kontrol | Rancangan | Keterbatasan | Verifikasi |
|---|---|---|---|
| **Password hashing** | Argon2id (`argon2-cffi`), parameter dimulai dari default pustaka dan divalidasi pada mesin target; kebijakan panjang minimum; tidak ada logging password | Tidak melindungi password lemah/di-reuse; parameter harus dituning | UT-AUTH-01, API-AUTH-03 |
| **Token validation** | Access JWT HS256 (exp, iat, iss, aud, jti, role); refresh token acak 256-bit, hanya hash disimpan, rotasi + deteksi reuse; denylist `jti` di Redis saat logout; vote ticket dengan secret terpisah | HS256 berbagi secret di Gateway dan Auth (OD-04); access token tetap berlaku sampai `exp` bila denylist tidak terjangkau | API-AUTH-04..06, UT-TKT-01 |
| **RBAC** | Gateway memetakan rute→role; setiap service memeriksa `X-User-Role` lagi; matriks di API_CONTRACTS B.0 | Header identitas dipercaya dari Gateway; bocornya `INTERNAL_API_KEY` melemahkan | API-RBAC-01 (semua endpoint × semua role) |
| **Rate limiting** | Redis per IP/rute dan per email untuk login (nilai awal API_CONTRACTS A.9); header `Retry-After` | Target awal harus dikalibrasi; IP bersama (NAT kampus) dapat memicu false positive | API-RL-01, ATK-09 |
| **Atomic database transaction** | Penerimaan suara, outbox, dan idempotency dalam satu transaksi | Hanya menjamin atomisitas lokal; bukan antar-service | IT-BAL-05 |
| **Unique constraint** | `UNIQUE(election_id, eligibility_ref)` dan lainnya (ARCHITECTURE D) | Menjaga konsistensi selama `eligibility_ref` benar dan tabel tidak diubah dengan hak superuser | CC-01, IT-BAL-02 |
| **Idempotency key** | `UNIQUE(eligibility_ref, idempotency_key)` + `request_hash` | Kunci dibatasi per hak memilih; TTL record terbatas | CC-02, IT-BAL-03, IT-BAL-04 |
| **Input validation** | Pydantic `extra="forbid"`, UUID/format ketat, batas ukuran body dan panjang list, validasi di Gateway dan service | Tidak menutup logika bisnis salah | API-VAL-01..04, SEC-INJ-01 |
| **Tamper-evident hash chain** | Per scope; `event_hash` atas canonical JSON; verifikasi menghitung ulang seluruh rantai dan membandingkan dengan checkpoint | **Mendeteksi** perubahan; tidak mencegah. Tidak melindungi bila penyerang menguasai seluruh database **dan** kunci/checkpoint dan membangun ulang rantai dari titik perubahan | ATK-06, SEC-AUD-01..04, UT-HASH-01..02 |
| **Backup/checkpoint audit terpisah** | Checkpoint (`scope_id`, `sequence`, `event_hash`, `hmac`) ditulis ke volume `audit_checkpoints` saat `ElectionClosed`, `ResultFinalized`, dan periodik; hash close dapat dipublikasikan manual (OD-06) | Volume berada di host yang sama; HMAC memakai kunci di environment; checkpoint pasca-tamper tidak berguna jika tidak dipublikasikan tepat waktu | SEC-AUD-04 |
| **Data minimization** | Allowlist payload audit/event; tidak ada `candidate_id`/identitas di event; log menolak field terlarang; IP disimpan sebagai HMAC terpotong | Metadata (waktu, jumlah) tetap dapat dikorelasikan | SEC-PRV-01..03 |
| **Secure configuration** | Jaringan internal, hanya gateway dipublikasikan, management RabbitMQ di loopback, kontainer non-root, tanpa debug/reload di profil non-lokal, CORS ketat, header keamanan dasar, endpoint uji terkunci `APP_ENV`+`ATTACK_LAB_ENABLED` | HTTP tanpa TLS pada MVP lokal | SEC-CFG-01..03 |
| **Secrets management** | Secret dari environment/berkas `.env` lokal (tidak di repo), placeholder di `.env.example`, secret berbeda per fungsi, rotasi manual didokumentasikan, tidak ada secret di log/error | Tidak ada vault; rotasi `JWT_SECRET` membuat semua sesi invalid; kompromi host membuka seluruh secret | SEC-CFG-01 (pemindaian repo), SEC-PRV-02 |

---

## D. Attack Lab

### D.0 Aturan keamanan penggunaan (Rules of Engagement)

1. Hanya dijalankan pada **lingkungan lokal/uji milik tim** (`APP_ENV` ∈ {`local`,`test`}). **Dilarang** diarahkan ke sistem pemilu atau layanan pihak ketiga.
2. Fitur dikunci `ATTACK_LAB_ENABLED=true` dan hanya menyasar election dengan `is_attack_lab=true` yang dibuat khusus (data fiktif).
3. Endpoint uji `/internal/v1/test/*` tidak ada pada profil non-uji dan tidak terdaftar di OpenAPI publik.
4. Setiap eksekusi tercatat di `attack_runs`; hasil membandingkan *expected* vs *actual*. Kolom "Expected" di bawah adalah **harapan rancangan**.
5. Ambang alert pada dokumen ini adalah **target awal yang perlu dikalibrasi**; dalam Attack Lab ambang dapat diturunkan lewat konfigurasi.

### D.1 Aturan deteksi anomali (Security Service)

| Rule | Nama | Kondisi (target awal) | Severity |
|---|---|---|---|
| R-01 | DOUBLE_VOTE_ATTEMPTS | ≥ 3 `VoteRejected(VOTER_ALREADY_VOTED)` per `client_fingerprint` dalam 5 menit | MEDIUM |
| R-02 | VOTE_REJECT_BURST | ≥ 20 `VoteRejected` (alasan apa pun) per election dalam 1 menit | MEDIUM |
| R-03 | AUTH_FAILURE_BURST | ≥ 10 signal `LOGIN_FAILED`/`TOKEN_INVALID` per fingerprint dalam 5 menit | MEDIUM |
| R-04 | RATE_LIMIT_BURST | ≥ 5 signal `RATE_LIMIT_EXCEEDED` per fingerprint dalam 1 menit | LOW |
| R-05 | AUDIT_INTEGRITY_FAILED | Setiap signal `AUDIT_INTEGRITY_FAILED` | CRITICAL |
| R-06 | OUTBOX_BACKLOG | Umur outbox `PENDING` tertua di Ballot > 60 detik (polling 30 detik) | HIGH |
| R-07 | VOTE_AFTER_CLOSE | ≥ 3 `VoteRejected(ELECTION_NOT_OPEN)` per election dalam 5 menit | LOW |
| R-08 | FORBIDDEN_ACCESS_BURST | ≥ 5 signal `FORBIDDEN` per fingerprint dalam 5 menit | MEDIUM |
| R-09 | DLQ_NOT_EMPTY | Kedalaman `*.dlq` > 0 (polling) | HIGH |
| R-10 | RECONCILIATION_MISMATCH | `TallyCompleted` dengan `reconciliation_status != MATCH` | HIGH |

Alert dideduplikasi lewat `dedupe_key`. **False positive** mungkin terjadi (mis. pemilih salah ketik atau NAT bersama); alert adalah sinyal untuk ditinjau, bukan keputusan blokir.

### D.2 Skenario (ATK-01 … ATK-10)

#### ATK-01 — Double voting

| Field | Isi |
|---|---|
| Tujuan | Memastikan pemilih yang sama tidak bisa memberi suara kedua |
| Prasyarat | Election lab `OPEN`; satu pemilih terdaftar dengan akun VOTER; ticket diterbitkan |
| Langkah simulasi | (1) `POST /ballots` kandidat A, key K1 → diterima. (2) `POST /ballots` kandidat B, key K2, ticket sama atau baru |
| Endpoint | `GET /elections/{id}/ballot`, `POST /ballots` |
| Expected response | (1) `201` dengan receipt. (2) `409 VOTER_ALREADY_VOTED` |
| Expected database state | `ballots`: tepat 1 baris untuk `(election, eligibility_ref)`; `idempotency_records`: 1 baris (K1); `voting_eligibility.status=VOTED` setelah event diproses; penerbitan ticket baru setelah itu → `409 VOTER_ALREADY_VOTED` |
| Expected audit event | Tepat 1 entri `VoteAccepted` di chain; tidak ada entri untuk penolakan |
| Expected security alert | R-01 setelah ambang percobaan terlampaui (ambang lab diturunkan); satu `VoteRejected` per penolakan |
| Pass/fail criteria | **PASS** bila semua poin di atas terpenuhi. **FAIL** bila ada > 1 baris `ballots` atau percobaan 2 diterima |

#### ATK-02 — 50 concurrent voting requests

| Field | Isi |
|---|---|
| Tujuan | Membuktikan keamanan terhadap race pada hak memilih yang sama |
| Prasyarat | Election lab `OPEN`; satu pemilih; satu ticket; rate limit Gateway dikonfigurasi sesuai varian |
| Langkah simulasi | **Varian A (langsung ke Ballot, profil test):** 50 request `POST /ballots` paralel, 50 `Idempotency-Key` berbeda, kandidat acak. **Varian B (lewat Gateway):** sama, dengan rate limit aktif. **Varian C:** 50 request paralel dengan `Idempotency-Key` **sama** dan payload sama |
| Endpoint | `POST /ballots` |
| Expected response | A: tepat 1× `201`, 49× `409 VOTER_ALREADY_VOTED`, tanpa `5xx`. B: campuran `201`/`409`/`429`, tanpa `5xx`, tepat ≤ 1× `201`. C: 1× `201` + 49× `200` dengan `Idempotent-Replayed: true` dan `receipt_id` identik |
| Expected database state | `ballots`: tepat 1 baris; `outbox_events` `VoteAccepted`: tepat 1 |
| Expected audit event | Tepat 1 entri `VoteAccepted` |
| Expected security alert | A/B: R-01 dan/atau R-02 (bergantung ambang lab); B: R-04 bila dibatasi |
| Pass/fail criteria | **PASS** bila baris `ballots` = 1, event `VoteAccepted` = 1, dan tidak ada `5xx`. **FAIL** bila salah satu tidak terpenuhi. Angka latensi dicatat sebagai pengamatan, bukan kriteria lulus |

#### ATK-03 — Invalid or expired token

| Field | Isi |
|---|---|
| Tujuan | Menolak token akses/ticket yang rusak, kedaluwarsa, tanda tangan salah, atau sudah di-logout |
| Prasyarat | Akun VOTER uji; token valid untuk dasar |
| Langkah simulasi | (1) Tanpa header Authorization. (2) Token dengan tanda tangan diubah. (3) Token kedaluwarsa. (4) Token setelah `logout` (jti di denylist). (5) `vote_ticket` kedaluwarsa/diubah/untuk election lain. (6) ≥ 10 percobaan di atas dari fingerprint sama |
| Endpoint | `GET /auth/me`, `GET /elections/{id}/ballot`, `POST /ballots` |
| Expected response | (1)–(4): `401 UNAUTHORIZED`. (5): `403 VOTE_TICKET_INVALID` |
| Expected database state | Tidak ada baris baru di `ballots`/`idempotency_records` |
| Expected audit event | Tidak ada |
| Expected security alert | R-03 setelah ≥ 10 signal `TOKEN_INVALID`/`LOGIN_FAILED` |
| Pass/fail criteria | **PASS** bila semua ditolak dengan kode yang sesuai, tanpa efek data, dan R-03 muncul. **FAIL** bila ada request lolos |

#### ATK-04 — Unauthorized result modification

| Field | Isi |
|---|---|
| Tujuan | Memastikan hasil tidak bisa diubah oleh role/endpoint yang tidak berhak |
| Prasyarat | Election lab `FINALIZED` dengan `final_results`; token VOTER, AUDITOR, tanpa token |
| Langkah simulasi | (1) VOTER dan AUDITOR memanggil `POST /results/elections/{id}/tally` dan `/finalize`. (2) Tanpa token memanggil keduanya. (3) ADMIN memanggil `tally`/`finalize` pada election yang sudah FINALIZED. (4) Mencoba `PUT`/`PATCH`/`DELETE` ke `/results/elections/{id}` dan `/ballots/*` |
| Endpoint | `POST /results/elections/{id}/tally`, `POST /results/elections/{id}/finalize`, `GET /results/elections/{id}` |
| Expected response | (1) `403 FORBIDDEN`. (2) `401 UNAUTHORIZED`. (3) `409 ELECTION_INVALID_STATE`. (4) `404`/`405` (endpoint tidak ada) |
| Expected database state | `final_results` tidak berubah (`result_hash` sama); tidak ada `tally_runs` baru |
| Expected audit event | Tidak ada entri baru untuk upaya gagal (hanya audit event bisnis) |
| Expected security alert | R-08 setelah ≥ 5 signal `FORBIDDEN` |
| Pass/fail criteria | **PASS** bila hasil tetap identik dan semua upaya ditolak. **FAIL** bila hasil/tally berubah |

#### ATK-05 — Voting after election closure

| Field | Isi |
|---|---|
| Tujuan | Menolak suara setelah election `CLOSED` atau lewat `end_at` |
| Prasyarat | Election lab `OPEN`, ticket diterbitkan, lalu ADMIN menutup election; varian: `end_at` terlewat |
| Langkah simulasi | (1) Ticket valid dipakai `POST /ballots` setelah `close`. (2) Meminta ballot baru setelah `close`. (3) Dengan `end_at` terlewat tetapi belum `close` |
| Endpoint | `POST /elections/{id}/close`, `GET /elections/{id}/ballot`, `POST /ballots` |
| Expected response | `409 ELECTION_NOT_OPEN` untuk semua |
| Expected database state | Jumlah `ballots` tidak bertambah setelah `closed_at` |
| Expected audit event | `ElectionClosed` tercatat; tidak ada `VoteAccepted` baru |
| Expected security alert | R-07 setelah ≥ 3 percobaan |
| Pass/fail criteria | **PASS** bila tidak ada suara setelah penutupan dan R-07 muncul. **FAIL** bila ada suara `accepted_at > closed_at` diterima |

#### ATK-06 — Audit record tampering pada database uji

| Field | Isi |
|---|---|
| Tujuan | Memastikan perubahan data audit terdeteksi |
| Prasyarat | Election lab dengan ≥ 10 entri audit valid; `verify` awal = `VALID`; checkpoint ada. Hanya `audit_db` **uji** |
| Langkah simulasi | (1) Ubah `payload_public` satu entri via endpoint uji atau SQL superuser pada DB uji. (2) Hapus satu entri tengah. (3) Sisipkan entri palsu. (4) Potong ekor rantai (hapus entri terakhir). (5) Jalankan `GET /audit/elections/{id}/verify` setiap kali setelah memulihkan (`/test/restore`) |
| Endpoint | `GET /audit/elections/{id}/verify`, `GET /audit/elections/{id}/proof`, `POST /internal/v1/test/tamper`, `POST /internal/v1/test/restore` |
| Expected response | `200` dengan `status=INVALID`, `first_failure.sequence` menunjuk entri terdampak; kasus (4) `INVALID` karena ketidakcocokan dengan checkpoint; setelah restore `VALID` |
| Expected database state | `integrity_checks` memuat hasil `INVALID`; data hanya berubah oleh langkah tamper |
| Expected audit event | — (bila rantai dapat ditulis, entri alert tercatat di scope GLOBAL) |
| Expected security alert | R-05 `CRITICAL` |
| Pass/fail criteria | **PASS** bila keempat modifikasi terdeteksi dengan lokasi kegagalan yang benar. **FAIL** bila ada modifikasi tidak terdeteksi. *Catatan:* skenario ini tidak membuktikan ketahanan terhadap penyerang yang membangun ulang rantai **dan** checkpoint (lihat G) |

#### ATK-07 — Duplicate event delivery

| Field | Isi |
|---|---|
| Tujuan | Memastikan event duplikat tidak menggandakan efek bisnis |
| Prasyarat | Election lab dengan beberapa suara; akses publish ke RabbitMQ uji |
| Langkah simulasi | (1) Publish ulang event `VoteAccepted` yang sama (`event_id` sama) 5×. (2) Publish ulang `ResultFinalized` dan `ElectionClosed`. (3) Putar ulang pesan dari DLQ. (4) Jalankan tally sebelum dan sesudah duplikasi |
| Endpoint | (tidak ada; lewat broker). Verifikasi: `GET /audit/events`, `GET /results/elections/{id}`, `GET /security/metrics` |
| Expected response | `GET` mengembalikan data yang sama sebelum/sesudah |
| Expected database state | `audit_events` tidak bertambah; `voting_eligibility` tetap `VOTED` sekali; `tally_items` identik; `processed_events` mencatat event sekali |
| Expected audit event | Tidak ada entri tambahan |
| Expected security alert | Tidak ada alert wajib; metrik `duplicates_dropped_total` naik |
| Pass/fail criteria | **PASS** bila tidak ada efek ganda di Audit/Voter/Result. **FAIL** bila ada entri atau hitungan bertambah |

#### ATK-08 — RabbitMQ downtime dan recovery

| Field | Isi |
|---|---|
| Tujuan | Memastikan suara tidak hilang dan event dipulihkan tanpa efek ganda |
| Prasyarat | Election lab `OPEN`; baseline outbox kosong |
| Langkah simulasi | (1) Hentikan kontainer RabbitMQ. (2) Kirim N suara dari N pemilih berbeda. (3) Cek receipt (`audit_status`). (4) Tunggu > 60 s. (5) Jalankan kembali RabbitMQ. (6) Tunggu relay selesai. (7) Varian: matikan `audit-service` saja |
| Endpoint | `POST /ballots`, `GET /ballots/receipt/{id}`, `GET /security/alerts`, `GET /audit/elections/{id}/verify` |
| Expected response | Langkah 2: `201` untuk setiap suara sah. Langkah 3: `audit_status=PENDING` |
| Expected database state | Selama gangguan: `outbox_events` `PENDING` = N, `ballots` = N. Setelah pulih: semua `PUBLISHED`; `audit_events` memuat N entri `VoteAccepted` tepat sekali |
| Expected audit event | N entri `VoteAccepted`, urutan sesuai konsumsi; `verify` = `VALID` |
| Expected security alert | R-06 selama backlog > 60 s |
| Pass/fail criteria | **PASS** bila tidak ada suara hilang atau ganda, outbox kosong, receipt berubah menjadi `RECORDED`. **FAIL** bila ada selisih B ≠ A setelah pemulihan |

#### ATK-09 — Excessive request and rate limiting

| Field | Isi |
|---|---|
| Tujuan | Memastikan pembatasan request dan percobaan login berulang |
| Prasyarat | Konfigurasi rate limit lab; akun uji |
| Langkah simulasi | (1) > batas `POST /auth/login` per menit dari satu IP. (2) Login gagal berulang pada satu email hingga lockout. (3) Banjir `GET /elections` |
| Endpoint | `POST /auth/login`, `GET /elections` |
| Expected response | `429 RATE_LIMIT_EXCEEDED` dengan `Retry-After`; lockout → `401 UNAUTHORIZED` (atau `423 ACCOUNT_LOCKED`) sesuai API_CONTRACTS |
| Expected database state | `users.failed_login_count`/`locked_until` terisi; tidak ada data bisnis berubah |
| Expected audit event | Tidak ada |
| Expected security alert | R-04, R-03 |
| Pass/fail criteria | **PASS** bila request melebihi batas ditolak 429, lockout bekerja, dan alert muncul. **FAIL** bila request tak terbatas diproses |

#### ATK-10 — Percobaan mengakses data identitas dan pilihan suara

| Field | Isi |
|---|---|
| Tujuan | Memverifikasi bahwa API/audit publik tidak membocorkan identitas atau pilihan |
| Prasyarat | Election lab dengan suara dan audit; token VOTER, AUDITOR, ADMIN |
| Langkah simulasi | (1) Memeriksa seluruh response `GET /audit/events`, `/proof`, `GET /ballots/receipt/{id}`, `GET /results/...` dan pesan event di broker. (2) Mencoba endpoint tidak ada: `/ballots/{id}`, `/ballots?user_id=`, `/elections/{id}/votes`. (3) VOTER/AUDITOR mencoba endpoint internal lewat Gateway (`/internal/v1/...`). (4) Memindai log kontainer |
| Endpoint | Endpoint di atas |
| Expected response | (1) Tidak ada `user_id`, email, `eligibility_ref`, `candidate_id`, `ballot_nonce`, token. (2) `404`. (3) `404`/`403`; internal tidak dirutekan Gateway |
| Expected database state | Tidak berubah |
| Expected audit event | Tidak ada |
| Expected security alert | R-08 bila ≥ 5 percobaan `FORBIDDEN` |
| Pass/fail criteria | **PASS** bila pemindaian field terlarang kosong di semua response/event/log. **FAIL** bila ada satu field terlarang muncul |

---

## E. Test Strategy

| Jenis | Cakupan | Alat | Lingkungan |
|---|---|---|---|
| Unit test | Fungsi murni: hash, canonical JSON, ticket, lifecycle, aturan anomali | Pytest | Tanpa I/O |
| Integration test | Service + PostgreSQL + RabbitMQ (+ Redis) | Pytest, Docker Compose profil `test` | Lokal |
| API test | Kontrak HTTP, RBAC, validasi | Pytest + HTTPX | Gateway + service |
| End-to-end test | Alur lengkap lewat Gateway (opsional UI) | Pytest + HTTPX; Playwright (opsional) | Stack penuh |
| Concurrency test | Race pada voting, idempotency, close boundary | Pytest + `asyncio`/`httpx.AsyncClient` | Stack penuh |
| Security test | Tamper, privasi, konfigurasi, injeksi | Pytest, SQL langsung pada DB uji | Profil `test` |
| Recovery test | Matikan/hidupkan RabbitMQ/service, DLQ replay | Pytest + Docker CLI | Profil `test` |
| Performance test | Pengamatan latensi/throughput | Skrip Python/`httpx` (alat beban opsional) | Satu mesin |

### E.1 Daftar test case

**Unit**

| ID | Uji |
|---|---|
| UT-AUTH-01 | Hash Argon2id memverifikasi password benar dan menolak yang salah; tidak ada password di repr/log |
| UT-TKT-01 | Vote ticket: valid, kedaluwarsa, tanda tangan salah, `aud/typ` salah, `election_id` berbeda |
| UT-HASH-01 | Canonical JSON dan `event_hash` deterministik pada urutan kunci berbeda |
| UT-HASH-02 | Perubahan satu field mengubah `event_hash`; verifikasi menemukan `sequence` pertama yang gagal |
| UT-COMMIT-01 | `ballot_commitment` berubah bila `candidate_id` atau nonce berubah |
| UT-LIFE-01 | Matriks transisi lifecycle: hanya transisi sah yang lolos |
| UT-IDEM-01 | `request_hash` konsisten untuk payload sama |
| UT-ANOM-01..10 | Evaluasi R-01..R-10 pada data jendela waktu sintetis |
| UT-ELIG-01 | `eligibility_ref` deterministik per `(election, voter)` dan berbeda antar election |

**Integration**

| ID | Uji |
|---|---|
| IT-BAL-01 | Suara sah diterima; `ballots`, `idempotency_records`, `outbox_events` terisi dalam satu transaksi |
| IT-BAL-02 | Suara kedua dengan `eligibility_ref` sama → `VOTER_ALREADY_VOTED` |
| IT-BAL-03 | Replay `Idempotency-Key` sama → respons sama, tanpa baris baru |
| IT-BAL-04 | Key sama + payload beda → `IDEMPOTENCY_CONFLICT` |
| IT-BAL-05 | Kegagalan setelah insert `ballots` (disuntikkan) → rollback; tidak ada `ballots` tanpa `outbox_events` |
| IT-BAL-06 | Election tidak OPEN atau lewat `end_at` → `ELECTION_NOT_OPEN` |
| IT-BAL-07 | Voter Service mati → `SERVICE_UNAVAILABLE`, tidak ada suara tersimpan |
| IT-OUT-01 | Relay menerbitkan outbox `PENDING` dan menandai `PUBLISHED`; backoff saat gagal |
| IT-AUD-01 | Konsumsi event membuat entri chain dengan `prev_hash` benar dan proyeksi allowlist |
| IT-AUD-02 | Event duplikat tidak membuat entri baru |
| IT-VOT-01..04 | Lifecycle, guard `schedule`, pembekuan kandidat/pemilih, penerbitan ticket |
| IT-VOT-05 | Klaim kelayakan oleh akun dengan email tidak terdaftar → `VOTER_NOT_ELIGIBLE`; dokumentasikan celah TH-14 |
| IT-RES-01 | Tally cocok dengan hitung ulang independen |
| IT-RES-02 | B ≠ A atau V → `RECONCILIATION_FAILED`; finalisasi ditolak |
| IT-RES-03 | Finalisasi menghasilkan `final_results`; percobaan UPDATE/DELETE oleh role aplikasi gagal |
| IT-RES-04 | Perubahan `candidate_id` di `ballots` uji → `INTEGRITY_FAILED` |
| IT-RES-05 | Finalisasi ditolak `AUDIT_VERIFICATION_FAILED` bila chain tidak valid |
| IT-SEC-01..06 | R-01, R-02, R-03, R-04, R-06, R-10 memunculkan alert dan `SecurityAlertRaised` |
| IT-ARCH-01 | Pemindaian: tidak ada koneksi/kredensial lintas database; tiap role hanya mengakses DB sendiri |

**API / RBAC**

| ID | Uji |
|---|---|
| API-AUTH-01..07 | Register, login, refresh (rotasi), reuse refresh → revoke family, logout, `me`, lockout |
| API-BAL-01..04 | Ballot view, kirim suara, `VOTER_ALREADY_VOTED`, receipt (kode benar/salah) |
| API-RBAC-01 | Tabel parametrik **setiap endpoint × {tanpa token, VOTER, AUDITOR, ADMIN}** sesuai API_CONTRACTS B.0 |
| API-VAL-01..04 | UUID salah, field ekstra, body terlalu besar, `Idempotency-Key` hilang |
| API-RL-01..02 | Batas rate dan header `Retry-After` |

**E2E / Concurrency / Security / Recovery / Performance**

| ID | Uji |
|---|---|
| E2E-01 | Alur pemilih: login → ballot → vote → receipt `PENDING` → `RECORDED` |
| E2E-02 | Lifecycle penuh `DRAFT→…→FINALIZED` |
| E2E-03 | Hasil final = hitungan independen dari seluruh suara sah; `GET /results/…/verify` = sesuai |
| CC-01 | 50 request paralel, 50 key berbeda, satu hak → 1 suara |
| CC-02 | 50 request paralel, key sama → 1 suara + replay |
| CC-03 | Voting paralel saat `close` dipanggil → tidak ada suara dengan `accepted_at > closed_at` dihitung |
| SEC-AUD-01..04 | Ubah, hapus, sisipkan, potong ekor → terdeteksi |
| SEC-DB-01..04 | Role aplikasi tidak bisa UPDATE/DELETE `ballots`/`final_results`/`audit_events`; superuser dapat (didokumentasikan sebagai batas) |
| SEC-PRV-01..04 | Tidak ada `user_id`, email, `eligibility_ref`, `candidate_id`, nonce, token di audit/proof/receipt/log/event non-Voter |
| SEC-CFG-01..03 | Tidak ada secret di repo; port internal tidak terbuka; endpoint uji tertutup bila `ATTACK_LAB_ENABLED=false` |
| SEC-INJ-01 | Payload SQL/JSON aneh ditolak validasi |
| REC-01 | RabbitMQ mati→hidup (ATK-08) |
| REC-02 | `audit-service` mati→hidup |
| REC-03 | Replay DLQ tanpa efek ganda |
| REC-04 | Event duplikat (ATK-07) |
| PERF-01..04 | Latensi `POST /ballots` paralel, lag outbox→audit, waktu verifikasi 10.000 event, throughput tally — **hanya pengukuran** terhadap NFR-PRF target awal |

### E.2 Pemetaan SM → verifikasi

| SM | Metode verifikasi |
|---|---|
| SM-01 | ATK-01, IT-BAL-02, API-BAL-03 |
| SM-02 | ATK-02, CC-01, CC-02 |
| SM-03 | ATK-06, SEC-AUD-01..04 |
| SM-04 | E2E-03, IT-RES-01..05 |
| SM-05 | ATK-03, ATK-04, API-RBAC-01 |
| SM-06 | ATK-08, REC-01..04 |
| SM-07 | IT-SEC-01..06, ATK-01/02/05/09 |
| SM-08 | ATK-10, SEC-PRV-01..04 |

---

## F. Acceptance Criteria

### F.1 Kriteria objektif

| ID | Kriteria | Dibuktikan oleh |
|---|---|---|
| AC-01 | Maksimal satu suara diterima per hak memilih: untuk setiap `(election_id, eligibility_ref)`, `COUNT(ballots) ≤ 1` pada seluruh skenario | ATK-01, ATK-02, CC-01 |
| AC-02 | Pengiriman ulang request yang sama (key + payload sama) tidak menambah suara dan mengembalikan `receipt_id` yang sama | CC-02, IT-BAL-03 |
| AC-03 | Audit checker mendeteksi modifikasi, penghapusan, penyisipan, dan pemotongan record uji | ATK-06, SEC-AUD-01..04 |
| AC-04 | Hasil final = hitungan ulang independen dari seluruh `ballots` ACCEPTED dengan `accepted_at ≤ closed_at`; B = A = V; semua commitment cocok | E2E-03, IT-RES-01..05 |
| AC-05 | Request tanpa izin tidak dapat mengubah hasil; tidak ada endpoint ubah suara/hasil | ATK-04, API-RBAC-01 |
| AC-06 | Pesan tertunda dipulihkan tanpa duplikasi efek bisnis | ATK-08, REC-01..03 |
| AC-07 | Event duplikat tidak menggandakan hasil penghitungan (tally dihitung dari ekspor Ballot dan Audit/Voter dedup) | ATK-07, REC-04, IT-AUD-02 |
| AC-08 | Data publik (audit, proof, receipt, hasil) tidak membocorkan pilihan individual maupun identitas | ATK-10, SEC-PRV-01..04 |
| AC-09 | Suara tidak diterima di luar `OPEN`/`end_at` | ATK-05, IT-BAL-06 |
| AC-10 | Setiap rule R-01..R-10 yang diuji menghasilkan alert sesuai kondisi | IT-SEC-01..06 |

### F.2 Expected outcome vs hasil aktual

Dokumen ini hanya mendefinisikan **expected outcome**. Tidak ada angka performa atau hasil lulus/gagal yang boleh dicantumkan sebelum pengujian benar-benar dijalankan. Angka pada NFR-PRF adalah **target awal yang harus divalidasi**.

### F.3 Template pencatatan hasil eksperimen aktual (diisi saat pengujian)

| Tanggal | Test/ATK | Commit/versi | Lingkungan | Hasil aktual | Lulus? | Catatan/bukti (log, query) |
|---|---|---|---|---|---|---|
| — | — | — | — | *belum dijalankan* | — | — |

---

## G. Security Limitations

1. **Prototipe edukasi, belum tersertifikasi** untuk pemilu resmi dan belum diaudit pihak independen.
2. **Hash chain bukan jaminan absolut.** Ia mendeteksi perubahan terhadap rantai/checkpoint yang ada; tidak mencegah modifikasi dan tidak melindungi bila penyerang menguasai seluruh database, kunci checkpoint, dan dapat membangun ulang rantai, atau bila checkpoint tidak dipublikasikan di luar kendali penyerang. Kegagalan komponen audit tidak menghentikan penerimaan suara (pilihan ketersediaan).
3. **Pseudonimisasi bukan anonimitas sempurna.** Kolusi antara `voter_db` dan `ballot_db`, korelasi waktu/log, dan kebocoran `ELIGIBILITY_PEPPER` dapat mengungkap hubungan identitas–pilihan. Receipt tidak memuat pilihan sehingga pemilih **tidak** dapat membuktikan pilihannya kepada pihak lain — tetapi juga tidak dapat memverifikasi sendiri bahwa pilihannya dihitung sebagaimana diberikan.
4. **Deteksi anomali berbasis aturan** dapat menghasilkan false positive (mis. NAT bersama) dan false negative (di bawah ambang atau saat signal best-effort hilang). Ambang adalah target awal.
5. **Bukan end-to-end verifiable voting.** Tidak ada protokol kriptografi pemilu (blind signature, mixnet, homomorphic tally, zero-knowledge); verifikasi hasil bergantung pada kepercayaan pada Ballot/Audit/Result sebagai satu penyelenggara.
6. **Kelayakan memilih bergantung pada daftar impor ADMIN dan pencocokan email** (OD-01, TH-14). Tanpa verifikasi email atau `voter_code`, impersonasi mungkin.
7. **Ketergantungan HS256 bersama**, tanpa TLS pada MVP lokal, dan secret dalam environment — kompromi host membuka seluruh secret.
8. **Insider/administrator infrastruktur** dengan akses penuh tidak tercakup mitigasi (TH-11).
9. **Ketersediaan:** tidak ada HA; DoS terdistribusi di luar lingkup; Voter mati → voting berhenti (fail-closed).
10. Seluruh pengujian Attack Lab hanya pada lingkungan lokal/uji milik tim.
