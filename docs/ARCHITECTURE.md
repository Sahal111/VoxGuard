# VoxGuard — Architecture

| Atribut | Nilai |
|---|---|
| Dokumen | `docs/ARCHITECTURE.md` |
| Versi | 0.1 — draft untuk review tim |
| Status | Rancangan; belum diimplementasikan |
| Terkait | `PROJECT_BRIEF.md` (FR/NFR/SM), `SECURITY_AND_TEST_PLAN.md` (TH/ATK/test), `API_CONTRACTS.md` (endpoint, event payload) |

Nama baku: service `api-gateway`, `auth-service`, `voter-service`, `ballot-service`, `audit-service`, `result-service`, `security-service`; database `auth_db`, `voter_db`, `ballot_db`, `audit_db`, `result_db`, `security_db`; role `ADMIN`, `VOTER`, `AUDITOR`.

---

## A. Architecture Overview

**Mengapa microservices?** Tujuan proyek mencakup *mendemonstrasikan* penerapan microservices yang benar. Pemisahan juga memberi manfaat nyata bagi keamanan: data identitas (`auth_db`), hak memilih (`voter_db`), isi suara (`ballot_db`), audit (`audit_db`), dan hasil (`result_db`) berada di database dan role database yang berbeda sehingga kompromi satu komponen tidak otomatis membuka seluruh data.

**Mengapa hanya enam service + gateway?** Tim hanya 2–3 orang. Setiap service menambah biaya (migrasi, test, deployment, observability). Enam service dipilih karena masing-masing memiliki *data* dan *alasan berubah* yang berbeda; fungsi yang tidak punya data sendiri digabungkan (rate limiting ke gateway, scheduler ke voter-service pada ADD-01). Semua berbahasa Python/FastAPI, satu pustaka bersama non-domain (`voxguard_common`: format error, middleware request ID, envelope event, canonical JSON, util hash).

### Keputusan teknis kunci

| ID | Keputusan | Alasan singkat |
|---|---|---|
| KD-01 | Semua traffic eksternal lewat `api-gateway`; service internal tidak dipublikasikan ke host | Satu titik rate limit, validasi awal, request ID |
| KD-02 | Gateway memvalidasi JWT dan meneruskan klaim sebagai header terpercaya (`X-User-Id`, `X-User-Role`, `X-User-Email`) + `X-Internal-Key`; **setiap service tetap memeriksa role sendiri** | RBAC di backend, defense in depth |
| KD-03 | Untuk `POST /ballots` gateway **tidak** meneruskan `X-User-Id`/`X-User-Email` dan tidak mencatat user id | Ballot Service tidak pernah melihat identitas pada saat suara dikirim |
| KD-04 | Kelayakan memilih dibuktikan dengan **vote ticket** (JWT pendek) yang diterbitkan Voter Service dan memuat `eligibility_ref` pseudonim, bukan `user_id` | Menghubungkan kelayakan dan suara tanpa membawa identitas |
| KD-05 | Anti double-vote **berlapis**: ticket valid, gate election, `UNIQUE(election_id, eligibility_ref)`, idempotency record, dan penandaan `VOTED` di Voter | Unique constraint hanya satu kontrol |
| KD-06 | Transactional outbox di setiap service yang menerbitkan event bisnis | Event tidak hilang bila broker mati |
| KD-07 | Audit hash chain **per scope** (per election + satu scope GLOBAL) dengan `audit_chain_heads` dan single consumer | Urutan deterministik, mudah diverifikasi |
| KD-08 | `ballot_commitment` (hash dengan nonce) dicatat di audit; Result memverifikasinya | Mendeteksi perubahan `candidate_id` pada `ballots` tanpa membocorkan pilihan |
| KD-09 | Tally dihitung dari ekspor internal Ballot (bukan akumulasi event) + rekonsiliasi tiga arah | Event duplikat tidak dapat menggandakan hasil |
| KD-10 | Hasil final: tabel `final_results` append-only (tanpa hak UPDATE/DELETE) + `result_hash` dicatat di audit | Result integrity |
| KD-11 | Retry konsumen memakai antrean TTL bertahap; setelah batas, pesan ke DLQ | Tanpa plugin tambahan |
| KD-12 | Checkpoint audit ditulis ke volume terpisah (JSONL ber-HMAC) | Anchor di luar `audit_db` |

---

## B. Architecture Diagram

```mermaid
flowchart LR
    FE["React Frontend (Vite + Tailwind)"]
    GW["API Gateway :8000"]

    subgraph SERVICES["Backend services (FastAPI)"]
        AUTH["Auth Service :8001"]
        VOTER["Voter Service :8002"]
        BALLOT["Ballot Service :8003"]
        AUDIT["Audit Service :8004"]
        RESULT["Result Service :8005"]
        SEC["Security Service :8006"]
    end

    subgraph PG["PostgreSQL: satu instance, enam database terpisah"]
        DBAUTH[("auth_db")]
        DBVOTER[("voter_db")]
        DBBALLOT[("ballot_db")]
        DBAUDIT[("audit_db")]
        DBRESULT[("result_db")]
        DBSEC[("security_db")]
    end

    MQ[["RabbitMQ exchange voxguard.events + DLX"]]
    RD[("Redis: rate limit, denylist jti, cache kandidat")]
    CP[/"Volume checkpoint audit"/]

    FE -->|"HTTP JSON sinkron"| GW
    GW -->|"sinkron"| AUTH
    GW -->|"sinkron"| VOTER
    GW -->|"sinkron"| BALLOT
    GW -->|"sinkron"| AUDIT
    GW -->|"sinkron"| RESULT
    GW -->|"sinkron"| SEC
    GW -->|"sinkron: rate limit, denylist"| RD

    BALLOT -->|"sinkron internal: ballot-info, ticket"| VOTER
    RESULT -->|"sinkron internal: tally-export, summary"| BALLOT
    RESULT -->|"sinkron internal: summary, commitments, verify"| AUDIT
    RESULT -->|"sinkron internal: summary"| VOTER
    SEC -->|"sinkron internal: polling outbox stats"| BALLOT
    BALLOT -->|"cache kandidat"| RD

    AUTH --> DBAUTH
    VOTER --> DBVOTER
    BALLOT --> DBBALLOT
    AUDIT --> DBAUDIT
    RESULT --> DBRESULT
    SEC --> DBSEC
    AUDIT --> CP

    VOTER -.->|"async publish via outbox"| MQ
    BALLOT -.->|"async publish via outbox"| MQ
    AUDIT -.->|"async publish via outbox"| MQ
    RESULT -.->|"async publish via outbox"| MQ
    SEC -.->|"async publish via outbox"| MQ
    GW -.->|"async best-effort: security signal"| MQ
    AUTH -.->|"async best-effort: security signal"| MQ
    MQ -.->|"async consume"| BALLOT
    MQ -.->|"async consume"| VOTER
    MQ -.->|"async consume"| AUDIT
    MQ -.->|"async consume"| SEC
```

**Legenda.** Panah penuh (`-->`) = koneksi **sinkron** (HTTP/SQL/Redis). Panah putus-putus (`-.->`) = **asinkron** lewat RabbitMQ. Foreign key tidak dipakai lintas database; satu-satunya hubungan lintas service adalah HTTP internal dan event.

**Alur request eksternal:** Frontend → Gateway (rate limit, request ID, validasi JWT, role) → service pemilik → database miliknya.
**Alur event asinkron:** service menulis event ke tabel `outbox_events` dalam transaksi yang sama dengan perubahan data → relay publish ke RabbitMQ → konsumen memproses idempotent.

---

## C. Service Responsibility Matrix

### C.1 api-gateway (tanpa database; memakai Redis)

