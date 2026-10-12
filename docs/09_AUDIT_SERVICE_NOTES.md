# 09 — Audit Service (Phase 12): Catatan Implementasi, Asumsi Kepercayaan, dan Batas

Dokumen ini menjelaskan apa yang **benar-benar** diimplementasikan pada Phase 12 dan apa yang belum. Sumber otoritatif tetap `03_…` (Bagian 11–12), `04_…` (5.10, 5.11, 5.14, 7), `05_…` (Bagian 4 #17–19, 8) dan `06_…`.

## 1. Alur event: tiga status yang berbeda

| Status | Arti | Bukti |
|---|---|---|
| **Published** | Relay outbox Ballot menerima *publisher confirm* dari broker **dan** pesan ter-rute ke minimal satu queue | `outbox_events.status = PUBLISHED` |
| **Consumed** | Audit menerima dan mem-parse pesan | log `audit_event_processed` |
| **Stored** | Entri ada di `audit_events`, head diperbarui, `processed_events` ditandai — satu transaksi ter-commit | baris di `audit_events` |

Pesan di-`ack` hanya setelah **Stored** (atau setelah diketahui sudah Stored sebelumnya). Pada kode lama Ballot, publish ke exchange tanpa queue tetap mendapat *ack* broker dan ditandai `PUBLISHED` padahal dibuang; sekarang relay memakai `mandatory=True` dan pesan yang dikembalikan broker dianggap gagal (retry/backoff, lalu `FAILED` bila habis).

`PUBLISHED` ≠ `Stored`. Receipt `RECORDED` **belum** tersedia (lihat §8).

## 2. Topologi RabbitMQ (kode aktual)

- Exchange `voxguard.events` (topic, durable) — nama dari SAD §11.1. Sebelumnya publisher Ballot memakai `voxguard`; diubah.
- Envelope: `event_id, event_type, schema_version, occurred_at, producer, correlation_id, payload` (Kontrak §8.1, `additionalProperties: false`). Sebelumnya Ballot mengirim `source_service`; diubah ke `producer`.
- Routing key `vote.accepted` → queue `audit.vote-accepted` (durable). Hanya `VoteAccepted` yang dikonsumsi pada fase ini.
- Retry bertingkat: `audit.vote-accepted.retry.<delay>ms` (TTL 5 s, 30 s, 120 s; dead-letter kembali ke queue kerja). Kegagalan ke-4 → `audit.vote-accepted.dlq`. Nama queue memuat delay karena RabbitMQ menolak deklarasi ulang dengan TTL berbeda (`PRECONDITION_FAILED`).
- Kegagalan **permanen** langsung ke DLQ: JSON rusak, envelope tidak valid, payload tidak valid, major schema ≠ 1, `event_type`/`producer` tak terduga. Header DLQ: `x-vg-failure` (kode tetap atau nama kelas exception — tanpa isi pesan), `x-vg-retry`.
- Retry/DLQ di-*republish* dengan konfirmasi broker, baru kemudian pesan asli di-`ack`. Bila republish gagal → `nack(requeue=True)`; tidak pernah di-`ack` tanpa salinan aman.
- DLQ tidak dikonsumsi otomatis. Replay manual aman (idempotent): publish ulang body DLQ ke exchange dengan routing key `vote.accepted`.
- `prefetch=1`: satu pesan diproses pada satu waktu per consumer, sehingga urutan pencatatan deterministik per instance.

Konsumen berjalan **di dalam proses `audit-service`** (lifespan FastAPI) bila `RABBITMQ_URL` terisi, sehingga `compose.yaml` yang sudah ada menjalankannya tanpa layanan baru. `/health/ready` mensyaratkan database dan (bila dikonfigurasi) consumer yang terhubung dan sedang meng-consume.

## 3. Struktur audit trail

Tabel (migration `alembic/versions/0001_create_audit_tables.py`): `audit_events`, `audit_chain_heads`, `audit_checkpoints`, `integrity_checks`, `outbox_events`, `processed_events`.

- **Scope** = `election_id`.
- **Hash**: SHA-256. `event_hash = SHA-256(canonical({scope_id, sequence, source_event_id, source_event_type, occurred_at, correlation_id, payload_public, prev_hash}))`. Kanonik: JSON kunci terurut, tanpa spasi, UTF-8, timestamp UTC lebar-tetap mikrodetik (`YYYY-MM-DDTHH:MM:SS.ffffffZ`); timestamp naif ditolak. Genesis `prev_hash` = 64 × `0`.
- `audit_events` ditolak `UPDATE/DELETE/TRUNCATE` oleh trigger (DBC-11) — ini hanya pertahanan terhadap bug aplikasi, **bukan** terhadap pemilik tabel/superuser.

### Transaksi dan urutan

`record_event` dalam **satu transaksi**: `INSERT processed_events … ON CONFLICT DO NOTHING` (duplikat berhenti di sini) → pastikan baris head ada → `SELECT … FOR UPDATE` pada head scope → hitung hash → `INSERT audit_events` (savepoint) → `UPDATE` head. Gagal di titik mana pun = rollback seluruhnya (tidak ada penanda "sudah diproses" tanpa entri, tidak ada head yang maju tanpa entri). Dua transaksi pada scope yang sama diserialkan oleh kunci head; `UNIQUE(scope_id, sequence)` dan `UNIQUE(source_event_id)` adalah pagar terakhir.

### Verifikasi (`verify_chain`)

Membaca ulang **seluruh baris tersimpan** (snapshot `REPEATABLE READ`, batch 1000) dan memeriksa urutan: `SEQUENCE_GAP`, `PREV_HASH_MISMATCH`, `EVENT_HASH_MISMATCH` (hash dihitung ulang dari field tersimpan), lalu head tersimpan vs ujung rantai (`HEAD_MISMATCH`), lalu checkpoint terbaru (HMAC dengan `AUDIT_CHECKPOINT_KEY`, hash event pada sequence-nya; `CHECKPOINT_MISMATCH`). Setiap pemeriksaan ditulis ke `integrity_checks` dengan kode alasan tetap (tanpa data event). Pengujian: `tests/integration/test_audit_integration.py` test_06a–06i memodifikasi database uji secara langsung.

## 4. Privasi

Yang disimpan di `payload_public` (allowlist, kontrak `04_…` 7.1): `election_id`, `ballot_id`, `receipt_id`, `accepted_at`, `ballot_commitment`.

| Field | Perlu? | Alasan |
|---|---|---|
| `eligibility_ref` | **Tidak disimpan** | Pseudonim yang dapat ditautkan ke identitas oleh pemegang `voter_db` + pepper. Dibuang saat parse (field di luar allowlist tidak pernah masuk ke objek yang di-hash/disimpan). |
| `candidate_id`, nonce, JWT, vote ticket, `receipt_code`, email, nama, `user_id` | **Tidak disimpan** | Tidak ada di payload kontrak; bila ada, dibuang. Diuji. |
| `receipt_id` | Ya | Bukti inklusi receipt (`/proof?receipt_id=`). Acak, tanpa identitas/pilihan. |
| `ballot_commitment` | Ya | Result mencocokkan commitment tanpa membuka pilihan (SAD §12). Nonce 256-bit tidak ada di audit. |
| `ballot_id` | Ya (sesuai ERD) | Korelasi dengan `ballots` untuk rekonsiliasi. Hanya terlihat oleh ADMIN/AUDITOR lewat `/audit/events`. |
| `accepted_at` / `occurred_at` | Ya | Dicatat apa adanya. Metadata waktu tetap dapat dikorelasikan pada pemilih sedikit (lihat `04_…` 7.3). |

Endpoint `/audit/events` mem-proyeksikan ulang `payload_public` lewat allowlist sebelum dikirim (defense in depth). Sistem **tidak** dinyatakan anonim: pemisahan layanan hanya menaikkan biaya pengaitan; DBA yang memegang `voter_db` + `ballot_db` + pepper tetap dapat menautkan.

## 5. Endpoint (Kontrak #17–19)

| Endpoint | Role | Catatan |
|---|---|---|
| `GET /api/v1/audit/events` | ADMIN, AUDITOR | `election_id` kosong → scope GLOBAL (nol UUID); `page_size ≤ 100` |
| `GET /api/v1/audit/elections/{id}/verify` | ADMIN, AUDITOR | Selalu `200` bila chain ada; `INVALID` dilaporkan di body. `404` bila tidak ada chain. Menulis `integrity_checks`. |
| `GET /api/v1/audit/elections/{id}/proof?receipt_id=` | ADMIN, AUDITOR, VOTER | Parameter chain, head, checkpoint terakhir, verifikasi terakhir, `receipt_event` atau `null`. `404` bila tidak ada chain. |

Autentikasi: Bearer JWT yang sama dengan layanan lain (`JWT_SECRET`); tanpa secret → semua token ditolak (fail-closed). Gateway sudah merutekan `/api/v1/audit`; service juga memeriksa sendiri (tidak mengandalkan Gateway).

`valid`/`VALID` hanya berarti **rantai tersimpan konsisten secara internal** (dan cocok dengan checkpoint bila ada). Itu bukan jaminan seluruh sistem tidak terkompromi, bukan bukti suara dihitung benar, dan bukan bukti independen.

## 6. Asumsi kepercayaan dan batas integritas

1. **Rebuild penuh tak terdeteksi tanpa checkpoint.** Penyerang dengan akses tulis ke seluruh `audit_db` dapat menonaktifkan trigger, mengubah entri, menghitung ulang semua hash dan head; `verify` lalu `VALID`. Diuji (test_06h) sebagai batas yang dinyatakan.
2. **Checkpoint HMAC hanya membantu bila kunci tidak ikut bocor.** Dengan checkpoint yang dibuat sebelum serangan, rebuild terdeteksi (`CHECKPOINT_MISMATCH`) — selama penyerang tidak memegang `AUDIT_CHECKPOINT_KEY`. Kunci dan volume checkpoint berada di host yang sama; ini bukan checkpoint independen/eksternal dan bukan bukti publik yang tak dapat dipalsukan.
3. **Pemotongan ekor** terdeteksi lewat head dan/atau checkpoint, tetapi bila penyerang memperbaiki head **dan** tidak ada checkpoint, tidak terdeteksi.
4. **Hak database.** `audit_app` adalah pemilik `audit_db` pada `init-databases.sh`, sehingga ia dapat menonaktifkan trigger. Pemisahan peran migrasi vs. runtime (`INSERT, SELECT` saja, DBC-11/SEC-DB-02) **belum** dilakukan; trigger tidak menghentikan superuser/owner.
5. **Chain membuktikan urutan pencatatan**, bukan urutan pemungutan; `occurred_at` berasal dari publisher.
6. **Event hilang sebelum diterbitkan** (mis. outbox Ballot dihapus) tidak terlihat oleh Audit; hanya rekonsiliasi B/A/V (Result, fase berikutnya) yang dapat menangkapnya.
7. Penyimpanan Audit mengandalkan kejujuran Ballot sebagai producer; consumer memvalidasi `producer`, tetapi broker belum memakai autentikasi per-layanan (satu user RabbitMQ bersama).

## 7. Operasional

- Migrasi (tidak otomatis saat start): `docker compose exec audit-service python -m alembic upgrade head`.
- Variabel baru: `JWT_SECRET`, `INTERNAL_API_KEY`, `AUDIT_DATABASE_URL_SYNC` diteruskan di `compose.yaml`. Opsional: `AUDIT_EXCHANGE`, `AUDIT_QUEUE`, `AUDIT_PREFETCH`, `AUDIT_RETRY_DELAYS_MS`.
- Memantau: kedalaman `audit.vote-accepted.dlq` (R-09, dikerjakan Security), log `audit_event_dead_lettered`, `audit_event_retry`, `audit_integrity_failed`.
- Mengubah `AUDIT_RETRY_DELAYS_MS` membuat queue retry baru; queue lama terkuras sendiri lewat TTL-nya lalu dapat dihapus.
- Satu instance consumer adalah konfigurasi yang diuji. Beberapa instance tetap aman (kunci head), tetapi urutan pencatatan antar-pesan tidak lagi mengikuti urutan queue.

## 8. Belum diimplementasikan (dependensi, bukan klaim)

| Item | Status |
|---|---|
| Consumer `VoteAccepted` di Voter (eligibility → `VOTED`) | **Belum ada** di `voter-service`; `voting_eligibility.status` tidak berubah oleh event. Anti-suara-ganda tetap dijaga `UNIQUE(election_id, eligibility_ref)` di Ballot. |
| `AuditRecorded` → `audit_acks` → receipt `RECORDED` (VG-S5-004) | Audit belum menerbitkan `AuditRecorded`; `audit_status` pada receipt tetap `PENDING`. |
| Consumer event lain (`ElectionOpened/Closed`, `TallyCompleted`, `ResultFinalized`, `SecurityAlertRaised`) | Allowlist ada, consumer belum. |
| Penulis checkpoint (ke volume, saat `ElectionClosed`/`ResultFinalized`/periodik) | Verifikasi membaca & memvalidasi checkpoint; **penulisnya belum ada** (VG-S5-003). Tabel diisi manual hanya di tes. |
| `SecuritySignalObserved` `AUDIT_INTEGRITY_FAILED` via outbox saat `INVALID` (VG-S5-010) | Belum; hanya log `audit_integrity_failed`. Tabel `outbox_events` ada tetapi belum ada relay di Audit. |
| Endpoint internal Result (`summary`, `commitments`, `verify`), `test/tamper` | Belum. |
| Peran DB runtime terpisah, TLS/auth RabbitMQ per layanan | Belum. |

## 9. Menjalankan tes

```
# Unit (tanpa DB/broker)
cd services/audit-service && python3 -m pytest tests -q
cd services/ballot-service && python3 -m pytest tests -q

# Integration (PostgreSQL + RabbitMQ nyata; dilewati bila tidak tersedia)
export AUDIT_IT_PG_URL=postgresql://user:pw@localhost:5432/postgres
export AUDIT_IT_AMQP_URL=amqp://user:pw@localhost:5672/vhost
# opsional, HANYA broker sekali pakai (menjalankan `rabbitmqctl stop_app`):
export AUDIT_IT_ALLOW_BROKER_RESTART=1
python3 -m pytest tests/integration/test_audit_integration.py -v
```

Integration test membuat database sementara dari migrasi Alembic yang sebenarnya dan menghasilkan `VoteAccepted` lewat `cast_vote()` dan `OutboxPublisher` Ballot yang asli.
