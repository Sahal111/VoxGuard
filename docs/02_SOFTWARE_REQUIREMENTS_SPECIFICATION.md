# VoxGuard — Software Requirements Specification (SRS)

## 1. Document Information

| Atribut | Nilai |
|---|---|
| Nama dokumen | Software Requirements Specification |
| Proyek | VoxGuard — Verifiable Digital Election System |
| Versi / Status | 0.1 / **Draft — belum disetujui** |
| Tanggal | 2026-10-10 |
| Pemilik | `[PEMILIK-DOKUMEN]` (placeholder; lihat legenda di `01_PROJECT_CHARTER.md`) |
| Acuan struktur | Terinspirasi IEEE 29148; **tidak** mengklaim kepatuhan atau sertifikasi |

| Versi | Tanggal | Perubahan |
|---|---|---|
| 0.1 | 2026-10-10 | Draf awal |

Dokumen terkait: `01_PROJECT_CHARTER.md`, `03_SYSTEM_ARCHITECTURE_DOCUMENT.md` (SAD). Dokumen pendamping lama di repository (tidak diubah): `PROJECT_BRIEF.md`, `ARCHITECTURE.md`, `SECURITY_AND_TEST_PLAN.md`, `API_CONTRACTS.md` — dipakai untuk detail skema API dan rencana uji. Penanda: **OPEN DECISION** = belum disepakati; **PROPOSED TARGET** = angka usulan; **PLANNED** = test belum dibuat. Status semua mekanisme: **direncanakan**, belum diimplementasikan atau diuji.

---

## 2. Purpose

SRS menetapkan *apa yang wajib dilakukan sistem*. Developer memakainya sebagai acuan implementasi, tester untuk menurunkan test case (setiap requirement memiliki ID stabil dan acceptance criteria), dan reviewer untuk menilai kelengkapan dan konsistensi. Cara *membangun* dijelaskan di SAD.

## 3. Product Scope

VoxGuard menyelenggarakan pemilihan skala kecil: Admin menyiapkan pemilihan, kandidat, dan daftar pemilih; Voter memberi satu suara; sistem mencatat audit tamper-evident, menghitung dan memfinalisasi hasil, mendeteksi anomali, dan menyediakan Attack Lab pada lingkungan uji. **Di luar batas:** pemilu resmi, anonimitas kriptografis sempurna, verifikasi identitas dunia nyata, E2E verifiability, produksi berskala besar (Bagian 16).

## 4. Product Perspective

Aplikasi web: frontend React/Vite/Tailwind → API Gateway → enam layanan FastAPI (`auth-service`, `voter-service`, `ballot-service`, `audit-service`, `result-service`, `security-service`) dengan database PostgreSQL per layanan (`auth_db`, `voter_db`, `ballot_db`, `audit_db`, `result_db`, `security_db`), RabbitMQ untuk event, Redis untuk rate limiting dan denylist token. Tidak ada integrasi eksternal. Diagram: SAD Bagian 4–5.

## 5. User Classes and Characteristics

| Kelas | Karakteristik | Hak ringkas |
|---|---|---|
| **Admin** | Panitia; paham operasi pemilihan, tidak harus teknis | Mengelola pemilihan, lifecycle, tally, finalisasi; lihat audit/alert |
| **Voter** | Peserta umum, keahlian teknis beragam; perlu UI sederhana | Memilih satu kali; receipt; hasil final |
| **Auditor** | Pemeriksa independen; memahami konsep hash/verifikasi | Hanya baca: audit, proof, hasil, alert; tanpa identitas/pilihan individu |
| **Developer/Operator teknis** | Menjalankan Compose, migrasi, uji, Attack Lab | Akses infrastruktur lokal; tidak memodifikasi pemilihan nyata |

Kelas Developer/Operator bukan peran aplikasi; ia memakai akun `ADMIN` seed lokal untuk fungsi administratif.

## 6. Operating Environment

| Komponen | Persyaratan |
|---|---|
| Klien | Browser modern (Chrome, Firefox, Edge, Safari versi terbaru) |
| Backend | Python + FastAPI, SQLAlchemy, Alembic |
| Data/messaging | PostgreSQL, RabbitMQ, Redis |
| Pengujian | Pytest, HTTPX |
| Deployment | Docker, Docker Compose, satu mesin lokal |
| Versi dependency | **OPEN DECISION (OD-19):** ditetapkan dan di-*pin* saat implementasi; tidak ada file dependency di repository saat ini |
| Lingkungan uji | Profil Compose `test` dengan database uji terpisah dan Attack Lab aktif |

## 7. Assumptions and Dependencies

- Tidak ada layanan eksternal; tidak ada integrasi pihak ketiga.
- Daftar pemilih disediakan Admin; tidak ada verifikasi identitas dunia nyata (OD-01).
- Satu instance tiap infrastruktur; jam sistem host konsisten (UTC).
- Skala dan beban: PROPOSED TARGET (OD-16).
- Dokumen kontrak API (`API_CONTRACTS.md`) adalah sumber skema endpoint; SRS tidak mengulanginya.

---

## 8. Functional Requirements

Kolom: **Aktor**, **Pra** (prasyarat), **Alur** (utama), **Gagal/Alt** (kondisi alternatif/kegagalan), **Acceptance**, **Pri** (Must/Should/Could). Kode error mengikuti `API_CONTRACTS.md` D.

### 8.1 Authentication and Authorization (FR-AUTH)

