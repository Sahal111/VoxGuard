# VoxGuard — API Contracts

| Atribut | Nilai |
|---|---|
| Dokumen | `docs/API_CONTRACTS.md` |
| Versi | 0.1 — draft untuk review tim |
| Status | Rancangan kontrak; belum diimplementasikan. Semua nilai contoh (UUID, hash, email, token) adalah **fiktif** |
| Terkait | `ARCHITECTURE.md` (service, tabel, event), `SECURITY_AND_TEST_PLAN.md` (ATK, test), `PROJECT_BRIEF.md` (FR) |

---

## A. API Conventions

| # | Topik | Aturan |
|---|---|---|
| A.1 | Prefix | Semua endpoint publik di bawah `/api/v1`. Gateway meneruskan path **tanpa rewrite**; setiap service melayani path yang sama. Endpoint internal di `/internal/v1/*` (tidak dirutekan Gateway) |
| A.2 | Format | JSON UTF-8 (`Content-Type: application/json`) untuk request dan response; field `snake_case`; field tak dikenal ditolak (`extra="forbid"`) |
| A.3 | ID | UUID string huruf kecil (v4), mis. `6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3` |
| A.4 | Waktu | ISO 8601 UTC dengan akhiran `Z`, mis. `2026-10-12T08:00:00Z` |
| A.5 | Autentikasi | `Authorization: Bearer <access_token>` (JWT HS256, TTL usulan 15 menit). Refresh token hanya dikirim di body `POST /auth/refresh` dan `/auth/logout`. Endpoint publik: `register`, `login`, `refresh`, `GET /ballots/receipt/{id}` (dengan `X-Receipt-Code`) |
| A.6 | Otorisasi | Role `ADMIN`, `VOTER`, `AUDITOR` dari klaim `role`; diperiksa di Gateway **dan** service (B.0). Gateway menambahkan `X-User-Id`, `X-User-Role`, `X-User-Email`, `X-Internal-Key`, `X-Client-Fingerprint`; header ini dari klien selalu dibuang. Untuk `POST /ballots` hanya `X-User-Role` yang diteruskan |
| A.7 | Request/Correlation ID | `X-Request-ID` (UUID) dibuat Gateway bila tidak ada/invalid, dikembalikan di setiap response dan masuk `error.request_id`. `X-Correlation-ID` diteruskan antar-service dan dimasukkan ke event |
| A.8 | Pagination | Query `page` (default 1) dan `page_size` (default 20, maks 100). Response: `{"items":[...],"page":{"page":1,"page_size":20,"total":57}}` |
| A.9 | Rate limit (**target awal, perlu kalibrasi**) | Default 120 req/menit/IP; `POST /auth/login` 10/menit/IP dan lockout akun setelah 5 gagal dalam 15 menit selama 15 menit; `POST /auth/register` 10/jam/IP; `POST /ballots` 10/menit/IP; `GET /ballots/receipt/*` 30/menit/IP; `POST /security/attacks/run` 5/menit. Response `429` + header `Retry-After` |
| A.10 | Idempotency | Header `Idempotency-Key` **wajib** pada `POST /ballots`: 16–64 karakter `[A-Za-z0-9_-]` (UUID v4 disarankan). Key dibatasi per hak memilih. Replay → `200` + `Idempotent-Replayed: true`. Endpoint lain tidak memakai idempotency key; transisi lifecycle bersifat idempoten lewat guard status |
| A.11 | Batas body | Default 64 KB; `voters/import` 1 MB (maks 1.000 baris) |
| A.12 | Versi OpenAPI | Kontrak ditulis agar dapat diterjemahkan ke OpenAPI 3.1 (Bagian F) |

### A.13 HTTP status code

| Kode | Pemakaian |
|---|---|
| 200 | Sukses, termasuk replay idempoten |
| 201 | Resource/suara dibuat |
| 202 | Pekerjaan asinkron diterima (Attack Lab) |
| 204 | Sukses tanpa body (logout) |
| 401 | `UNAUTHORIZED` (token hilang/invalid/kedaluwarsa, login gagal) |
| 403 | `FORBIDDEN`, `VOTER_NOT_ELIGIBLE`, `VOTE_TICKET_INVALID` |
| 404 | `NOT_FOUND`, `RECEIPT_NOT_FOUND` |
| 409 | Konflik state/idempotency/duplikat |
| 422 | `VALIDATION_ERROR` |
| 423 | `ACCOUNT_LOCKED` |
| 429 | `RATE_LIMIT_EXCEEDED` |
| 500 | `INTERNAL_ERROR` |
| 503 | `SERVICE_UNAVAILABLE` |

---

## B. Endpoint Inventory

### B.0 Matriks role × endpoint (dasar API-RBAC-01)

`—` = ditolak (401 bila tanpa token, 403 bila role salah). `●` = diizinkan. `●*` = diizinkan dengan syarat di kolom catatan.

| Endpoint | Service | Anon | VOTER | AUDITOR | ADMIN | Catatan |
|---|---|---|---|---|---|---|
| `POST /auth/register` | auth | ●* | ●* | ●* | ● | Tanpa field `role` → membuat VOTER; field `role` hanya sah bila pemanggil ADMIN |
| `POST /auth/login` | auth | ● | ● | ● | ● | |
| `POST /auth/refresh` | auth | ● | ● | ● | ● | Berbasis refresh token |
| `POST /auth/logout` | auth | — | ● | ● | ● | |
| `GET /auth/me` | auth | — | ● | ● | ● | |
| `POST /elections` | voter | — | — | — | ● | |
| `GET /elections` | voter | — | ●* | ● | ● | VOTER hanya election tempat ia terdaftar dan bukan DRAFT; AUDITOR bukan DRAFT |
| `GET /elections/{id}` | voter | — | ●* | ●* | ● | Sama; di luar hak → `404` |
| `POST /elections/{id}/candidates` | voter | — | — | — | ● | |
| `POST /elections/{id}/voters/import` | voter | — | — | — | ● | |
| `POST /elections/{id}/schedule` | voter | — | — | — | ● | *Endpoint tambahan* untuk `DRAFT→SCHEDULED` |
| `POST /elections/{id}/open` | voter | — | — | — | ● | |
| `POST /elections/{id}/close` | voter | — | — | — | ● | |
| `GET /elections/{id}/ballot` | ballot | — | ● | — | — | ADMIN/AUDITOR tidak memilih |
| `POST /ballots` | ballot | — | ● | — | — | |
| `GET /ballots/receipt/{id}` | ballot | ●* | ●* | ●* | ●* | Wajib `X-Receipt-Code` yang benar |
| `GET /audit/events` | audit | — | — | ● | ● | |
| `GET /audit/elections/{id}/verify` | audit | — | — | ● | ● | |
| `GET /audit/elections/{id}/proof` | audit | — | ● | ● | ● | OD-08 |
| `POST /results/elections/{id}/tally` | result | — | — | — | ● | |
| `POST /results/elections/{id}/finalize` | result | — | — | — | ● | |
| `GET /results/elections/{id}` | result | — | ●* | ● | ● | VOTER hanya bila FINAL, selain itu `RESULT_NOT_FINALIZED` |
| `GET /results/elections/{id}/verify` | result | — | ●* | ● | ● | VOTER hanya bila FINAL |
| `GET /security/alerts` | security | — | — | ● | ● | |
| `POST /security/attacks/run` | security | — | — | — | ● | Hanya bila Attack Lab aktif |
| `GET /security/attacks/{id}` | security | — | — | — | ● | |
| `GET /security/metrics` | security | — | — | ● | ● | |

Tidak ada endpoint `PUT`/`PATCH`/`DELETE` untuk `ballots`, `audit_events`, `tally_*`, maupun `final_results`. Metode lain pada path ini → `404`/`405`.

### B.1 Auth Service

#### POST `/api/v1/auth/register`

