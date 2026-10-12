"""VoxGuard - Diagram Arsitektur Sistem (RANCANGAN / PROPOSED).
Sumber: 03_SYSTEM_ARCHITECTURE_DOCUMENT.md Bagian 5-7 dan 11, ARCHITECTURE.md B-C dan F, 04_DATABASE_DESIGN_ERD.md Bagian 3.
Jalankan: python3 01_system_architecture.py  ->  ../01_system_architecture.png
"""
import os
from matplotlib.patches import Arc, Ellipse, Rectangle
from diagram_kit import Canvas, INK, GRAY

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "01_system_architecture.png")
c = Canvas(0, 3200, -330, 2120)

BLUE, GREEN, ORANGE, PURPLE, SQL = "#1D4ED8", "#047857", "#C2410C", "#7C3AED", "#4B5563"
DASH = (0, (8, 5))
DOT = (0, (1.5, 4))

c.banner(1600, 2060, "VoxGuard - Diagram Arsitektur Sistem",
         "Status: RANCANGAN (Proposed / Draft) - repository saat ini hanya berisi dokumen; seluruh komponen belum diimplementasikan")


def halo_line(pts, color, lw=2.4, ls="-", head="-|>", label=None, lx=None, ly=None, lsize=12.5):
    c.line(pts, color="white", lw=lw + 6, z=2.2)
    c.arrow(pts, color=color, lw=lw, ls=ls, head=head, scale=20, z=2.4)
    if label:
        c.text(lx, ly, label, size=lsize, style="italic", color=color, z=11)


def cylinder(cx, cy, w, h, label, fc="#EEF2FF"):
    eh = 34
    c.ax.add_patch(Rectangle((cx - w / 2, cy - h / 2 + eh / 2), w, h - eh, fc=fc, ec="none", zorder=3))
    c.line([(cx - w / 2, cy - h / 2 + eh / 2), (cx - w / 2, cy + h / 2 - eh / 2)], lw=2, z=4)
    c.line([(cx + w / 2, cy - h / 2 + eh / 2), (cx + w / 2, cy + h / 2 - eh / 2)], lw=2, z=4)
    c.ax.add_patch(Arc((cx, cy - h / 2 + eh / 2), w, eh, theta1=180, theta2=360, ec=INK, lw=2, zorder=4))
    c.ax.add_patch(Ellipse((cx, cy + h / 2 - eh / 2), w, eh, fc=fc, ec=INK, lw=2, zorder=4))
    c.text(cx, cy - 6, label, size=15, weight="bold", z=6)


# ---------------- kolom service ----------------
cols = {"auth": 640, "audit": 1080, "result": 1520, "ballot": 1960, "voter": 2400, "security": 2840}
SY0, SY1 = 1015, 1255  # tepi bawah/atas kotak service
SCY = (SY0 + SY1) / 2
SW = 360

svc = {
    "auth": ("auth-service", ":8001", "Akun, sesi, token JWT",
             "terbit: SecuritySignalObserved*", "konsumsi: -"),
    "audit": ("audit-service", ":8004", "Hash chain, verifikasi, proof",
              "terbit: AuditRecorded,\nSecuritySignalObserved",
              "konsumsi: Election*, VoteAccepted,\nTally*, Result*, Alert*"),
    "result": ("result-service", ":8005", "Tally, rekonsiliasi, finalisasi",
               "terbit: TallyCompleted,\nResultFinalized", "konsumsi: -"),
    "ballot": ("ballot-service", ":8003", "Suara, idempotency, receipt",
               "terbit: VoteAccepted/Rejected",
               "konsumsi: ElectionOpened/Closed,\nAuditRecorded"),
    "voter": ("voter-service", ":8002", "Pemilihan, kelayakan, ticket",
              "terbit: ElectionOpened/Closed",
              "konsumsi: VoteAccepted,\nResultFinalized"),
    "security": ("security-service", ":8006", "Anomali, alert, Attack Lab",
                 "terbit: SecurityAlertRaised",
                 "konsumsi: Election*, Vote*,\nAuditRecorded, Tally*, Signal*"),
}