| ID | Nama dan deskripsi | Aktor | Pra | Alur | Gagal/Alt | Acceptance | Pri |
|---|---|---|---|---|---|---|---|
| FR-AUTH-001 | **Registrasi/provisioning akun.** Pembuatan akun sesuai kebijakan (OD-11) | Anonim, Admin | Email belum terdaftar | Anonim mendaftar → akun `VOTER`. Admin dapat membuat `ADMIN`/`AUDITOR`. Admin pertama dibuat lewat seed lokal | Email ada → `CONFLICT`; role tinggi oleh non-Admin → `FORBIDDEN`; data salah → `VALIDATION_ERROR` | Tanpa field role menghasilkan `VOTER`; tidak ada jalur publik membuat Admin/Auditor; password tidak ada di response/log | Must |
| FR-AUTH-002 | **Login.** Menerbitkan access token dan refresh token | Semua | Akun aktif | Kirim email+password → verifikasi hash → token | Gagal → `UNAUTHORIZED` generik; terkunci → `ACCOUNT_LOCKED` | Token memuat role dan masa berlaku; kegagalan tidak membedakan email/password salah | Must |
| FR-AUTH-003 | **Refresh token/sesi.** Rotasi refresh token | Semua | Refresh token valid | Tukar token → pasangan baru; lama ditandai dirotasi | Token dipakai ulang → seluruh keluarga sesi dicabut, `UNAUTHORIZED` | Token lama tidak dapat dipakai dua kali | Must |
| FR-AUTH-004 | **Logout.** Mencabut sesi | Semua terautentikasi | Login | Cabut refresh session + denylist `jti` | Token invalid → `UNAUTHORIZED` | Access token pasca-logout ditolak (selama denylist tersedia) | Must |
| FR-AUTH-005 | **Informasi pengguna saat ini** (`me`) | Semua terautentikasi | Login | Kembalikan id, email, nama, role | Tanpa token → `UNAUTHORIZED` | Tidak memuat hash password atau token | Must |
| FR-AUTH-006 | **Pemeriksaan peran dan izin.** Role dicek di Gateway dan di tiap layanan | Sistem | Token valid | Cocokkan role dengan matriks endpoint | Role salah → `FORBIDDEN`; tanpa token → `UNAUTHORIZED` | Setiap endpoint × role sesuai matriks (`API_CONTRACTS.md` B.0) | Must |
| FR-AUTH-007 | **Penanganan kredensial tidak valid.** Lockout dan batas percobaan | Sistem | — | Hitung kegagalan; kunci sementara | Lewat ambang → `ACCOUNT_LOCKED` | Setelah N gagal (**PROPOSED TARGET:** 5 dalam 15 menit) akun terkunci sementara; sinyal keamanan dikirim | Should |

### 8.2 Election Management (FR-ELEC)

| ID | Nama dan deskripsi | Aktor | Pra | Alur | Gagal/Alt | Acceptance | Pri |
|---|---|---|---|---|---|---|---|
| FR-ELEC-001 | **Membuat pemilihan** (status `DRAFT`) | Admin | Login Admin | Isi judul, deskripsi, `start_at`, `end_at` | `start_at ≥ end_at` → `VALIDATION_ERROR` | Pemilihan dibuat `DRAFT`; hanya Admin | Must |
| FR-ELEC-002 | **Daftar dan detail pemilihan** | Admin, Auditor, Voter | Login | Admin/Auditor melihat sesuai hak; Voter hanya yang ia berhak ikuti dan bukan `DRAFT` | Di luar hak → `NOT_FOUND` | Voter tidak melihat pemilihan lain atau `DRAFT` | Must |
| FR-ELEC-003 | **Kelola kandidat** | Admin | Status `DRAFT` | Tambah kandidat (nama, urutan) | Status bukan `DRAFT` → `ELECTION_INVALID_STATE`; nama/urutan ganda → `CONFLICT` | Kandidat unik per pemilihan | Must |
| FR-ELEC-004 | **Kelola daftar pemilih** (impor) | Admin | Status `DRAFT` | Impor daftar (email, referensi eksternal, label) | Duplikat/format salah → `VALIDATION_ERROR` (all-or-nothing); bukan `DRAFT` → `ELECTION_INVALID_STATE` | Daftar tersimpan; tidak berisi data pribadi sungguhan pada data uji | Must |
| FR-ELEC-005 | **Menjadwalkan** (`DRAFT→SCHEDULED`) | Admin | ≥ 2 kandidat, ≥ 1 pemilih, jadwal valid | Validasi → bekukan kandidat/pemilih → buat kelayakan | Guard gagal → `VALIDATION_ERROR` | Setelah `SCHEDULED`, kandidat dan pemilih tidak dapat diubah | Must |
| FR-ELEC-006 | **Membuka pemilihan** (`SCHEDULED→OPEN`) | Admin | `SCHEDULED`, sebelum `end_at` | Ubah status → event `ElectionOpened` | Status salah → `ELECTION_INVALID_STATE` | Status `OPEN`; event dicatat di audit | Must |
| FR-ELEC-007 | **Menutup pemilihan** (`OPEN→CLOSED`) | Admin | `OPEN` | Ubah status, catat `closed_at` → event `ElectionClosed` | Status salah → `ELECTION_INVALID_STATE` | Suara baru ditolak setelah `closed_at` | Must |
| FR-ELEC-008 | **Menolak perubahan tidak sah setelah pemilihan dimulai** | Sistem | Status ≥ `SCHEDULED` | Tolak perubahan kandidat/pemilih/jadwal | `ELECTION_INVALID_STATE` | Tidak ada jalur API mengubah kandidat/pemilih setelah `SCHEDULED` (BR-008) | Must |

### 8.3 Voter Eligibility (FR-ELIG)

