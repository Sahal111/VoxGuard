# VoxGuard — API Contract Specification

## 1. Document Information

| Atribut | Nilai |
|---|---|
| Nama dokumen | API Contract Specification |
| Versi kontrak | `v1` (prefix `/api/v1`); versi dokumen 0.1 |
| Status | **Draft — rancangan kontrak, belum disetujui, belum diimplementasikan** |
| Tanggal | 2026-10-10 |
| Pemilik | `[PEMILIK-DOKUMEN]` (placeholder) |
| Acuan | SRS (`02_…`), SAD (`03_…`), Database Design (`04_…`). Pendamping lama (tidak diubah): `API_CONTRACTS.md` — berisi contoh JSON tambahan per endpoint |

| Versi | Tanggal | Perubahan |
|---|---|---|
| 0.1 | 2026-10-10 | Draf awal; menyempurnakan `API_CONTRACTS.md` (tambah `producer` pada event, katalog terstruktur) |

Contoh JSON pada dokumen ini fiktif dan hanya menunjukkan format. Selisih dengan `API_CONTRACTS.md` dicatat di Bagian 12; untuk selisih, dokumen ini yang menjadi acuan kontrak berikutnya (usulan; OD-14).

---

## 2. API Design Principles

| Prinsip | Ketetapan |
|---|---|
| Protokol | REST/JSON (UTF-8) lewat API Gateway; OpenAPI 3.1 (Bagian 9) |
| Versi | Prefix `/api/v1` dipakai konsisten (repository belum memiliki format lain). Endpoint internal: `/internal/v1/*` (tidak dirutekan Gateway) |
| Tanggal/waktu | ISO 8601 UTC dengan `Z`: `2026-10-12T08:00:00Z` |
| Identitas resource | UUID huruf kecil; path memakai `{id}` UUID; ID tidak mengandung data pribadi |
| Penamaan | `snake_case` pada field; plural pada koleksi; kata kerja domain hanya untuk aksi non-CRUD (`/open`, `/close`, `/schedule`, `/tally`, `/finalize`) |
| Pagination | `page` (default 1), `page_size` (default 20, maks 100); respons `{"items":[…],"page":{"page","page_size","total"}}` |
| Sorting | `sort` berisi satu field whitelist, awalan `-` untuk menurun (mis. `sort=-created_at`); field tak dikenal → `VALIDATION_ERROR` |
| Filtering | Query parameter bernama sesuai field (mis. `status`, `severity`, `election_id`); hanya yang tercantum per endpoint |
| Error | Skema seragam `{"error":{"code","message","details","request_id"}}` (Bagian 7) |
| Request/Correlation ID | `X-Request-ID` (UUID) dibuat Gateway bila tidak ada/invalid dan dikembalikan di setiap respons; `X-Correlation-ID` diteruskan antar-layanan dan masuk ke event. Header ini dari klien divalidasi (UUID) |
| Idempotency | Header `Idempotency-Key` **wajib** untuk `POST /ballots`; endpoint lain idempoten lewat guard status (mengulang transisi → `409 ELECTION_INVALID_STATE`) |
| Authentication | `Authorization: Bearer <access_token>` (JWT); refresh token hanya di body |
| Authorization | Role diperiksa di Gateway **dan** layanan (Bagian 3) |
| Timeout dan retry | Klien→Gateway: timeout klien (**PROPOSED**: 10 s); Gateway→layanan: **PROPOSED** 8 s; layanan→layanan internal: **PROPOSED** 2 s, tanpa retry otomatis untuk operasi yang mengubah state. Klien boleh me-retry `GET` dan `POST /ballots` (dengan `Idempotency-Key` yang sama) pada timeout/`503`/`429` setelah `Retry-After` |
| Backward compatibility | Dalam `v1`: hanya perubahan **aditif** (field respons opsional baru, endpoint baru, nilai enum baru yang diabaikan klien lama). Penghapusan/penggantian nama/pengetatan validasi/perubahan makna = *breaking* → `v2` (Bagian 10). Klien wajib mengabaikan field tak dikenal pada respons; server menolak field tak dikenal pada request (`extra="forbid"`) |
| Pembatasan ukuran | Body default 64 KB; `voters/import` 1 MB (maks 1.000 baris) |
| Rate limit | `429 RATE_LIMIT_EXCEEDED` + `Retry-After`; nilai batas **PROPOSED** (lihat `API_CONTRACTS.md` A.9) |

---

## 3. Authentication and Authorization Matrix

### 3.1 Authentication vs authorization

- **Authentication** = siapa pemanggil: pengguna (JWT) atau layanan internal (header `X-Internal-Key` dari jaringan Docker internal).
- **Authorization** = tindakan yang boleh: role pada klaim `role`, dan kepemilikan/kelayakan untuk resource (mis. VOTER hanya pemilihan tempat ia terdaftar).
- Gateway menghapus header `X-User-*`, `X-Internal-Key`, `X-Client-Fingerprint` dari klien, lalu menambahkannya sendiri. Layanan memeriksa ulang `X-User-Role`; proteksi frontend tidak diandalkan.

### 3.2 Matriks hak akses

`●` boleh · `—` tolak · `●*` dengan syarat.

| Kemampuan | Anon | VOTER | AUDITOR | ADMIN | Service internal |
|---|---|---|---|---|---|
| Register VOTER / login / refresh | ● | ● | ● | ● | — |
| Register ADMIN/AUDITOR | — | — | — | ● | — |
| Logout, `me` | — | ● | ● | ● | — |
| Buat pemilihan, kandidat, impor pemilih, schedule, open, close | — | — | — | ● | — |
| Lihat daftar/detail pemilihan | — | ●* (hanya yang ia berhak; bukan `DRAFT`) | ●* (bukan `DRAFT`) | ● | — |
| Meminta ballot + ticket, mengirim suara | — | ● | — | — | — |
| Receipt (dengan `X-Receipt-Code`) | ●* | ●* | ●* | ●* | — |
| Audit: events, verify | — | — | ● | ● | — |
| Audit: proof | — | ● | ● | ● | — |
| Tally, finalize | — | — | — | ● | — |
| **Hasil sebelum finalisasi** (`PROVISIONAL`) | — | — (`RESULT_NOT_FINALIZED`) | ● | ● | — |
| **Hasil setelah finalisasi** (`FINAL`) dan `verify` | — | ● | ● | ● | — |
| Alerts, metrics | — | — | ● | ● | — |
| Attack Lab (run, get) | — | — | — | ●* (hanya lab aktif di lingkungan lokal/uji) | — |
| Endpoint internal | — | — | — | — | ●* (hanya pemanggil yang diizinkan, Bagian 3.3) |
| **Data identitas pemilih** (email, nama, `external_ref`) | — | — | — | ●* (hanya daftar pemilih pemilihan yang ia kelola; tidak ada endpoint baca di MVP selain jumlah) | — |
| **Pilihan suara individual** | — | — | — | — | ●* (hanya Result menerima `candidate_id` per `ballot_id` tanpa identitas, via ekspor internal) |

