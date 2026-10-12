"""Alat bantu gambar diagram teknis VoxGuard (matplotlib, tanpa dependensi lain).

Satu satuan data = satu piksel pada dpi 100, sehingga koordinat pada skrip diagram
sama dengan koordinat piksel pada PNG hasil. Semua diagram berstatus RANCANGAN.
"""
import math
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, FancyArrowPatch, FancyBboxPatch, Rectangle, Circle, Polygon
from matplotlib.lines import Line2D

FONT = "DejaVu Sans"
plt.rcParams["font.family"] = FONT
INK = "#1F2937"
GRAY = "#6B7280"
LIGHT = "#F3F4F6"


class Canvas:
    def __init__(self, x0, x1, y0, y1, dpi=100):
        self.x0, self.x1, self.y0, self.y1, self.dpi = x0, x1, y0, y1, dpi
        w, h = x1 - x0, y1 - y0
        self.fig = plt.figure(figsize=(w / dpi, h / dpi), dpi=dpi, facecolor="white")
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(x0, x1)
        self.ax.set_ylim(y0, y1)
        self.ax.set_aspect("equal")
        self.ax.axis("off")

    # ---- teks ----
    def text(self, x, y, s, size=15, weight="normal", ha="center", va="center",
             color=INK, style="normal", z=10, linespacing=1.25):
        return self.ax.text(x, y, s, fontsize=size, fontweight=weight, ha=ha, va=va,
                            color=color, fontstyle=style, zorder=z, linespacing=linespacing,
                            family=FONT)

    # ---- bentuk ----
    def rect(self, x, y, w, h, fc="white", ec=INK, lw=2, ls="-", z=1, r=0):
        if r:
            p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                               fc=fc, ec=ec, lw=lw, ls=ls, zorder=z)
        else:
            p = Rectangle((x, y), w, h, fc=fc, ec=ec, lw=lw, ls=ls, zorder=z)
        self.ax.add_patch(p)
        return p

    def ellipse(self, cx, cy, w, h, fc=LIGHT, ec=INK, lw=2, ls="-", z=3):
        p = Ellipse((cx, cy), w, h, fc=fc, ec=ec, lw=lw, ls=ls, zorder=z)
        self.ax.add_patch(p)
        return p

    def poly(self, pts, fc="white", ec=INK, lw=2, z=4, ls="-"):
        p = Polygon(pts, closed=True, fc=fc, ec=ec, lw=lw, zorder=z, ls=ls)
        self.ax.add_patch(p)

    def circle(self, cx, cy, r, fc="white", ec=INK, lw=2, z=4):
        self.ax.add_patch(Circle((cx, cy), r, fc=fc, ec=ec, lw=lw, zorder=z))

    def line(self, pts, color=INK, lw=2, ls="-", z=2):
        xs, ys = zip(*pts)
        self.ax.add_line(Line2D(xs, ys, color=color, lw=lw, ls=ls, zorder=z,
                                solid_capstyle="butt", dash_capstyle="butt"))

    def arrow(self, pts, color=INK, lw=2, ls="-", head="-|>", fc=None, scale=22, z=2, shrink=0):
        """Polyline dengan kepala panah pada segmen terakhir (head=None => tanpa kepala)."""
        if len(pts) > 2:
            self.line(pts[:-1], color=color, lw=lw, ls=ls, z=z)
            pts = pts[-2:]
        if head is None:
            self.line(pts, color=color, lw=lw, ls=ls, z=z)
            return
        p = FancyArrowPatch(pts[0], pts[1], arrowstyle=head, mutation_scale=scale,
                            color=color, fc=fc if fc else color, ec=color, lw=lw, ls=ls,
                            zorder=z, shrinkA=shrink, shrinkB=shrink, joinstyle="miter")
        self.ax.add_patch(p)

    def actor(self, x, y, label, size=17, lbl_dx=0, lbl_dy=-118, lbl_ha="center", scale=1.0):
        """Figur aktor UML. (x, y) = pusat badan; kepala di atas."""
        s = scale
        self.circle(x, y + 62 * s, 22 * s, lw=2.4)
        self.line([(x, y + 40 * s), (x, y - 34 * s)], lw=2.4, z=4)
        self.line([(x - 34 * s, y + 18 * s), (x + 34 * s, y + 18 * s)], lw=2.4, z=4)
        self.line([(x, y - 34 * s), (x - 30 * s, y - 84 * s)], lw=2.4, z=4)
        self.line([(x, y - 34 * s), (x + 30 * s, y - 84 * s)], lw=2.4, z=4)
        self.text(x + lbl_dx, y + lbl_dy * s, label, size=size, weight="bold", ha=lbl_ha, va="top")

    def banner(self, cx, y, title, subtitle):
        self.text(cx, y, title, size=33, weight="bold")
        self.text(cx, y - 52, subtitle, size=17, color="#B45309", weight="bold")

    def save(self, path):
        self.fig.savefig(path, dpi=self.dpi, facecolor="white")
        plt.close(self.fig)


def tri_head_pts(tip, frm, size=20):
    """Titik segitiga kosong (generalisasi UML) dengan ujung di `tip` menghadap dari `frm`."""
    dx, dy = tip[0] - frm[0], tip[1] - frm[1]
    d = math.hypot(dx, dy) or 1
    ux, uy = dx / d, dy / d
    bx, by = tip[0] - ux * size * 1.5, tip[1] - uy * size * 1.5
    px, py = -uy, ux
    return [tip, (bx + px * size * 0.75, by + py * size * 0.75),
            (bx - px * size * 0.75, by - py * size * 0.75)]