| Item | Isi |
|---|---|
| Service pemilik | auth-service |
| Deskripsi | Membuat akun. Tanpa `role` → `VOTER` |
| Role | Anon (VOTER); ADMIN untuk membuat `ADMIN`/`AUDITOR` |
| Request body | `email` (format email, ≤ 254), `password` (12–128 karakter), `display_name` (1–100), `role` (opsional) |
| Validasi penting | Email dinormalisasi lowercase; `role` ∈ {ADMIN,VOTER,AUDITOR} dan hanya oleh ADMIN; password tidak pernah dicatat |
| Efek database | `auth_db.users` INSERT (Argon2id) |
| Event | Tidak ada |
| Error | `409 CONFLICT` (email terdaftar), `403 FORBIDDEN` (role oleh non-ADMIN), `422 VALIDATION_ERROR`, `429` |

```json
{
  "email": "andi@example.test",
  "password": "contoh-password-panjang-123",
  "display_name": "Andi Contoh"
}
```

Response `201`:

```json
{
  "id": "c3e5a1b9-7d58-4f93-a02b-5a4b9c8d3f76",
  "email": "andi@example.test",
  "display_name": "Andi Contoh",
  "role": "VOTER",
  "created_at": "2026-10-10T07:00:00Z"
}
```

#### POST `/api/v1/auth/login`

| Item | Isi |
|---|---|
| Service pemilik | auth-service |
| Deskripsi | Autentikasi; menerbitkan access token + refresh token |
| Role | Anon |
| Request body | `email`, `password` |
| Validasi penting | Cek lockout sebelum verifikasi; pesan kegagalan generik; penambahan `failed_login_count` |
| Efek database | `refresh_sessions` INSERT; `users.last_login_at`, `failed_login_count`, `locked_until` UPDATE |
| Event | `SecuritySignalObserved` (`LOGIN_FAILED`, `ACCOUNT_LOCKED`) — best-effort |
| Error | `401 UNAUTHORIZED`, `423 ACCOUNT_LOCKED`, `422 VALIDATION_ERROR`, `429 RATE_LIMIT_EXCEEDED` |

Response `200`:

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiJ9.contoh.signature",
  "token_type": "Bearer",
  "expires_in": 900,
  "refresh_token": "contoh-refresh-token-acak",
  "user": {
    "id": "c3e5a1b9-7d58-4f93-a02b-5a4b9c8d3f76",
    "email": "andi@example.test",
    "display_name": "Andi Contoh",
    "role": "VOTER"
  }
}
```

#### POST `/api/v1/auth/refresh`

| Item | Isi |
|---|---|
| Service pemilik | auth-service |
| Deskripsi | Menukar refresh token dengan pasangan token baru (rotasi) |
| Role | Anon (berbasis refresh token) |
| Request body | `refresh_token` |
| Validasi penting | Hash cocok, belum kedaluwarsa/revoked; token yang sudah dirotasi dipakai lagi → seluruh `family_id` direvokasi |
| Efek database | `refresh_sessions`: sesi lama `rotated_at`, sesi baru INSERT (atau revoke family) |
| Event | `SecuritySignalObserved` (`TOKEN_INVALID`, best-effort) pada reuse |
| Error | `401 UNAUTHORIZED`, `422`, `429` |

Response `200`: sama dengan bentuk login (tanpa objek `user` boleh dihilangkan).

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiJ9.contoh2.signature",
  "token_type": "Bearer",
  "expires_in": 900,
  "refresh_token": "contoh-refresh-token-baru"
}
```

#### POST `/api/v1/auth/logout`

| Item | Isi |
|---|---|
| Service pemilik | auth-service |
| Deskripsi | Mencabut sesi refresh dan memasukkan `jti` access token ke denylist |
| Role | VOTER, AUDITOR, ADMIN |
| Request body | `refresh_token` |
| Efek database | `refresh_sessions.revoked_at` UPDATE; Redis `deny:jti:<jti>` hingga `exp` |
| Event | Tidak ada |
| Error | `401 UNAUTHORIZED`, `422` |

Response `204` (tanpa body).

#### GET `/api/v1/auth/me`

| Item | Isi |
|---|---|
| Service pemilik | auth-service |
| Role | VOTER, AUDITOR, ADMIN |
| Efek database | Baca `users` |
| Event | Tidak ada |
| Error | `401 UNAUTHORIZED` |

```json
{
  "id": "c3e5a1b9-7d58-4f93-a02b-5a4b9c8d3f76",
  "email": "andi@example.test",
  "display_name": "Andi Contoh",
  "role": "VOTER"
}
```

### B.2 Voter Service (Election)

#### POST `/api/v1/elections`

| Item | Isi |
|---|---|
| Service pemilik | voter-service |
| Deskripsi | Membuat election berstatus `DRAFT` |
| Role | ADMIN |
| Request body | `title` (3–150), `description` (≤ 2000), `start_at`, `end_at`, `is_attack_lab` (default false) |
| Validasi penting | `start_at < end_at`; `is_attack_lab=true` hanya bila Attack Lab aktif, jika tidak `403 FORBIDDEN` |
| Efek database | `voter_db.elections` INSERT |
| Event | Tidak ada |
| Error | `401`, `403`, `422` |

```json
{
  "title": "Pemilihan Ketua Kelas 3A",
  "description": "Simulasi pemilihan ketua kelas",
  "start_at": "2026-10-12T08:00:00Z",
  "end_at": "2026-10-12T10:00:00Z",
  "is_attack_lab": false
}
```

Response `201`:

```json
{
  "id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
  "title": "Pemilihan Ketua Kelas 3A",
  "description": "Simulasi pemilihan ketua kelas",
  "status": "DRAFT",
  "start_at": "2026-10-12T08:00:00Z",
  "end_at": "2026-10-12T10:00:00Z",
  "is_attack_lab": false,
  "created_at": "2026-10-10T07:10:00Z"
}
```

#### GET `/api/v1/elections`

| Item | Isi |
|---|---|
| Service pemilik | voter-service |
| Deskripsi | Daftar election (terfilter menurut role, lihat B.0) |
| Role | ADMIN, AUDITOR, VOTER |
| Query | `status` (opsional), `page`, `page_size` |
| Efek database | Baca `elections` (+ `voters` untuk VOTER via email/`user_id`) |
| Event | Tidak ada |
| Error | `401`, `422` |

```json
{
  "items": [
    {
      "id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
      "title": "Pemilihan Ketua Kelas 3A",
      "status": "OPEN",
      "start_at": "2026-10-12T08:00:00Z",
      "end_at": "2026-10-12T10:00:00Z"
    }
  ],
  "page": { "page": 1, "page_size": 20, "total": 1 }
}
```

#### GET `/api/v1/elections/{id}`

| Item | Isi |
|---|---|
| Service pemilik | voter-service |
| Deskripsi | Detail election + kandidat; ADMIN/AUDITOR juga mendapat `voter_count` dan `participation_count` |
| Role | ADMIN, AUDITOR, VOTER (terbatas) |
| Efek database | Baca |
| Event | Tidak ada |
| Error | `401`, `404 NOT_FOUND` (termasuk di luar hak akses), `422` |

```json
{
  "id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
  "title": "Pemilihan Ketua Kelas 3A",
  "description": "Simulasi pemilihan ketua kelas",
  "status": "OPEN",
  "start_at": "2026-10-12T08:00:00Z",
  "end_at": "2026-10-12T10:00:00Z",
  "opened_at": "2026-10-12T08:00:30Z",
  "closed_at": null,
  "finalized_at": null,
  "candidates": [
    { "id": "a1c4e8f2-5b36-4d71-8c09-3e2f7a6b1d54", "name": "Calon A", "description": "Visi A", "ballot_order": 1 },
    { "id": "b7d2f9a3-6c47-4e82-9d1a-4f3a8b7c2e65", "name": "Calon B", "description": "Visi B", "ballot_order": 2 }
  ],
  "voter_count": 30,
  "participation_count": 12
}
```