| ID | Nama dan deskripsi | Aktor | Pra | Alur | Gagal/Alt | Acceptance | Pri |
|---|---|---|---|---|---|---|---|
| FR-ELIG-001 | **Validasi kelayakan dan penerbitan vote ticket** | Voter | Login; pemilihan `OPEN` | Voter meminta ballot → Voter Service cek daftar, status, belum memilih → terbitkan ticket berpseudonim | Tak terdaftar → `VOTER_NOT_ELIGIBLE`; sudah memilih → `VOTER_ALREADY_VOTED`; tidak `OPEN` → `ELECTION_NOT_OPEN` | Ticket tidak memuat identitas; berlaku singkat (**PROPOSED TARGET:** 10 menit) | Must |
| FR-ELIG-002 | **Menolak pengguna tak terdaftar** | Sistem | — | Tidak ada baris pemilih untuk akun → tolak | `VOTER_NOT_ELIGIBLE` | Akun VOTER tak terdaftar tidak mendapat ticket | Must |
| FR-ELIG-003 | **Perubahan status pemilih** (mis. `REVOKED`) | Admin | Sebelum `OPEN` | Cabut kelayakan | Setelah `OPEN` → tidak diizinkan di MVP (BR-008) | Pemilih `REVOKED` ditolak | Could |
| FR-ELIG-004 | **Pembatasan akses data pribadi pemilih** | Sistem | — | Daftar pemilih hanya terlihat Admin; Auditor/Voter tidak | `FORBIDDEN` | Tidak ada endpoint publik yang mengembalikan email/nama pemilih | Must |

### 8.4 Ballot Casting (FR-BALL)

| ID | Nama dan deskripsi | Aktor | Pra | Alur | Gagal/Alt | Acceptance | Pri |
|---|---|---|---|---|---|---|---|
| FR-BALL-001 | **Menampilkan pemilihan dan ballot** | Voter | Eligible, `OPEN` | Tampilkan kandidat + ticket | Lihat FR-ELIG-001 | Hanya pemilihan yang boleh diikuti | Must |
| FR-BALL-002 | **Menerima suara valid** | Voter | Ticket valid | Validasi ticket, status, kandidat → simpan | Ticket rusak → `VOTE_TICKET_INVALID`; kandidat tidak ada → `VALIDATION_ERROR` | Suara tersimpan tanpa `user_id`/email | Must |
| FR-BALL-003 | **Mencegah suara ganda** | Sistem | — | Satu kelayakan hanya satu suara (unique constraint + transaksi) | `VOTER_ALREADY_VOTED` | Percobaan kedua ditolak; satu baris suara per kelayakan | Must |
| FR-BALL-004 | **Menangani request paralel** | Sistem | — | Serialisasi konflik lewat database | Tanpa 5xx | **PROPOSED TARGET:** 50 request paralel → tepat satu suara | Must |
| FR-BALL-005 | **Idempotency** | Voter | `Idempotency-Key` ada | Key sama + payload sama → respons sama | Key sama + payload beda → `IDEMPOTENCY_CONFLICT`; key hilang → `VALIDATION_ERROR` | Retry tidak menambah suara; receipt sama | Must |
| FR-BALL-006 | **Menolak suara di luar waktu pemilihan** | Sistem | — | Status harus `OPEN` dan `now ≤ end_at` | `ELECTION_NOT_OPEN`; Voter Service tak tersedia → `SERVICE_UNAVAILABLE` (fail-closed) | Tidak ada suara dengan `accepted_at > closed_at` dihitung | Must |
| FR-BALL-007 | **Tanda terima tanpa pilihan** | Voter | Suara diterima | Beri `receipt_id` + kode; status audit `PENDING`/`RECORDED` | Kode salah → `RECEIPT_NOT_FOUND` | Receipt tidak memuat kandidat atau identitas | Must |
| FR-BALL-008 | **Transactional outbox** | Sistem | — | Event `VoteAccepted` ditulis dalam transaksi suara | — | Tidak ada suara tanpa baris outbox; saat broker mati suara tetap diterima | Must |

### 8.5 Audit and Integrity (FR-AUDT)

| ID | Nama dan deskripsi | Aktor | Pra | Alur | Gagal/Alt | Acceptance | Pri |
|---|---|---|---|---|---|---|---|
| FR-AUDT-001 | **Mencatat event penting** | Sistem | Event diterima | Proyeksi allowlist → append | Skema salah → DLQ | Event duplikat tidak membuat entri baru | Must |
| FR-AUDT-002 | **Menyusun hash chain** | Sistem | — | Hash entri memuat hash sebelumnya per scope | — | Urutan `sequence` tanpa celah; `prev_hash` konsisten | Must |
| FR-AUDT-003 | **Memeriksa integritas** | Admin, Auditor | Ada entri | Hitung ulang rantai, bandingkan checkpoint | Gagal → status `INVALID` dengan lokasi | Mendeteksi ubah/hapus/sisip/potong ekor pada data uji | Must |
| FR-AUDT-004 | **Bukti audit yang diizinkan** | Admin, Auditor, Voter | — | Sajikan head, checkpoint, hasil verifikasi, opsional bukti receipt | — | Tidak ada identitas, pilihan, atau pseudonim kelayakan | Must |
| FR-AUDT-005 | **Checkpoint audit di luar database** | Sistem | — | Tulis checkpoint ber-HMAC ke volume terpisah | — | Verifikasi membandingkan dengan checkpoint | Should |
| FR-AUDT-006 | **Deteksi manipulasi pada skenario uji** | Admin | Lab aktif | Attack Lab memodifikasi record uji lalu verifikasi | — | Setiap jenis modifikasi terdeteksi | Must |

### 8.6 Result Management (FR-RSLT)