| Aspek | Isi |
|---|---|
| Tujuan | Pintu masuk tunggal, perlindungan awal |
| Tanggung jawab | Routing; validasi awal (content-type JSON, batas ukuran body, format UUID path, header `Idempotency-Key` pada `POST /ballots`); rate limiting (Redis); pembuatan `X-Request-ID` dan `X-Correlation-ID`; verifikasi JWT + cek denylist `jti`; penerusan header identitas; CORS; log akses tanpa body; emisi security signal best-effort |
| Batasan | Tidak menyimpan data bisnis; tidak mengambil keputusan otorisasi akhir (service memeriksa ulang); tidak mencatat body, token, atau user id untuk `POST /ballots` |
| Endpoint | Semua `/api/v1/*` (routing). Milik sendiri: `GET /health/live`, `GET /health/ready` |
| Database | Tidak ada. Redis: kunci `rl:*`, `deny:jti:*` |
| Event dipublikasikan | `SecuritySignalObserved` (best-effort, tanpa outbox) |
| Event dikonsumsi | — |
| Dependensi | Semua service (sinkron), Redis, RabbitMQ (publish signal) |

**Tabel routing** (urutan penting: aturan spesifik lebih dulu)

| Pola path | Service tujuan | Meneruskan identitas? |
|---|---|---|
| `/api/v1/auth/*` | auth-service | Ya (jika ada token) |
| `/api/v1/elections/{id}/ballot` | ballot-service | Ya (hanya untuk penerbitan ticket; tidak disimpan/dilog) |
| `/api/v1/elections*` (lainnya) | voter-service | Ya |
| `/api/v1/ballots` (POST) | ballot-service | **Tidak** (hanya `X-User-Role`) |
| `/api/v1/ballots/receipt/{id}` | ballot-service | Tidak |
| `/api/v1/audit/*` | audit-service | Ya |
| `/api/v1/results/*` | result-service | Ya |
| `/api/v1/security/*` | security-service | Ya |

### C.2 auth-service

| Aspek | Isi |
|---|---|
| Tujuan | Identitas akun dan sesi |
| Tanggung jawab | Register, login, refresh (rotasi + deteksi reuse), logout, `me`; Argon2id; penerbitan access token (JWT HS256, TTL 15 menit — usulan awal); lockout login; revokasi sesi; denylist `jti` ke Redis saat logout |
| Batasan | Tidak mengetahui election, hak memilih, atau suara |
| Endpoint | `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me` |
| Database | `auth_db` (`users`, `refresh_sessions`) |
| Event dipublikasikan | `SecuritySignalObserved` (`LOGIN_FAILED`, `ACCOUNT_LOCKED`; best-effort) |
| Event dikonsumsi | — |
| Dependensi | Redis, RabbitMQ (signal) |

### C.3 voter-service

| Aspek | Isi |
|---|---|
| Tujuan | Data pemilu, kelayakan pemilih, dan lifecycle |
| Tanggung jawab | CRUD terbatas election/kandidat/daftar pemilih (hanya saat DRAFT); transisi lifecycle; penerbitan vote ticket; penghitungan `eligibility_ref`; penandaan `VOTED` dari event; endpoint internal `ballot-info`, `ticket`, `summary`; menerapkan `FINALIZED` dari event |
| Batasan | Tidak menyimpan isi suara; tidak menghitung hasil; tidak menjadi sumber kebenaran "sudah memilih" (Ballot yang memutuskan; Voter hanya cermin eventual untuk penolakan dini dan statistik) |
| Endpoint publik | `POST /elections`, `GET /elections`, `GET /elections/{id}`, `POST /elections/{id}/candidates`, `POST /elections/{id}/voters/import`, `POST /elections/{id}/schedule` *(tambahan, diperlukan untuk transisi `DRAFT→SCHEDULED`)*, `POST /elections/{id}/open`, `POST /elections/{id}/close` |
| Endpoint internal | `GET /internal/v1/elections/{id}/ballot-info`, `POST /internal/v1/elections/{id}/eligibility/tickets`, `GET /internal/v1/elections/{id}/summary` |
| Database | `voter_db` (`elections`, `candidates`, `voters`, `voting_eligibility`, `outbox_events`, `processed_events`) |
| Event dipublikasikan | `ElectionOpened`, `ElectionClosed` |
| Event dikonsumsi | `VoteAccepted` (tandai `VOTED`), `ResultFinalized` (set `FINALIZED`) |
| Dependensi | RabbitMQ |

### C.4 ballot-service

| Aspek | Isi |
|---|---|
| Tujuan | Penerimaan suara yang aman dan idempotent |
| Tanggung jawab | Menyajikan ballot + meminta ticket ke Voter; validasi ticket; cek status election (gate lokal + sinkron ke Voter, fail-closed); transaksi penerimaan suara; idempotency; receipt; outbox; ekspor internal untuk tally; mencatat `audit_acks` |
| Batasan | **Tidak** menyimpan `user_id`/email; tidak menampilkan atau mengirim `candidate_id` per suara lewat event atau API publik; tidak menghitung hasil resmi; tidak ada endpoint ubah/hapus suara |
| Endpoint publik | `GET /elections/{id}/ballot`, `POST /ballots`, `GET /ballots/receipt/{id}` |
| Endpoint internal | `GET /internal/v1/elections/{id}/tally-export`, `GET /internal/v1/elections/{id}/summary`, `GET /internal/v1/outbox/stats` |
| Database | `ballot_db` (`ballots`, `idempotency_records`, `outbox_events`, `election_gates`, `audit_acks`, `processed_events`) |
| Event dipublikasikan | `VoteAccepted`, `VoteRejected` |
| Event dikonsumsi | `ElectionOpened`, `ElectionClosed` (gate), `AuditRecorded` (receipt audit status) |
| Dependensi | voter-service (sinkron), Redis (cache kandidat), RabbitMQ |

### C.5 audit-service

| Aspek | Isi |
|---|---|
| Tujuan | Catatan audit tamper-evident dan bukti publik yang aman |
| Tanggung jawab | Konsumsi event → proyeksi allowlist → append ke hash chain; verifikasi chain; proof; checkpoint ke volume; endpoint internal untuk Result; menerbitkan `AuditRecorded`; menerbitkan signal bila verifikasi gagal |
| Batasan | Tidak menerima identitas pemilih atau `candidate_id`; tidak ada endpoint edit/hapus record; tidak menafsirkan makna bisnis event |
| Endpoint publik | `GET /audit/events`, `GET /audit/elections/{id}/verify`, `GET /audit/elections/{id}/proof` |
| Endpoint internal | `GET /internal/v1/elections/{id}/summary`, `GET /internal/v1/elections/{id}/commitments`, `POST /internal/v1/elections/{id}/verify`, serta **khusus lokal/uji** `POST /internal/v1/test/tamper` dan `POST /internal/v1/test/restore` (butuh `APP_ENV` ∈ {local,test} dan `ATTACK_LAB_ENABLED=true`) |
| Database | `audit_db` (`audit_events`, `audit_chain_heads`, `audit_checkpoints`, `integrity_checks`, `outbox_events`, `processed_events`) |
| Event dipublikasikan | `AuditRecorded`, `SecuritySignalObserved` (`AUDIT_INTEGRITY_FAILED`, via outbox) |
| Event dikonsumsi | `ElectionOpened`, `ElectionClosed`, `VoteAccepted`, `TallyCompleted`, `ResultFinalized`, `SecurityAlertRaised` |
| Dependensi | RabbitMQ, volume checkpoint |

### C.6 result-service

| Aspek | Isi |
|---|---|
| Tujuan | Penghitungan, rekonsiliasi, finalisasi, verifikasi hasil |
| Tanggung jawab | Tally dari ekspor Ballot; rekonsiliasi tiga arah; verifikasi ballot commitment; verifikasi audit sebelum finalisasi; penyimpanan snapshot; finalisasi immutable; verifikasi hasil |
| Batasan | Tidak menerima suara; tidak mengubah `final_results`; tidak mengakses `ballot_db` langsung (hanya endpoint internal) |
| Endpoint publik | `POST /results/elections/{id}/tally`, `POST /results/elections/{id}/finalize`, `GET /results/elections/{id}`, `GET /results/elections/{id}/verify` |
| Database | `result_db` (`tally_runs`, `tally_items`, `final_results`, `outbox_events`) |
| Event dipublikasikan | `TallyCompleted`, `ResultFinalized` |
| Event dikonsumsi | — (MVP) |
| Dependensi | ballot-service, audit-service, voter-service (sinkron internal), RabbitMQ |

### C.7 security-service

