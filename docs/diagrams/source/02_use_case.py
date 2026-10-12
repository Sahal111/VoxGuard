"""VoxGuard - Use Case Diagram (RANCANGAN / PROPOSED).
Sumber: SRS Bagian 5 dan 8; 05_API_CONTRACT_SPECIFICATION.md Bagian 3.2 (matriks hak akses).
Jalankan: python3 02_use_case.py  ->  ../02_use_case.png
"""
import os
from diagram_kit import Canvas, INK, GRAY

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "02_use_case.png")
c = Canvas(0, 2740, -460, 2110)

c.banner(1370, 2040, "VoxGuard - Use Case Diagram",
         "Status: RANCANGAN (Proposed / Draft) - belum ada kode; use case diturunkan dari SRS dan matriks hak akses")

# ---------- batas sistem ----------
c.rect(380, 100, 2020, 1860, fc="white", ec=INK, lw=2.6, z=0)
c.text(1390, 1928, "Sistem VoxGuard (prototipe edukasi, Docker Compose lokal)", size=19, weight="bold")

EW, EH = 440, 76


def uc(cx, cy, code, label, fc="#F3F4F6"):
    c.ellipse(cx, cy, EW, EH, fc=fc)
    c.text(cx, cy, f"{code} {label}", size=14)
    return cx, cy


def group(x, y, w, h, title):
    c.rect(x, y, w, h, fc="#FAFAFA", ec=GRAY, lw=1.6, ls=(0, (6, 4)), z=0.5)
    c.text(x + 14, y + h - 18, title, size=14.5, weight="bold", ha="left", va="center", color="#374151")


# ---------- kelompok ----------
group(400, 640, 600, 1190, "Pemungutan suara (khusus VOTER)")
group(1100, 685, 500, 575, "Fungsi umum (semua peran)")
group(1100, 170, 500, 480, "Audit dan keamanan (ADMIN, AUDITOR)")
group(1790, 740, 520, 1130, "Pengelolaan pemilihan dan hasil (khusus ADMIN)")

# ---------- use case ----------
L, M, R = 720, 1350, 2050
vs = {}
vs["01"] = uc(L, 1720, "UC-01", "Registrasi akun VOTER")
vs["11"] = uc(L, 1590, "UC-11", "Melihat pemilihan yang berhak")
vs["14"] = uc(L, 1460, "UC-14", "Memberikan suara")
vs["12"] = uc(L, 1330, "UC-12", "Meminta ballot + vote ticket")
vs["13"] = uc(L, 1200, "UC-13", "Memeriksa kelayakan pemilih")
vs["15"] = uc(L, 700, "UC-15", "Memeriksa receipt")

cm = {}
cm["02"] = uc(M, 1180, "UC-02", "Login")
cm["03"] = uc(M, 1070, "UC-03", "Refresh sesi dan logout")
cm["18"] = uc(M, 960, "UC-18", "Melihat proof audit")
cm["22"] = uc(M, 850, "UC-22", "Melihat hasil final")
cm["23"] = uc(M, 740, "UC-23", "Memverifikasi hasil final")

au = {}
au["16"] = uc(M, 560, "UC-16", "Melihat catatan audit")
au["17"] = uc(M, 450, "UC-17", "Verifikasi integritas hash chain")
au["21"] = uc(M, 340, "UC-21", "Melihat hasil sementara")
au["24"] = uc(M, 230, "UC-24", "Melihat alert dan metrik")

ad = {}
ad["04"] = uc(R, 1760, "UC-04", "Membuat akun ADMIN/AUDITOR")
ad["05"] = uc(R, 1650, "UC-05", "Membuat pemilihan")
ad["06"] = uc(R, 1540, "UC-06", "Mengelola kandidat")
ad["07"] = uc(R, 1430, "UC-07", "Mengimpor daftar pemilih")
ad["08"] = uc(R, 1320, "UC-08", "Menjadwalkan pemilihan")
ad["09"] = uc(R, 1210, "UC-09", "Membuka pemilihan")
ad["10"] = uc(R, 1100, "UC-10", "Menutup pemilihan")
ad["19"] = uc(R, 990, "UC-19", "Tally dan rekonsiliasi")
ad["20"] = uc(R, 880, "UC-20", "Memfinalisasi hasil")
ad["25"] = uc(R, 770, "UC-25", "Attack Lab (hanya lokal/uji)")

# ---------- aktor ----------
VX, VY = 170, 1000
AX, AY = 2580, 1290
UX, UY = 2580, 400
c.actor(VX, VY, "Pemilih\n(VOTER)", size=18)
c.actor(AX, AY, "Administrator\n(ADMIN)", size=18)
c.actor(UX, UY, "Auditor\n(AUDITOR)", size=18)

# ---------- asosiasi: Pemilih ----------
VB = 440  # bus Pemilih (kiri)
c.line([(VX + 36, VY + 18), (VB, VY + 18)], lw=2)
c.line([(VB, 700), (VB, 1720)], lw=2)
for k in ("01", "11", "14", "12", "15"):
    x, y = vs[k]
    c.line([(VB, y), (x - EW / 2, y)], lw=2)
c.circle(VB, VY + 18, 6, fc=INK, ec=INK, z=5)
# koridor ke kelompok umum
VB2 = 1040
c.line([(VB, VY + 18), (VB2, VY + 18)], lw=2)
c.line([(VB2, 740), (VB2, 1180)], lw=2)
for k, (x, y) in cm.items():
    c.line([(VB2, y), (x - EW / 2, y)], lw=2)
c.circle(VB2, VY + 18, 6, fc=INK, ec=INK, z=5)