Auditor **tidak** memperoleh identitas pemilih maupun pilihan individu pada endpoint mana pun. Tidak ada endpoint publik yang mengembalikan pilihan per suara atau per receipt.

### 3.3 Service-to-service

| Pemanggil → Callee | Endpoint internal | Tujuan |
|---|---|---|
| ballot → voter | `GET /internal/v1/elections/{id}/ballot-info`; `POST …/eligibility/tickets` | Status pemilihan; penerbitan ticket |
| result → voter | `GET /internal/v1/elections/{id}/summary` | Status, `closed_at`, kandidat, partisipasi |
| result → ballot | `GET …/tally-export`; `GET …/summary` | Data tally (tanpa identitas/`eligibility_ref`) |
| result → audit | `GET …/summary`; `GET …/commitments`; `POST …/verify` | Rekonsiliasi dan verifikasi |
| security → ballot | `GET /internal/v1/outbox/stats` | Polling backlog |
| security → audit | `POST /internal/v1/test/tamper`, `…/restore` | Hanya Attack Lab, `APP_ENV` lokal/uji |

Autentikasi: `X-Internal-Key` (OD-05: kunci bersama atau per pemanggil) + jaringan internal. Layanan menolak pemanggil di luar tabel (`FORBIDDEN`).

---

## 4. Endpoint Catalog

Semua path di bawah `/api/v1`. Skema [S-xx] didefinisikan di Bagian 5.1. `Auth` = persyaratan autentikasi. Satu endpoint baru ditambahkan dari baseline: **`POST /elections/{id}/schedule`** (diperlukan transisi `DRAFT→SCHEDULED`, BR-003).

| # | Method path | Pemilik | Role / Auth |
|---|---|---|---|
| 1 | `POST /auth/register` | auth | Anon (VOTER); ADMIN untuk role lain |
| 2 | `POST /auth/login` | auth | Anon |
| 3 | `POST /auth/refresh` | auth | Anon + refresh token |
| 4 | `POST /auth/logout` | auth | VOTER, AUDITOR, ADMIN |
| 5 | `GET /auth/me` | auth | VOTER, AUDITOR, ADMIN |
| 6 | `POST /elections` | voter | ADMIN |
| 7 | `GET /elections` | voter | ADMIN, AUDITOR, VOTER (terfilter) |
| 8 | `GET /elections/{id}` | voter | ADMIN, AUDITOR, VOTER (terbatas) |
| 9 | `POST /elections/{id}/candidates` | voter | ADMIN |
| 10 | `POST /elections/{id}/voters/import` | voter | ADMIN |
| 11 | `POST /elections/{id}/schedule` | voter | ADMIN |
| 12 | `POST /elections/{id}/open` | voter | ADMIN |
| 13 | `POST /elections/{id}/close` | voter | ADMIN |
| 14 | `GET /elections/{id}/ballot` | ballot | VOTER |
| 15 | `POST /ballots` | ballot | VOTER |
| 16 | `GET /ballots/receipt/{id}` | ballot | Publik + `X-Receipt-Code` |
| 17 | `GET /audit/events` | audit | ADMIN, AUDITOR |
| 18 | `GET /audit/elections/{id}/verify` | audit | ADMIN, AUDITOR |
| 19 | `GET /audit/elections/{id}/proof` | audit | ADMIN, AUDITOR, VOTER |
| 20 | `POST /results/elections/{id}/tally` | result | ADMIN |
| 21 | `POST /results/elections/{id}/finalize` | result | ADMIN |
| 22 | `GET /results/elections/{id}` | result | ADMIN, AUDITOR; VOTER hanya `FINAL` |
| 23 | `GET /results/elections/{id}/verify` | result | ADMIN, AUDITOR; VOTER hanya `FINAL` |
| 24 | `GET /security/alerts` | security | ADMIN, AUDITOR |
| 25 | `POST /security/attacks/run` | security | ADMIN (lab aktif) |
| 26 | `GET /security/attacks/{id}` | security | ADMIN |
| 27 | `GET /security/metrics` | security | ADMIN, AUDITOR |

Kesehatan (tanpa auth, tidak dirutekan Gateway): `GET /health/live`, `GET /health/ready` pada setiap layanan.

---

## 5. Detailed Endpoint Specifications

Setiap baris memuat: tujuan, path/query/header, request, validasi, sukses, error, side effect + event, idempotency/retry. Header umum (semua): `X-Request-ID` (opsional, UUID), `Authorization` (kecuali publik). Error umum yang tidak diulang: `401 UNAUTHORIZED` (token), `403 FORBIDDEN` (role), `429 RATE_LIMIT_EXCEEDED`, `500 INTERNAL_ERROR`, `503 SERVICE_UNAVAILABLE`, semuanya berskema [S-ERR]. Error `422 VALIDATION_ERROR` berlaku untuk semua input.

### 5.1 Skema bersama dan contoh

**[S-ERR]** error:

```json
{
  "error": {
    "code": "VOTER_ALREADY_VOTED",
    "message": "Hak memilih ini sudah digunakan.",
    "details": [],
    "request_id": "7a9c1e3f-5b7d-4f91-8a23-4c6e8a0b2d45"
  }
}
```

**[S-PAGE]** `{"items":[…],"page":{"page":1,"page_size":20,"total":57}}`.

**[S-REGISTER-IN]** → **[S-USER]**:

```json
{ "email": "andi@example.test", "password": "contoh-password-panjang-123", "display_name": "Andi Contoh" }
```