| ID | Nama dan deskripsi | Aktor | Pra | Alur | Gagal/Alt | Acceptance | Pri |
|---|---|---|---|---|---|---|---|
| FR-RSLT-001 | **Menghitung suara sah** | Admin | Pemilihan `CLOSED` | Ambil ekspor suara dari Ballot, hitung per kandidat | Bukan `CLOSED` → `ELECTION_INVALID_STATE` | Hitungan sama dengan hitung ulang independen | Must |
| FR-RSLT-002 | **Rekonsiliasi** | Sistem | Tally berjalan | Bandingkan jumlah suara (Ballot), catatan audit, dan partisipasi (Voter) + commitment | Selisih → `RECONCILIATION_FAILED`/`BALLOT_INTEGRITY_FAILED` | Status `MATCH` hanya jika semua cocok | Must |
| FR-RSLT-003 | **Penghitungan ulang** | Admin | Belum final | Jalankan tally baru (`run_number` naik) | Sudah final → `ELECTION_INVALID_STATE` (OD-13) | Riwayat run tersimpan | Should |
| FR-RSLT-004 | **Finalisasi hasil** | Admin | Tally `COMPLETED`+`MATCH`; audit `VALID` | Simpan snapshot + `result_hash` (immutable) → event | — | Hasil final tidak dapat diubah lewat API | Must |
| FR-RSLT-005 | **Menolak finalisasi bila prasyarat belum terpenuhi** | Sistem | — | Cek tally, rekonsiliasi, verifikasi audit | `RECONCILIATION_FAILED`, `AUDIT_VERIFICATION_FAILED` | Finalisasi ditolak untuk tiap prasyarat tak terpenuhi | Must |
| FR-RSLT-006 | **Hasil sesuai kewenangan** | Admin, Auditor, Voter | — | Admin/Auditor: sementara atau final; Voter hanya final | Voter sebelum final → `RESULT_NOT_FINALIZED` | Voter tidak melihat hasil sementara | Must |
| FR-RSLT-007 | **Verifikasi hasil** | Admin, Auditor, Voter | Sudah final | Hitung ulang dan cocokkan snapshot, hash, audit | Sebelum final → `RESULT_NOT_FINALIZED` | Mismatch dilaporkan per pemeriksaan | Should |

### 8.7 Security Monitoring (FR-SECM)

| ID | Nama dan deskripsi | Aktor | Pra | Alur | Gagal/Alt | Acceptance | Pri |
|---|---|---|---|---|---|---|---|
| FR-SECM-001 | **Mencatat aktivitas keamanan** | Sistem | — | Simpan event/sinyal ter-allowlist | Event duplikat dibuang | Tanpa identitas atau pilihan | Must |
| FR-SECM-002 | **Deteksi anomali berbasis aturan** | Sistem | — | Evaluasi aturan R-01..R-10 (`SECURITY_AND_TEST_PLAN.md` D.1) | False positive mungkin | Kondisi aturan memicu alert | Must |
| FR-SECM-003 | **Alert** | Admin, Auditor | — | Daftar alert dengan severity | — | Alert terdedup; dapat difilter | Must |
| FR-SECM-004 | **Metrik** | Admin, Auditor | — | Sajikan metrik operasional/keamanan | — | Metrik tersedia tanpa data sensitif | Should |
| FR-SECM-005 | **Attack Lab hanya di lingkungan uji** | Admin | `ATTACK_LAB_ENABLED` dan `APP_ENV` lokal/uji | Jalankan skenario pada pemilihan lab | Lab nonaktif → `FORBIDDEN` | Hanya menyasar pemilihan `is_attack_lab=true`; tidak dapat menyerang sistem eksternal | Must |
| FR-SECM-006 | **Mencatat hasil simulasi** | Admin | — | Simpan expected vs actual per langkah | — | Hasil aktual tersimpan dan dapat dibaca | Must |

### 8.8 System Operations (FR-SYSO) dan Antarmuka Pengguna (FR-UI)

| ID | Nama dan deskripsi | Aktor | Pra | Alur | Gagal/Alt | Acceptance | Pri |
|---|---|---|---|---|---|---|---|
| FR-SYSO-001 | **Health check** | Operator | — | `/health/live`, `/health/ready` tiap layanan | Dependensi mati → ready gagal | Compose memakainya untuk urutan start | Must |
| FR-SYSO-002 | **Logging terstruktur** | Sistem | — | Log JSON dengan request/correlation ID | — | Tidak ada field terlarang (NFR-PRV-003) | Must |
| FR-SYSO-003 | **Correlation ID** | Sistem | — | Gateway membuat ID; diteruskan ke layanan dan event | — | ID sama terlihat pada request, log, dan event terkait | Must |
| FR-SYSO-004 | **Penanganan kesalahan** | Sistem | — | Format error baku | — | Tanpa stack trace/secret ke pengguna | Must |
| FR-SYSO-005 | **Retry dan pemulihan event** | Sistem | — | Relay outbox, retry bertahap, DLQ, replay manual | Pesan permanen gagal → DLQ | Event tertunda diproses tanpa efek ganda | Must |
| FR-SYSO-006 | **Kesiapan layanan** | Operator | — | Compose menunggu dependensi sehat; migrasi sebelum start | — | Stack dapat dinaikkan dari kondisi kosong | Must |
| FR-SYSO-007 | **Rate limiting** | Gateway | — | Batas per IP/rute | Lewat batas → `RATE_LIMIT_EXCEEDED` | Nilai batas: PROPOSED TARGET (`API_CONTRACTS.md` A.9) | Must |
| FR-UI-001 | **UI Voter:** login, daftar pemilihan, ballot, konfirmasi, receipt, hasil final | Voter | — | Alur memilih | Pesan error jelas | Alur selesai tanpa pindah ke alat lain | Must |
| FR-UI-002 | **UI Admin:** kelola pemilihan, kandidat, pemilih, lifecycle, tally, finalisasi | Admin | — | — | — | Tindakan terlarang ditampilkan nonaktif dan tetap ditolak backend | Must |
| FR-UI-003 | **UI Auditor/Security:** verifikasi audit, bukti, alert, metrik, Attack Lab | Auditor, Admin | — | — | — | Auditor tidak melihat kontrol tulis | Should |

---

## 9. Business Rules

