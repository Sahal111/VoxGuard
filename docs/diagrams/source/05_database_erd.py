"""VoxGuard - ERD konseptual database-per-service (RANCANGAN / PROPOSED).
Sumber: 04_DATABASE_DESIGN_ERD.md Bagian 3-5 (kolom, tipe, constraint) dan 03_SYSTEM_ARCHITECTURE_DOCUMENT.md Bagian 7-8.
Hanya kolom kunci dan kolom penting yang digambar; skema lengkap ada di dokumen 04.
Jalankan: python3 05_database_erd.py -> ../05_database_erd.png
Referensi lintas database digambar sebagai lencana bernomor (R1..R5), BUKAN garis foreign key.
"""
import os
from diagram_kit import Canvas, INK, GRAY

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "05_database_erd.png")
HDR = {"auth": "#DBEAFE", "voter": "#DCFCE7", "ballot": "#FEF3C7", "audit": "#FCE7F3", "result": "#E0E7FF", "security": "#FEE2E2"}
CLB = {"auth": "#EFF6FF", "voter": "#F0FDF4", "ballot": "#FFFBEB", "audit": "#FDF2F8", "result": "#EEF2FF", "security": "#FEF2F2"}
MARK = {"PK": ("PK", "#B91C1C"), "FK": ("FK", "#1D4ED8"), "UK": ("UK", "#047857"), "": ("", INK)}
PURPLE = "#7C3AED"
TABLES = {
    "auth": {
        "users": [("PK", "id", "uuid"), ("UK", "email", "text"), ("", "display_name", "text"), ("", "password_hash", "text"),
                  ("", "role", "text"), ("", "is_active", "boolean"), ("", "failed_login_count", "integer"),
                  ("", "locked_until", "timestamptz")],
        "refresh_sessions": [("PK", "id", "uuid"), ("FK", "user_id", "uuid"), ("", "family_id", "uuid"),
                             ("UK", "token_hash", "char(64)"), ("", "expires_at", "timestamptz"),
                             ("", "revoked_at", "timestamptz"), ("FK", "replaced_by", "uuid (self)")],
    },
    "voter": {
        "elections": [("PK", "id", "uuid"), ("", "title", "text"), ("", "status", "text"), ("", "start_at", "timestamptz"),
                      ("", "end_at", "timestamptz"), ("", "closed_at", "timestamptz"), ("", "is_attack_lab", "boolean"),
                      ("", "created_by", "uuid")],
        "candidates": [("PK", "id", "uuid"), ("FK", "election_id", "uuid"), ("UK", "name", "text"),
                       ("UK", "ballot_order", "integer")],
        "voters": [("PK", "id", "uuid"), ("FK", "election_id", "uuid"), ("UK", "email_normalized", "text"),
                   ("UK", "external_ref", "text"), ("", "user_id", "uuid")],
        "voting_eligibility": [("PK", "id", "uuid"), ("FK", "election_id, voter_id", "uuid (komposit)"),
                               ("UK", "eligibility_ref", "char(64)"), ("", "status", "text")],
    },
    "ballot": {
        "ballots": [("PK", "id", "uuid"), ("", "election_id", "uuid"), ("UK", "eligibility_ref", "char(64)"),
                    ("", "candidate_id", "uuid"), ("", "ballot_nonce", "char(64)"), ("", "ballot_commitment", "char(64)"),
                    ("UK", "receipt_id", "uuid"), ("FK", "outbox_event_id", "uuid"), ("", "accepted_at", "timestamptz")],
        "idempotency_records": [("PK", "id", "uuid"), ("UK", "eligibility_ref", "char(64)"),
                                ("UK", "idempotency_key", "text"), ("", "request_hash", "char(64)"),
                                ("", "response_snapshot", "jsonb"), ("", "expires_at", "timestamptz")],
        "outbox_events": [("PK", "id", "uuid"), ("", "event_type", "text"), ("", "payload", "jsonb"),
                          ("", "status", "text"), ("", "attempts", "integer"), ("", "next_attempt_at", "timestamptz")],
        "election_gates": [("PK", "election_id", "uuid"), ("", "status", "text"), ("", "closed_at", "timestamptz")],
        "audit_acks": [("PK", "source_event_id", "uuid"), ("", "audit_sequence", "bigint"), ("", "event_hash", "char(64)")],
    },
    "audit": {
        "audit_chain_heads": [("PK", "scope_id", "uuid"), ("", "last_sequence", "bigint"), ("", "last_hash", "char(64)")],
        "audit_events": [("PK", "id", "uuid"), ("UK", "scope_id", "uuid"), ("UK", "sequence", "bigint"),
                         ("UK", "source_event_id", "uuid"), ("", "source_event_type", "text"),
                         ("", "payload_public", "jsonb"), ("", "prev_hash", "char(64)"), ("", "event_hash", "char(64)")],
        "audit_checkpoints": [("PK", "id", "uuid"), ("UK", "scope_id", "uuid"), ("UK", "sequence", "bigint"),
                              ("", "event_hash", "char(64)"), ("", "hmac", "char(64)")],
        "integrity_checks": [("PK", "id", "uuid"), ("", "scope_id", "uuid"), ("", "status", "text"),
                             ("", "first_failure_sequence", "bigint"), ("", "checkpoint_matches", "boolean")],
    },
    "result": {
        "tally_runs": [("PK", "id", "uuid"), ("UK", "election_id", "uuid"), ("UK", "run_number", "integer"),
                       ("", "status", "text"), ("", "reconciliation_status", "text"), ("", "ballots_counted", "integer"),
                       ("", "ballot_set_digest", "char(64)")],
        "tally_items": [("PK", "id", "uuid"), ("FK", "tally_run_id", "uuid"), ("", "candidate_id", "uuid"),
                        ("", "vote_count", "integer")],
        "final_results": [("PK", "id", "uuid"), ("UK", "election_id", "uuid"), ("FK", "tally_run_id", "uuid"),
                          ("", "result_hash", "char(64)"), ("", "snapshot", "jsonb")],
    },
    "security": {
        "security_events": [("PK", "id", "uuid"), ("UK", "event_id", "uuid"), ("", "event_type", "text"),
                            ("", "signal_type", "text"), ("", "client_fingerprint", "char(24)"),
                            ("", "election_id", "uuid")],
        "anomaly_alerts": [("PK", "id", "uuid"), ("", "rule_code", "text"), ("", "severity", "text"),
                           ("UK", "dedupe_key", "text"), ("", "resolved_at", "timestamptz")],
        "attack_runs": [("PK", "id", "uuid"), ("", "attack_code", "text"), ("", "status", "text"),
                        ("", "election_id", "uuid"), ("", "result", "jsonb")],
    },
}
DBNAME = {k: k + "_db" for k in TABLES}
OWNER = {k: k + "-service" for k in TABLES}