| Aspek | Isi |
|---|---|
| Tujuan | Deteksi anomali berbasis aturan, alert, metrik, Attack Lab |
| Tanggung jawab | Menyimpan `security_events` dari event; evaluasi aturan R-01..R-10; polling statistik (outbox Ballot, kedalaman DLQ via RabbitMQ management API); alert; metrik; orkestrasi Attack Lab terbatas pada election `is_attack_lab=true` |
| Batasan | Tidak memblokir request (deteksi, bukan pencegahan); tidak menyimpan identitas pemilih atau `candidate_id`; Attack Lab nonaktif kecuali `ATTACK_LAB_ENABLED=true` dan `APP_ENV` ∈ {local,test} |
| Endpoint | `GET /security/alerts`, `POST /security/attacks/run`, `GET /security/attacks/{id}`, `GET /security/metrics` |
| Database | `security_db` (`security_events`, `anomaly_alerts`, `attack_runs`, `outbox_events`) |
| Event dipublikasikan | `SecurityAlertRaised` |
| Event dikonsumsi | `ElectionOpened`, `ElectionClosed`, `VoteAccepted`, `VoteRejected`, `AuditRecorded`, `TallyCompleted`, `SecuritySignalObserved` |
| Dependensi | RabbitMQ (+ management API), ballot-service (polling), gateway (target Attack Lab) |

---

## D. Database Ownership and Schema

**Aturan umum.** Satu instance PostgreSQL, enam database; masing-masing service memakai role database sendiri dan tidak punya hak ke database lain. **Tidak ada foreign key lintas database.** Referensi lintas service (mis. `election_id`, `candidate_id`, `user_id`) hanyalah UUID tanpa FK; konsistensinya dijaga oleh logika aplikasi dan event. ID utama memakai UUID (`gen_random_uuid()`), waktu memakai `timestamptz` (UTC).

### D.1 Enam hal yang dipisahkan

| Entitas | Service | Tabel | Berisi | Tidak boleh berisi |
|---|---|---|---|---|
| Identitas akun | auth | `users` | email, hash password, role | Hak memilih, pilihan |
| Hak/kelayakan memilih | voter | `voters`, `voting_eligibility` | daftar pemilih, `eligibility_ref`, status `VOTED` | Pilihan kandidat |
| Isi suara | ballot | `ballots` | `candidate_id`, `eligibility_ref`, `ballot_commitment`, nonce | `user_id`, email |
| Bukti penerimaan | ballot | `ballots.receipt_id`, `audit_acks` | receipt_id (kode diturunkan HMAC, tidak disimpan) | Pilihan |
| Catatan audit | audit | `audit_events` | event publik ter-allowlist, hash | identitas, `candidate_id`, `eligibility_ref` |
| Hasil penghitungan | result | `tally_*`, `final_results` | hitungan per kandidat, digest | per-suara identitas |

### D.2 auth_db

**`users`**

| Kolom | Tipe | Keterangan |
|---|---|---|
| `id` | UUID | **PK** |
| `email` | TEXT | **UNIQUE** (disimpan lowercase) |
| `display_name` | TEXT | NOT NULL |
| `password_hash` | TEXT | Argon2id; NOT NULL |
| `role` | TEXT | CHECK ∈ (`ADMIN`,`VOTER`,`AUDITOR`) |
| `is_active` | BOOLEAN | default true |
| `failed_login_count` | INT | default 0 |
| `locked_until` | TIMESTAMPTZ | nullable |
| `created_at`, `updated_at`, `last_login_at` | TIMESTAMPTZ | |

Index: `UNIQUE(email)`.

**`refresh_sessions`**

| Kolom | Tipe | Keterangan |
|---|---|---|
| `id` | UUID | **PK** |
| `user_id` | UUID | index; FK **lokal** ke `users.id` (satu database) |
| `family_id` | UUID | index; satu keluarga per login |
| `token_hash` | CHAR(64) | SHA-256 refresh token; **UNIQUE** |
| `issued_at`, `expires_at` | TIMESTAMPTZ | |
| `rotated_at`, `revoked_at` | TIMESTAMPTZ | nullable |
| `replaced_by` | UUID | nullable |
| `ip_hash` | CHAR(24) | HMAC IP terpotong (minimisasi) |

Index: `(user_id)`, `(family_id)`, `UNIQUE(token_hash)`. Pemakaian ulang refresh token yang sudah dirotasi → seluruh `family_id` direvokasi.

### D.3 voter_db

**`elections`**: `id` UUID **PK**; `title` TEXT; `description` TEXT; `status` TEXT CHECK ∈ (`DRAFT`,`SCHEDULED`,`OPEN`,`CLOSED`,`FINALIZED`); `start_at`, `end_at` TIMESTAMPTZ (CHECK `start_at < end_at`); `opened_at`, `closed_at`, `finalized_at` nullable; `is_attack_lab` BOOLEAN default false; `created_by` UUID (id user ADMIN, tanpa FK); `created_at`, `updated_at`; `version` INT (optimistic lock). Index: `(status)`, `(created_by)`.

**`candidates`**: `id` UUID **PK**; `election_id` UUID FK lokal; `name` TEXT; `description` TEXT; `ballot_order` INT. **UNIQUE** `(election_id, ballot_order)`, **UNIQUE** `(election_id, name)`. Index: `(election_id)`. Hanya dapat diubah saat `DRAFT`.

**`voters`**: `id` UUID **PK**; `election_id` UUID FK lokal; `email_normalized` TEXT; `external_ref` TEXT (mis. NIM fiktif pada data uji); `display_label` TEXT; `user_id` UUID nullable (terisi saat klaim pertama; tanpa FK lintas DB); `created_at`. **UNIQUE** `(election_id, email_normalized)`, **UNIQUE** `(election_id, external_ref)`; index `(election_id, user_id)`.

**`voting_eligibility`**: `id` UUID **PK**; `election_id` UUID; `voter_id` UUID FK lokal ke `voters`; `eligibility_ref` CHAR(64); `status` TEXT CHECK ∈ (`ELIGIBLE`,`TICKET_ISSUED`,`VOTED`,`REVOKED`); `ticket_issued_at`, `voted_marked_at` nullable; `created_at`. **UNIQUE** `(election_id, voter_id)`, **UNIQUE** `(election_id, eligibility_ref)`. Index `(election_id, status)`.

**`processed_events`**: `event_id` UUID, `consumer` TEXT, `processed_at` TIMESTAMPTZ; **PK** `(event_id, consumer)`.

**`outbox_events`**: struktur standar (D.8).

### D.4 ballot_db

**`ballots`** (append-only)

| Kolom | Tipe | Keterangan |
|---|---|---|
| `id` | UUID | **PK** |
| `election_id` | UUID | NOT NULL (tanpa FK) |
| `eligibility_ref` | CHAR(64) | pseudonim dari Voter |
| `candidate_id` | UUID | pilihan; **tidak** dikirim ke event/audit |
| `ballot_nonce` | CHAR(64) | hex 32 byte acak; internal |
| `ballot_commitment` | CHAR(64) | SHA-256 (lihat D.7) |
| `receipt_id` | UUID | **UNIQUE** |
| `status` | TEXT | CHECK = `ACCEPTED` |
| `accepted_at` | TIMESTAMPTZ | |
| `outbox_event_id` | UUID | id event `VoteAccepted` (penghubung receipt↔audit) |

Constraint: **`UNIQUE (election_id, eligibility_ref)`** (kontrol utama double vote). Index: `(election_id)`, `UNIQUE(receipt_id)`, `UNIQUE(outbox_event_id)`. Trigger `BEFORE UPDATE OR DELETE` menolak operasi; role `ballot_app` hanya memiliki `INSERT, SELECT`.

**`idempotency_records`**: `id` UUID **PK**; `election_id` UUID; `eligibility_ref` CHAR(64); `idempotency_key` TEXT (16–64 karakter `[A-Za-z0-9_-]`); `request_hash` CHAR(64) (SHA-256 canonical `{election_id, candidate_id}`); `response_snapshot` JSONB (`receipt_id`, `election_id`, `accepted_at`); `created_at`; `expires_at`. **UNIQUE** `(eligibility_ref, idempotency_key)`. Index `(expires_at)`. Catatan: record dibuat dan di-commit **atomik bersama** `ballots` sehingga tidak ada status `PROCESSING` yang terlihat.