| ID | Aturan |
|---|---|
| BR-001 | Satu kelayakan pemilih menghasilkan **paling banyak satu suara sah** per pemilihan |
| BR-002 | Suara hanya diterima saat status `OPEN` **dan** `now ≤ end_at` |
| BR-003 | Lifecycle: `DRAFT → SCHEDULED → OPEN → CLOSED → FINALIZED`; tidak ada transisi mundur; tidak ada *reopen* |
| BR-004 | Hasil tidak boleh difinalisasi sebelum tally `COMPLETED`, rekonsiliasi `MATCH`, dan verifikasi audit `VALID` |
| BR-005 | Event duplikat tidak boleh menggandakan efek bisnis |
| BR-006 | Hak akses diperiksa di backend, bukan hanya di frontend |
| BR-007 | Pilihan suara dan identitas pemilih tidak dimasukkan ke event audit/keamanan yang tidak membutuhkannya |
| BR-008 | Kandidat, daftar pemilih, dan jadwal **dibekukan** saat `SCHEDULED`. Setelah itu tidak ada perubahan di MVP; kebutuhan perubahan harus lewat keputusan eksplisit dan tercatat di audit (belum didefinisikan, OPEN DECISION OD-20) |
| BR-009 | Hasil final hanya ditambahkan (*append-only*); tidak ada endpoint ubah/hapus suara atau hasil final |
| BR-010 | Attack Lab hanya pada pemilihan berflag lab di lingkungan lokal/uji |
| BR-011 | Satu akun memiliki satu role; Admin tidak otomatis pemilih |
| BR-012 | Tidak ada hasil (termasuk sementara) sebelum pemilihan `CLOSED` (usulan, OD-12) |

Transisi lifecycle dan wewenang rinci: SAD Bagian 7.3 dan `ARCHITECTURE.md` H.

---

## 10. Non-Functional Requirements

Target angka berlabel **PROPOSED TARGET** belum memiliki baseline dan **belum tercapai**. Metode verifikasi: T = test otomatis, I = inspeksi/review, D = demo, M = pengukuran.

### Security

| ID | Requirement | Verifikasi | Pri |
|---|---|---|---|
| NFR-SEC-001 | Password disimpan sebagai hash Argon2id; tidak pernah di-log atau dikembalikan | T (unit), I | Must |
| NFR-SEC-002 | Semua endpoint non-publik menuntut token valid; role dicek di Gateway dan layanan | T (API-RBAC matriks) | Must |
| NFR-SEC-003 | Rate limiting pada login dan voting; respons `429` + `Retry-After` | T, M | Must |
| NFR-SEC-004 | Input divalidasi ketat (tipe, panjang, field tak dikenal ditolak) | T | Must |
| NFR-SEC-005 | Perlindungan replay: refresh token berotasi dengan deteksi reuse; vote ticket berumur pendek; idempotency key | T | Must |
| NFR-SEC-006 | Secret hanya dari environment; tidak ada di repo/dokumen/log | I (pemindaian), T | Must |
| NFR-SEC-007 | Data sensitif (password hash, `ELIGIBILITY_PEPPER`, nonce suara) tidak dikembalikan lewat API | T | Must |
| NFR-SEC-008 | Hanya Gateway yang dipublikasikan; layanan internal tidak dapat dijangkau dari luar jaringan Compose; autentikasi antarlayanan dengan kunci internal | I, T | Must |
| NFR-SEC-009 | Role database hak minimum; tabel suara/audit/hasil final tanpa UPDATE/DELETE bagi role aplikasi | I, T | Must |

### Privacy

| ID | Requirement | Verifikasi | Pri |
|---|---|---|---|
| NFR-PRV-001 | Minimisasi data: tabel suara tidak menyimpan `user_id`/email; event audit/keamanan tanpa pilihan dan identitas | T (pemindaian field) | Must |
| NFR-PRV-002 | Identitas dan pilihan dipisahkan di layanan/database berbeda; pseudonim `eligibility_ref` per pemilihan; batas anonimitas didokumentasikan | I, analisis | Must |
| NFR-PRV-003 | Log tidak memuat password, token, ticket, kode receipt, `candidate_id`, nonce | T (pemindaian log) | Must |
| NFR-PRV-004 | Retensi dan penghapusan data: kebijakan ditetapkan (OD-17); data uji dapat dihapus lewat reset lingkungan | I | Should |
| NFR-PRV-005 | Auditor tidak mendapat identitas atau pilihan individu | T | Must |

### Reliability

| ID | Requirement | Verifikasi | Pri |
|---|---|---|---|
| NFR-REL-001 | Penerimaan suara tidak bergantung pada ketersediaan RabbitMQ atau Audit Service | T (pemulihan) | Must |
| NFR-REL-002 | Ketergantungan sinkron kritis (status pemilihan) bersifat fail-closed (`SERVICE_UNAVAILABLE`) | T | Must |
| NFR-REL-003 | Event at-least-once; konsumen idempotent; retry bertahap; pesan gagal ke DLQ | T | Must |
| NFR-REL-004 | Idempotency suara: retry tidak menambah suara | T | Must |
| NFR-REL-005 | Konsistensi penghitungan: hasil final sama dengan hitung ulang independen dari suara sah | T | Must |
| NFR-REL-006 | Recovery: setelah broker/layanan pulih, backlog outbox menjadi nol tanpa duplikasi efek | T | Must |

### Performance (PROPOSED TARGET)

| ID | Requirement | Verifikasi | Pri |
|---|---|---|---|
| NFR-PRF-001 | p95 latensi `POST /ballots` ≤ 500 ms pada perangkat pengembangan, 50 request paralel | M (PERF) | Should |
| NFR-PRF-002 | Throughput: 50 request voting paralel selesai tanpa 5xx | T (CC) | Must |
| NFR-PRF-003 | Lag outbox→audit p95 ≤ 10 s saat broker sehat | M | Should |
| NFR-PRF-004 | Tally untuk 1.000 suara selesai ≤ 10 s | M | Could |
| NFR-PRF-005 | Verifikasi hash chain 10.000 entri ≤ 60 s | M | Could |

### Scalability