#### POST `/api/v1/elections/{id}/candidates`

| Item | Isi |
|---|---|
| Service pemilik | voter-service |
| Deskripsi | Menambah kandidat |
| Role | ADMIN |
| Request body | `name` (1–100), `description` (≤ 1000), `ballot_order` (≥ 1) |
| Validasi penting | Hanya saat `DRAFT`; `UNIQUE(election_id, name)` dan `UNIQUE(election_id, ballot_order)` |
| Efek database | `candidates` INSERT |
| Event | Tidak ada |
| Error | `403`, `404`, `409 ELECTION_INVALID_STATE`, `409 CONFLICT`, `422` |

```json
{ "name": "Calon A", "description": "Visi A", "ballot_order": 1 }
```

Response `201`:

```json
{
  "id": "a1c4e8f2-5b36-4d71-8c09-3e2f7a6b1d54",
  "election_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
  "name": "Calon A",
  "description": "Visi A",
  "ballot_order": 1
}
```

#### POST `/api/v1/elections/{id}/voters/import`

| Item | Isi |
|---|---|
| Service pemilik | voter-service |
| Deskripsi | Mengimpor daftar pemilih (all-or-nothing) |
| Role | ADMIN |
| Request body | `voters[]` berisi `email`, `external_ref`, `display_label` (1–1.000 baris) |
| Validasi penting | Hanya saat `DRAFT`; email unik per election; `external_ref` unik per election; data uji fiktif |
| Efek database | `voters` INSERT; **belum** membuat `voting_eligibility` (dibuat saat `schedule`) |
| Event | Tidak ada |
| Error | `403`, `404`, `409 ELECTION_INVALID_STATE`, `422 VALIDATION_ERROR` (detail per indeks baris) |

```json
{
  "voters": [
    { "email": "andi@example.test", "external_ref": "NIM-0001", "display_label": "Andi Contoh" },
    { "email": "sari@example.test", "external_ref": "NIM-0002", "display_label": "Sari Contoh" }
  ]
}
```

Response `201`:

```json
{ "election_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3", "imported": 2 }
```

#### POST `/api/v1/elections/{id}/schedule` *(tambahan)*

| Item | Isi |
|---|---|
| Service pemilik | voter-service |
| Deskripsi | `DRAFT → SCHEDULED`; membekukan kandidat dan daftar pemilih |
| Role | ADMIN |
| Request body | Tidak ada |
| Validasi penting | ≥ 2 kandidat; ≥ 1 pemilih; `start_at < end_at`; `end_at` masa depan |
| Efek database | `elections.status`; `voting_eligibility` INSERT (satu per pemilih dengan `eligibility_ref`) |
| Event | Tidak ada |
| Error | `403`, `404`, `409 ELECTION_INVALID_STATE`, `422 VALIDATION_ERROR` |

Response `200`: `{"id":"6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3","status":"SCHEDULED"}`

```json
{ "id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3", "status": "SCHEDULED" }
```

#### POST `/api/v1/elections/{id}/open`

| Item | Isi |
|---|---|
| Service pemilik | voter-service |
| Deskripsi | `SCHEDULED → OPEN` |
| Role | ADMIN |
| Validasi penting | Status `SCHEDULED`; `now < end_at` |
| Efek database | `elections.status`, `opened_at`; `outbox_events` INSERT (satu transaksi) |
| Event | `ElectionOpened` |
| Error | `403`, `404`, `409 ELECTION_INVALID_STATE` |

```json
{ "id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3", "status": "OPEN", "opened_at": "2026-10-12T08:00:30Z" }
```

#### POST `/api/v1/elections/{id}/close`

| Item | Isi |
|---|---|
| Service pemilik | voter-service |
| Deskripsi | `OPEN → CLOSED`; suara berikutnya ditolak |
| Role | ADMIN |
| Validasi penting | Status `OPEN` |
| Efek database | `elections.status`, `closed_at`; `outbox_events` INSERT |
| Event | `ElectionClosed` |
| Error | `403`, `404`, `409 ELECTION_INVALID_STATE` |

```json
{ "id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3", "status": "CLOSED", "closed_at": "2026-10-12T10:00:05Z" }
```

### B.3 Ballot Service

#### GET `/api/v1/elections/{id}/ballot`

| Item | Isi |
|---|---|
| Service pemilik | ballot-service |
| Deskripsi | Menyajikan kandidat dan menerbitkan **vote ticket** berpseudonim |
| Role | VOTER |
| Query | Tidak ada |
| Validasi penting | Ballot meneruskan `user_id`/`email` ke Voter hanya untuk penerbitan ticket (tidak disimpan/dilog); Voter memeriksa terdaftar, `OPEN`, `now ≤ end_at`, belum `VOTED` |
| Efek database | Ballot: tidak ada. Voter: `voting_eligibility.status=TICKET_ISSUED`, `ticket_issued_at` |
| Event | Tidak ada |
| Error | `401`, `403 FORBIDDEN`, `403 VOTER_NOT_ELIGIBLE`, `409 VOTER_ALREADY_VOTED`, `409 ELECTION_NOT_OPEN`, `404`, `503 SERVICE_UNAVAILABLE` |

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

#### POST `/api/v1/ballots`

| Item | Isi |
|---|---|
| Service pemilik | ballot-service |
| Deskripsi | Mengirim satu suara (lihat Bagian C) |
| Role | VOTER |
| Header wajib | `Authorization`, `Idempotency-Key` |
| Request body | `election_id`, `candidate_id`, `vote_ticket` |
| Validasi penting | Ticket valid (signature, `exp`, `aud`, `typ`, `election_id`); gate dan status election; `candidate_id` milik election; payload ketat |
| Efek database | Satu transaksi: `idempotency_records`, `ballots`, `outbox_events` (+ update snapshot) |
| Event | `VoteAccepted` (sukses); `VoteRejected` (penolakan bisnis) |
| Error | `401 UNAUTHORIZED`, `403 VOTE_TICKET_INVALID`, `409 ELECTION_NOT_OPEN`, `409 VOTER_ALREADY_VOTED`, `409 IDEMPOTENCY_CONFLICT`, `422 VALIDATION_ERROR`, `429`, `503` |

Request/response lengkap: Bagian C.

#### GET `/api/v1/ballots/receipt/{id}`

| Item | Isi |
|---|---|
| Service pemilik | ballot-service |
| Deskripsi | Bukti penerimaan suara. `{id}` = `receipt_id`. **Tidak memuat pilihan** |
| Role | Publik dengan header `X-Receipt-Code` |
| Validasi penting | `receipt_code` = HMAC turunan `receipt_id`; kode salah atau id tidak ada → `404 RECEIPT_NOT_FOUND` (tidak membedakan) |
| Efek database | Baca `ballots` (hanya `receipt_id`, `election_id`, `accepted_at`, `outbox_event_id`) dan `audit_acks` |
| Event | Tidak ada |
| Error | `404 RECEIPT_NOT_FOUND`, `422`, `429` |

```json
{
  "receipt_id": "d9f6b2c4-8e69-4a04-b13c-6b5c0d9e4a87",
  "election_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
  "status": "ACCEPTED",
  "accepted_at": "2026-10-12T08:20:11Z",
  "audit_status": "RECORDED",
  "audit": {
    "sequence": 14,
    "event_hash": "9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c",
    "recorded_at": "2026-10-12T08:20:13Z"
  }
}
```

`audit_status` ∈ {`PENDING`, `RECORDED`}; bila `PENDING`, `audit` bernilai `null`. `RECORDED` ≠ *terverifikasi* (verifikasi lewat `GET /audit/elections/{id}/verify`).

### B.4 Audit Service

#### GET `/api/v1/audit/events`