**`election_gates`**: `election_id` UUID **PK**; `status` TEXT (`OPEN`/`CLOSED`); `closed_at` nullable; `updated_at`. Diisi dari `ElectionOpened/Closed`. Hanya mempercepat penolakan; keputusan akhir memakai cek sinkron ke Voter.

**`audit_acks`**: `source_event_id` UUID **PK** (= `outbox_event_id` suatu suara); `audit_sequence` BIGINT; `event_hash` CHAR(64); `recorded_at` TIMESTAMPTZ. Diisi dari `AuditRecorded` yang `source_event_type = VoteAccepted`.

**`processed_events`**: seperti D.3. **`outbox_events`**: D.8.

### D.5 audit_db

**`audit_events`**

| Kolom | Tipe | Keterangan |
|---|---|---|
| `id` | UUID | **PK** |
| `scope_id` | UUID | `election_id`, atau `00000000-0000-0000-0000-000000000000` untuk scope GLOBAL |
| `sequence` | BIGINT | mulai 1 per scope |
| `source_event_id` | UUID | **UNIQUE** (dedup) |
| `source_event_type` | TEXT | |
| `occurred_at` | TIMESTAMPTZ | dari event |
| `recorded_at` | TIMESTAMPTZ | |
| `correlation_id` | UUID | |
| `payload_public` | JSONB | hasil proyeksi allowlist |
| `prev_hash` | CHAR(64) | genesis = 64 karakter `0` |
| `event_hash` | CHAR(64) | lihat D.7 |

Constraint: **`UNIQUE (scope_id, sequence)`**, `UNIQUE (source_event_id)`. Index `(scope_id, sequence)`, `(source_event_type)`. Role `audit_app`: `INSERT, SELECT` saja.

**`audit_chain_heads`**: `scope_id` UUID **PK**; `last_sequence` BIGINT; `last_hash` CHAR(64); `updated_at`. Baris dikunci `SELECT … FOR UPDATE` saat append.

**`audit_checkpoints`**: `id` UUID **PK**; `scope_id`; `sequence` BIGINT; `event_hash` CHAR(64); `reason` TEXT (`ELECTION_CLOSED`,`RESULT_FINALIZED`,`PERIODIC`,`MANUAL`); `exported_path` TEXT; `hmac` CHAR(64); `created_at`. **UNIQUE** `(scope_id, sequence)`.

**`integrity_checks`**: `id` UUID **PK**; `scope_id`; `status` TEXT (`VALID`,`INVALID`); `events_checked` BIGINT; `head_sequence` BIGINT; `head_hash` CHAR(64); `first_failure_sequence` BIGINT nullable; `failure_reason` TEXT nullable; `checkpoint_compared` BOOLEAN; `checkpoint_matches` BOOLEAN nullable; `requested_by` UUID nullable; `created_at`. Index `(scope_id, created_at DESC)`.

**`processed_events`**, **`outbox_events`**: seperti sebelumnya.

### D.6 result_db dan security_db

**`tally_runs`**: `id` UUID **PK**; `election_id`; `run_number` INT; `status` TEXT ∈ (`RUNNING`,`COMPLETED`,`RECONCILIATION_FAILED`,`INTEGRITY_FAILED`,`FAILED`); `closed_at` TIMESTAMPTZ; `ballots_counted` INT; `ballot_set_digest` CHAR(64); `audit_vote_events` INT; `voter_participation` INT; `audit_head_sequence` BIGINT; `audit_head_hash` CHAR(64); `reconciliation_status` TEXT (`MATCH`/`MISMATCH`); `error_code` TEXT nullable; `started_by` UUID; `started_at`, `completed_at`. **UNIQUE** `(election_id, run_number)`. Index `(election_id, started_at DESC)`.

**`tally_items`**: `id` UUID **PK**; `tally_run_id` UUID FK lokal; `candidate_id` UUID; `candidate_name` TEXT (snapshot); `vote_count` INT. **UNIQUE** `(tally_run_id, candidate_id)`.

**`final_results`** (append-only): `id` UUID **PK**; `election_id` UUID **UNIQUE**; `tally_run_id` UUID **UNIQUE**; `result_hash` CHAR(64); `snapshot` JSONB (`items`, `total_ballots`, `ballot_set_digest`, `audit_head_hash`); `finalized_by` UUID; `finalized_at`. Role `result_app`: `INSERT, SELECT` pada tabel ini; trigger menolak UPDATE/DELETE.

**`security_events`**: `id` UUID **PK**; `event_id` UUID **UNIQUE** (dedup); `source_service` TEXT; `event_type` TEXT; `signal_type` TEXT nullable; `election_id` UUID nullable; `client_fingerprint` CHAR(24) nullable; `reason_code` TEXT nullable; `details` JSONB (allowlist; tanpa identitas/pilihan); `occurred_at`, `received_at`. Index `(event_type, occurred_at)`, `(client_fingerprint, occurred_at)`, `(election_id, occurred_at)`.

**`anomaly_alerts`**: `id` UUID **PK**; `rule_code` TEXT (`R-01`..`R-10`); `severity` TEXT (`LOW`,`MEDIUM`,`HIGH`,`CRITICAL`); `election_id` nullable; `dedupe_key` TEXT; `title` TEXT; `description` TEXT; `evidence` JSONB; `occurrence_count` INT; `first_seen_at`, `last_seen_at`; `resolved_at` nullable. **UNIQUE** `(dedupe_key)` untuk alert yang belum resolved (partial unique index `WHERE resolved_at IS NULL`). Index `(severity, last_seen_at DESC)`.

**`attack_runs`**: `id` UUID **PK**; `attack_code` TEXT (`ATK-01`..`ATK-10`); `status` TEXT ∈ (`QUEUED`,`RUNNING`,`PASSED`,`FAILED`,`ERROR`); `election_id` UUID (election lab); `parameters` JSONB; `result` JSONB (langkah, expected vs actual, bukti); `triggered_by` UUID; `started_at`, `finished_at`, `created_at`. Index `(attack_code, created_at DESC)`.

### D.7 Pseudonim, commitment, dan hash chain

**`eligibility_ref`** = `HMAC-SHA256(key=ELIGIBILITY_PEPPER, msg="voxguard:elig:v1|" + election_id + "|" + voter_id)` dalam hex. `ELIGIBILITY_PEPPER` hanya dimiliki voter-service. `eligibility_ref` berbeda per election sehingga tidak dapat dipakai menautkan suara lintas election.

**`ballot_commitment`** = `SHA-256("voxguard:ballot:v1|" + election_id + "|" + ballot_id + "|" + candidate_id + "|" + ballot_nonce)` (hex). Nonce 256-bit membuat commitment tidak dapat di-brute-force walau himpunan kandidat kecil. Commitment masuk ke `VoteAccepted` dan audit; nonce tidak pernah keluar dari `ballot_db` kecuali lewat ekspor internal ke Result.

**`event_hash`** = `SHA-256(canonical_json({scope_id, sequence, source_event_id, source_event_type, occurred_at, correlation_id, payload_public, prev_hash}))`. *Canonical JSON*: kunci terurut, tanpa spasi (`separators=(",",":")`), UTF-8, timestamp `YYYY-MM-DDTHH:MM:SS.ffffffZ`. Implementasi tunggal di `voxguard_common` agar identik di Audit dan verifier.

### D.8 Struktur standar `outbox_events`

Dimiliki terpisah oleh voter, ballot, audit, result, security (satu tabel per database).

| Kolom | Tipe | Keterangan |
|---|---|---|
| `id` | UUID | **PK** = `event_id` |
| `event_type` | TEXT | mis. `VoteAccepted` |
| `routing_key` | TEXT | mis. `vote.accepted` |
| `schema_version` | TEXT | default `1.0` |
| `correlation_id` | UUID | |
| `payload` | JSONB | sesuai kontrak (API_CONTRACTS E) |
| `status` | TEXT | `PENDING`/`PUBLISHED`/`FAILED` |
| `attempts` | INT | default 0 |
| `next_attempt_at` | TIMESTAMPTZ | default now() |
| `created_at`, `published_at` | TIMESTAMPTZ | |
| `last_error` | TEXT | tanpa data sensitif |