| ID | Requirement | Verifikasi | Pri |
|---|---|---|---|
| NFR-SCL-001 | Layanan dirancang *stateless* (state di PostgreSQL/Redis) agar dapat ditambah instance; kecuali Audit consumer (single consumer untuk urutan chain) dan outbox relay (aman multi-instance via `SKIP LOCKED`) | I | Should |
| NFR-SCL-002 | Bottleneck diketahui: PostgreSQL tunggal, satu antrean audit; dicatat sebagai batas | I | Could |

### Maintainability

| ID | Requirement | Verifikasi | Pri |
|---|---|---|---|
| NFR-MNT-001 | Satu tanggung jawab dan satu pemilik data per layanan; tanpa akses tabel lintas layanan | I (IT-ARCH-01) | Must |
| NFR-MNT-002 | Kontrak API/event dapat diterjemahkan ke OpenAPI 3.1 dan Pydantic | I | Must |
| NFR-MNT-003 | Migrasi Alembic per layanan | D, T | Must |
| NFR-MNT-004 | Automated test mencakup unit, integrasi, API, konkurensi, keamanan, pemulihan | I | Must |
| NFR-MNT-005 | Dokumentasi teknis dimutakhirkan bersama perubahan kontrak | I | Should |

### Observability

| ID | Requirement | Verifikasi | Pri |
|---|---|---|---|
| NFR-OBS-001 | Log terstruktur JSON dengan `request_id` dan `correlation_id` | I, T | Must |
| NFR-OBS-002 | Health dan readiness check semua layanan | T | Must |
| NFR-OBS-003 | Metrik dan alert keamanan; pemantauan outbox backlog dan DLQ | T | Should |

### Usability and Accessibility

| ID | Requirement | Verifikasi | Pri |
|---|---|---|---|
| NFR-USA-001 | Navigasi jelas per peran; alur memilih ≤ 4 langkah (PROPOSED TARGET) | D, I | Should |
| NFR-USA-002 | Validasi formulir dan pesan error berbahasa Indonesia yang dapat dipahami | D, T | Should |
| NFR-USA-003 | Desain responsif (layar ponsel dan desktop) | D | Should |
| NFR-USA-004 | Aksesibilitas dasar: label formulir, kontras memadai, navigasi keyboard | I | Could |

### Portability

| ID | Requirement | Verifikasi | Pri |
|---|---|---|---|
| NFR-POR-001 | Seluruh lingkungan pengembangan dapat dijalankan dengan Docker Compose dari repository bersih mengikuti instruksi tertulis | D | Must |

---

## 11. External Interface Requirements

| Antarmuka | Persyaratan |
|---|---|
| Antarmuka pengguna | Web React responsif; tiga ruang kerja berdasarkan role (Voter, Admin, Auditor/Security) |
| REST API | JSON UTF-8 lewat Gateway, prefix `/api/v1`; OpenAPI 3.1; ID UUID; waktu UTC ISO 8601 |
| Autentikasi | `Authorization: Bearer <access_token>`; refresh token hanya di body refresh/logout |
| Header | `X-Request-ID`, `X-Correlation-ID`, `Idempotency-Key` (voting) |
| Event broker | RabbitMQ exchange topic dengan envelope baku (`event_id`, `event_type`, `schema_version`, `occurred_at`, `correlation_id`, `payload`) |
| Database | PostgreSQL; satu database per layanan; akses hanya oleh pemilik |
| Kontrak antarlayanan | Sinkron: panggilan internal terbatas (Ballot→Voter, Result→Ballot/Audit/Voter, Security→Ballot); asinkron: event. Detail: `API_CONTRACTS.md`, SAD Bagian 11 dan 15 |

Skema endpoint lengkap berada di `API_CONTRACTS.md`; SRS tidak mendefinisikan endpoint baru yang bertentangan.

## 12. Data Requirements

| Entitas | Layanan pemilik | Catatan integritas/akses/sensitivitas |
|---|---|---|
| User | auth | Email, hash password: sensitif; tidak pernah di-log |
| Election | voter | Status mengikuti lifecycle; perubahan dibatasi (BR-008) |
| Candidate | voter | Dibekukan saat `SCHEDULED` |
| Voter | voter | Email/label pemilih: data pribadi, hanya Admin |
| Voting Eligibility | voter | `eligibility_ref` pseudonim per pemilihan |
| Ballot | ballot | `candidate_id` + `eligibility_ref`; tanpa `user_id`; append-only |
| Audit Event | audit | Payload ter-allowlist; hash chain; append-only |
| Tally Run | result | Riwayat hitungan dan rekonsiliasi |
| Final Result | result | Immutable; `result_hash` |
| Security Event | security | Tanpa identitas/pilihan; fingerprint IP ter-hash |
| Anomaly Alert | security | Dedup; bukti ter-allowlist |
| Attack Run | security | Hanya data lab; hasil expected vs actual |

Kebutuhan data: integritas lewat constraint, transaksi, dan hak minimum; pemisahan data sensitif (identitas di `auth_db`/`voter_db`, pilihan di `ballot_db`); retensi: OD-17. Sistem **tidak** menautkan identitas ke pilihan dalam satu relasi; pihak yang mengakses *kedua* database dapat menautkan lewat pseudonim (batas dinyatakan di Bagian 16). Skema kolom: `ARCHITECTURE.md` D dan SAD Bagian 8.

## 13. Error Handling Requirements

| Kategori | Kode (HTTP) | Persyaratan |
|---|---|---|
| Validation error | `VALIDATION_ERROR` (422) | Daftar field bermasalah tanpa detail internal |
| Authentication error | `UNAUTHORIZED` (401), `ACCOUNT_LOCKED` (423) | Pesan generik; tidak membocorkan keberadaan akun |
| Authorization error | `FORBIDDEN` (403), `VOTER_NOT_ELIGIBLE` (403), `VOTE_TICKET_INVALID` (403) | Tidak membocorkan keberadaan resource di luar hak (gunakan `NOT_FOUND`) |
| Conflict | `VOTER_ALREADY_VOTED`, `IDEMPOTENCY_CONFLICT`, `ELECTION_NOT_OPEN`, `ELECTION_INVALID_STATE`, `CONFLICT` (409) | Kondisi dapat dibedakan klien |
| Rate limit exceeded | `RATE_LIMIT_EXCEEDED` (429) | Sertakan `Retry-After` |
| Dependency unavailable | `SERVICE_UNAVAILABLE` (503) | Fail-closed untuk validasi suara |
| Internal server error | `INTERNAL_ERROR` (500) | Pesan generik + `request_id` |