```json
{ "id": "c3e5a1b9-7d58-4f93-a02b-5a4b9c8d3f76", "email": "andi@example.test", "display_name": "Andi Contoh", "role": "VOTER", "created_at": "2026-10-10T07:00:00Z" }
```

**[S-LOGIN-IN]** `{"email","password"}` → **[S-TOKEN]**:

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiJ9.contoh.signature",
  "token_type": "Bearer",
  "expires_in": 900,
  "refresh_token": "contoh-refresh-token-acak",
  "user": { "id": "c3e5a1b9-7d58-4f93-a02b-5a4b9c8d3f76", "email": "andi@example.test", "display_name": "Andi Contoh", "role": "VOTER" }
}
```

**[S-ELECTION-IN]** / **[S-ELECTION]**:

```json
{ "title": "Pemilihan Ketua Kelas 3A", "description": "Simulasi", "start_at": "2026-10-12T08:00:00Z", "end_at": "2026-10-12T10:00:00Z", "is_attack_lab": false }
```

```json
{
  "id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
  "title": "Pemilihan Ketua Kelas 3A",
  "description": "Simulasi",
  "status": "DRAFT",
  "start_at": "2026-10-12T08:00:00Z",
  "end_at": "2026-10-12T10:00:00Z",
  "opened_at": null,
  "closed_at": null,
  "finalized_at": null,
  "is_attack_lab": false,
  "candidates": [],
  "created_at": "2026-10-10T07:10:00Z"
}
```

`voter_count` dan `participation_count` hanya ada pada respons ADMIN/AUDITOR.

**[S-CANDIDATE-IN]** `{"name","description","ballot_order"}` → `{"id","election_id","name","description","ballot_order"}`. **[S-VOTERS-IN]**:

```json
{ "voters": [ { "email": "sari@example.test", "external_ref": "NIM-0002", "display_label": "Sari Contoh" } ] }
```

→ `{"election_id":"…","imported":1}`.

**[S-BALLOT-VIEW]**:

```json
{
  "election_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
  "title": "Pemilihan Ketua Kelas 3A",
  "end_at": "2026-10-12T10:00:00Z",
  "candidates": [
    { "id": "a1c4e8f2-5b36-4d71-8c09-3e2f7a6b1d54", "name": "Calon A", "description": "Visi A", "ballot_order": 1 },
    { "id": "b7d2f9a3-6c47-4e82-9d1a-4f3a8b7c2e65", "name": "Calon B", "description": "Visi B", "ballot_order": 2 }
  ],
  "vote_ticket": "eyJhbGciOiJIUzI1NiJ9.contoh-ticket.signature",
  "ticket_expires_at": "2026-10-12T08:15:00Z"
}
```

**[S-VOTE-IN]** / **[S-RECEIPT]** (Bagian 6):

```json
{ "election_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3", "candidate_id": "a1c4e8f2-5b36-4d71-8c09-3e2f7a6b1d54", "vote_ticket": "eyJhbGciOiJIUzI1NiJ9.contoh-ticket.signature" }
```

```json
{ "receipt_id": "d9f6b2c4-8e69-4a04-b13c-6b5c0d9e4a87", "receipt_code": "VG-7K4Q-5M2D-X6TP-3RWA", "election_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3", "accepted_at": "2026-10-12T08:20:11Z", "audit_status": "PENDING" }
```

**[S-RECEIPT-LOOKUP]**:

```json
{
  "receipt_id": "d9f6b2c4-8e69-4a04-b13c-6b5c0d9e4a87",
  "election_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
  "status": "ACCEPTED",
  "accepted_at": "2026-10-12T08:20:11Z",
  "audit_status": "RECORDED",
  "audit": { "sequence": 14, "event_hash": "9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c", "recorded_at": "2026-10-12T08:20:13Z" }
}
```

**[S-VERIFY-AUDIT]**:

```json
{
  "check_id": "3d5f7a91-4e60-4b8a-9c1d-2e4f6a8b0c13",
  "election_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
  "status": "VALID",
  "events_checked": 14,
  "head_sequence": 14,
  "head_hash": "9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c",
  "first_failure": null,
  "checkpoint": { "compared": true, "matches": true, "checkpoint_sequence": 14 },
  "checked_at": "2026-10-12T10:30:00Z"
}
```

**[S-TALLY]**:

```json
{
  "tally_run_id": "2c4e6a81-3d5f-4b79-8c9b-1d3f5a7b9ea2",
  "election_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
  "run_number": 1,
  "status": "COMPLETED",
  "reconciliation": { "status": "MATCH", "ballots_counted": 12, "audit_vote_events": 12, "voter_participation": 12, "ballot_set_digest": "5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e" },
  "items": [
    { "candidate_id": "a1c4e8f2-5b36-4d71-8c09-3e2f7a6b1d54", "candidate_name": "Calon A", "vote_count": 7 },
    { "candidate_id": "b7d2f9a3-6c47-4e82-9d1a-4f3a8b7c2e65", "candidate_name": "Calon B", "vote_count": 5 }
  ],
  "completed_at": "2026-10-12T10:05:00Z"
}
```

(Angka hanya ilustrasi format.) **[S-FINALIZE-IN]** `{"tally_run_id":"…"}`; **[S-FINAL]** `{"election_id","tally_run_id","status":"FINAL","result_hash","finalized_at"}`; **[S-RESULT]** = `{"election_id","status":"PROVISIONAL"|"FINAL","tally_run_id","total_ballots","items":[…],"ballot_set_digest","result_hash"|null,"finalized_at"|null}`.

**[S-ALERT]**:

```json
{
  "id": "0a2c4e6f-1b3d-4f57-8a79-9b1d3f5a7c80",
  "rule_code": "R-01",
  "severity": "MEDIUM",
  "election_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
  "title": "Percobaan double voting berulang",
  "description": "Beberapa penolakan VOTER_ALREADY_VOTED dari fingerprint klien yang sama",
  "evidence": { "count": 3, "window_minutes": 5 },
  "occurrence_count": 1,
  "first_seen_at": "2026-10-12T08:25:00Z",
  "last_seen_at": "2026-10-12T08:27:00Z",
  "resolved_at": null
}
```

**[S-ATTACK-IN]** `{"attack_id":"ATK-02","parameters":{"variant":"A","concurrency":50}}` → **[S-ATTACK]** `{"id","attack_id","status","election_id","started_at","finished_at","steps":[{"step","expected","actual","passed"}],"result":{"passed","summary"}}`. **[S-VERIFY-RESULT]** `{"election_id","status":"MATCH"|"MISMATCH","checks":{…},"verified_at"}`. **[S-PROOF]**, **[S-AUDIT-EVENT]**, **[S-METRICS]**: contoh lengkap di `API_CONTRACTS.md` B.4 dan B.6 (format identik).

### 5.2 Auth Service

| # | Rincian |
|---|---|
| **1 `POST /auth/register`** | **Tujuan:** buat akun. **Request:** [S-REGISTER-IN] (+ `role` opsional hanya ADMIN). **Validasi:** email format RFC dan ≤ 254, dinormalisasi lowercase; password 12–128; `display_name` 1–100; `role` ∈ {ADMIN,VOTER,AUDITOR}. **Sukses:** `201` [S-USER]. **Error:** `409 CONFLICT` (email ada), `403 FORBIDDEN` (role oleh non-ADMIN), `422`. **Side effect:** `INSERT users`. **Event:** —. **Retry:** tidak idempoten; ulang → `409 CONFLICT` |
| **2 `POST /auth/login`** | **Tujuan:** autentikasi. **Request:** [S-LOGIN-IN]. **Validasi:** non-kosong; cek lockout. **Sukses:** `200` [S-TOKEN]. **Error:** `401 UNAUTHORIZED` (generik), `423 ACCOUNT_LOCKED`, `422`. **Side effect:** `INSERT refresh_sessions`; update `failed_login_count/last_login_at`. **Event:** `SecuritySignalObserved` (`LOGIN_FAILED`/`ACCOUNT_LOCKED`, best-effort). **Retry:** aman; tiap sukses membuat sesi baru |
| **3 `POST /auth/refresh`** | **Request:** `{"refresh_token":"…"}`. **Sukses:** `200` token baru (tanpa `user`). **Error:** `401 UNAUTHORIZED` (kedaluwarsa/dicabut/reuse). **Side effect:** rotasi atomik; reuse → cabut `family_id`. **Event:** `SecuritySignalObserved` `TOKEN_INVALID` pada reuse. **Retry:** token lama tidak dapat dipakai dua kali; klien menyimpan pasangan terbaru |
| **4 `POST /auth/logout`** | **Request:** `{"refresh_token":"…"}`. **Sukses:** `204`. **Error:** `401`, `422`. **Side effect:** `refresh_sessions.revoked_at`; denylist `jti` Redis. **Idempotency:** mengulang → `204` |
| **5 `GET /auth/me`** | **Sukses:** `200` `{"id","email","display_name","role"}`. **Error:** `401`. Tanpa side effect |

### 5.3 Voter Service

| # | Rincian |
|---|---|
| **6 `POST /elections`** | **Request:** [S-ELECTION-IN]. **Validasi:** judul 3–150; `start_at < end_at`; `is_attack_lab=true` hanya bila Attack Lab aktif (`403 FORBIDDEN`). **Sukses:** `201` [S-ELECTION] (`DRAFT`). **Error:** `403`, `422`. **Side effect:** `INSERT elections`. **Event:** — |
| **7 `GET /elections`** | **Query:** `status`, `sort` (`created_at`/`start_at`), `page`, `page_size`. **Sukses:** `200` [S-PAGE] berisi ringkasan `{id,title,status,start_at,end_at}`. VOTER: hanya terdaftar & bukan `DRAFT`; AUDITOR: bukan `DRAFT`. **Error:** `422` |
| **8 `GET /elections/{id}`** | **Path:** `id` UUID. **Sukses:** `200` [S-ELECTION] + kandidat (+ `voter_count`, `participation_count` untuk ADMIN/AUDITOR). **Error:** `404 NOT_FOUND` (termasuk di luar hak VOTER) |
| **9 `POST /elections/{id}/candidates`** | **Request:** [S-CANDIDATE-IN]. **Validasi:** status `DRAFT`; nama 1–100; `ballot_order ≥ 1`. **Sukses:** `201`. **Error:** `404`, `409 ELECTION_INVALID_STATE`, `409 CONFLICT` (nama/urutan ganda), `422`. **Side effect:** `INSERT candidates` |
| **10 `POST /elections/{id}/voters/import`** | **Request:** [S-VOTERS-IN] (1–1.000 baris). **Validasi:** `DRAFT`; email/`external_ref` unik per pemilihan; all-or-nothing. **Sukses:** `201` `{"election_id","imported"}`. **Error:** `404`, `409 ELECTION_INVALID_STATE`, `422` (details per `index` baris). **Side effect:** `INSERT voters` (belum membuat `voting_eligibility`). **Retry:** pengulangan → `422`/`409` karena duplikat |
| **11 `POST /elections/{id}/schedule`** | Tanpa body. **Validasi:** `DRAFT`; ≥ 2 kandidat; ≥ 1 pemilih; `end_at` di masa depan. **Sukses:** `200` `{"id","status":"SCHEDULED"}`. **Error:** `404`, `409 ELECTION_INVALID_STATE`, `422`. **Side effect:** `UPDATE elections`; `INSERT voting_eligibility` (semua pemilih); bekukan kandidat/pemilih. **Event:** —. **Retry:** ulang → `409 ELECTION_INVALID_STATE` |
| **12 `POST /elections/{id}/open`** | **Validasi:** `SCHEDULED`; `now < end_at`. **Sukses:** `200` `{"id","status":"OPEN","opened_at"}`. **Error:** `404`, `409 ELECTION_INVALID_STATE`. **Side effect:** `UPDATE elections` + `INSERT outbox_events` (satu transaksi). **Event:** `ElectionOpened` |
| **13 `POST /elections/{id}/close`** | **Validasi:** `OPEN`. **Sukses:** `200` `{"id","status":"CLOSED","closed_at"}`. **Error:** sama. **Event:** `ElectionClosed` |

### 5.4 Ballot Service

| # | Rincian |
|---|---|
| **14 `GET /elections/{id}/ballot`** | **Role:** VOTER. **Validasi:** Voter Service memeriksa pemilih terdaftar, `OPEN`, `now ≤ end_at`, belum `VOTED`. **Sukses:** `200` [S-BALLOT-VIEW]. **Error:** `403 VOTER_NOT_ELIGIBLE`, `409 VOTER_ALREADY_VOTED`, `409 ELECTION_NOT_OPEN`, `404`, `503` (Voter tidak tersedia, fail-closed). **Side effect:** Voter: `voting_eligibility.status='TICKET_ISSUED'`; Ballot tidak menyimpan identitas. **Retry:** boleh diulang; ticket baru berlaku, `eligibility_ref` sama |
| **15 `POST /ballots`** | Lihat **Bagian 6** (kontrak lengkap) |
| **16 `GET /ballots/receipt/{id}`** | **Path:** `id` = `receipt_id`. **Header:** `X-Receipt-Code` wajib. **Sukses:** `200` [S-RECEIPT-LOOKUP] (tanpa pilihan/identitas). **Error:** `404 RECEIPT_NOT_FOUND` (id tak ada atau kode salah; tidak dibedakan), `422`, `429`. **Side effect:** baca saja. `audit_status` = `PENDING` bila `AuditRecorded` belum diterima, `RECORDED` bila sudah (bukan berarti terverifikasi) |

### 5.5 Audit Service

| # | Rincian |
|---|---|
| **17 `GET /audit/events`** | **Query:** `election_id` (kosong → scope GLOBAL), `event_type`, `from_sequence`, `to_sequence`, `order` (`asc` default), `page`, `page_size`. **Sukses:** `200` [S-PAGE] [S-AUDIT-EVENT]. **Error:** `403`, `422`. Hanya `payload_public` ter-allowlist |
| **18 `GET /audit/elections/{id}/verify`** | **Sukses:** `200` [S-VERIFY-AUDIT]; kegagalan integritas dilaporkan di body (`status="INVALID"`, `first_failure{sequence,reason}`), **bukan** error HTTP. **Error:** `404`, `403`, `503`. **Side effect:** `INSERT integrity_checks`. **Event:** `SecuritySignalObserved` `AUDIT_INTEGRITY_FAILED` bila `INVALID` (outbox). **Retry:** aman diulang (menambah baris pemeriksaan) |
| **19 `GET /audit/elections/{id}/proof`** | **Query:** `receipt_id` (opsional). **Sukses:** `200` [S-PROOF] (parameter chain, head, checkpoint, verifikasi terakhir, `receipt_event` atau `null`). Tanpa identitas, pilihan, `eligibility_ref` |

### 5.6 Result Service

| # | Rincian |
|---|---|
| **20 `POST /results/elections/{id}/tally`** | **Validasi:** pemilihan `CLOSED`; belum ada `final_results`. **Sukses:** `201` [S-TALLY] bila `COMPLETED`. **Error:** `409 ELECTION_INVALID_STATE`, `409 RECONCILIATION_FAILED` / `409 BALLOT_INTEGRITY_FAILED` (run tersimpan; `details` memuat `tally_run_id` dan ringkasan B/A/V), `404`, `503`. **Side effect:** `INSERT tally_runs/items` + outbox. **Event:** `TallyCompleted`. **Retry:** setiap panggilan = run baru (`run_number` naik), aman |
| **21 `POST /results/elections/{id}/finalize`** | **Request:** [S-FINALIZE-IN]. **Validasi:** run `COMPLETED`+`MATCH` dan milik pemilihan; verifikasi Audit `VALID`. **Sukses:** `200` [S-FINAL]. **Error:** `409 ELECTION_INVALID_STATE` (sudah final/bukan CLOSED), `409 RECONCILIATION_FAILED`, `409 AUDIT_VERIFICATION_FAILED`, `404`, `422`, `503`. **Side effect:** `INSERT final_results` + outbox (satu transaksi). **Event:** `ResultFinalized`. **Retry:** ulang → `409 ELECTION_INVALID_STATE`; hasil final tidak berubah |
| **22 `GET /results/elections/{id}`** | **Sukses:** `200` [S-RESULT]. ADMIN/AUDITOR: `PROVISIONAL` (dari tally terakhir) atau `FINAL`; VOTER: hanya `FINAL`. **Error:** `409 RESULT_NOT_FINALIZED` (VOTER sebelum final; atau belum ada tally), `404` |
| **23 `GET /results/elections/{id}/verify`** | **Sukses:** `200` [S-VERIFY-RESULT] (rincian tiap pemeriksaan). **Error:** `409 RESULT_NOT_FINALIZED`, `404`, `503` |

### 5.7 Security Service

| # | Rincian |
|---|---|
| **24 `GET /security/alerts`** | **Query:** `severity`, `rule_code`, `election_id`, `resolved` (bool), `page`, `page_size`. **Sukses:** `200` [S-PAGE] [S-ALERT]. **Error:** `403`, `422` |
| **25 `POST /security/attacks/run`** | **Request:** [S-ATTACK-IN]. **Validasi:** `attack_id` ∈ ATK-01..10; `concurrency ≤ 100`; Attack Lab aktif dan `APP_ENV` ∈ {local,test} (jika tidak `403 FORBIDDEN`); satu run aktif (`409 CONFLICT`). **Sukses:** `202` `{"id","attack_id","status":"QUEUED","election_id":null,"created_at"}`. **Side effect:** `INSERT attack_runs`; runner hanya menargetkan election `is_attack_lab=true`. **Retry:** tidak idempoten (run baru) |
| **26 `GET /security/attacks/{id}`** | **Sukses:** `200` [S-ATTACK] (expected vs actual per langkah; nilai aktual diisi runner). **Error:** `404`, `403` |
| **27 `GET /security/metrics`** | **Sukses:** `200` [S-METRICS] (alert terbuka per severity, suara diterima/ditolak per alasan, rate limit, umur outbox tertua, kedalaman DLQ, lag audit, duplikat dibuang). Nilai pada contoh bukan hasil pengukuran |

---

## 6. Ballot API Contract

### 6.1 Request

`POST /api/v1/ballots`; header: `Authorization: Bearer <access_token>` (role VOTER), `Idempotency-Key: <16–64 karakter [A-Za-z0-9_-]>` (UUID v4 disarankan), `Content-Type: application/json`. Body [S-VOTE-IN]: `election_id`, `candidate_id`, `vote_ticket`.

| Aspek | Ketetapan |
|---|---|
| **Identitas pemanggil** | Gateway memverifikasi JWT/role, **membuang** `X-User-Id` dan `X-User-Email` untuk rute ini; Ballot Service hanya mengetahui role. Tidak ada data pribadi di body |
| **Pemilihan yang dituju** | `election_id` harus sama dengan klaim `election_id` pada ticket |
| **Referensi kandidat** | `candidate_id` harus milik pemilihan itu (dari `ballot-info`); jika tidak → `422 VALIDATION_ERROR` |
| **Idempotency key** | Wajib; ruang lingkup per hak memilih (`eligibility_ref` dari ticket). Hilang/format salah → `422` |
| **Validasi status pemilihan** | Gate lokal `election_gates` + cek sinkron ke Voter (tanpa cache status): status `OPEN` dan `now ≤ end_at` → jika tidak `409 ELECTION_NOT_OPEN`; Voter tidak terjangkau → `503 SERVICE_UNAVAILABLE` (**fail-closed**, tidak ada suara diterima) |
| **Validasi kelayakan** | Ticket: tanda tangan, `exp`, `aud=voxguard-ballot`, `typ=vote-ticket`, `election_id`; gagal → `403 VOTE_TICKET_INVALID`. Token akses invalid → `401 UNAUTHORIZED`. Pemilih tak terdaftar tidak akan pernah memperoleh ticket (`VOTER_NOT_ELIGIBLE` pada langkah ballot view) |
| **Pencegahan suara ganda** | Satu transaksi dengan `UNIQUE(election_id, eligibility_ref)` (`04_…` DBC-05): pelanggaran → `409 VOTER_ALREADY_VOTED` |
| **Request bersamaan** | Konflik diserialkan oleh indeks unik: tepat satu `201`; sisanya `409 VOTER_ALREADY_VOTED` (key berbeda) atau `200` replay (key sama + payload sama) — `04_…` Bagian 6.3 |
| **Retry setelah timeout** | Klien mengulang dengan `Idempotency-Key` **yang sama**: bila transaksi pertama commit → `200` + `Idempotent-Replayed: true` + `receipt` identik; bila tidak commit → diproses seperti baru. Key sama dengan `candidate_id` berbeda → `409 IDEMPOTENCY_CONFLICT`. Key baru setelah suara tercatat → `409 VOTER_ALREADY_VOTED` |
| **Response sukses** | `201` [S-RECEIPT] (`receipt_id`, `receipt_code`, `election_id`, `accepted_at`, `audit_status="PENDING"`). Replay → `200` body identik |
| **Penolakan request tidak valid** | `401` token; `403 VOTE_TICKET_INVALID`; `409 ELECTION_NOT_OPEN`; `409 VOTER_ALREADY_VOTED`; `409 IDEMPOTENCY_CONFLICT`; `422` payload/kandidat/header; `429`; `503` |
| **Side effect dan event** | Satu COMMIT: `idempotency_records`, `ballots`, `outbox_events(VoteAccepted)`. Penolakan bisnis menulis `VoteRejected` (alasan saja) pada transaksi singkat terpisah |

### 6.2 Receipt

- `receipt_id` acak; `receipt_code` = turunan HMAC dari `receipt_id` (dapat dibentuk ulang untuk replay tanpa disimpan).
- Receipt **tidak memuat** pilihan kandidat, `candidate_id`, identitas, atau `eligibility_ref`; `GET /ballots/receipt/{id}` hanya mengembalikan status penerimaan dan status audit.
- **Makna receipt:** membuktikan bahwa request suara **diterima sesuai rancangan** dan (bila `RECORDED`) tercatat di chain audit. Receipt **bukan** bukti kriptografis bahwa pilihan Anda dihitung dengan benar, **bukan** bukti pilihan, dan sistem **bukan** E2E-verifiable. `audit_status="RECORDED"` bukan "terverifikasi" (verifikasi lewat endpoint 18/23).
- Kontrak tidak pernah mengirim identitas lengkap pemilih bersama pilihan kandidat ke layanan mana pun, termasuk Audit.

---

## 7. Standard Error Schema

Skema [S-ERR]: `error.code` (kode mesin), `error.message` (Bahasa Indonesia, aman ditampilkan), `error.details` (array objek `{"field","issue"}`; boleh kosong), `error.request_id` (= `X-Request-ID`). Stack trace, SQL, nama tabel, secret, dan detail internal tidak pernah dikirim; detail hanya di log internal dengan `request_id`.

| Code | HTTP | Pemakaian |
|---|---|---|
| `VALIDATION_ERROR` | 422 | Input tidak valid, header wajib hilang, kandidat bukan milik pemilihan |
| `UNAUTHORIZED` | 401 | Token hilang/invalid/kedaluwarsa; kredensial salah |
| `FORBIDDEN` | 403 | Role tidak berwenang; Attack Lab nonaktif |
| `VOTER_NOT_ELIGIBLE` | 403 | Bukan pemilih sah |
| `VOTE_TICKET_INVALID` | 403 | Ticket rusak/kedaluwarsa/untuk pemilihan lain |
| `NOT_FOUND`, `RECEIPT_NOT_FOUND` | 404 | Resource tidak ada atau di luar hak akses |
| `VOTER_ALREADY_VOTED`, `IDEMPOTENCY_CONFLICT`, `ELECTION_NOT_OPEN`, `ELECTION_INVALID_STATE`, `RESULT_NOT_FINALIZED`, `AUDIT_VERIFICATION_FAILED`, `RECONCILIATION_FAILED`, `BALLOT_INTEGRITY_FAILED`, `CONFLICT` | 409 | Konflik state/duplikat/prasyarat |
| `ACCOUNT_LOCKED` | 423 | Akun terkunci sementara |
| `RATE_LIMIT_EXCEEDED` | 429 | Batas laju terlampaui (+ `Retry-After`) |
| `INTERNAL_ERROR` | 500 | Kesalahan tak terduga |
| `SERVICE_UNAVAILABLE` | 503 | Dependensi tidak tersedia (+ `Retry-After` bila diketahui) |

Kesalahan yang sama selalu memakai kode dan status yang sama pada semua layanan; layanan internal memakai skema yang sama.

---

## 8. Event Contract Specifications

### 8.1 Envelope (JSON Schema 2020-12)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://voxguard.local/schemas/event-envelope-1.0.json",
  "title": "EventEnvelope",
  "type": "object",
  "additionalProperties": false,
  "required": ["event_id", "event_type", "schema_version", "occurred_at", "producer", "correlation_id", "payload"],
  "properties": {
    "event_id": { "type": "string", "format": "uuid" },
    "event_type": {
      "enum": [
        "ElectionOpened", "ElectionClosed", "VoteAccepted", "VoteRejected", "AuditRecorded",
        "TallyCompleted", "ResultFinalized", "SecurityAlertRaised", "SecuritySignalObserved"
      ]
    },
    "schema_version": { "type": "string", "pattern": "^[0-9]+\\.[0-9]+$" },
    "occurred_at": { "type": "string", "format": "date-time" },
    "producer": { "enum": ["api-gateway", "auth-service", "voter-service", "ballot-service", "audit-service", "result-service", "security-service"] },
    "correlation_id": { "type": "string", "format": "uuid" },
    "payload": { "type": "object" }
  }
}
```