Index: `(status, next_attempt_at)`, `(created_at)`. Relay: `SELECT … WHERE status='PENDING' AND next_attempt_at <= now() ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 50`, publish dengan *publisher confirms*, lalu tandai `PUBLISHED`.

### D.9 Kelayakan, konsumsi hak memilih, dan keamanan terhadap request paralel

`UNIQUE(election_id, eligibility_ref)` hanyalah satu kontrol. Rancangan lengkapnya:

1. **Memperoleh otorisasi kelayakan yang valid.** `GET /elections/{id}/ballot` → Ballot Service memanggil `POST /internal/v1/elections/{id}/eligibility/tickets` di Voter Service (dengan `user_id`/`email` dari Gateway). Voter memeriksa: baris `voters` cocok (email ter-normalisasi atau `user_id` yang sudah terikat), status election `OPEN` dan `now ≤ end_at`, `voting_eligibility.status` bukan `VOTED`/`REVOKED`. Bila lolos, Voter menandai `TICKET_ISSUED` dan menerbitkan **vote ticket** (JWT HS256 ditandatangani `VOTE_TICKET_SECRET`, dibagi hanya oleh Voter dan Ballot) dengan klaim `iss=voxguard-voter`, `aud=voxguard-ballot`, `typ=vote-ticket`, `election_id`, `eligibility_ref`, `jti`, `iat`, `exp` (TTL usulan awal 10 menit). Ticket **tidak** memuat `user_id` atau email. Ticket boleh diminta ulang (hak sama, `eligibility_ref` sama); ini aman karena pembatas akhir adalah kontrol 3–4.
2. **Validasi saat suara dikirim.** Ballot memverifikasi tanda tangan, `exp`, `aud`, `typ`, dan `election_id` = body; mengecek `election_gates`; memanggil `ballot-info` (status tidak di-cache; fail-closed 503 jika Voter tidak tersedia); memastikan `candidate_id` ada pada election.
3. **Konsumsi hak memilih atomik** di `ballot_db` dalam satu transaksi (algoritma di bawah) dengan `UNIQUE(election_id, eligibility_ref)` sebagai penjaga akhir; PostgreSQL menyerialkan insert unik yang berkonflik sehingga hanya satu transaksi yang commit.
4. **Idempotency** `UNIQUE(eligibility_ref, idempotency_key)` untuk retry.
5. **Cermin di Voter.** `VoteAccepted` → Voter menandai `VOTED` (eventual) untuk penolakan dini dan statistik partisipasi; *bukan* penjaga utama.

**Algoritma transaksi `POST /ballots`** (isolation default `READ COMMITTED` cukup karena bergantung pada unique constraint):

```text
BEGIN
 1. INSERT INTO idempotency_records(...) ON CONFLICT (eligibility_ref, idempotency_key) DO NOTHING RETURNING id
    - Jika konflik dengan transaksi lain yang belum commit, INSERT menunggu hingga transaksi itu commit/rollback.
    - Jika 0 baris: SELECT record. request_hash sama -> kembalikan response_snapshot (200, Idempotent-Replayed: true).
                                   request_hash beda -> ROLLBACK, 409 IDEMPOTENCY_CONFLICT.
 2. INSERT INTO ballots(...)  -- pelanggaran UNIQUE(election_id, eligibility_ref) -> ROLLBACK, 409 VOTER_ALREADY_VOTED
 3. INSERT INTO outbox_events(VoteAccepted)   -- dalam transaksi yang sama
 4. UPDATE idempotency_records SET response_snapshot = ...
COMMIT
```

`VoteRejected` ditulis ke outbox pada transaksi terpisah yang singkat (alasan saja; tanpa identitas/pilihan). Kegagalan setelah COMMIT (mis. respons hilang di jaringan) aman: klien mengulang dengan `Idempotency-Key` sama dan menerima hasil yang sama.

### D.10 Batas privasi rancangan pseudonim

- Ballot tidak menyimpan `user_id`, dan `POST /ballots` datang tanpa header identitas. Namun **Voter Service** mengetahui `voter → eligibility_ref`, dan **Ballot Service** mengetahui `eligibility_ref → candidate_id`. Pihak yang dapat membaca **kedua** database (mis. administrator server) dapat menautkan identitas ke pilihan. Pemisahan database dan role hanya mempersulit, tidak meniadakan.
- Korelasi waktu: `ticket_issued_at` (Voter), `accepted_at` (Ballot), dan log akses Gateway dapat dikorelasikan. Mitigasi sebagian: Ballot tidak mencatat identitas; Gateway tidak mencatat user id untuk `POST /ballots`; keterbatasan tetap ada (lihat TH-12).
- Ballot Service sempat menerima `X-User-Id` pada `GET …/ballot` hanya untuk diteruskan ke Voter dan tidak menyimpannya.
- **Pseudonimisasi saja bukan anonimitas sempurna.** Untuk jaminan lebih kuat dibutuhkan protokol kriptografi pemilu (mis. blind signature) yang tidak termasuk MVP.

---

## E. Core Data Flows

### E.1 Login dan verifikasi pemilih

```mermaid
sequenceDiagram
    autonumber
    actor U as Pemilih
    participant FE as Frontend
    participant GW as API Gateway
    participant AU as Auth Service
    participant BA as Ballot Service
    participant VO as Voter Service
    participant RD as Redis

    U->>FE: Isi email dan password
    FE->>GW: POST /api/v1/auth/login
    GW->>RD: Cek rate limit per IP dan email
    GW->>AU: Teruskan dengan X-Request-ID
    AU->>AU: Cek lockout lalu verifikasi Argon2id
    alt kredensial salah
        AU-->>GW: 401 UNAUTHORIZED
        GW-->>FE: 401
    else berhasil
        AU-->>GW: 200 access_token dan refresh_token
        GW-->>FE: 200
    end
    FE->>GW: GET /api/v1/elections/ID/ballot dengan Bearer token
    GW->>RD: Cek denylist jti
    GW->>GW: Verifikasi JWT dan role VOTER
    GW->>BA: Teruskan dengan X-User-Id dan X-User-Email
    BA->>VO: POST internal eligibility tickets
    VO->>VO: Cocokkan voters, cek status OPEN, cek belum VOTED
    alt tidak terdaftar
        VO-->>BA: 403 VOTER_NOT_ELIGIBLE
        BA-->>FE: 403 VOTER_NOT_ELIGIBLE
    else sudah memilih
        VO-->>BA: 409 VOTER_ALREADY_VOTED
        BA-->>FE: 409 VOTER_ALREADY_VOTED
    else layak
        VO-->>BA: vote_ticket dengan eligibility_ref
        BA-->>FE: 200 kandidat dan vote_ticket
    end
```

### E.2 Pengiriman suara

```mermaid
sequenceDiagram
    autonumber
    actor U as Pemilih
    participant FE as Frontend
    participant GW as API Gateway
    participant BA as Ballot Service
    participant VO as Voter Service
    participant DB as ballot_db

    U->>FE: Pilih kandidat lalu konfirmasi
    FE->>GW: POST /api/v1/ballots dengan Idempotency-Key
    GW->>GW: Validasi JWT, role VOTER, rate limit, header wajib
    GW->>BA: Teruskan tanpa X-User-Id dan X-User-Email
    BA->>BA: Verifikasi vote_ticket dan cek election_gates
    BA->>VO: GET internal ballot-info
    alt Voter tidak tersedia
        BA-->>FE: 503 SERVICE_UNAVAILABLE dan fail-closed
    else election tidak menerima suara
        BA-->>FE: 409 ELECTION_NOT_OPEN
    else kandidat tidak valid
        BA-->>FE: 422 VALIDATION_ERROR
    else lanjut ke transaksi
        BA->>DB: BEGIN
        BA->>DB: INSERT idempotency_records ON CONFLICT DO NOTHING
        alt key sama dan request_hash sama
            BA-->>FE: 200 response tersimpan dengan Idempotent-Replayed true
        else key sama tetapi request_hash beda
            BA-->>FE: 409 IDEMPOTENCY_CONFLICT
        else record baru
            BA->>DB: INSERT ballots
            alt pelanggaran UNIQUE election_id dan eligibility_ref
                BA->>DB: ROLLBACK
                BA-->>FE: 409 VOTER_ALREADY_VOTED
            else berhasil
                BA->>DB: INSERT outbox_events VoteAccepted
                BA->>DB: UPDATE idempotency_records response_snapshot
                BA->>DB: COMMIT
                BA-->>FE: 201 receipt_id dan receipt_code dengan audit_status PENDING
            end
        end
    end
```

