"""LGU detail sheet — A1 landscape, every monument in the LGU labelled.

    python3 sheet_detail.py "Paracale"
"""
import sys

import contextily as cx
import matplotlib.pyplot as plt
import numpy as np
from adjustText import adjust_text
from matplotlib import patheffects as pe
from shapely.geometry import box

from atlas_common import *

LGU = sys.argv[1]
SHEETS = {lgu: i + 2 for i, lgu in enumerate(sorted(CN_LGUS))}
SHEET_NO = SHEETS[LGU]

pts, adm = load()
poly = adm[adm.shapeName == LGU].geometry.union_all()
own = pts[pts.lgu == LGU].copy()

# Keep every monument labelled with this LGU on its sheet, even where it plots inside a
# neighbour (Mercedes Pls-677-D inside present-day Daet, for instance). Only positions that
# cannot be meaningful are left off: offshore, local-system coordinates, or >15 km away.
own["d_poly"] = own.geometry.distance(poly)
off = (own.qa == "offshore") | own.local_system | (own.d_poly > 15000)
far = own[off]
near = own[~off]

SHEET_W, SHEET_H = 841, 594           # A1 landscape, mm
MAP_L, MAP_B, MAP_W, MAP_H = 16, 20, 590, 556
SCALES = [10_000, 12_500, 15_000, 20_000, 25_000, 30_000, 40_000, 50_000, 60_000, 75_000, 100_000]

# Frame on the polygon parts that matter: the largest part plus any part carrying
# monuments. Pointless outlying islets otherwise push the scale down a notch.
parts = list(poly.geoms) if poly.geom_type == "MultiPolygon" else [poly]
parts.sort(key=lambda g: -g.area)
keep = [parts[0]] + [g for g in parts[1:] if (near.geometry.distance(g) < 500).any()]
bx0 = min(g.bounds[0] for g in keep); by0 = min(g.bounds[1] for g in keep)
bx1 = max(g.bounds[2] for g in keep); by1 = max(g.bounds[3] for g in keep)
if not near.empty:
    nb_ = near.total_bounds
    bx0, by0, bx1, by1 = min(bx0, nb_[0]), min(by0, nb_[1]), max(bx1, nb_[2]), max(by1, nb_[3])
need_w, need_h = (bx1 - bx0) * 1.06, (by1 - by0) * 1.06
SCALE = next(s for s in SCALES if MAP_W / 1000 * s >= need_w and MAP_H / 1000 * s >= need_h)
PAPER = "A1"
if SCALE > 50_000:
    # Too coarse to label every monument on A1 — go up to A0 instead of down in scale.
    PAPER = "A0"
    SHEET_W, SHEET_H = 1189, 841
    MAP_L, MAP_B, MAP_W, MAP_H = 16, 20, 900, 800
    SCALE = next(s for s in SCALES if MAP_W / 1000 * s >= need_w and MAP_H / 1000 * s >= need_h)
cxm, cym = (bx0 + bx1) / 2, (by0 + by1) / 2
half_w, half_h = MAP_W / 1000 * SCALE / 2, MAP_H / 1000 * SCALE / 2
xmin, xmax, ymin, ymax = cxm - half_w, cxm + half_w, cym - half_h, cym + half_h
frame = box(xmin, ymin, xmax, ymax)
zoom = 15 if SCALE <= 25_000 else 14 if SCALE <= 60_000 else 13
print(f"{LGU}: 1:{SCALE:,} {PAPER} zoom {zoom}, {len(own)} own points ({len(far)} off-sheet)", file=sys.stderr)

fig = plt.figure(figsize=(SHEET_W * MM, SHEET_H * MM), facecolor="white")
ax = fig.add_axes([MAP_L / SHEET_W, MAP_B / SHEET_H, MAP_W / SHEET_W, MAP_H / SHEET_H])
ax.set_xlim(xmin, xmax)
ax.set_ylim(ymin, ymax)
ax.set_aspect("equal")
cx.add_basemap(ax, crs=CRS, source=cx.providers.Esri.WorldTopoMap, zoom=zoom,
               attribution=False, reset_extent=True)