# lencana referensi lintas database: (db, tabel, kolom) -> kode
BADGE = {
    ("voter", "voting_eligibility", "eligibility_ref"): "R1", ("ballot", "ballots", "eligibility_ref"): "R1",
    ("voter", "candidates", "id"): "R2", ("ballot", "ballots", "candidate_id"): "R2", ("result", "tally_items", "candidate_id"): "R2",
    ("auth", "users", "id"): "R3", ("voter", "voters", "user_id"): "R3", ("voter", "elections", "created_by"): "R3",
    ("voter", "elections", "id"): "R4", ("ballot", "ballots", "election_id"): "R4", ("ballot", "election_gates", "election_id"): "R4",
    ("result", "tally_runs", "election_id"): "R4", ("result", "final_results", "election_id"): "R4",
    ("security", "security_events", "election_id"): "R4", ("security", "attack_runs", "election_id"): "R4",
    ("ballot", "audit_acks", "source_event_id"): "R5", ("audit", "audit_events", "source_event_id"): "R5",
}
# FK lokal (dalam satu database): (db, induk, anak, kolom FK anak, kardinalitas induk, kardinalitas anak)
FKS = [
    ("auth", "users", "refresh_sessions", "user_id", "1", "N"),
    ("voter", "elections", "candidates", "election_id", "1", "N"),
    ("voter", "elections", "voters", "election_id", "1", "N"),
    ("voter", "voters", "voting_eligibility", "election_id, voter_id", "1", "0..1"),
    ("ballot", "outbox_events", "ballots", "outbox_event_id", "1", "0..1"),
    ("result", "tally_runs", "tally_items", "tally_run_id", "1", "N"),
    ("result", "tally_runs", "final_results", "tally_run_id", "1", "0..1"),
]
ORDER = {  # urutan tabel dalam kolom (induk di atas anak)
    "auth": ["users", "refresh_sessions"],
    "voter": ["elections", "candidates", "voters", "voting_eligibility"],
    "ballot": ["outbox_events", "ballots", "idempotency_records", "election_gates", "audit_acks"],
    "audit": ["audit_chain_heads", "audit_events", "audit_checkpoints", "integrity_checks"],
    "result": ["tally_runs", "tally_items", "final_results"],
    "security": ["security_events", "anomaly_alerts", "attack_runs"],
}
W, H = 2100, 3280
c = Canvas(0, W, 0, H)
Y = lambda t: H - t  # koordinat dari atas