Contoh (`VoteAccepted`):

```json
{
  "event_id": "0c1d2e3f-4a5b-4c6d-8e7f-9a0b1c2d3e4f",
  "event_type": "VoteAccepted",
  "schema_version": "1.0",
  "occurred_at": "2026-10-12T08:20:11Z",
  "producer": "ballot-service",
  "correlation_id": "7a9c1e3f-5b7d-4f91-8a23-4c6e8a0b2d47",
  "payload": {
    "election_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
    "ballot_id": "f1b8d4e6-0a8b-4c26-9d35-8d7e2f1a6ca9",
    "receipt_id": "d9f6b2c4-8e69-4a04-b13c-6b5c0d9e4a87",
    "accepted_at": "2026-10-12T08:20:11Z",
    "ballot_commitment": "5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e",
    "eligibility_ref": "7c4e7c4e7c4e7c4e7c4e7c4e7c4e7c4e7c4e7c4e7c4e7c4e7c4e7c4e7c4e7c4e"
  }
}
```

`event_id` = `outbox_events.id`; `producer` = nama layanan penerbit; `correlation_id` dari `X-Correlation-ID`. Contoh payload event lain: `API_CONTRACTS.md` E.2 (tambahkan `producer` sesuai tabel di bawah).

### 8.2 Payload minimal, producer, consumer