# Knock the topo basemap back so the monuments carry the page
ax.add_patch(matplotlib.patches.Rectangle((xmin, ymin), xmax - xmin, ymax - ymin,
             fc="white", ec="none", alpha=0.38, zorder=1.5))

# Veil everything outside this LGU
outside = gpd.GeoSeries([frame.difference(poly)], crs=CRS)
outside.plot(ax=ax, facecolor="white", edgecolor="none", alpha=0.5, zorder=2)
others = adm[(adm.shapeName != LGU) & adm.intersects(frame)]
others.boundary.plot(ax=ax, color=INK2, linewidth=0.7, alpha=0.7, zorder=3)
gpd.GeoSeries([poly], crs=CRS).boundary.plot(ax=ax, color=INK, linewidth=2.0, zorder=4)

halo = [pe.withStroke(linewidth=3.5, foreground="white")]
for _, r in others.iterrows():
    clip = r.geometry.intersection(frame)
    if clip.is_empty or clip.area < 4e6:
        continue
    p = clip.representative_point()
    label = r.shapeName.upper()
    if r.shapeName in SHEETS:
        label += f"\nsheet {SHEETS[r.shapeName]}"
    ax.text(p.x, p.y, label, ha="center", va="center", fontsize=11, color=MUTED,
            fontweight="bold", zorder=6, path_effects=halo, linespacing=1.3)

step = 1000 if SCALE <= 30_000 else 2000 if SCALE <= 60_000 else 5000
ptm_grid(ax, step, label_every=1, fs=7.5)
GSTEP = 1 if SCALE <= 30_000 else 2 if SCALE <= 60_000 else 5
graticule(ax, GSTEP, fs=8)

vis = pts[pts.geometry.within(frame)]
others_pts = vis[vis.lgu != LGU]
own_vis = vis[vis.lgu == LGU]
mscale = 1.9
draw_points(ax, others_pts, scale=mscale * 0.8, alpha=0.35, zbase=10)
draw_points(ax, own_vis, scale=mscale, alpha=1.0, zbase=20)
draw_flags(ax, own_vis, scale=mscale * 0.9, z=40)

texts = []
dense = len(own_vis) > 150
for _, r in own_vis.iterrows():
    t = r.mon_type
    if t == "P":
        txt, fs, w = f"P{r.mon_no}", 5.2, "normal"
    else:
        txt = short_label(r, with_project=not dense or t in ("BLLM", "BLBM"))
        fs = 7.2 if t in ("BLLM", "PRS92", "TRIG", "BLBM") else 6.2
        w = "bold" if t in ("BLLM", "PRS92") else "normal"
    texts.append(ax.text(r.geometry.x, r.geometry.y, txt, fontsize=fs, fontweight=w, color=INK,
                         zorder=50, path_effects=[pe.withStroke(linewidth=2.2, foreground="white")]))
if texts:
    adjust_text(texts, ax=ax, expand=(1.15, 1.35), force_text=(0.25, 0.5),
                max_move=None if len(texts) < 200 else 40, iter_lim=400 if len(texts) < 200 else 200,
                arrowprops=dict(arrowstyle="-", color=INK2, lw=0.3))

# Matter-specific callouts
if LGU == "Paracale":
    for sub_q, text, dx, dy in [
        ("Batobalane", "Paracale-001\nBLBM Nos. 1–2, Bo. of Batobalane", -5200, -2600),
        ("BLLM No. 1, Pls 1047 D", "BLLM No. 1, Pls-1047-D\n(poblacion) — 7.3 km NE of Batobalane", 2200, 3200),
    ]:
        s = own_vis[own_vis.pointref.str.contains(sub_q, regex=False)]
        if s.empty:
            continue
        x, y = s.geometry.x.mean(), s.geometry.y.mean()
        ax.annotate(text, xy=(x, y), xytext=(x + dx, y + dy), fontsize=10, color=INK, zorder=70,
                    ha="left", va="center",
                    bbox=dict(boxstyle="round,pad=0.45", fc="white", ec=INK, lw=0.8),
                    arrowprops=dict(arrowstyle="-|>", color=INK, lw=0.9, shrinkB=8))