### E.3 Pencatatan audit dan transactional outbox

```mermaid
sequenceDiagram
    autonumber
    participant BA as Ballot Service
    participant OB as outbox_events
    participant RL as Outbox Relay
    participant MQ as RabbitMQ
    participant AUD as Audit Service
    participant AD as audit_db
    participant CP as Volume checkpoint

    BA->>OB: INSERT VoteAccepted dalam transaksi suara
    loop setiap 1 detik
        RL->>OB: SELECT PENDING FOR UPDATE SKIP LOCKED
        RL->>MQ: Publish routing key vote.accepted dengan confirm
        MQ-->>RL: ack
        RL->>OB: UPDATE status PUBLISHED
    end
    MQ->>AUD: Deliver ke audit.q.events
    AUD->>AD: Cek processed_events untuk event_id
    alt sudah diproses
        AUD->>MQ: ack tanpa efek bisnis baru
    else baru
        AUD->>AUD: Proyeksi allowlist payload_public
        AUD->>AD: BEGIN lalu lock audit_chain_heads FOR UPDATE
        AUD->>AD: Hitung event_hash lalu INSERT audit_events
        AUD->>AD: UPDATE chain head, INSERT processed_events, INSERT outbox AuditRecorded
        AUD->>AD: COMMIT
        AUD->>CP: Tulis checkpoint bila syarat terpenuhi
        AUD->>MQ: ack
    end
    MQ->>BA: AuditRecorded ke ballot.q.audit
    BA->>BA: INSERT audit_acks sehingga receipt audit_status menjadi RECORDED
```

### E.4 Penghitungan dan finalisasi hasil

```mermaid
sequenceDiagram
    autonumber
    actor A as Admin
    participant GW as API Gateway
    participant RS as Result Service
    participant VO as Voter Service
    participant BA as Ballot Service
    participant AUD as Audit Service
    participant RD as result_db
    participant MQ as RabbitMQ

    A->>GW: POST /api/v1/results/elections/ID/tally
    GW->>RS: Teruskan setelah cek role ADMIN
    RS->>VO: GET internal summary
    alt election bukan CLOSED
        RS-->>A: 409 ELECTION_INVALID_STATE karena status bukan CLOSED
    else CLOSED
        RS->>BA: GET internal tally-export dan summary
        RS->>AUD: GET internal commitments dan summary
        RS->>RS: Hitung ulang per kandidat dan ballot_set_digest
        RS->>RS: Cocokkan commitment tiap suara
        RS->>RS: Rekonsiliasi B sama dengan A sama dengan V
        RS->>RD: INSERT tally_runs dan tally_items
        RS->>RD: INSERT outbox TallyCompleted
        RS-->>A: 201 tally_run dengan status
    end
    A->>GW: POST /api/v1/results/elections/ID/finalize
    GW->>RS: Teruskan setelah cek role ADMIN
    RS->>RS: Syarat tally_run COMPLETED dan MATCH
    RS->>AUD: POST internal verify
    alt audit INVALID
        RS-->>A: 409 AUDIT_VERIFICATION_FAILED
    else audit VALID
        RS->>RD: INSERT final_results dan outbox ResultFinalized
        RS-->>A: 200 hasil final dengan result_hash
        RS->>MQ: ResultFinalized via relay
        MQ->>VO: Set election FINALIZED
        MQ->>AUD: Catat result_hash di chain
    end
```

### E.5 Pemulihan event setelah kegagalan broker

```mermaid
sequenceDiagram
    autonumber
    participant BA as Ballot Service
    participant OB as outbox_events
    participant RL as Outbox Relay
    participant MQ as RabbitMQ
    participant AUD as Audit Service
    participant SE as Security Service

    Note over MQ: RabbitMQ mati
    BA->>OB: Suara tetap diterima dan outbox PENDING bertambah
    RL->>MQ: Publish gagal
    RL->>OB: attempts naik dan next_attempt_at diundur dengan backoff
    SE->>BA: Polling internal outbox stats
    SE->>SE: Umur PENDING tertua melewati ambang lalu alert R-06
    Note over MQ: RabbitMQ aktif kembali
    RL->>MQ: Reconnect lalu publish berurutan created_at dengan confirm
    MQ->>AUD: Deliver pesan tertunda
    AUD->>AUD: Dedup lewat processed_events
    AUD->>MQ: AuditRecorded
    MQ->>BA: AuditRecorded memperbarui audit_acks
    RL->>OB: Backlog PENDING menjadi nol
    SE->>BA: Polling berikutnya dan alert R-06 dapat ditandai resolved
```

### E.6 Simulasi serangan dan penanganan alert

```mermaid
sequenceDiagram
    autonumber
    actor A as Admin
    participant GW as API Gateway
    participant SE as Security Service
    participant TG as Target service pada election lab
    participant MQ as RabbitMQ
    participant AUD as Audit Service

    A->>GW: POST /api/v1/security/attacks/run
    GW->>SE: Teruskan setelah cek role ADMIN
    alt Attack Lab nonaktif atau bukan lingkungan lokal
        SE-->>A: 403 FORBIDDEN
    else aktif
        SE->>SE: INSERT attack_runs QUEUED lalu pastikan election is_attack_lab
        SE-->>A: 202 attack_run id
        SE->>TG: Jalankan langkah simulasi via Gateway atau jalur uji
        TG-->>SE: Response aktual
        TG-->>MQ: Event VoteRejected atau SecuritySignalObserved
        MQ->>SE: Consume ke security.q.events
        SE->>SE: Evaluasi aturan R-xx
        SE->>SE: INSERT anomaly_alerts dan outbox SecurityAlertRaised
        SE->>MQ: SecurityAlertRaised via relay
        MQ->>AUD: Catat alert di chain scope terkait
        SE->>SE: Bandingkan actual dengan expected lalu set PASSED atau FAILED
    end
    A->>GW: GET /api/v1/security/attacks/ID
    GW->>SE: Ambil hasil
    SE-->>A: 200 status, langkah, bukti
```

---

## F. Event-Driven Architecture

### F.1 Topologi RabbitMQ

| Objek | Konfigurasi |
|---|---|
| Exchange utama | `voxguard.events` — tipe `topic`, durable |
| Exchange retry | `voxguard.retry` — `direct`; exchange DLQ: `voxguard.dlx` — `direct` |
| Pesan | `delivery_mode=2` (persistent), `content_type=application/json`, header `x-attempt` |
| Konsumen | manual ack, `prefetch=1` untuk Audit (menjaga urutan chain), 10 untuk lainnya |

| Queue | Binding (routing key) | Konsumen |
|---|---|---|
| `audit.q.events` | `election.*`, `vote.accepted`, `tally.completed`, `result.finalized`, `security.alert_raised` | audit-service |
| `ballot.q.election` | `election.*` | ballot-service |
| `ballot.q.audit` | `audit.recorded` | ballot-service |
| `voter.q.ballot` | `vote.accepted` | voter-service |
| `voter.q.result` | `result.finalized` | voter-service |
| `security.q.events` | `election.*`, `vote.*`, `audit.recorded`, `tally.completed`, `security.signal_observed` | security-service |

Setiap queue punya `<queue>.retry.5s`, `<queue>.retry.30s`, `<queue>.retry.120s` (TTL, dead-letter kembali ke exchange utama via routing key asal) dan `<queue>.dlq`.

### F.2 Katalog event

Semua event memakai envelope `{event_id, event_type, schema_version, occurred_at, correlation_id, payload}` (contoh lengkap: `API_CONTRACTS.md` E). `event_id` = UUID (= `outbox_events.id`), `occurred_at` UTC, `correlation_id` UUID diteruskan dari `X-Correlation-ID` request awal.