| Item | Isi |
|---|---|
| Service pemilik | audit-service |
| Deskripsi | Daftar entri audit (payload publik ter-allowlist) |
| Role | ADMIN, AUDITOR |
| Query | `election_id` (opsional; tanpa → scope GLOBAL), `event_type`, `from_sequence`, `to_sequence`, `page`, `page_size` |
| Efek database | Baca `audit_events` |
| Event | Tidak ada |
| Error | `401`, `403`, `422` |

```json
{
  "items": [
    {
      "id": "e0a7c3d5-9f7a-4b15-8c24-7c6d1e0f5b98",
      "scope_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
      "sequence": 14,
      "source_event_id": "0c1d2e3f-4a5b-4c6d-8e7f-9a0b1c2d3e4f",
      "source_event_type": "VoteAccepted",
      "occurred_at": "2026-10-12T08:20:11Z",
      "recorded_at": "2026-10-12T08:20:13Z",
      "payload_public": {
        "election_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
        "ballot_id": "f1b8d4e6-0a8b-4c26-9d35-8d7e2f1a6ca9",
        "receipt_id": "d9f6b2c4-8e69-4a04-b13c-6b5c0d9e4a87",
        "accepted_at": "2026-10-12T08:20:11Z",
        "ballot_commitment": "5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e"
      },
      "prev_hash": "1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b",
      "event_hash": "9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c"
    }
  ],
  "page": { "page": 1, "page_size": 20, "total": 14 }
}
```

#### GET `/api/v1/audit/elections/{id}/verify`

| Item | Isi |
|---|---|
| Service pemilik | audit-service |
| Deskripsi | Menghitung ulang seluruh hash chain scope election dan membandingkan dengan checkpoint terbaru |
| Role | ADMIN, AUDITOR |
| Validasi penting | `{id}` UUID; kegagalan verifikasi dilaporkan di body (`200`), bukan sebagai error HTTP |
| Efek database | `integrity_checks` INSERT |
| Event | `SecuritySignalObserved` (`AUDIT_INTEGRITY_FAILED`) bila `INVALID` (outbox) |
| Error | `401`, `403`, `404`, `422` |

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

Contoh bila gagal (`status=INVALID`): `first_failure` = `{"sequence": 7, "reason": "EVENT_HASH_MISMATCH"}`; nilai `reason` ∈ {`EVENT_HASH_MISMATCH`, `PREV_HASH_MISMATCH`, `SEQUENCE_GAP`, `CHECKPOINT_MISMATCH`, `HEAD_MISMATCH`}.

#### GET `/api/v1/audit/elections/{id}/proof`

| Item | Isi |
|---|---|
| Service pemilik | audit-service |
| Deskripsi | Bukti audit yang aman dipublikasikan: parameter chain, head, checkpoint, hasil verifikasi terakhir; opsional bukti inklusi suatu receipt |
| Role | ADMIN, AUDITOR, VOTER |
| Query | `receipt_id` (opsional) |
| Validasi penting | Hanya data ter-allowlist; tidak ada identitas, `eligibility_ref`, `candidate_id`, nonce |
| Efek database | Baca `audit_events`, `audit_checkpoints`, `integrity_checks` |
| Event | Tidak ada |
| Error | `401`, `404`, `422` |

```json
{
  "election_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
  "hash_algorithm": "SHA-256",
  "canonicalization": "JSON kunci terurut, tanpa spasi, UTF-8, timestamp UTC mikrodetik",
  "genesis_hash": "0000000000000000000000000000000000000000000000000000000000000000",
  "event_count": 14,
  "head_sequence": 14,
  "head_hash": "9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c",
  "latest_checkpoint": {
    "sequence": 14,
    "event_hash": "9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c",
    "reason": "ELECTION_CLOSED",
    "created_at": "2026-10-12T10:00:06Z"
  },
  "last_verified": { "status": "VALID", "checked_at": "2026-10-12T10:30:00Z" },
  "receipt_event": {
    "sequence": 14,
    "prev_hash": "1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b",
    "event_hash": "9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c"
  }
}
```

`receipt_event` bernilai `null` bila `receipt_id` tidak diberikan atau belum tercatat.

### B.5 Result Service

#### POST `/api/v1/results/elections/{id}/tally`

| Item | Isi |
|---|---|
| Service pemilik | result-service |
| Deskripsi | Menjalankan penghitungan dan rekonsiliasi (sinkron pada skala MVP) |
| Role | ADMIN |
| Request body | Tidak ada |
| Validasi penting | Election `CLOSED` dan belum ada `final_results`; hitung ulang per kandidat dari ekspor Ballot (`accepted_at ≤ closed_at`); cocokkan `ballot_commitment`; B = A = V |
| Efek database | `tally_runs`, `tally_items` INSERT; `outbox_events` INSERT |
| Event | `TallyCompleted` |
| Error | `403`, `404`, `409 ELECTION_INVALID_STATE`, `409 RECONCILIATION_FAILED`, `409 BALLOT_INTEGRITY_FAILED`, `503` |

Response `201` (`status` ∈ `COMPLETED`, atau `RECONCILIATION_FAILED`/`INTEGRITY_FAILED` yang juga disimpan dan dikembalikan sebagai `409` dengan `details`):

```json
{
  "tally_run_id": "2c4e6a81-3d5f-4b79-8c9b-1d3f5a7b9ea2",
  "election_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
  "run_number": 1,
  "status": "COMPLETED",
  "reconciliation": {
    "status": "MATCH",
    "ballots_counted": 12,
    "audit_vote_events": 12,
    "voter_participation": 12,
    "ballot_set_digest": "5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e"
  },
  "items": [
    { "candidate_id": "a1c4e8f2-5b36-4d71-8c09-3e2f7a6b1d54", "candidate_name": "Calon A", "vote_count": 7 },
    { "candidate_id": "b7d2f9a3-6c47-4e82-9d1a-4f3a8b7c2e65", "candidate_name": "Calon B", "vote_count": 5 }
  ],
  "completed_at": "2026-10-12T10:05:00Z"
}
```

*(Nilai pada contoh hanya ilustrasi format, bukan hasil pengujian.)*

#### POST `/api/v1/results/elections/{id}/finalize`

| Item | Isi |
|---|---|
| Service pemilik | result-service |
| Deskripsi | Finalisasi hasil immutable |
| Role | ADMIN |
| Request body | `tally_run_id` |
| Validasi penting | Tally `COMPLETED`+`MATCH`; panggil verifikasi Audit dan harus `VALID`; belum ada `final_results` |
| Efek database | `final_results` INSERT (append-only) + `outbox_events` INSERT dalam satu transaksi |
| Event | `ResultFinalized` |
| Error | `403`, `404`, `409 ELECTION_INVALID_STATE`, `409 RECONCILIATION_FAILED`, `409 AUDIT_VERIFICATION_FAILED`, `422`, `503` |

```json
{ "tally_run_id": "2c4e6a81-3d5f-4b79-8c9b-1d3f5a7b9ea2" }
```

Response `200`:

```json
{
  "election_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
  "tally_run_id": "2c4e6a81-3d5f-4b79-8c9b-1d3f5a7b9ea2",
  "status": "FINAL",
  "result_hash": "1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b",
  "finalized_at": "2026-10-12T10:10:00Z"
}
```

#### GET `/api/v1/results/elections/{id}`

| Item | Isi |
|---|---|
| Service pemilik | result-service |
| Deskripsi | Hasil. ADMIN/AUDITOR: sementara (`PROVISIONAL`, dari tally terakhir) atau `FINAL`. VOTER: hanya `FINAL` |
| Role | ADMIN, AUDITOR, VOTER |
| Efek database | Baca `tally_*`, `final_results` |
| Event | Tidak ada |
| Error | `401`, `404`, `409 RESULT_NOT_FINALIZED` (VOTER/belum ada tally) |