c.banner(W / 2, Y(60), "VoxGuard - ERD Konseptual Database per Service",
         "Status: RANCANGAN (Proposed / Draft) - belum ada migration; kolom dan relasi mengikuti 04_DATABASE_DESIGN_ERD.md")
c.text(W / 2, Y(150), "Satu instance PostgreSQL, enam database terpisah, satu DB role per service. "
       "Tidak ada foreign key lintas database; hanya kolom penting yang digambar.", size=16, color="#374151")

TW, RH, HH, GAP = 470, 29, 40, 38
CW = 590
XS = [60, 60 + CW + 60 + 0, 60 + 2 * (CW + 60)]
ROWS = [["auth", "voter", "ballot"], ["audit", "result", "security"]]
RT = [200, 1550]  # top y tiap baris klaster
CH = [1280, 1000]
pos = {}   # (db, tabel) -> (x, ytop, h)
rowy = {}  # (db, tabel, kolom) -> (y, xkanan)


def draw_table(db, name, x, ytop):
    cols = TABLES[db][name]
    h = HH + RH * len(cols)
    c.rect(x, Y(ytop + h), TW, h, fc="white", ec=INK, lw=1.8, z=3)
    c.rect(x, Y(ytop + HH), TW, HH, fc=HDR[db], ec=INK, lw=1.8, z=4)
    c.text(x + TW / 2, Y(ytop + HH / 2), name, size=16, weight="bold", z=6)
    for n, (key, col, typ) in enumerate(cols):
        yy = ytop + HH + RH * n + RH / 2
        lab, colr = MARK[key]
        if lab:
            c.text(x + 12, Y(yy), lab, size=11.5, weight="bold", color=colr, ha="left", z=6)
        c.text(x + 52, Y(yy), col, size=13.5, weight="bold" if key == "PK" else "normal", ha="left", z=6)
        c.text(x + TW - 12, Y(yy), typ, size=11.5, color="#6B7280", ha="right", z=6)
        first = col.split(",")[0].strip()
        rowy[(db, name, first)] = (Y(yy), x + TW)
        if (db, name, first) in BADGE:
            code = BADGE[(db, name, first)]
            c.circle(x + TW + 22, Y(yy), 17, fc=PURPLE, ec=PURPLE, z=6)
            c.text(x + TW + 22, Y(yy), code, size=10.5, weight="bold", color="white", z=7)
    return h


for r, dbs in enumerate(ROWS):
    for k, db in enumerate(dbs):
        x0 = XS[k]
        c.rect(x0, Y(RT[r] + CH[r]), CW, CH[r], fc=CLB[db], ec="#374151", lw=2.6, z=1, r=18)
        c.text(x0 + 20, Y(RT[r] + 30), DBNAME[db], size=22, weight="bold", ha="left")
        c.text(x0 + 20 + 14 * len(DBNAME[db]) + 70, Y(RT[r] + 32), f"milik {OWNER[db]}", size=14, color="#374151", ha="left")
        ytop = RT[r] + 70
        for t in ORDER[db]:
            h = draw_table(db, t, x0 + 60, ytop)
            pos[(db, t)] = (x0 + 60, ytop, h)
            ytop += h + GAP