# ---------- asosiasi: Admin ----------
AB = 2340  # bus Admin (kanan kelompok ADMIN)
c.line([(AX - 36, AY + 18), (AB, AY + 18)], lw=2)
c.line([(AB, 770), (AB, 1760)], lw=2)
for k, (x, y) in ad.items():
    c.line([(AB, y), (x + EW / 2, y)], lw=2)
c.circle(2500, AY + 18, 6, fc=INK, ec=INK, z=5)
# turun ke koridor bawah
c.line([(2500, AY + 18), (2500, 500)], lw=2)
# ke kelompok umum (bus kanan x=1660)
CB = 1660
c.line([(2500, 700), (CB, 700)], lw=2)
c.circle(2500, 700, 6, fc=INK, ec=INK, z=5)
c.line([(CB, 640), (CB, 1180)], lw=2)
for k, (x, y) in cm.items():
    c.line([(CB, y), (x + EW / 2, y)], lw=2)
# ke kelompok audit (bus kanan x=1660, bagian bawah)
c.line([(2500, 500), (CB, 500)], lw=2)
c.circle(2500, 500, 6, fc=INK, ec=INK, z=5)
c.line([(CB, 230), (CB, 560)], lw=2)
for k, (x, y) in au.items():
    c.line([(CB, y), (x + EW / 2, y)], lw=2)

# ---------- asosiasi: Auditor ----------
c.line([(UX - 36, UY + 18), (CB, UY + 18)], lw=2)
c.circle(2460, UY + 18, 6, fc=INK, ec=INK, z=5)
c.line([(2460, UY + 18), (2460, 640)], lw=2)
c.line([(2460, 640), (CB, 640)], lw=2)

# ---------- include ----------
def dashed_arrow(pts):
    c.arrow(pts, lw=1.8, ls=(0, (6, 4)), head="->", scale=20)

x13, y13 = vs["13"]
x12, y12 = vs["12"]
x14, y14 = vs["14"]
dashed_arrow([(L, y14 - EH / 2), (L, y12 + EH / 2)])
c.text(L + 18, (y14 + y12) / 2, "<<include>>", size=12.5, ha="left", style="italic")
dashed_arrow([(L, y12 - EH / 2), (L, y13 + EH / 2)])
c.text(L + 18, (y12 + y13) / 2, "<<include>>", size=12.5, ha="left", style="italic")
# UC-20 -> UC-17
dashed_arrow([(R - EW / 2, 880), (1730, 880), (1730, 472), (1529, 472)])
c.text(1738, 600, "<<include>>", size=12.5, ha="left", style="italic")

# ---------- catatan dalam batas sistem (kiri bawah) ----------
def note(x, y, w, h, s):
    c.rect(x, y, w, h, fc="#FEF9C3", ec="#9CA3AF", lw=1.4, z=2)
    c.text(x + 12, y + h / 2, s, size=13, ha="left", va="center")

note(420, 420, 600, 150,
     "UC-14 hanya saat pemilihan OPEN dan now <= end_at.\n"
     "Satu hak suara = paling banyak satu suara.\n"
     "ADMIN dan AUDITOR tidak dapat memilih.")
note(420, 250, 600, 140,
     "UC-20 mensyaratkan tally COMPLETED dengan\n"
     "rekonsiliasi MATCH dan audit VALID (UC-17).\n"
     "Tidak ada endpoint untuk mengubah hasil final.")
note(420, 130, 600, 90,
     "UC-21: VOTER tidak dapat melihat hasil sebelum\nFINALIZED; kebijakan Auditor = OPEN DECISION OD-12.")

# ---------- legenda (di bawah batas sistem) ----------
LX, LY = 380, -420
c.rect(LX, LY, 2020, 470, fc="white", ec="#9CA3AF", lw=1.6, z=0)
c.text(LX + 20, LY + 440, "Legenda", size=19, weight="bold", ha="left")
c.actor(LX + 90, LY + 330, "", scale=0.55)
c.text(LX + 150, LY + 335, "Aktor: peran pengguna aplikasi (VOTER, ADMIN, AUDITOR)", size=14.5, ha="left")
c.ellipse(LX + 100, LY + 255, 120, 50)
c.text(LX + 180, LY + 255, "Use case (UC-xx)", size=14.5, ha="left")
c.line([(LX + 40, LY + 185), (LX + 160, LY + 185)], lw=2)
c.text(LX + 180, LY + 185, "Asosiasi aktor - use case (garis percabangan = beberapa use case dari satu aktor;\n"
       "titik hitam = titik cabang, bukan use case)", size=14.5, ha="left")
c.arrow([(LX + 40, LY + 110), (LX + 160, LY + 110)], lw=1.8, ls=(0, (6, 4)), head="->", scale=20)
c.text(LX + 180, LY + 110, "<<include>>: use case yang di pangkal panah wajib memanggil use case di ujung panah",
       size=14.5, ha="left")
c.rect(LX + 40, LY + 30, 120, 40, fc="#FAFAFA", ec=GRAY, lw=1.6, ls=(0, (6, 4)))
c.text(LX + 180, LY + 50, "Pengelompokan use case berdasarkan peran (bukan elemen UML formal)", size=14.5, ha="left")
c.text(LX + 1030, LY + 330,
       "Catatan lingkup:\n"
       "- Developer/Operator tidak digambar: bukan peran aplikasi (SRS Bagian 5).\n"
       "- UC-01 diakses pengguna yang belum login; UC-15 memakai kode receipt\n"
       "  (tanpa login), keduanya tanpa aktor tambahan.\n"
       "- Role ditegakkan di backend (Gateway dan tiap service).\n"
       "- Hak akses mengacu ke matriks 05_API_CONTRACT_SPECIFICATION 3.2.\n"
       "- Seluruhnya RANCANGAN, bukan hasil implementasi.",
       size=14.5, ha="left", va="top")

c.save(OUT)
print("ok", OUT)