```json
{
  "election_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
  "status": "FINAL",
  "tally_run_id": "2c4e6a81-3d5f-4b79-8c9b-1d3f5a7b9ea2",
  "total_ballots": 12,
  "items": [
    { "candidate_id": "a1c4e8f2-5b36-4d71-8c09-3e2f7a6b1d54", "candidate_name": "Calon A", "vote_count": 7 },
    { "candidate_id": "b7d2f9a3-6c47-4e82-9d1a-4f3a8b7c2e65", "candidate_name": "Calon B", "vote_count": 5 }
  ],
  "ballot_set_digest": "5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e",
  "result_hash": "1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b",
  "finalized_at": "2026-10-12T10:10:00Z"
}
```

#### GET `/api/v1/results/elections/{id}/verify`

| Item | Isi |
|---|---|
| Service pemilik | result-service |
| Deskripsi | Menghitung ulang dari ekspor Ballot dan membandingkan dengan `final_results` dan chain audit (`ResultFinalized`) |
| Role | ADMIN, AUDITOR, VOTER |
| Validasi penting | Hanya election dengan `final_results`; VOTER tidak boleh sebelum FINAL |
| Efek database | Baca saja |
| Event | Tidak ada |
| Error | `401`, `404`, `409 RESULT_NOT_FINALIZED`, `503` |

```json
{
  "election_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
  "status": "MATCH",
  "checks": {
    "recount_matches_snapshot": true,
    "ballot_set_digest_matches": true,
    "commitments_match": true,
    "result_hash_matches": true,
    "audit_chain_valid": true,
    "result_hash_recorded_in_audit": true
  },
  "verified_at": "2026-10-12T11:00:00Z"
}
```

`status` ∈ {`MATCH`, `MISMATCH`}; rincian setiap pengecekan wajib ada agar penyebab mismatch dapat ditelusuri.

### B.6 Security Service

#### GET `/api/v1/security/alerts`

| Item | Isi |
|---|---|
| Service pemilik | security-service |
| Role | ADMIN, AUDITOR |
| Query | `severity`, `rule_code`, `election_id`, `resolved` (bool), `page`, `page_size` |
| Efek database | Baca `anomaly_alerts` |
| Event | Tidak ada |
| Error | `401`, `403`, `422` |

```json
{
  "items": [
    {
      "id": "0a2c4e6f-1b3d-4f57-8a79-9b1d3f5a7c80",
      "rule_code": "R-01",
      "severity": "MEDIUM",
      "election_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
      "title": "Percobaan double voting berulang",
      "description": "Beberapa penolakan VOTER_ALREADY_VOTED dari fingerprint klien yang sama",
      "evidence": { "client_fingerprint": "a1b2c3d4e5f60718293a4b5c", "count": 3, "window_minutes": 5 },
      "occurrence_count": 1,
      "first_seen_at": "2026-10-12T08:25:00Z",
      "last_seen_at": "2026-10-12T08:27:00Z",
      "resolved_at": null
    }
  ],
  "page": { "page": 1, "page_size": 20, "total": 1 }
}
```

#### POST `/api/v1/security/attacks/run`

| Item | Isi |
|---|---|
| Service pemilik | security-service |
| Deskripsi | Menjalankan satu skenario Attack Lab pada election lab |
| Role | ADMIN |
| Request body | `attack_id` (`ATK-01`..`ATK-10`), `parameters` (opsional; mis. `variant`, `concurrency`) |
| Validasi penting | `ATTACK_LAB_ENABLED=true` dan `APP_ENV` ∈ {local,test}, jika tidak `403 FORBIDDEN`; hanya satu run aktif (`409 CONFLICT`); target hanya election `is_attack_lab=true`; `concurrency` ≤ 100 |
| Efek database | `security_db.attack_runs` INSERT |
| Event | Tidak ada langsung; aksi simulasi memicu event bisnis/keamanan biasa |
| Error | `401`, `403`, `409 CONFLICT`, `422`, `429` |

```json
{ "attack_id": "ATK-02", "parameters": { "variant": "A", "concurrency": 50 } }
```

Response `202`:

```json
{
  "id": "1b3d5f70-2c4e-4a68-9b8a-0c2e4f6a8d91",
  "attack_id": "ATK-02",
  "status": "QUEUED",
  "election_id": null,
  "created_at": "2026-10-12T09:00:00Z"
}
```

#### GET `/api/v1/security/attacks/{id}`

| Item | Isi |
|---|---|
| Service pemilik | security-service |
| Role | ADMIN |
| Efek database | Baca `attack_runs` |
| Event | Tidak ada |
| Error | `401`, `403`, `404`, `422` |

```json
{
  "id": "1b3d5f70-2c4e-4a68-9b8a-0c2e4f6a8d91",
  "attack_id": "ATK-02",
  "status": "PASSED",
  "election_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
  "started_at": "2026-10-12T09:00:01Z",
  "finished_at": "2026-10-12T09:00:09Z",
  "steps": [
    {
      "step": "Kirim 50 request voting paralel",
      "expected": "tepat 1 suara diterima, tanpa 5xx",
      "actual": "diisi runner saat eksekusi",
      "passed": true
    }
  ],
  "result": { "passed": true, "summary": "diisi runner saat eksekusi" }
}
```

*(Contoh di atas hanya format; `actual` dan `summary` diisi hasil eksekusi nyata.)*

#### GET `/api/v1/security/metrics`

| Item | Isi |
|---|---|
| Service pemilik | security-service |
| Role | ADMIN, AUDITOR |
| Efek database | Baca `security_events`, `anomaly_alerts` + hasil polling |
| Event | Tidak ada |
| Error | `401`, `403` |

```json
{
  "generated_at": "2026-10-12T10:30:00Z",
  "alerts_open": { "LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0 },
  "votes": { "accepted_total": 0, "rejected_total": { "VOTER_ALREADY_VOTED": 0, "ELECTION_NOT_OPEN": 0, "VOTE_TICKET_INVALID": 0 } },
  "rate_limit_exceeded_total": 0,
  "outbox_pending_oldest_age_seconds": 0,
  "dlq_depth": { "audit.q.events.dlq": 0, "ballot.q.audit.dlq": 0 },
  "audit_lag_seconds": 0,
  "duplicates_dropped_total": 0
}
```

*(Nilai nol hanyalah bentuk skema, bukan hasil pengukuran.)*

### B.7 Endpoint internal (tidak dirutekan Gateway)

Autentikasi: header `X-Internal-Key` (OD-05) dan jaringan Docker internal. Tidak muncul di OpenAPI publik.

| Endpoint | Service | Pemanggil | Fungsi |
|---|---|---|---|
| `GET /internal/v1/elections/{id}/ballot-info` | voter | ballot | `status`, `accepting_votes`, `closed_at`, `end_at`, daftar kandidat |
| `POST /internal/v1/elections/{id}/eligibility/tickets` | voter | ballot | Menerbitkan vote ticket (body `user_id`, `email`) |
| `GET /internal/v1/elections/{id}/summary` | voter | result | `status`, `closed_at`, `voted_count`, `candidates[]` |
| `GET /internal/v1/elections/{id}/tally-export` | ballot | result | Halaman `{ballot_id, candidate_id, ballot_nonce, accepted_at}` (tanpa `eligibility_ref`) |
| `GET /internal/v1/elections/{id}/summary` | ballot | result | `accepted_count`, `ballot_set_digest`, `outbox_pending_count` |
| `GET /internal/v1/outbox/stats` | ballot | security | `pending_count`, `oldest_pending_age_seconds` |
| `GET /internal/v1/elections/{id}/summary` | audit | result | `vote_accepted_count`, `head_sequence`, `head_hash` |
| `GET /internal/v1/elections/{id}/commitments` | audit | result | Halaman `{ballot_id, ballot_commitment}` |
| `POST /internal/v1/elections/{id}/verify` | audit | result | Verifikasi chain; body hasil sama dengan `verify` publik |
| `POST /internal/v1/test/tamper`, `POST /internal/v1/test/restore` | audit | security (Attack Lab) | **Hanya** `APP_ENV` ∈ {local,test} dan `ATTACK_LAB_ENABLED=true`, hanya scope election lab |