| Event | Routing key | Publisher | Consumer | Isi payload (ringkas) | Dedup di consumer |
|---|---|---|---|---|---|
| `ElectionOpened` | `election.opened` | voter-service | ballot (gate), audit, security | `election_id`, `title`, `opened_at`, `end_at` | `processed_events` (ballot, audit); `UNIQUE(event_id)` (security) |
| `ElectionClosed` | `election.closed` | voter-service | ballot (gate), audit, security | `election_id`, `closed_at` | sama |
| `VoteAccepted` | `vote.accepted` | ballot-service | audit, voter, security | `election_id`, `ballot_id`, `receipt_id`, `accepted_at`, `ballot_commitment`, `eligibility_ref`\* | audit: `UNIQUE(source_event_id)` + `processed_events`; voter: `processed_events` + update idempoten |
| `VoteRejected` | `vote.rejected` | ballot-service | security | `election_id` (nullable), `reason_code`, `client_fingerprint`, `rejected_at` | `UNIQUE(event_id)` |
| `AuditRecorded` | `audit.recorded` | audit-service | ballot, security | `scope_id`, `source_event_id`, `source_event_type`, `sequence`, `event_hash`, `recorded_at` | `audit_acks` PK `source_event_id`; `UNIQUE(event_id)` |
| `TallyCompleted` | `tally.completed` | result-service | audit, security | `election_id`, `tally_run_id`, `run_number`, `status`, `reconciliation_status`, `ballots_counted`, `ballot_set_digest` | `processed_events`; `UNIQUE(event_id)` |
| `ResultFinalized` | `result.finalized` | result-service | audit, voter | `election_id`, `tally_run_id`, `result_hash`, `finalized_at` | `processed_events`; transisi FINALIZED idempoten |
| `SecurityAlertRaised` | `security.alert_raised` | security-service | audit | `alert_id`, `rule_code`, `severity`, `election_id` (nullable), `title`, `raised_at` | `processed_events` |
| `SecuritySignalObserved` | `security.signal_observed` | api-gateway, auth-service (best-effort); audit-service (outbox) | security | `signal_type`, `source_service`, `client_fingerprint`, `election_id` (nullable), `observed_at` | `UNIQUE(event_id)` |

\* `eligibility_ref` hanya untuk Voter. Audit dan Security **membuang** field ini dan `ballot_commitment` tidak boleh dicampur dengan identitas; keduanya memakai proyeksi allowlist. **`candidate_id` dan identitas pemilih tidak pernah ada dalam event.**

### F.3 Kebijakan deduplikasi, retry, dan DLQ

- **Deduplikasi:** setiap konsumen memeriksa `processed_events(event_id, consumer)` **dalam transaksi yang sama** dengan efek bisnis. Alternatif unik alami (mis. `UNIQUE(source_event_id)`) dipakai bila tersedia.
- **Retry:** kegagalan sementara → publish ulang ke retry queue bertingkat (5 s, 30 s, 120 s). Percobaan ke-4 gagal → `<queue>.dlq` dengan header `x-death`, alasan, dan `x-attempt`. Kesalahan permanen (validasi skema gagal) langsung ke DLQ.
- **DLQ:** tidak dikonsumsi otomatis. Security memantau kedalaman DLQ (R-09). Replay dilakukan manual oleh ADMIN setelah penyebab diperbaiki (OD-09 menyebut opsi alat replay). Replay aman karena konsumen idempotent.
- **Event tak dikenal / versi skema lebih baru:** ditolak ke DLQ, tidak diabaikan diam-diam.
- **Signal best-effort** (Gateway/Auth): boleh hilang saat broker mati; konsekuensi: deteksi R-03/R-04/R-08 bisa terlewat saat gangguan (dicatat di residual risk).

---

## G. Consistency and Failure Handling

| Topik | Rancangan |
|---|---|
| **Database transaction** | Perubahan data + baris outbox + `processed_events` (untuk konsumen) berada dalam satu transaksi lokal. Tidak ada transaksi terdistribusi/2PC |
| **Transactional outbox** | Event ditulis bersama data; relay menerbitkan dengan publisher confirms, at-least-once. Event dapat terbit lebih dari sekali dan tidak menjamin urutan antar-agregat |
| **Idempotent consumer** | `processed_events` / unique alami; efek bisnis tepat satu kali walau pesan datang berkali-kali |
| **Retry dan DLQ** | Lihat F.3 |
| **Rekonsiliasi suara** | Tiga angka dibandingkan saat tally: **B** = jumlah `ballots` ACCEPTED dengan `accepted_at ≤ closed_at` (Ballot), **A** = jumlah entri `VoteAccepted` di chain Audit, **V** = jumlah `VOTED` di Voter. Syarat `MATCH`: B = A = V **dan** `ballot_set_digest` Result = digest Ballot **dan** setiap `ballot_commitment` cocok. Selain itu `RECONCILIATION_FAILED`/`INTEGRITY_FAILED` dan finalisasi ditolak. Suara dengan `accepted_at > closed_at` ditandai anomali dan tidak dihitung |
| **Diterima ≠ berhasil diproses** | Status suara di Ballot adalah `ACCEPTED` begitu transaksi commit. Status audit terpisah: receipt melaporkan `audit_status = PENDING` sampai `AuditRecorded` untuk `outbox_event_id` suara itu diterima dan `audit_acks` terisi (`RECORDED`). `RECORDED` berarti *tercatat di chain*, **bukan** *terverifikasi*; verifikasi hanya dari endpoint `verify`. Sistem tidak menyatakan suara "sudah diaudit" sebelum itu |
| **Audit Service tidak tersedia** | Suara tetap diterima (NFR-REL-01). Event menumpuk di outbox/queue; receipt menampilkan `PENDING`; R-06 mengingatkan; finalisasi ditolak selama A ≠ B |
| **RabbitMQ mati lalu aktif** | Relay terus mencoba dengan backoff eksponensial (maks 60 s); setelah aktif, publish berurutan `created_at`; konsumen dedup; Audit mengurutkan chain sesuai urutan konsumsi (chain membuktikan urutan *pencatatan*, bukan urutan pemungutan) |
| **Voter Service tidak tersedia saat voting** | Ballot gagal-tertutup (503). Suara tidak diterima tanpa validasi status |
| **Crash antara COMMIT dan respons** | Klien retry dengan `Idempotency-Key` sama → respons tersimpan |
| **Crash relay/consumer** | Outbox `PENDING` dan pesan unacked tetap ada; diproses ulang saat service naik |

---

## H. Election Lifecycle

`DRAFT → SCHEDULED → OPEN → CLOSED → FINALIZED` (tidak ada transisi mundur; tidak ada *reopen*).

| Transisi | Pemicu | Berwenang | Guard | Efek |
|---|---|---|---|---|
| `DRAFT → SCHEDULED` | `POST /elections/{id}/schedule` | ADMIN | ≥ 2 kandidat; ≥ 1 pemilih; `start_at < end_at`; `end_at` di masa depan; `eligibility_ref` terbentuk untuk semua pemilih | Kandidat dan daftar pemilih **dibekukan** |
| `SCHEDULED → OPEN` | `POST /elections/{id}/open` | ADMIN (otomatis: ADD-01) | `now < end_at` | Set `opened_at`; outbox `ElectionOpened` |
| `OPEN → CLOSED` | `POST /elections/{id}/close` | ADMIN (otomatis: ADD-01) | status `OPEN` | Set `closed_at`; outbox `ElectionClosed`; Audit membuat checkpoint |
| `CLOSED → FINALIZED` | `POST /results/elections/{id}/finalize` | ADMIN (dieksekusi Result; Voter menerapkan dari event) | tally `COMPLETED`+`MATCH`; audit `VALID`; belum ada `final_results` | `final_results`; `ResultFinalized`; Voter set `FINALIZED` (eventual) |

Aturan tambahan: suara diterima hanya bila status `OPEN` **dan** `now ≤ end_at`; tally hanya saat `CLOSED`; setelah `final_results` ada, tally ulang ditolak. `GET /elections/{id}` dapat sesaat menampilkan `CLOSED` padahal `final_results` sudah ada (menunggu event); sumber kebenaran status hasil adalah `GET /results/…`.

