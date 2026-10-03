"""Sheet 1 — province overview, 1:100,000 on a 1350 x 840 mm sheet (36-inch roll)."""
import sys

import contextily as cx
import matplotlib.pyplot as plt
from adjustText import adjust_text
from matplotlib.lines import Line2D
from matplotlib import patheffects as pe

from atlas_common import *

pts, adm = load()
cn = adm[adm.shapeName.isin(CN_LGUS)]
nb = adm[~adm.shapeName.isin(CN_LGUS)]

SCALE = 100_000
SHEET_W, SHEET_H = 1350, 840                     # mm
MAP_L, MAP_B = 22, 30                            # mm
PAD = 2000                                       # m around data
xmin = min(cn.total_bounds[0], pts.total_bounds[0]) - PAD
xmax = max(cn.total_bounds[2], pts.total_bounds[2]) + PAD
ymin = min(cn.total_bounds[1], pts.total_bounds[1]) - PAD
ymax = max(cn.total_bounds[3], pts.total_bounds[3]) + PAD
map_w = (xmax - xmin) / SCALE * 1000             # mm
map_h = (ymax - ymin) / SCALE * 1000
print(f"map {map_w:.0f} x {map_h:.0f} mm", file=sys.stderr)

fig = plt.figure(figsize=(SHEET_W * MM, SHEET_H * MM), facecolor="white")
ax = fig.add_axes([MAP_L / SHEET_W, MAP_B / SHEET_H, map_w / SHEET_W, map_h / SHEET_H])
ax.set_xlim(xmin, xmax)
ax.set_ylim(ymin, ymax)
ax.set_aspect("equal")

cx.add_basemap(ax, crs=CRS, source=cx.providers.Esri.WorldGrayCanvas, zoom=13,
               attribution=False, reset_extent=True)

# Neighbouring LGUs: grey wash so Camarines Norte reads as the subject
nb.plot(ax=ax, facecolor="#dcdad3", edgecolor="#b9b7b0", linewidth=0.4, alpha=0.7, zorder=2)
cn.plot(ax=ax, facecolor="none", edgecolor=INK2, linewidth=0.9, zorder=3)
cn.dissolve().boundary.plot(ax=ax, color=INK, linewidth=1.6, zorder=4)

ptm_grid(ax, 5000, label_every=2, fs=10)
graticule(ax, 5, fs=10.5)

# Detail sheet numbers follow alphabetical LGU order
SHEETS = {lgu: i + 2 for i, lgu in enumerate(sorted(CN_LGUS))}
halo = [pe.withStroke(linewidth=4, foreground="white")]
for _, r in cn.iterrows():
    p = r.geometry.representative_point()
    n = int((pts["lgu"] == r.shapeName).sum())
    ax.text(p.x, p.y, r.shapeName.upper(), ha="center", va="center", fontsize=22,
            color="#6b6a65", fontweight="bold", alpha=0.9, zorder=6, path_effects=halo)
    ax.text(p.x, p.y - 2100, f"{n} points · sheet {SHEETS[r.shapeName]}", ha="center",
            va="center", fontsize=12, color=INK2, zorder=6, path_effects=halo)

draw_points(ax, pts, scale=1.0)
draw_flags(ax, pts, scale=1.0)

# Selective labels: control, triangulation, and every BLLM No. 1
lab = pts[(pts.mon_type.isin(["PRS92", "TRIG", "PPM"])) |
          ((pts.mon_type == "BLLM") & (pts.mon_no.astype(str) == "1") & (pts.variant.fillna("") == ""))]
texts = []
for _, r in lab.iterrows():
    texts.append(ax.text(r.geometry.x, r.geometry.y, short_label(r), fontsize=7.5,
                         color=INK, zorder=50, path_effects=[pe.withStroke(linewidth=2, foreground="white")]))
adjust_text(texts, ax=ax, expand=(1.3, 1.6), force_text=(0.3, 0.6),
            arrowprops=dict(arrowstyle="-", color=INK2, lw=0.35))

# Live-matter callouts (Paracale-001)
def callout(gp_ids, text, dx, dy):
    sub = pts[pts.gp_id.isin(gp_ids)]
    x, y = sub.geometry.x.mean(), sub.geometry.y.mean()
    ax.annotate(text, xy=(x, y), xytext=(x + dx, y + dy), fontsize=11.5, color=INK,
                ha="left", va="center", zorder=70,
                bbox=dict(boxstyle="round,pad=0.45", fc="white", ec=INK, lw=0.7),
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=0.8, shrinkB=6))

bat = pts[pts.pointref.str.contains("Batobalane")].gp_id.tolist()
callout(bat, "Paracale-001\nBLBM Nos. 1–2, Bo. of Batobalane\n7.3 km SW of BLLM No. 1, Pls-1047-D",
        -21000, -9000)