Contoh `ballot-info`:

```json
{
  "election_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
  "status": "OPEN",
  "accepting_votes": true,
  "end_at": "2026-10-12T10:00:00Z",
  "closed_at": null,
  "candidates": [
    { "id": "a1c4e8f2-5b36-4d71-8c09-3e2f7a6b1d54", "name": "Calon A", "description": "Visi A", "ballot_order": 1 },
    { "id": "b7d2f9a3-6c47-4e82-9d1a-4f3a8b7c2e65", "name": "Calon B", "description": "Visi B", "ballot_order": 2 }
  ]
}
```

Setiap service juga menyediakan `GET /health/live` dan `GET /health/ready` (tanpa autentikasi, tidak dirutekan Gateway).

---

## C. Voting Request Contract

### C.1 Request

`POST /api/v1/ballots`

Header: `Authorization: Bearer <access_token>`, `Idempotency-Key: <key>`, `Content-Type: application/json`.

```json
{
  "election_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
  "candidate_id": "a1c4e8f2-5b36-4d71-8c09-3e2f7a6b1d54",
  "vote_ticket": "eyJhbGciOiJIUzI1NiJ9.contoh-ticket.signature"
}
```

Tidak ada `user_id`, email, nama, atau data pribadi lain di body maupun header yang diteruskan ke Ballot Service.

### C.2 Response sukses `201`

```json
{
  "receipt_id": "d9f6b2c4-8e69-4a04-b13c-6b5c0d9e4a87",
  "receipt_code": "VG-7K4Q-5M2D-X6TP-3RWA",
  "election_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
  "accepted_at": "2026-10-12T08:20:11Z",
  "audit_status": "PENDING"
}
```

Replay (`Idempotency-Key` + payload sama) → `200` dengan body identik dan header `Idempotent-Replayed: true`. `receipt_code` diturunkan ulang secara deterministik (`"VG-" + base32(HMAC-SHA256(RECEIPT_SECRET, receipt_id))` dikelompokkan 4-4-4-4) sehingga tidak perlu disimpan. `audit_status` awal selalu `PENDING`; sistem **tidak** menyatakan suara "sudah diaudit" sampai receipt menunjukkan `RECORDED`, dan "terverifikasi" hanya lewat `verify`.

### C.3 Aturan idempotency dan konkurensi

| Situasi | Hasil |
|---|---|
| Key baru, hak memilih belum dipakai | `201` |
| Key sama, payload sama (retry/paralel) | `200` replay, `receipt_id` sama, tidak ada suara baru |
| Key sama, `candidate_id` berbeda | `409 IDEMPOTENCY_CONFLICT` |
| Key berbeda, hak memilih sudah dipakai | `409 VOTER_ALREADY_VOTED` |
| 50 request paralel hak sama | Tepat satu `201`; sisanya `200` replay (key sama) atau `409 VOTER_ALREADY_VOTED` (key berbeda) |
| Election tidak `OPEN` / lewat `end_at` | `409 ELECTION_NOT_OPEN` |
| Voter Service tidak terjangkau | `503 SERVICE_UNAVAILABLE` (fail-closed) |

### C.4 Validasi kelayakan tanpa menautkan identitas ke pilihan

1. **Penerbitan** (`GET /elections/{id}/ballot`): identitas hanya dilihat Voter Service, yang memeriksa daftar pemilih dan status, lalu menerbitkan **vote ticket** berisi `election_id` dan `eligibility_ref` pseudonim (HMAC; ARCHITECTURE D.7) — tanpa `user_id`/email.
2. **Pengiriman** (`POST /ballots`): Gateway membuang header identitas; Ballot hanya melihat ticket. Ballot memverifikasi tanda tangan/`exp`/`aud`/`typ`/`election_id`, lalu mengonsumsi hak memilih lewat `UNIQUE(election_id, eligibility_ref)` di transaksi yang sama dengan penyimpanan suara dan outbox.
3. **Receipt** berupa `receipt_id` acak + kode turunan HMAC; tidak memuat identitas maupun `candidate_id`, dan tidak ada endpoint yang mengembalikan pilihan berdasarkan receipt/ticket/`eligibility_ref`.
4. **Batas:** Voter mengetahui `voter → eligibility_ref`, Ballot mengetahui `eligibility_ref → candidate_id`; pihak yang memegang keduanya dapat menautkan. Ticket dan receipt tidak membawa identitas, tetapi pseudonimisasi **bukan** anonimitas sempurna (SECURITY_AND_TEST_PLAN G.3).

---

## D. Error Schema

```json
{
  "error": {
    "code": "VOTER_ALREADY_VOTED",
    "message": "Hak memilih ini sudah digunakan.",
    "request_id": "7a9c1e3f-5b7d-4f91-8a23-4c6e8a0b2d45",
    "details": []
  }
}
```

`details` opsional (array objek `{ "field": "...", "issue": "..." }`). `message` berbahasa Indonesia, tanpa data sensitif; `request_id` = `X-Request-ID`.

| Code | HTTP | Pesan contoh | Endpoint tipikal |
|---|---|---|---|
| `UNAUTHORIZED` | 401 | Autentikasi diperlukan atau tidak valid. | Semua yang butuh token; login gagal |
| `FORBIDDEN` | 403 | Anda tidak berwenang melakukan tindakan ini. | RBAC, Attack Lab nonaktif |
| `ELECTION_NOT_OPEN` | 409 | Pemilu tidak sedang dibuka. | `GET …/ballot`, `POST /ballots` |
| `VOTER_NOT_ELIGIBLE` | 403 | Anda tidak terdaftar sebagai pemilih. | `GET …/ballot` |
| `VOTER_ALREADY_VOTED` | 409 | Hak memilih ini sudah digunakan. | `GET …/ballot`, `POST /ballots` |
| `IDEMPOTENCY_CONFLICT` | 409 | Idempotency-Key sama dipakai dengan isi berbeda. | `POST /ballots` |
| `VALIDATION_ERROR` | 422 | Data permintaan tidak valid. | Semua |
| `AUDIT_VERIFICATION_FAILED` | 409 | Verifikasi audit gagal; tindakan dibatalkan. | `finalize` |
| `RESULT_NOT_FINALIZED` | 409 | Hasil belum difinalisasi. | `GET /results/…` |
| `RATE_LIMIT_EXCEEDED` | 429 | Terlalu banyak permintaan. Coba lagi nanti. | Semua (+ `Retry-After`) |
| `SERVICE_UNAVAILABLE` | 503 | Layanan sementara tidak tersedia. | Semua yang bergantung layanan lain |

Kode tambahan (konsisten di keempat dokumen):

| Code | HTTP | Pemakaian |
|---|---|---|
| `NOT_FOUND` | 404 | Resource tidak ada atau di luar hak akses (VOTER) |
| `RECEIPT_NOT_FOUND` | 404 | Receipt tidak ada atau kode salah |
| `CONFLICT` | 409 | Duplikat (email, nama kandidat, run Attack Lab aktif) |
| `ELECTION_INVALID_STATE` | 409 | Transisi/aksi tidak sah pada status saat ini |
| `VOTE_TICKET_INVALID` | 403 | Ticket rusak, kedaluwarsa, atau untuk election lain |
| `ACCOUNT_LOCKED` | 423 | Akun terkunci sementara |
| `RECONCILIATION_FAILED` | 409 | B, A, V tidak sama |
| `BALLOT_INTEGRITY_FAILED` | 409 | `ballot_commitment` tidak cocok |
| `INTERNAL_ERROR` | 500 | Kesalahan tak terduga (tanpa detail internal) |

---

## E. Event Contracts