| Event | Producer | Consumer | Payload (field wajib) |
|---|---|---|---|
| `ElectionOpened` | voter-service | ballot, audit, security | `election_id`, `title`, `opened_at`, `end_at` |
| `ElectionClosed` | voter-service | ballot, audit, security | `election_id`, `closed_at` |
| `VoteAccepted` | ballot-service | audit, voter, security | `election_id`, `ballot_id`, `receipt_id`, `accepted_at`, `ballot_commitment`, `eligibility_ref`\* |
| `VoteRejected` | ballot-service | security | `election_id` (nullable), `reason_code`, `client_fingerprint`, `rejected_at` |
| `AuditRecorded` | audit-service | ballot, security | `scope_id`, `source_event_id`, `source_event_type`, `sequence`, `event_hash`, `recorded_at` |
| `TallyCompleted` | result-service | audit, security | `election_id`, `tally_run_id`, `run_number`, `status`, `reconciliation_status`, `ballots_counted`, `ballot_set_digest` |
| `ResultFinalized` | result-service | audit, voter | `election_id`, `tally_run_id`, `result_hash`, `finalized_at` |
| `SecurityAlertRaised` | security-service | audit | `alert_id`, `rule_code`, `severity`, `election_id` (nullable), `title`, `raised_at` |
| `SecuritySignalObserved` *(tambahan arsitektur)* | api-gateway, auth-service (best-effort); audit-service (outbox) | security | `signal_type`, `source_service`, `client_fingerprint` (nullable), `election_id` (nullable), `observed_at` |