# ---------------- baris atas: Pengguna, Frontend ----------------
c.rect(430, 1830, 700, 120, fc="#F9FAFB", r=14)
c.text(780, 1905, "Pengguna (browser)", size=17, weight="bold")
c.text(780, 1860, "VOTER, ADMIN, AUDITOR", size=14)
c.rect(1400, 1810, 1100, 150, fc="#ECFDF5", r=14)
c.text(1950, 1925, "Frontend", size=18, weight="bold")
c.text(1950, 1885, "React + Vite + TypeScript* + Tailwind CSS", size=15)
c.text(1950, 1845, "UI Voter, Admin, Auditor/Security (:5173)", size=13.5, color="#374151")
c.arrow([(1130, 1890), (1400, 1890)], color=BLUE, lw=2.6, scale=22)
c.text(1265, 1912, "HTTP", size=13, style="italic", color=BLUE)
c.arrow([(1950, 1810), (1950, 1700)], color=BLUE, lw=2.6, scale=22)
c.text(1975, 1755, "HTTP/JSON  /api/v1  (sinkron)", size=13, style="italic", color=BLUE, ha="left")

# ---------------- Gateway + Redis ----------------
c.rect(430, 1540, 2580, 160, fc="#EFF6FF", ec=BLUE, lw=2.6, r=14)
c.text(1720, 1665, "API Gateway (:8000) - satu-satunya API yang dipublikasikan", size=19, weight="bold")
c.text(1720, 1620, "routing /api/v1/*, verifikasi JWT + RBAC awal, rate limit, X-Request-ID dan X-Correlation-ID,",
       size=14.5)
c.text(1720, 1580, "membuang header identitas klien (dan tidak meneruskan identitas untuk POST /ballots)", size=14.5)

c.rect(40, 1540, 300, 160, fc="#F5F3FF", ec=PURPLE, lw=2.4, r=14)
c.text(190, 1665, "Redis", size=19, weight="bold", color="#5B21B6")
c.text(190, 1620, "rate limit (rl:*)", size=13.5)
c.text(190, 1585, "denylist jti (deny:jti:*)", size=13.5)
c.arrow([(340, 1620), (430, 1620)], color=PURPLE, lw=2.4, head="<|-|>", scale=18)

# ---------------- service ----------------
for key, (name, port, desc, pub, sub) in svc.items():
    cx = cols[key]
    c.rect(cx - SW / 2, SY0, SW, SY1 - SY0, fc="#F8FAFC", ec=INK, lw=2.4, r=12, z=3)
    c.text(cx, SY1 - 26, f"{name} {port}", size=16.5, weight="bold", z=6)
    c.text(cx, SY1 - 58, desc, size=13.5, z=6)
    c.text(cx - SW / 2 + 14, SY1 - 90, pub, size=11.5, ha="left", va="top", color="#9A3412", z=6)
    ny = SY1 - 90 - (2 if "\n" not in pub else 3) * 18 + 4
    c.text(cx - SW / 2 + 14, ny - 6, sub, size=11.5, ha="left", va="top", color="#9A3412", z=6)

# ---------------- Gateway -> service (REST sinkron) ----------------
for key, cx in cols.items():
    c.arrow([(cx, 1540), (cx, SY1)], color=BLUE, lw=2.6, scale=22, z=2.0)
c.text(640 + 20, 1480, "REST sinkron per rute /api/v1/*", size=12.5, style="italic", color=BLUE, ha="left")

# ---------------- Panggilan internal sinkron antar-service ----------------
def internal(pts, label, lx, ly):
    halo_line(pts, GREEN, lw=2.6, head="-|>", label=label, lx=lx, ly=ly)