Semua event dikirim ke exchange `voxguard.events` (topic) dengan envelope baku. Deduplikasi, retry, dan DLQ mengikuti ARCHITECTURE F.3.

### E.1 JSON Schema envelope (Draft 2020-12)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://voxguard.local/schemas/event-envelope-1.0.json",
  "title": "EventEnvelope",
  "type": "object",
  "additionalProperties": false,
  "required": ["event_id", "event_type", "schema_version", "occurred_at", "correlation_id", "payload"],
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
    "correlation_id": { "type": "string", "format": "uuid" },
    "payload": { "type": "object" }
  }
}
```

Consumer memvalidasi envelope dan skema payload berdasarkan `event_type` + `schema_version`; gagal validasi → DLQ (tidak di-retry). Perubahan kompatibel menaikkan minor (`1.1`), perubahan tak kompatibel menaikkan major dan di-*publish* berdampingan sampai semua konsumen siap.

### E.2 Kontrak per event

**Header AMQP:** `message_id = event_id`, `correlation_id = correlation_id`, `x-attempt`.

#### ElectionOpened — `election.opened`

Publisher: voter-service. Consumer: ballot-service (`ballot.q.election`), audit-service, security-service.

```json
{
  "event_id": "11111111-aaaa-4bbb-8ccc-000000000001",
  "event_type": "ElectionOpened",
  "schema_version": "1.0",
  "occurred_at": "2026-10-12T08:00:30Z",
  "correlation_id": "7a9c1e3f-5b7d-4f91-8a23-4c6e8a0b2d45",
  "payload": {
    "election_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
    "title": "Pemilihan Ketua Kelas 3A",
    "opened_at": "2026-10-12T08:00:30Z",
    "end_at": "2026-10-12T10:00:00Z"
  }
}
```

#### ElectionClosed — `election.closed`

Publisher: voter-service. Consumer: ballot-service, audit-service, security-service.

```json
{
  "event_id": "11111111-aaaa-4bbb-8ccc-000000000002",
  "event_type": "ElectionClosed",
  "schema_version": "1.0",
  "occurred_at": "2026-10-12T10:00:05Z",
  "correlation_id": "7a9c1e3f-5b7d-4f91-8a23-4c6e8a0b2d46",
  "payload": {
    "election_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
    "closed_at": "2026-10-12T10:00:05Z"
  }
}
```

#### VoteAccepted — `vote.accepted`

Publisher: ballot-service. Consumer: audit-service (proyeksi allowlist), voter-service (`voter.q.ballot`), security-service. **Tanpa `candidate_id` dan tanpa identitas.** `eligibility_ref` hanya dipakai Voter; Audit/Security membuangnya.

```json
{
  "event_id": "0c1d2e3f-4a5b-4c6d-8e7f-9a0b1c2d3e4f",
  "event_type": "VoteAccepted",
  "schema_version": "1.0",
  "occurred_at": "2026-10-12T08:20:11Z",
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

#### VoteRejected — `vote.rejected`

Publisher: ballot-service. Consumer: security-service. `reason_code` ∈ {`VOTER_ALREADY_VOTED`, `ELECTION_NOT_OPEN`, `VOTE_TICKET_INVALID`, `IDEMPOTENCY_CONFLICT`, `CANDIDATE_INVALID`}.

```json
{
  "event_id": "11111111-aaaa-4bbb-8ccc-000000000004",
  "event_type": "VoteRejected",
  "schema_version": "1.0",
  "occurred_at": "2026-10-12T08:25:01Z",
  "correlation_id": "7a9c1e3f-5b7d-4f91-8a23-4c6e8a0b2d48",
  "payload": {
    "election_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
    "reason_code": "VOTER_ALREADY_VOTED",
    "client_fingerprint": "a1b2c3d4e5f60718293a4b5c",
    "rejected_at": "2026-10-12T08:25:01Z"
  }
}
```

#### AuditRecorded — `audit.recorded`

Publisher: audit-service. Consumer: ballot-service (`ballot.q.audit`, hanya untuk `source_event_type = VoteAccepted`), security-service.

```json
{
  "event_id": "11111111-aaaa-4bbb-8ccc-000000000005",
  "event_type": "AuditRecorded",
  "schema_version": "1.0",
  "occurred_at": "2026-10-12T08:20:13Z",
  "correlation_id": "7a9c1e3f-5b7d-4f91-8a23-4c6e8a0b2d47",
  "payload": {
    "scope_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
    "source_event_id": "0c1d2e3f-4a5b-4c6d-8e7f-9a0b1c2d3e4f",
    "source_event_type": "VoteAccepted",
    "sequence": 14,
    "event_hash": "9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c9f2c",
    "recorded_at": "2026-10-12T08:20:13Z"
  }
}
```

#### TallyCompleted — `tally.completed`

Publisher: result-service. Consumer: audit-service, security-service (R-10).

```json
{
  "event_id": "11111111-aaaa-4bbb-8ccc-000000000006",
  "event_type": "TallyCompleted",
  "schema_version": "1.0",
  "occurred_at": "2026-10-12T10:05:00Z",
  "correlation_id": "7a9c1e3f-5b7d-4f91-8a23-4c6e8a0b2d49",
  "payload": {
    "election_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
    "tally_run_id": "2c4e6a81-3d5f-4b79-8c9b-1d3f5a7b9ea2",
    "run_number": 1,
    "status": "COMPLETED",
    "reconciliation_status": "MATCH",
    "ballots_counted": 12,
    "ballot_set_digest": "5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e5d3e"
  }
}
```

#### ResultFinalized — `result.finalized`

Publisher: result-service. Consumer: audit-service, voter-service (`voter.q.result`; set `FINALIZED`).

```json
{
  "event_id": "11111111-aaaa-4bbb-8ccc-000000000007",
  "event_type": "ResultFinalized",
  "schema_version": "1.0",
  "occurred_at": "2026-10-12T10:10:00Z",
  "correlation_id": "7a9c1e3f-5b7d-4f91-8a23-4c6e8a0b2d4a",
  "payload": {
    "election_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
    "tally_run_id": "2c4e6a81-3d5f-4b79-8c9b-1d3f5a7b9ea2",
    "result_hash": "1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b1a7b",
    "finalized_at": "2026-10-12T10:10:00Z"
  }
}
```

#### SecurityAlertRaised — `security.alert_raised`

Publisher: security-service. Consumer: audit-service (dicatat di scope election atau GLOBAL bila `election_id` null). Tanpa `evidence` mentah dan tanpa fingerprint.

```json
{
  "event_id": "11111111-aaaa-4bbb-8ccc-000000000008",
  "event_type": "SecurityAlertRaised",
  "schema_version": "1.0",
  "occurred_at": "2026-10-12T08:27:00Z",
  "correlation_id": "7a9c1e3f-5b7d-4f91-8a23-4c6e8a0b2d4b",
  "payload": {
    "alert_id": "0a2c4e6f-1b3d-4f57-8a79-9b1d3f5a7c80",
    "rule_code": "R-01",
    "severity": "MEDIUM",
    "election_id": "6f1d2b7e-3c41-4a8f-9d2e-1b7c5a90e4d3",
    "title": "Percobaan double voting berulang",
    "raised_at": "2026-10-12T08:27:00Z"
  }
}
```

#### SecuritySignalObserved — `security.signal_observed`

Publisher: api-gateway dan auth-service (best-effort, tanpa outbox); audit-service (via outbox, untuk `AUDIT_INTEGRITY_FAILED`). Consumer: security-service. `signal_type` ∈ {`RATE_LIMIT_EXCEEDED`, `TOKEN_INVALID`, `FORBIDDEN`, `LOGIN_FAILED`, `ACCOUNT_LOCKED`, `AUDIT_INTEGRITY_FAILED`}.

```json
{
  "event_id": "11111111-aaaa-4bbb-8ccc-000000000009",
  "event_type": "SecuritySignalObserved",
  "schema_version": "1.0",
  "occurred_at": "2026-10-12T08:30:00Z",
  "correlation_id": "7a9c1e3f-5b7d-4f91-8a23-4c6e8a0b2d4c",
  "payload": {
    "signal_type": "RATE_LIMIT_EXCEEDED",
    "source_service": "api-gateway",
    "client_fingerprint": "a1b2c3d4e5f60718293a4b5c",
    "election_id": null,
    "observed_at": "2026-10-12T08:30:00Z"
  }
}
```

### E.3 Proyeksi allowlist `payload_public` di Audit

| Event | Field yang boleh masuk `audit_events.payload_public` |
|---|---|
| `ElectionOpened` | `election_id`, `title`, `opened_at`, `end_at` |
| `ElectionClosed` | `election_id`, `closed_at` |
| `VoteAccepted` | `election_id`, `ballot_id`, `receipt_id`, `accepted_at`, `ballot_commitment` (**bukan** `eligibility_ref`) |
| `TallyCompleted` | seluruh payload |
| `ResultFinalized` | seluruh payload |
| `SecurityAlertRaised` | `alert_id`, `rule_code`, `severity`, `title`, `raised_at` |

Field di luar tabel dibuang; event dengan field wajib hilang → DLQ.

### E.4 Ringkasan deduplikasi, retry, dan DLQ

| Aspek | Aturan |
|---|---|
| Dedup key | `event_id` (`processed_events(event_id, consumer)` atau unique alami: `audit_events.source_event_id`, `security_events.event_id`, `audit_acks.source_event_id`) |
| Retry | Retry queue 5 s → 30 s → 120 s; header `x-attempt` |
| DLQ | `<queue>.dlq` setelah percobaan ke-4 gagal atau kesalahan permanen (skema); dipantau R-09 |
| Replay | Manual (OD-09), aman karena konsumen idempotent |
| Urutan | Tidak dijamin lintas agregat; konsumen tidak boleh bergantung pada urutan global |

---

## F. OpenAPI Alignment

### F.1 Struktur OpenAPI 3.1

| Elemen | Aturan |
|---|---|
| `openapi` | `3.1.0`; skema memakai JSON Schema 2020-12 (nullable ditulis `"type": ["string","null"]`) |
| `servers` | `http://localhost:8000` (Gateway). Swagger tiap service tersedia di `/docs` pada jaringan internal untuk pengembangan |
| `tags` | `Auth`, `Elections`, `Ballots`, `Audit`, `Results`, `Security` |
| `operationId` | `camelCase` dari metode+resource: `registerUser`, `loginUser`, `refreshToken`, `logoutUser`, `getMe`, `createElection`, `listElections`, `getElection`, `addCandidate`, `importVoters`, `scheduleElection`, `openElection`, `closeElection`, `getBallot`, `castBallot`, `getReceipt`, `listAuditEvents`, `verifyAudit`, `getAuditProof`, `runTally`, `finalizeResult`, `getResult`, `verifyResult`, `listAlerts`, `runAttack`, `getAttackRun`, `getSecurityMetrics` |
| `securitySchemes` | `bearerAuth` (`http`, `bearer`, `bearerFormat: JWT`); `receiptCode` (`apiKey` in header `X-Receipt-Code`) |
| Ekstensi | `x-roles: ["ADMIN"]` pada tiap operasi (sumber untuk generator RBAC dan API-RBAC-01) |
| `components/schemas` | `ErrorResponse`, `Page`, semua model di F.2, `EventEnvelope`, payload event per tipe |
| `components/parameters` | `RequestId`, `IdempotencyKey`, `PageParam`, `PageSizeParam` |
| `components/responses` | `Unauthorized`, `Forbidden`, `NotFound`, `ValidationError`, `RateLimited`, `ServiceUnavailable` (semuanya `ErrorResponse`) |
| Penggabungan | Gateway dapat menyajikan dokumen gabungan hasil merge OpenAPI tiap service (OD: pilih saat implementasi; MVP boleh Swagger per service) |

### F.2 Model Pydantic (v2) yang dapat langsung diadaptasi

```python
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


Role = Literal["ADMIN", "VOTER", "AUDITOR"]
ElectionStatus = Literal["DRAFT", "SCHEDULED", "OPEN", "CLOSED", "FINALIZED"]


class ErrorDetail(StrictModel):
    field: Optional[str] = None
    issue: str


class ErrorBody(StrictModel):
    code: str
    message: str
    request_id: UUID
    details: list[ErrorDetail] = []


class ErrorResponse(StrictModel):
    error: ErrorBody


class PageInfo(StrictModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)


class RegisterRequest(StrictModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    display_name: str = Field(min_length=1, max_length=100)
    role: Optional[Role] = None  # hanya sah bila pemanggil ADMIN


class LoginRequest(StrictModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(StrictModel):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int
    refresh_token: str


class ElectionCreate(StrictModel):
    title: str = Field(min_length=3, max_length=150)
    description: str = Field(default="", max_length=2000)
    start_at: datetime
    end_at: datetime
    is_attack_lab: bool = False


class CandidateCreate(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    ballot_order: int = Field(ge=1)


class VoterRow(StrictModel):
    email: EmailStr
    external_ref: str = Field(min_length=1, max_length=64)
    display_label: str = Field(min_length=1, max_length=100)


class VoterImportRequest(StrictModel):
    voters: list[VoterRow] = Field(min_length=1, max_length=1000)


class VoteRequest(StrictModel):
    election_id: UUID
    candidate_id: UUID
    vote_ticket: str = Field(min_length=20, max_length=4096)


class VoteReceiptResponse(StrictModel):
    receipt_id: UUID
    receipt_code: str = Field(pattern=r"^VG-[A-Z2-7]{4}(-[A-Z2-7]{4}){3}$")
    election_id: UUID
    accepted_at: datetime
    audit_status: Literal["PENDING", "RECORDED"]


class FinalizeRequest(StrictModel):
    tally_run_id: UUID


class AttackRunRequest(StrictModel):
    attack_id: Literal[
        "ATK-01", "ATK-02", "ATK-03", "ATK-04", "ATK-05",
        "ATK-06", "ATK-07", "ATK-08", "ATK-09", "ATK-10",
    ]
    parameters: dict = {}


class EventEnvelope(StrictModel):
    event_id: UUID
    event_type: Literal[
        "ElectionOpened", "ElectionClosed", "VoteAccepted", "VoteRejected", "AuditRecorded",
        "TallyCompleted", "ResultFinalized", "SecurityAlertRaised", "SecuritySignalObserved",
    ]
    schema_version: str = Field(pattern=r"^[0-9]+\.[0-9]+$")
    occurred_at: datetime
    correlation_id: UUID
    payload: dict
```

Catatan implementasi (rancangan): `Idempotency-Key` dibaca sebagai header (`Header(..., min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")`); dependency `require_roles("ADMIN")` dipasang per router dan sumber `x-roles` di OpenAPI; `responses={...}` mengacu `ErrorResponse`.

### F.3 Konsistensi lintas dokumen

| Elemen | Sumber kebenaran | Direferensikan di |
|---|---|---|
| Nama service/DB/tabel | ARCHITECTURE C, D | API_CONTRACTS B (kolom "Efek database"), SECURITY (A, B) |
| Event, publisher, consumer | ARCHITECTURE F.2 | API_CONTRACTS E, B (kolom Event), SECURITY (D) |
| Error code | API_CONTRACTS D | SECURITY (ATK), ARCHITECTURE E (diagram) |
| Role dan RBAC | PROJECT_BRIEF E, API_CONTRACTS B.0 | SECURITY C (RBAC), API-RBAC-01 |
| ID FR/SM/ATK/test | PROJECT_BRIEF, SECURITY_AND_TEST_PLAN | seluruh dokumen |
| Status mekanisme | Semua berstatus **rancangan** hingga diimplementasikan dan diuji | — |