\* `eligibility_ref` hanya dikonsumsi Voter; Audit dan Security membuangnya lewat proyeksi allowlist. `reason_code` `VoteRejected` ∈ {`VOTER_ALREADY_VOTED`, `ELECTION_NOT_OPEN`, `VOTE_TICKET_INVALID`, `IDEMPOTENCY_CONFLICT`, `CANDIDATE_INVALID`}; `signal_type` ∈ {`RATE_LIMIT_EXCEEDED`, `TOKEN_INVALID`, `FORBIDDEN`, `LOGIN_FAILED`, `ACCOUNT_LOCKED`, `AUDIT_INTEGRITY_FAILED`}.

### 8.3 Minimisasi data

- **Tidak boleh** ada di event mana pun: `candidate_id` suara individual, `ballot_nonce`, email, nama, `user_id`, token, password. Baseline `VoteAccepted` **tidak** menyertakan pilihan maupun identitas.
- `eligibility_ref` (pseudonim) hanya pada `VoteAccepted` untuk Voter; konsumen lain wajib membuangnya. Menyertakan data tambahan memerlukan alasan terdokumentasi dan persetujuan (**OPEN DECISION** per kasus).
- Proyeksi allowlist Audit: `04_…` Bagian 7.1 dan SAD Bagian 11–12.