internal([(1430, SY1), (1430, 1305), (1170, 1305), (1170, SY1)], "summary, commitments, verify", 1300, 1330)
internal([(1630, SY1), (1630, 1305), (1910, 1305), (1910, SY1)], "tally-export, summary", 1770, 1330)
internal([(2080, SY1), (2080, 1305), (2270, 1305), (2270, SY1)], "ballot-info, ticket", 2175, 1330)
internal([(1560, SY1), (1560, 1365), (2330, 1365), (2330, SY1)], "summary (Result -> Voter)", 1785, 1388)
internal([(2770, SY1), (2770, 1425), (2020, 1425), (2020, SY1)], "outbox/stats (polling)", 2400, 1448)

# ---------------- Auth -> Redis (denylist jti) ----------------
halo_line([(cols["auth"] - SW / 2, SCY), (190, SCY), (190, 1540)], PURPLE, lw=2.4,
          label="SET deny:jti (logout)", lx=215, ly=SCY + 28)

# ---------------- Database per service ----------------
c.rect(430, 540, 2580, 395, fc="#FCFCFD", ec=GRAY, lw=2, ls=(0, (3, 4)), z=0.5, r=10)
c.text(450, 905, "PostgreSQL - satu instance, enam database terpisah; setiap service memakai role database "
       "sendiri (tanpa akses lintas-database)", size=14, weight="bold", ha="left", color="#374151").set_bbox(dict(fc="#FCFCFD", ec="none", pad=3))
dbs = {
    "auth": ("auth_db", "users\nrefresh_sessions"),
    "audit": ("audit_db", "audit_events\naudit_chain_heads\naudit_checkpoints\nintegrity_checks"),
    "result": ("result_db", "tally_runs\ntally_items\nfinal_results"),
    "ballot": ("ballot_db", "ballots\nidempotency_records\nelection_gates\naudit_acks"),
    "voter": ("voter_db", "elections, candidates\nvoters\nvoting_eligibility"),
    "security": ("security_db", "security_events\nanomaly_alerts\nattack_runs"),
}
for key, (dbn, tables) in dbs.items():
    cx = cols[key]
    cylinder(cx, 790, 220, 130, dbn)
    c.text(cx, 712, tables, size=11.5, va="top", color="#374151")
    c.arrow([(cx, SY0), (cx, 855)], color=SQL, lw=2.4, head="<|-|>", scale=18, z=2.0)
c.text(470, 560, "+ outbox_events dan processed_events pada service yang menerbitkan/mengonsumsi event "
       "(auth_db tidak memiliki keduanya)", size=12, ha="left", style="italic", color="#4B5563").set_bbox(dict(fc="#FCFCFD", ec="none", pad=3))

# ---------------- RabbitMQ ----------------
c.rect(430, 330, 2580, 100, fc="#FFF7ED", ec=ORANGE, lw=2.6, r=14)
c.text(1720, 395, "RabbitMQ - exchange voxguard.events (topic) + retry bertingkat + DLX/DLQ", size=18, weight="bold",
       color="#9A3412")
c.text(1720, 353, "pesan persisten, at-least-once; konsumen idempotent (processed_events / unique alami)",
       size=13.5, color="#7C2D12")

for key, cx in cols.items():
    outbox = key != "auth"
    pub_style = DASH if outbox else DOT
    c.line([(cx + 150, SY0), (cx + 150, 430)], color="white", lw=8, z=2.2)
    c.arrow([(cx + 150, SY0), (cx + 150, 430)], color=ORANGE, lw=2.4, ls=pub_style, scale=20, z=2.4)
    if key not in ("auth", "result"):
        c.line([(cx - 150, 430), (cx - 150, SY0)], color="white", lw=8, z=2.2)
        c.arrow([(cx - 150, 430), (cx - 150, SY0)], color=ORANGE, lw=2.4, ls=DASH, scale=20, z=2.4)