Stack trace, secret, SQL, dan informasi sensitif **tidak boleh** dikirim ke pengguna; detail hanya di log internal dengan `request_id`. Format error baku: `API_CONTRACTS.md` D.

---

## 14. Acceptance and Verification Matrix

Test case berstatus **PLANNED** (rencana ada di `SECURITY_AND_TEST_PLAN.md` E; belum ada kode uji). Hanya requirement Must ditampilkan; Should/Could mengikuti metode di tabel NFR dan acceptance FR.

| Requirement | Ringkasan | Metode | Skenario (PLANNED) | Hasil yang diharapkan | Pri |
|---|---|---|---|---|---|
| FR-AUTH-001 | Registrasi aman | Test API | API-AUTH-01 | Hanya `VOTER` lewat jalur publik | Must |
| FR-AUTH-002 | Login | Test API | API-AUTH-02, 03 | Token valid / `UNAUTHORIZED` generik | Must |
| FR-AUTH-003 | Refresh rotasi | Test API | API-AUTH-04 | Reuse mencabut keluarga sesi | Must |
| FR-AUTH-004 | Logout | Test API | API-AUTH-05 | Token pasca-logout ditolak | Must |
| FR-AUTH-005 | `me` | Test API | API-AUTH-06 | Data pengguna tanpa rahasia | Must |
| FR-AUTH-006 | RBAC | Test API parametrik | API-RBAC-01, ATK-03, ATK-04 | Sesuai matriks role | Must |
| FR-ELEC-001..004 | Pemilihan, kandidat, pemilih | Test API/integrasi | IT-VOT-01..04 | Sesuai guard status | Must |
| FR-ELEC-005..008 | Lifecycle dan pembekuan | Unit + integrasi | UT-LIFE-01, IT-VOT-02..03 | Hanya transisi sah | Must |
| FR-ELIG-001, 002, 004 | Kelayakan dan privasi | Integrasi | IT-VOT-04, 05, ATK-10 | Ticket hanya untuk pemilih sah | Must |
| FR-BALL-001..002 | Ballot dan penerimaan | Integrasi/E2E | IT-BAL-01, E2E-01 | Suara tersimpan tanpa identitas | Must |
| FR-BALL-003 | Cegah suara ganda | Integrasi/Attack | IT-BAL-02, ATK-01 | `VOTER_ALREADY_VOTED`; satu baris | Must |
| FR-BALL-004 | Request paralel | Konkurensi | CC-01, ATK-02 | Tepat satu suara | Must |
| FR-BALL-005 | Idempotency | Integrasi/Konkurensi | IT-BAL-03, 04, CC-02 | Respons sama; `IDEMPOTENCY_CONFLICT` | Must |
| FR-BALL-006 | Waktu pemilihan | Integrasi/Attack | IT-BAL-06, 07, ATK-05 | `ELECTION_NOT_OPEN`/fail-closed | Must |
| FR-BALL-007 | Receipt | Test API | API-BAL-04, SEC-PRV-01 | Tanpa pilihan/identitas | Must |
| FR-BALL-008 | Outbox | Integrasi | IT-BAL-05, IT-OUT-01 | Suara dan outbox atomik | Must |
| FR-AUDT-001..003 | Catat, chain, verifikasi | Unit/integrasi | IT-AUD-01, 02, UT-HASH-01, 02 | Rantai valid; duplikat diabaikan | Must |
| FR-AUDT-004 | Bukti publik | Test/pemindaian | SEC-PRV-01 | Tanpa data sensitif | Must |
| FR-AUDT-006 | Deteksi manipulasi | Attack | ATK-06, SEC-AUD-01..04 | Semua modifikasi terdeteksi | Must |
| FR-RSLT-001, 002 | Tally dan rekonsiliasi | Integrasi | IT-RES-01, 02, 04 | `MATCH` hanya bila semua cocok | Must |
| FR-RSLT-004, 005 | Finalisasi | Integrasi | IT-RES-03, 05 | Immutable; ditolak bila prasyarat gagal | Must |
| FR-RSLT-006 | Hak akses hasil | Test API | ATK-04, API-RBAC-01 | Voter hanya hasil final | Must |
| FR-SECM-001..003 | Event, aturan, alert | Integrasi | IT-SEC-01..06 | Alert sesuai kondisi | Must |
| FR-SECM-005, 006 | Attack Lab terkunci dan tercatat | Test/demo | SEC-CFG-03, ATK-01..10 | Nonaktif di luar uji; hasil tercatat | Must |
| FR-SYSO-001..007 | Operasi sistem | Demo/test | SEC-CFG-01..03, REC-01..04, API-RL-01 | Sesuai acceptance | Must |
| FR-UI-001, 002 | UI Voter dan Admin | Demo/E2E | E2E-01, E2E-02 | Alur utama selesai | Must |
| NFR-SEC-001..009 | Keamanan | Test/inspeksi | UT-AUTH-01, SEC-CFG, SEC-DB | Sesuai tabel NFR | Must |
| NFR-PRV-001..003, 005 | Privasi | Pemindaian | SEC-PRV-01..04 | Tidak ada field terlarang | Must |
| NFR-REL-001..006 | Reliabilitas | Pemulihan/konkurensi | REC-01..04, CC-01..03 | Tanpa suara hilang/ganda | Must |
| NFR-PRF-002 | 50 request paralel tanpa 5xx | Konkurensi | CC-01 | Tanpa 5xx | Must |
| NFR-MNT-001..004 | Pemeliharaan | Inspeksi | IT-ARCH-01 | Tidak ada akses lintas DB | Must |
| NFR-OBS-001, 002 | Log dan health | Test/inspeksi | SEC-PRV-02, FR-SYSO-001 | Sesuai | Must |
| NFR-POR-001 | Compose dari repo bersih | Demo | Prosedur instalasi | Stack hidup | Must |