bar = {10_000: 1000, 12_500: 1000, 15_000: 1000, 20_000: 2000, 25_000: 2000, 30_000: 2000,
       40_000: 5000, 50_000: 5000, 60_000: 5000, 75_000: 5000, 100_000: 10000}[SCALE]
scale_bar(ax, bar, 5 if bar != 2000 else 4, x_frac=0.025, y_frac=0.03, fs=9)
north_arrow(ax, x_frac=0.962, y_frac=0.91, size_frac=0.06, fs=15)
for s in ax.spines.values():
    s.set_linewidth(1.0)
    s.set_color(INK)

# ------------------------------------------------------------------ panel ----
PX_mm = MAP_L + MAP_W + 14
panel = fig.add_axes([PX_mm / SHEET_W, MAP_B / SHEET_H, (SHEET_W - 12 - PX_mm) / SHEET_W, MAP_H / SHEET_H])
panel.axis("off")
PH = MAP_H / 25.4 * 72
PWp = (SHEET_W - 12 - PX_mm) / 25.4 * 72
panel.set_xlim(0, PWp)
panel.set_ylim(-PH, 0)
cur = [0.0]

def gap(p):
    cur[0] -= p

def T(text, size, weight="normal", color=INK, x=0, ha="left", style="normal", lead=1.32, advance=True, family=None):
    kw = {"family": family} if family else {}
    panel.text(x, cur[0], text, fontsize=size, fontweight=weight, color=color, va="top", ha=ha,
               style=style, **kw)
    if advance:
        cur[0] -= size * lead

psgc = own.psgc_code.dropna().iloc[0] if not own.empty else ""
T("LANDTEK MAPPING DIVISION  ·  CAMARINES NORTE TIE POINTS", 8.5, "bold", INK2); gap(6)
T(LGU, 34 if len(LGU) < 14 else 27, "bold", INK, lead=1.15)
T(f"Sheet {SHEET_NO} of 13  ·  Scale 1:{SCALE:,} at {PAPER}", 12, "bold", INK)
T(f"PSGC {psgc}  ·  {len(own)} monuments  ·  "
  f"{own.survey_project.replace('', np.nan).nunique()} survey projects", 10, color=INK2)
gap(4)
panel.plot([0, PWp], [cur[0], cur[0]], color=INK, lw=1.0); gap(12)

T("LEGEND", 10, "bold", INK2); gap(2)
cnt = own.mon_type.value_counts()
for t, (f, marker, size, label) in SYM.items():
    if cnt.get(t, 0) == 0:
        continue
    panel.scatter([10], [cur[0] - 5.5], s=size * 1.7, marker=marker, c=FAM[f],
                  edgecolors=EDGE if t != "P" else "none", linewidths=0.45, clip_on=False)
    T(label, 9, x=26, advance=False)
    T(f"{cnt[t]}", 9, color=INK2, x=PWp, ha="right", lead=1.5)
nflag = int(own_vis.flagged.sum())
if nflag:
    panel.scatter([10], [cur[0] - 6], s=260, marker="o", facecolors="none", edgecolors=INK,
                  linewidths=1.1, clip_on=False)
    T("Flagged — outside this LGU's boundary", 9, x=26, advance=False)
    T(f"{nflag}", 9, color=INK2, x=PWp, ha="right", lead=1.5)
panel.scatter([10], [cur[0] - 5.5], s=40, marker="o", c="#bbbbbb", alpha=0.5, clip_on=False)
T("Monuments of neighbouring LGUs (faded, unlabelled)", 9, x=26, lead=1.5)
if len(far):
    gap(2)
    T(f"{len(far)} monument(s) labelled {LGU} are left off this sheet:", 9, "bold", INK)
    T("offshore, local-system coordinates, or >15 km away. See Appendix B.", 9, color=INK2)