north_arrow(ax, x_frac=0.968, y_frac=0.905, size_frac=0.06, fs=18)
scale_bar(ax, 10000, 5, x_frac=0.025, y_frac=0.035, fs=11)

for s in ax.spines.values():
    s.set_linewidth(1.0)
    s.set_color(INK)

# ------------------------------------------------------------ side panel ----
PX = (MAP_L + map_w + 26) / SHEET_W
PW = (SHEET_W - 16) / SHEET_W - PX
panel = fig.add_axes([PX, MAP_B / SHEET_H, PW, map_h / SHEET_H])
panel.axis("off")
PH_PT = map_h / 25.4 * 72                       # panel height in points
PW_PT = PW * SHEET_W / 25.4 * 72
panel.set_xlim(0, PW_PT)
panel.set_ylim(-PH_PT, 0)                        # y in points, 0 at top, negative down
cur = [0.0]

def gap(pt):
    cur[0] -= pt

def T(text, size, weight="normal", color=INK, x=0, ha="left", style="normal", lead=1.32, advance=True):
    panel.text(x, cur[0], text, fontsize=size, fontweight=weight, color=color, va="top",
               ha=ha, style=style)
    if advance:
        cur[0] -= size * lead

def rule(lw=0.8, color=INK):
    panel.plot([0, PW_PT], [cur[0], cur[0]], color=color, lw=lw)

R = PW_PT                                        # right edge
T("LANDTEK MAPPING DIVISION", 13, "bold", INK2); gap(10)
T("Camarines Norte", 50, "bold", INK, lead=1.12)
T("Survey tie points", 34, "normal", INK, lead=1.3); gap(4)
T(f"{len(pts):,} DENR-LMB monuments  ·  12 LGUs  ·  28 survey projects", 14, color=INK2); gap(10)
rule(1.2); gap(12)
T("Sheet 1 of 13  ·  Province overview", 15, "bold")
T("Scale 1:100,000 at 1350 × 840 mm  ·  36-inch roll", 12.5, color=INK2)
T("Dataset ph-tiepoints-camarines-norte v1.0.0  ·  retrieved 21 Sep 2026", 11, color=INK2)
gap(22)

T("LEGEND", 13, "bold", INK2); gap(4)
counts = pts.mon_type.value_counts()
for fam in ["location", "boundary", "control", "other"]:
    T(FAMILY_TITLES[fam], 13, "bold", INK, lead=1.45)
    for t, (f, marker, size, label) in SYM.items():
        if f != fam or counts.get(t, 0) == 0:
            continue
        panel.scatter([14], [cur[0] - 7], s=size * 2.2, marker=marker, c=FAM[f],
                      edgecolors=EDGE if t != "P" else "none", linewidths=0.5, clip_on=False)
        T(label, 11.5, x=36, advance=False)
        T(f"{counts.get(t, 0):,}", 11.5, color=INK2, x=R, ha="right", lead=1.55)
    gap(6)
panel.scatter([14], [cur[0] - 8], s=400, marker="o", facecolors="none", edgecolors=INK,
              linewidths=1.2, clip_on=False)
T("Flagged — outside its labelled LGU, or offshore", 11.5, x=36, advance=False)
T(f"{int(pts.flagged.sum())}", 11.5, color=INK2, x=R, ha="right", lead=1.3)
T("Administrative-boundary check only. See Appendix B.", 10.5, color=INK2, x=36, lead=1.7)
panel.plot([0, 28], [cur[0] - 7] * 2, color=INK, lw=1.8)
T("Province boundary", 11.5, x=36, lead=1.55)
panel.plot([0, 28], [cur[0] - 7] * 2, color=INK2, lw=1.0)
T("Municipal boundary (administrative)", 11.5, x=36, lead=1.55)
panel.add_patch(matplotlib.patches.Rectangle((0, cur[0] - 12), 28, 10, fc="#dcdad3", ec="#b9b7b0", lw=0.5))
T("Neighbouring province", 11.5, x=36, lead=1.55)
gap(20)

T("COVERAGE BY LGU", 13, "bold", INK2); gap(4)
cols = [("LGU", 0, "left"), ("Points", R * 0.58, "right"), ("BLLM", R * 0.72, "right"),
        ("PRS92", R * 0.86, "right"), ("Sheet", R, "right")]
for h, x, a in cols:
    T(h, 11, "bold", INK2, x=x, ha=a, advance=False)
gap(16); rule(0.5, MUTED); gap(5)
for lgu in sorted(CN_LGUS, key=lambda l: -(pts.lgu == l).sum()):
    s = pts[pts.lgu == lgu]
    vals = [lgu, f"{len(s)}", f"{(s.mon_type == 'BLLM').sum()}", f"{(s.mon_type == 'PRS92').sum()}",
            f"{SHEETS[lgu]}"]
    for (h, x, a), v in zip(cols, vals):
        T(v, 11, "bold" if (h == "PRS92" and v == "0") else "normal", INK, x=x, ha=a, advance=False)
    gap(15.5)