### 8.4 Pengiriman, duplikasi, retry, DLQ

| Aspek | Kebijakan |
|---|---|
| Penerbitan | Transactional outbox; at-least-once; relay `SKIP LOCKED` dengan publisher confirms; sinyal Gateway/Auth best-effort |
| Duplicate delivery | Tiap konsumen idempotent: `processed_events(event_id, consumer)` dalam transaksi yang sama dengan efek, atau unique alami (`audit_events.source_event_id`, `security_events.event_id`, `audit_acks.source_event_id`) |
| Retry | Antrean retry bertingkat (**PROPOSED**: 5 s, 30 s, 120 s); percobaan ke-4 gagal → `<queue>.dlq` |
| DLQ | Tidak dikonsumsi otomatis; dipantau (aturan R-09); replay manual aman karena idempotent. Skema tidak valid/versi tak dikenal → langsung DLQ |
| Urutan | Tidak dijamin lintas agregat; konsumen tidak boleh bergantung pada urutan global |
| Validasi | Konsumen memvalidasi envelope dan payload terhadap skema `event_type` + `schema_version` |

---

## 9. OpenAPI Requirements

Spesifikasi OpenAPI 3.1 (dihasilkan FastAPI per layanan, digabung bila perlu) harus memuat:

| Elemen | Ketentuan |
|---|---|
| `paths` | Seluruh endpoint Bagian 4 dengan `operationId` unik (`camelCase`, mis. `castBallot`), `tags`, `summary`, dan ekstensi `x-roles` (sumber matriks uji RBAC) |
| `components/schemas` | Semua skema [S-xx], `ErrorResponse`, `Page`, `EventEnvelope`, payload event; JSON Schema 2020-12 (`type: ["string","null"]` untuk nullable); `additionalProperties: false` pada request |
| `securitySchemes` | `bearerAuth` (http bearer JWT); `receiptCode` (apiKey header `X-Receipt-Code`) |
| `parameters` | `RequestId`, `IdempotencyKey`, `PageParam`, `PageSizeParam`, `SortParam` |
| `responses` | Reusable `Unauthorized`, `Forbidden`, `NotFound`, `ValidationError`, `Conflict`, `RateLimited`, `ServiceUnavailable` berskema `ErrorResponse` |
| `examples` | Minimal satu contoh sukses dan satu contoh error per endpoint; harus lolos validasi terhadap skemanya |
| `tags` | `Auth`, `Elections`, `Ballots`, `Audit`, `Results`, `Security` |
| Versioning | `info.version` mengikuti kontrak (`1.x`); `servers` menyatakan prefix `/api/v1` |
| Pengecualian | Endpoint `/internal/v1/*` dan health tidak muncul di spesifikasi publik |