# sinyal best-effort dari Gateway -> RabbitMQ (jalur tepi kanan)
c.line([(3010, 1590), (3110, 1590), (3110, 380), (3010, 380)], color="white", lw=8, z=2.2)
c.arrow([(3010, 1590), (3110, 1590), (3110, 380), (3010, 380)], color=ORANGE, lw=2.4, ls=DOT, scale=20, z=2.4)
t = c.text(3150, 980, "SecuritySignalObserved (best-effort, tanpa outbox)", size=13, style="italic", color=ORANGE)
t.set_rotation(90)

# ---------------- Legenda dan catatan ----------------
LX, LY, LW, LH = 430, -300, 2580, 550
c.rect(LX, LY, LW, LH - 40, fc="white", ec="#9CA3AF", lw=1.8, z=0)
c.text(LX + 20, 190, "Legenda", size=20, weight="bold", ha="left")
rows = [
    (BLUE, "-", "-|>", "Request/response REST sinkron: Pengguna -> Frontend -> API Gateway -> service pemilik (JSON)."),
    (GREEN, "-", "-|>", "Panggilan internal sinkron antar-service (/internal/v1/*, X-Internal-Key); panah dari pemanggil ke yang dipanggil."),
    (ORANGE, DASH, "-|>", "Event asinkron lewat RabbitMQ (transactional outbox, at-least-once): panah ke band = terbit, panah ke service = konsumsi."),
    (ORANGE, DOT, "-|>", "Sinyal keamanan best-effort tanpa outbox (Gateway dan Auth); dapat hilang saat broker mati."),
    (SQL, "-", "<|-|>", "SQL ke database milik sendiri (satu role per service); tidak ada akses atau foreign key lintas database."),
    (PURPLE, "-", "<|-|>", "Akses Redis: rate limit dan denylist jti (Gateway; Auth menulis denylist saat logout)."),
]
y = 120
for col, ls, head, txt in rows:
    c.arrow([(LX + 30, y), (LX + 170, y)], color=col, lw=2.6, ls=ls, head=head, scale=20)
    c.text(LX + 195, y, txt, size=13.5, ha="left")
    y -= 56
c.text(LX + 30, y - 4, "Event bertanda * : terbit dan konsumsi lengkap tiap service ada di dokumen 03 Bagian 11 dan ARCHITECTURE.md F.",
       size=12.5, ha="left", style="italic", color="#4B5563")

nx = 1900
c.text(nx, 190, "Catatan dan batas rancangan", size=20, weight="bold", ha="left")
notes = [
    "- Seluruh komponen adalah RANCANGAN; belum ada kode, Compose, atau migrasi.",
    "- Tepat satu API Gateway dan enam service backend (Auth, Voter, Ballot, Audit, Result, Security).",
    "- Hanya Gateway (:8000) dan frontend (:5173) yang dipublikasikan; service berada di jaringan",
    "  Docker internal voxguard-net. Management RabbitMQ hanya di 127.0.0.1:15672.",
    "- Hubungan identitas-pilihan dipisah antar database (voter_db dan ballot_db); ini mengurangi",
    "  risiko, bukan anonimitas sempurna (lihat dokumen 04 Bagian 7).",
    "- *TypeScript tercantum pada brief tugas, tetapi dokumen 01-08 hanya menyebut React/Vite/",
    "  Tailwind: konflik dicatat di 10_DIAGRAM_EXPLANATION.md.",
    "- Fungsi Redis mengikuti SRS dan SAD (rate limit, denylist jti). 'Cache kandidat' hanya ada di",
    "  ARCHITECTURE.md dan tidak digambar (konflik dicatat).",
    "- Tidak digambar agar tidak padat: volume audit_checkpoints (audit-service) dan polling",
    "  management API RabbitMQ oleh security-service.",
]
ny = 140
for n in notes:
    c.text(nx, ny, n, size=12.8, ha="left")
    ny -= 36

c.save(OUT)
print("ok", OUT)