---

## I. Deployment Architecture

### I.1 Topologi Docker Compose

| Service | Port host | Catatan |
|---|---|---|
| `frontend` | 5173 | Vite dev/preview |
| `api-gateway` | 8000 | satu-satunya API yang dipublikasikan |
| `auth-service`, `voter-service`, `ballot-service`, `audit-service`, `result-service`, `security-service` | — (internal 8001–8006) | profil `test` boleh mengekspos `ballot-service:8003` ke `127.0.0.1` untuk ATK-02 jalur langsung |
| `postgres` | — | satu instance, 6 database |
| `rabbitmq` | 127.0.0.1:15672 (management) | hanya loopback |
| `redis` | — | internal |

Jaringan `voxguard-net` (bridge). Volume: `pg_data`, `rabbitmq_data`, `audit_checkpoints` (dipisahkan dari `pg_data`). Kontainer berjalan non-root.

### I.2 Contoh kerangka `docker-compose.yml` (rancangan)

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_SUPERUSER_PASSWORD}
    volumes:
      - pg_data:/var/lib/postgresql/data
      - ./infra/postgres-init:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 3s
      retries: 20
    networks: [voxguard-net]

  rabbitmq:
    image: rabbitmq:3.13-management
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]
      interval: 10s
      timeout: 5s
      retries: 12
    ports: ["127.0.0.1:15672:15672"]
    networks: [voxguard-net]

  redis:
    image: redis:7
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10
    networks: [voxguard-net]

  ballot-service:
    build: ./services/ballot
    env_file: .env
    environment:
      DATABASE_URL: postgresql+psycopg://ballot_app:${BALLOT_DB_PASSWORD}@postgres:5432/ballot_db
    depends_on:
      postgres: { condition: service_healthy }
      rabbitmq: { condition: service_healthy }
      redis: { condition: service_healthy }
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8003/health/ready')"]
      interval: 10s
      timeout: 5s
      retries: 10
    networks: [voxguard-net]

  api-gateway:
    build: ./gateway
    env_file: .env
    ports: ["8000:8000"]
    depends_on:
      ballot-service: { condition: service_healthy }
    networks: [voxguard-net]

networks:
  voxguard-net: {}

volumes:
  pg_data: {}
  rabbitmq_data: {}
  audit_checkpoints: {}
```

(Service lain mengikuti pola `ballot-service`; urutan start: postgres/rabbitmq/redis → auth → voter → ballot/audit → result/security → gateway → frontend.)

### I.3 Inisialisasi database dan hak minimum (rancangan)

```sql
-- infra/postgres-init/01-databases.sql (nilai password diinjeksi dari environment, bukan ditulis di sini)
CREATE DATABASE auth_db;   CREATE DATABASE voter_db;   CREATE DATABASE ballot_db;
CREATE DATABASE audit_db;  CREATE DATABASE result_db;  CREATE DATABASE security_db;
-- Satu role per service: auth_app, voter_app, ballot_app, audit_app, result_app, security_app
-- Contoh hak minimum setelah migrasi (dijalankan oleh role migrator):
REVOKE ALL ON ballots FROM ballot_app;
GRANT SELECT, INSERT ON ballots TO ballot_app;
GRANT SELECT, INSERT ON audit_events TO audit_app;
GRANT SELECT, INSERT ON final_results TO result_app;
```

### I.4 Environment variables

| Variabel | Dipakai oleh | Keterangan |
|---|---|---|
| `APP_ENV` | semua | `local` / `test` / `prod-like` |
| `LOG_LEVEL` | semua | default `INFO` |
| `DATABASE_URL` | service ber-DB | satu per service; password dari env |
| `RABBITMQ_URL`, `REDIS_URL` | semua yang memakai | |
| `JWT_SECRET` | auth, gateway | acak ≥ 32 byte (OD-04) |
| `ACCESS_TOKEN_TTL_MIN`, `REFRESH_TOKEN_TTL_DAYS` | auth | usulan awal 15 / 7 |
| `VOTE_TICKET_SECRET`, `TICKET_TTL_MIN` | voter, ballot | usulan awal 10 menit |
| `ELIGIBILITY_PEPPER` | voter | **hanya** voter |
| `RECEIPT_SECRET` | ballot | **hanya** ballot (turunan `receipt_code`) |
| `FINGERPRINT_SECRET` | gateway | HMAC IP untuk `client_fingerprint` |
| `INTERNAL_API_KEY` | semua | header `X-Internal-Key` (OD-05) |
| `AUDIT_CHECKPOINT_KEY`, `AUDIT_CHECKPOINT_DIR` | audit | HMAC checkpoint dan direktori volume |
| `ATTACK_LAB_ENABLED` | security, audit | default `false` |
| `RATE_LIMIT_*` | gateway | batas per rute (nilai awal di API_CONTRACTS A.9) |
| `RABBITMQ_MGMT_URL` | security | polling DLQ |

Semua nilai di `.env.example` berupa placeholder `CHANGE_ME`; `.env` masuk `.gitignore`. Pembangkitan lokal disarankan dengan `openssl rand -hex 32`. Tidak ada secret sungguhan di dokumen atau repo.

### I.5 Health check, migrasi, dan konfigurasi lokal

- **Health:** `GET /health/live` (proses hidup) dan `GET /health/ready` (DB + broker/Redis terjangkau) di setiap service; dipakai `healthcheck` Compose.
- **Migrasi:** setiap service memiliki direktori Alembic sendiri; entrypoint menjalankan `alembic upgrade head` **sebelum** `uvicorn`, setelah `postgres` healthy. Satu replika per service (tidak ada balapan migrasi).
- **Topologi broker:** exchange/queue dideklarasikan idempoten saat startup oleh konsumen/relay.
- **Seed lokal:** skrip membuat satu ADMIN dari env (tanpa password di repo) dan data uji fiktif.
- **Profil `test`:** mengaktifkan `ATTACK_LAB_ENABLED`, port langsung Ballot, dan database uji terpisah.
- **Struktur repositori (rancangan):** `gateway/`, `services/{auth,voter,ballot,audit,result,security}/`, `shared/voxguard_common/`, `frontend/`, `infra/`, `docs/`, `docker-compose.yml`.

---

## J. OPEN DECISIONS

| ID | Keputusan belum final | Opsi | Rekomendasi |
|---|---|---|---|
| OD-01 | Cara memastikan pemilik akun adalah pemilih sah | (a) cocokkan email terimpor; (b) verifikasi email; (c) `voter_code` sekali pakai dibagikan luring | MVP: (a) dengan risiko dicatat (TH-14); tambahkan (c) sebagai ADD-02 |
| OD-02 | Open/close otomatis | (a) manual saja; (b) scheduler di voter-service | MVP: (a) + penegakan `end_at` saat voting; (b) = ADD-01 |
| OD-03 | `eligibility_ref` di tabel `ballots` atau tabel partisipasi terpisah | (a) satu tabel; (b) dua tabel | (a) untuk kesederhanaan; tinjau ulang setelah uji privasi |
| OD-04 | Algoritma JWT | (a) HS256 bersama; (b) RS256/EdDSA | MVP: (a); (b) = ADD-05 |
| OD-05 | Autentikasi antar-service | (a) satu `INTERNAL_API_KEY`; (b) kunci per pemanggil; (c) mTLS | (b) bila waktu cukup, minimal (a) |
| OD-06 | Tujuan checkpoint audit | (a) volume lokal terpisah; (b) penyimpanan eksternal; (c) publikasi hash manual saat close | (a) + (c) |
| OD-07 | Aturan dua orang untuk finalisasi | (a) satu ADMIN; (b) dua ADMIN berbeda | MVP: (a); (b) = ADD-03 |
| OD-08 | Proof audit dan verify hasil | (a) wajib login; (b) publik tanpa login | (a) pada MVP |
| OD-09 | Alat replay DLQ | (a) skrip Python; (b) Shovel/UI RabbitMQ | (a) |
| OD-10 | Ballot commitment (KD-08) pada MVP | (a) ya; (b) tunda | (a) — murah dan menutup celah perubahan `candidate_id` |