Untuk tugas dokumentasi ini tidak dibuat berkas OpenAPI terpisah.

---

## 10. Contract Testing and Versioning

| Topik | Ketetapan |
|---|---|
| Validasi skema | Respons dan request tiap endpoint divalidasi terhadap OpenAPI di test (CT-01) |
| Consumer-driven contract | Frontend dan konsumen internal (Result→Ballot/Audit/Voter) mendefinisikan harapan; provider memverifikasinya (CT-02). Bila alat khusus belum dipakai, cukup tes HTTPX yang membaca contoh dari kontrak (usulan) |
| Compatibility | Tes memastikan perubahan aditif tidak mematahkan klien lama (CT-03); diff skema OpenAPI antar commit dijalankan di CI (usulan) |
| Perubahan *breaking* | Hanya via `v2`; `v1` dipertahankan selama masa transisi (OPEN DECISION durasi); header `Deprecation`/`Sunset` diberikan |
| Versioning event | `schema_version` `major.minor`; minor aditif; major baru diterbitkan berdampingan sampai semua konsumen siap; konsumen menolak major tak dikenal ke DLQ |
| Pengujian negatif | Setiap endpoint diuji untuk 401/403/404/409/422 (CT-04, API-RBAC-01) |
| Sinkronisasi FE–BE | Tipe frontend dibangkitkan/diperiksa dari OpenAPI; perubahan kontrak lewat PR dokumen ini + tinjauan pemilik terdampak (CT-05) |

ID test didefinisikan di `07_TEST_PLAN_ACCEPTANCE_CRITERIA.md`; semua berstatus PLANNED.

---

## 11. API Acceptance Checklist

| # | Pemeriksaan | Status |
|---|---|---|
| 1 | Semua 27 endpoint + `schedule` ada di OpenAPI dengan `operationId`, `x-roles`, skema request/response | ☐ |
| 2 | Prefix `/api/v1` konsisten; internal hanya `/internal/v1` dan tidak dirutekan Gateway | ☐ |
| 3 | Tiap endpoint memakai error schema [S-ERR] dan kode yang tercantum | ☐ |
| 4 | `POST /ballots` mewajibkan `Idempotency-Key`; skenario paralel/retry sesuai Bagian 6 | ☐ |
| 5 | Receipt dan semua respons tidak memuat `candidate_id`, identitas, `eligibility_ref` | ☐ |
| 6 | Event memuat `event_id`, `event_type`, `schema_version`, `occurred_at`, `producer`, `correlation_id`, `payload`; payload minimal | ☐ |
| 7 | Matriks role × endpoint (Bagian 3) lolos API-RBAC-01 | ☐ |
| 8 | Tidak ada endpoint ubah/hapus suara, audit, atau hasil final | ☐ |
| 9 | Request ID/Correlation ID muncul di respons, log, dan event | ☐ |
| 10 | Contoh JSON valid terhadap skema; tidak ada stack trace/detail internal pada error | ☐ |
| 11 | Frontend dan backend memakai kontrak yang sama (CT-05) | ☐ |

Seluruh kotak kosong: belum ada yang diverifikasi.

---

## 12. Konflik dan Keputusan Terbuka

| ID | Catatan | Penyelesaian yang disarankan |
|---|---|---|
| C-API-01 | Envelope event di SAD 11.1 dan `API_CONTRACTS.md` E.1 **tidak memuat `producer`**, sedangkan kebutuhan kontrak ini mewajibkannya | Pakai envelope di Bagian 8.1 (`producer` wajib, `schema_version` `1.0` karena belum ada implementasi). Perbarui SAD 11.1 dan `API_CONTRACTS.md` E pada revisi berikutnya |
| C-API-02 | `POST /elections/{id}/schedule` dan event `SecuritySignalObserved` bukan bagian baseline prompt | Dipertahankan (alasan: BR-003, kebutuhan Security); sudah ada di SAD/SRS |
| C-API-03 | Kode error tambahan (`ELECTION_INVALID_STATE`, `VOTE_TICKET_INVALID`, dll.) di luar daftar awal | Dipertahankan; konsisten di SRS Bagian 13 |
| OD-05 | Autentikasi antar-layanan: satu kunci atau per pemanggil | Usulan: per pemanggil bila waktu cukup |
| OD-08 | `proof` dan `verify` hasil memerlukan login atau publik | Usulan MVP: wajib login |
| OD-24 | Durasi dukungan `v1` setelah `v2` | Tentukan saat ada perubahan breaking |