# FK lokal: braket di margin kiri tabel
off = {}
for db, par, ch, col, cp, cc in FKS:
    px, pt, ph = pos[(db, par)]
    cx_, ct, chh = pos[(db, ch)]
    ypk = rowy[(db, par, "id")][0] if (db, par, "id") in rowy else Y(pt + HH + RH / 2)
    ycol = rowy[(db, ch, col.split(",")[0].strip())][0]
    n = off.get((db, par), 0) + 1
    off[(db, par)] = n
    bx = px - 12 * n - 4
    c.line([(px, ypk), (bx, ypk), (bx, ycol), (cx_, ycol)], color=INK, lw=2.2, z=2)
    if (db, par, "lab") not in off:
        off[(db, par, "lab")] = 1
        c.text(px - 8, ypk + 14, cp, size=12.5, weight="bold", ha="right", z=8)
    c.text(bx + 4, ycol - 14, cc, size=12.5, weight="bold", ha="right", z=8)

# catatan dalam klaster
ax_, at_, ah_ = pos[("audit", "audit_chain_heads")]
ev_x, ev_t, ev_h = pos[("audit", "audit_events")]
c.text(ax_ + TW / 2, Y(at_ + ah_ + GAP / 2 - 4), "relasi logis scope_id (tanpa FK) di audit_chain_heads - audit_events",
       size=12, style="italic", color="#9D174D", z=8)
bx_, bt_, bh_ = pos[("ballot", "ballots")]
c.text(XS[1] + CW / 2, Y(RT[0] + CH[0] - 30), "UNIQUE (election_id, eligibility_ref) pada ballot_db.ballots\n= penjaga utama satu suara per pemilih",
       size=12.5, style="italic", color="#92400E", z=8)

# ---------- legenda dan tabel referensi lintas-DB ----------
D = 140
Yl = lambda t: Y(t + D)
top = RT[1] + CH[1] + 40
c.rect(60, 40, W - 120, H - top - 40 - 0, fc="white", ec="#9CA3AF", lw=1.6, z=0)
base = top + 20
c.text(90, Y(base + 25), "Legenda", size=20, weight="bold", ha="left")
c.text(90, Y(base + 75), "PK  primary key        FK  foreign key (hanya dalam SATU database)        UK  bagian dari unique constraint",
       size=14.5, ha="left")
c.line([(90, Y(base + 125)), (150, Y(base + 125))], lw=2.2)
c.text(165, Y(base + 125), "FK lokal; 1 = sisi induk, N atau 0..1 = sisi anak (kardinalitas)", size=14.5, ha="left")
c.circle(120, Y(base + 175), 17, fc=PURPLE, ec=PURPLE)
c.text(120, Y(base + 175), "R", size=10.5, weight="bold", color="white", z=7)
c.text(165, Y(base + 175), "Referensi logis LINTAS database: nilai yang sama, BUKAN foreign key, tidak dijaga PostgreSQL", size=14.5, ha="left")
c.text(90, Y(base + 225), "Asumsi: hanya kolom kunci/penting; tipe dan constraint mengikuti dokumen 04 (Draft). "
       "Dokumen 03 dan 04 berbeda detail skema (C-DB-01/02); diagram memakai 04.", size=14, ha="left", color="#374151")
c.text(90, Y(base + 265), "Tiap service hanya memakai DB role-nya sendiri; data lintas service lewat REST atau event RabbitMQ.",
       size=14, ha="left", color="#374151")

RY = base + 335
c.text(90, Y(RY), "Referensi logis lintas database (dijaga di level aplikasi/event)", size=19, weight="bold", ha="left")
refs = [
    ("R1", "eligibility_ref: voter_db.voting_eligibility = ballot_db.ballots (pseudonim HMAC dari election_id|voter_id)"),
    ("R2", "candidate_id: voter_db.candidates.id dirujuk ballot_db.ballots dan result_db.tally_items"),
    ("R3", "user_id: auth_db.users.id dirujuk voter_db.voters.user_id dan voter_db.elections.created_by"),
    ("R4", "election_id: voter_db.elections.id dirujuk ballot_db, result_db, dan security_db"),
    ("R5", "source_event_id: ballot_db.audit_acks = audit_db.audit_events (event AuditRecorded)"),
]
for n, (code, txt) in enumerate(refs):
    yy = Y(RY + 50 + n * 48)
    c.circle(120, yy, 17, fc=PURPLE, ec=PURPLE)
    c.text(120, yy, code, size=10.5, weight="bold", color="white", z=7)
    c.text(155, yy, txt, size=14, ha="left")
c.save(OUT)
print("ok", OUT)