gap(10)

T("GRIDS", 10, "bold", INK2); gap(2)
panel.plot([0, 20], [cur[0] - 5] * 2, color=INK2, lw=0.6)
T(f"PTM grid — PRS92 / Zone IV (EPSG:3124), every {step/1000:g} km.", 9, x=26)
T("Labelled in km, bottom and left edges.", 9, x=26, color=INK2)
panel.plot([0, 20], [cur[0] - 5] * 2, color=GRAT, lw=0.9, dashes=(5, 3.5))
T(f"Graticule — WGS84 lat/lon (EPSG:4326), every {GSTEP}′.", 9, x=26)
T("Labelled top and right edges. Reads directly against GPS.", 9, x=26, color=INK2)
gap(2)
T("Monuments plotted from the published PTM values. The source's", 8.5, color=INK2)
T("own lat/lon are PRS92, not WGS84 — ~217 m apart on the ground.", 8.5, color=INK2)
gap(10)

LIST_MAX = 140
if 0 < len(own) <= LIST_MAX:
    T("MONUMENTS ON THIS SHEET", 10, "bold", INK2); gap(3)
    cols = [("Monument", 0, "left"), ("Easting", PWp * 0.78, "right"), ("Northing", PWp, "right")]
    for h, x, a in cols:
        T(h, 7.8, "bold", INK2, x=x, ha=a, advance=False)
    gap(11)
    panel.plot([0, PWp], [cur[0] + 2, cur[0] + 2], color=MUTED, lw=0.4)
    order = {t: i for i, t in enumerate(["BLLM", "BLBM", "PRS92", "TRIG", "PPM", "MBM", "PBM", "BDRY", "BBM", "FZM", "P"])}
    def k(r):
        try:
            n = int(r.mon_no)
        except (TypeError, ValueError):
            n = 10**6
        return (order.get(r.mon_type, 99), r.survey_project or "", n, str(r.mon_no))
    rows = sorted(own.itertuples(), key=k)
    avail = PH + cur[0] - 30
    fs = 7.2 if len(rows) * 7.2 * 1.32 < avail else max(5.6, avail / len(rows) / 1.32)
    for r in rows:
        mark = " ⚑" if r.flagged else ""
        T(short_label(r._asdict(), with_project=True)[:46] + mark, fs, x=0, advance=False)
        T(f"{r.ptm_east:,.2f}", fs, x=PWp * 0.78, ha="right", advance=False, family="DejaVu Sans Mono")
        T(f"{r.ptm_north:,.2f}", fs, x=PWp, ha="right", lead=1.32, family="DejaVu Sans Mono")
    gap(3)
    T("⚑ flagged (Appendix B).  Full record in Appendix D.", 7, color=INK2)
else:
    T("MONUMENT LIST", 10, "bold", INK2); gap(2)
    T(f"{len(own)} monuments — too many to list on the sheet.", 9)
    T("Coordinates for every one are in Appendix D (gazetteer).", 9, color=INK2)

# footer
panel.text(0, -PH, "Reference grade only (inferred_strong) — not a certified monument description.\n"
           "Tie points: DENR-LMB via Geoportal Lot Plotter, 21 Sep 2026. Boundaries: geoBoundaries\n"
           "PHL ADM3 (NAMRIA/PSA/OCHA 2020), administrative. Basemap: Esri, HERE, Garmin,\n"
           "Intermap, USGS, NGA, © OpenStreetMap contributors, GIS user community.",
           fontsize=6.6, color=INK2, va="bottom", linespacing=1.35)

out = os.path.join(OUT, f"sheet_{SHEET_NO:02d}_{LGU.replace(' ', '_')}.pdf")
fig.savefig(out, dpi=220)
print(f"{LGU} -> {out}", file=sys.stderr)