---

## 15. Traceability Matrix

Semua test case berstatus **PLANNED**. Layanan: GW = api-gateway, AU = auth, VO = voter, BA = ballot, AD = audit, RE = result, SE = security, FE = frontend.

| Objective (Charter) | Requirement | Layanan | Test case (PLANNED) | Deliverable |
|---|---|---|---|---|
| OBJ-01 Cegah suara ganda | FR-BALL-002..006, BR-001, NFR-REL-004 | BA, VO | IT-BAL-02, CC-01, CC-02, ATK-01, ATK-02 | D-04, D-05, D-06 |
| OBJ-02 Deteksi percobaan ganda | FR-SECM-001..003 | SE, BA | IT-SEC-01, ATK-01 | D-04, D-06 |
| OBJ-03 Integritas audit | FR-AUDT-001..006 | AD | IT-AUD-01, SEC-AUD-01..04, ATK-06 | D-04, D-05 |
| OBJ-04 Konsistensi penghitungan | FR-RSLT-001..007, NFR-REL-005 | RE, BA, AD, VO | IT-RES-01..05, E2E-03 | D-04, D-05 |
| OBJ-05 Deteksi anomali | FR-SECM-002..006 | SE | IT-SEC-01..06, ATK-01..10 | D-06 |
| OBJ-06 Komunikasi antarlayanan | FR-BALL-008, FR-SYSO-005, NFR-REL-001..006 | BA, AD, VO, SE | IT-OUT-01, ATK-07, ATK-08, REC-01..04 | D-04, D-05 |
| OBJ-07 Otorisasi backend | FR-AUTH-001..007, BR-006, NFR-SEC-002 | AU, GW, semua | API-RBAC-01, ATK-03, ATK-04 | D-04, D-05 |
| OBJ-08 Kerahasiaan identitas–pilihan | FR-ELIG-001, 004, FR-BALL-007, NFR-PRV-001..005, BR-007 | VO, BA, AD, SE | SEC-PRV-01..04, ATK-10 | D-03, D-05 |

**Pemetaan ke seri dokumen lama** (penelusuran): `PROJECT_BRIEF.md` FR-01..FR-23 ↔ SRS: FR-01/02/03 → FR-AUTH; FR-04/05 → FR-ELEC; FR-06 → FR-ELIG-001; FR-07..FR-11 → FR-BALL; FR-12 → FR-BALL-008, FR-SYSO-005; FR-13/14 → FR-AUDT; FR-15..17 → FR-RSLT; FR-18/19/23 → FR-SECM; FR-20 → FR-SYSO-003, 007; FR-21 → FR-SYSO-005; FR-22 → FR-UI. Pemetaan ke komponen arsitektur: SAD Bagian 6.

---

## 16. Out of Scope and Known Limitations

Klaim yang **tidak** dapat dibuat tanpa desain, implementasi, dan pengujian tambahan:

- Sistem memenuhi persyaratan pemilu resmi atau tersertifikasi.
- Anonimitas sempurna: pseudonimisasi mengurangi risiko, bukan menjamin; kolusi `voter_db` + `ballot_db`, korelasi waktu, dan kebocoran pepper dapat mengungkap hubungan identitas–pilihan.
- Hash chain menjamin tidak mungkin dimanipulasi: ia hanya membantu **mendeteksi** perubahan; penyerang yang menguasai seluruh database dan kunci/checkpoint dapat membangun ulang rantai.
- *End-to-end verifiable voting:* tidak ada protokol kriptografi pemilu; pemilih tidak dapat memverifikasi sendiri bahwa pilihannya dihitung sebagaimana diberikan.
- Keamanan formal terbukti, atau tahan DoS terdistribusi dan penyerang berhak akses infrastruktur penuh.
- Kelayakan = identitas nyata: impersonasi akun melalui email milik orang lain mungkin (OD-01).
- Deteksi anomali berbasis aturan dapat menghasilkan false positive/negative.
- Semua kontrol berstatus **direncanakan**; belum ada hasil pengujian.

## 17. Open Questions

| ID | Pertanyaan | Usulan | Status |
|---|---|---|---|
| OD-01 | Cara memastikan pemilik akun adalah pemilih sah | Email terimpor (MVP) → `voter_code` | OPEN DECISION |
| OD-11 | Registrasi mandiri atau oleh Admin? | Mandiri hanya `VOTER`; Admin/Auditor oleh Admin | OPEN DECISION |
| OD-12 | Auditor boleh melihat jumlah suara sebelum penutupan? | Tidak; tally hanya setelah `CLOSED` | OPEN DECISION |
| OD-13 | Hasil dapat dihitung ulang setelah finalisasi? | Tidak; sebelum final boleh (run baru) | OPEN DECISION |
| OD-16 | Target peserta dan beban concurrent | PROPOSED TARGET: ≤ 1.000 pemilih; 50 request paralel | OPEN DECISION |
| OD-17 | Lama penyimpanan data audit | Selama masa penilaian akademik | OPEN DECISION |
| OD-19 | Versi dependency | Pin saat implementasi | OPEN DECISION |
| OD-20 | Kebijakan perubahan kandidat/pemilih setelah dibuka | Tidak diizinkan di MVP; bila perlu, tindakan tercatat di audit | OPEN DECISION |
| OD-02, 07, 14, 15, 18 | Lihat `01_PROJECT_CHARTER.md` Bagian 14 | — | OPEN DECISION |