unres = pts[pts.lgu.fillna("") == ""]
T("(locality unresolved)", 11, color=INK2, style="italic", advance=False)
T(f"{len(unres)}", 11, color=INK2, x=R * 0.58, ha="right", advance=False)
T(f"{(unres.mon_type == 'PRS92').sum()}", 11, color=INK2, x=R * 0.86, ha="right", advance=False)
gap(15.5); rule(0.5, MUTED); gap(6)
T("Talisay has no PRS92 control. Tie GNSS work there to a", 10.5, color=INK2, style="italic")
T("neighbouring LGU's station.", 10.5, color=INK2, style="italic")
gap(20)

top = cur[0] + 4
gap(8)
T("COORDINATE REFERENCE", 13, "bold", INK2, x=10); gap(2)
panel.plot([10, 38], [cur[0] - 6] * 2, color=INK2, lw=0.6)
T("PTM grid — PRS92 / Zone IV, EPSG:3124. 5 km,", 11, x=46, lead=1.38)
T("labelled in km on the bottom and left edges.", 11, x=46, lead=1.5)
panel.plot([10, 38], [cur[0] - 6] * 2, color=GRAT, lw=0.9, dashes=(5, 3.5))
T("Graticule — WGS84 lat/lon (EPSG:4326). 5′,", 11, x=46, lead=1.38)
T("labelled on the top and right edges. Matches GPS.", 11, x=46, lead=1.5)
for ln in ["Points plotted from the published PTM values directly.",
           "",
           "The source publishes lat/lon on PRS92 (EPSG:4683),",
           "not WGS84. Plotted raw on Google Earth or any WGS84",
           "imagery, every monument lands ~217 m SE of its true",
           "position. Use the WGS84 layer or the KMZ for imagery."]:
    T(ln, 11, x=10, lead=1.38)
gap(6)
panel.add_patch(matplotlib.patches.Rectangle((0, cur[0]), R, top - cur[0], fc="none", ec=INK, lw=0.9))
gap(22)

T("STATUS", 13, "bold", INK2); gap(2)
for ln in ["Reference grade only — provenance inferred_strong.",
           "Not a certified monument description: the source",
           "carries no recovery status, physical description or",
           "accuracy order. Verify against the DENR-LMB / Region V",
           "LMS certified record before any survey or filing."]:
    T(ln, 11, lead=1.38)
gap(20)

T("SOURCES", 13, "bold", INK2); gap(2)
for ln in ["Tie points — DENR Land Management Bureau via the",
           "DENR/NAMRIA Geoportal Lot Plotter, 21 Sep 2026.",
           "Boundaries — geoBoundaries PHL ADM3 (NAMRIA, PSA,",
           "OCHA; 2020), CC BY 3.0 IGO. Administrative, not cadastral.",
           "Basemap — Esri, HERE, Garmin, © OpenStreetMap",
           "contributors, and the GIS user community."]:
    T(ln, 10.5, color=INK2, lead=1.38)

# ---- key to detail sheets (inset at foot of panel) ----
gap(26)
T("KEY TO DETAIL SHEETS", 13, "bold", INK2); gap(6)
key_top_mm = MAP_B + map_h + cur[0] / 72 * 25.4          # cur is negative points from panel top
key_h_mm = key_top_mm - MAP_B - 4
kw_mm = PW * SHEET_W
kax = fig.add_axes([PX, (MAP_B + 2) / SHEET_H, PW, key_h_mm / SHEET_H])
kax.set_aspect("equal")
cn.plot(ax=kax, facecolor="#f3f2ee", edgecolor=INK2, linewidth=0.7)
cn.dissolve().boundary.plot(ax=kax, color=INK, linewidth=1.2)
for _, r in cn.iterrows():
    p = r.geometry.representative_point()
    kax.text(p.x, p.y, f"{SHEETS[r.shapeName]}", ha="center", va="center", fontsize=15,
             fontweight="bold", color=INK)
    kax.text(p.x, p.y - 3300, r.shapeName, ha="center", va="center", fontsize=8.5, color=INK2)
kax.set_xlim(cn.total_bounds[0] - 1500, cn.total_bounds[2] + 1500)
kax.set_ylim(cn.total_bounds[1] - 1500, cn.total_bounds[3] + 1500)
kax.axis("off")

print(f"panel used {-cur[0]:.0f} of {PH_PT:.0f} pt", file=sys.stderr)

fig.savefig(os.path.join(OUT, "sheet_01_overview.pdf"), dpi=200)
print("sheet 1 done", file=sys.stderr)
