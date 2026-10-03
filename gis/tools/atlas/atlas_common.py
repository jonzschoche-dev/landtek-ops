"""Shared setup for the LandTek tie point atlas."""
import os
import warnings

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
DS = os.path.join(HERE, "..", "..", "datasets", "ph-tiepoints-camarines-norte")
INPUTS = os.path.join(HERE, "inputs")
OUT = os.path.join(HERE, "build")
os.makedirs(OUT, exist_ok=True)
CRS = "EPSG:3124"          # PRS92 / Philippines zone IV — the survey grid
MM = 1 / 25.4              # mm -> inches

matplotlib.rcParams.update({
    "font.family": "DejaVu Sans",
    "pdf.fonttype": 42,     # embed TrueType so text stays text
    "axes.linewidth": 0.6,
})

# ---- colour: validated categorical slots 1-3 (all-pairs PASS, light) --------
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#8a8984"
SURFACE = "#fcfcfb"
FAM = {
    "location": "#2a78d6",   # slot 1 blue
    "boundary": "#eb6834",   # slot 2 orange
    "control":  "#1baf7a",   # slot 3 aqua  (sub-3:1 -> dark outline + labels = relief)
    "other":    "#8a8984",   # neutral, not a categorical slot
}
EDGE = "#232323"

# mon_type -> (family, marker, size_pt2 overview, legend label)
SYM = {
    "BLLM":  ("location", "^", 46, "BLLM — Bureau of Lands Location Monument"),
    "BLBM":  ("location", "s", 30, "BLBM — Bureau of Lands Barrio Monument"),
    "BBM":   ("boundary", "o", 16, "BBM — Barrio Boundary Monument"),
    "MBM":   ("boundary", "D", 20, "MBM — Municipal Boundary Monument"),
    "PBM":   ("boundary", "v", 34, "PBM — Provincial Boundary Monument"),
    "BDRY":  ("boundary", "h", 30, "Bdry. Mon. — named boundary monument"),
    "PRS92": ("control",  "*", 110, "PRS92 geodetic control (CMN)"),
    "TRIG":  ("control",  "p", 44, "Triangulation station"),
    "PPM":   ("control",  "X", 40, "PPM — US Army 29th Engineer monument"),
    "FZM":   ("other",    "H", 30, "FZM — Forest Zone Monument"),
    "P":     ("other",    ".", 10, "P — numbered cadastral point (Cad-176)"),
}
DRAW_ORDER = ["P", "BBM", "MBM", "PBM", "BDRY", "FZM", "BLBM", "BLLM", "TRIG", "PPM", "PRS92"]
FAMILY_TITLES = {
    "location": "Location monuments",
    "boundary": "Boundary monuments",
    "control": "Geodetic control",
    "other": "Other",
}

CN_LGUS = ["Basud", "Capalonga", "Daet", "Jose Panganiban", "Labo", "Mercedes",
           "Paracale", "San Lorenzo Ruiz", "San Vicente", "Santa Elena", "Talisay", "Vinzons"]


def load():
    pts = gpd.read_file(os.path.join(DS, "data", "tiepoints_ptm4.geojson")).set_crs(CRS, allow_override=True)
    adm = gpd.read_file(os.path.join(INPUTS, "region_adm3.gpkg"))[["shapeName", "geometry"]].to_crs(CRS)
    qa = pd.read_csv(os.path.join(INPUTS, "lgu_check.csv"))[["gp_id", "in_lgu", "dist_to_own_m"]]
    pts = pts.merge(qa, on="gp_id", how="left")
    same = pts["in_lgu"] == pts["lgu"]
    pts["qa"] = np.select(
        [same, pts["in_lgu"].isna(), pts["dist_to_own_m"] <= 500],
        ["inside", "offshore", "edge"], default="outside")
    pts["flagged"] = pts["qa"].isin(["outside", "offshore"])
    pts["local_system"] = pts["pointref"].str.contains("Basiad System", case=False)
    return pts, adm


def short_label(r, with_project=True):
    t, n, proj = r["mon_type"], str(r["mon_no"] or ""), r["survey_project"] or ""
    if t == "PRS92":
        return n                                 # "CMN 3085"
    if t == "TRIG":
        return f"Trig. {n}"
    if t == "PPM":
        return f"PPM {n}"
    if t == "BDRY":
        return f"Bdry. {n}"
    base = f"{t} {n}".strip()
    if with_project and proj and t in ("BLLM", "BBM", "MBM", "PBM", "BLBM"):
        base += f" · {proj}"
    if r.get("barrio") and t == "BLBM":
        base += f" ({r['barrio']})"
    if r.get("variant"):
        base += f" [{r['variant']}]"
    return base


def draw_points(ax, pts, scale=1.0, alpha=1.0, zbase=10):
    for i, t in enumerate(DRAW_ORDER):
        sub = pts[pts["mon_type"] == t]
        if sub.empty:
            continue
        fam, marker, size, _ = SYM[t]
        lw = 0.0 if t == "P" else 0.45
        ax.scatter(sub.geometry.x, sub.geometry.y, s=size * scale, marker=marker,
                   c=FAM[fam], edgecolors=EDGE if t != "P" else "none", linewidths=lw,
                   alpha=alpha, zorder=zbase + i)


def draw_flags(ax, pts, scale=1.0, z=40):
    f = pts[pts["flagged"]]
    if not f.empty:
        ax.scatter(f.geometry.x, f.geometry.y, s=230 * scale, marker="o",
                   facecolors="none", edgecolors=INK, linewidths=1.1, zorder=z)


def ptm_grid(ax, step, label_every=1, fs=7):
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    xs = np.arange(np.ceil(x0 / step) * step, x1, step)
    ys = np.arange(np.ceil(y0 / step) * step, y1, step)
    for x in xs:
        ax.axvline(x, color=INK2, lw=0.25, alpha=0.45, zorder=5)
    for y in ys:
        ax.axhline(y, color=INK2, lw=0.25, alpha=0.45, zorder=5)
    ax.set_xticks(xs[::label_every])
    ax.set_yticks(ys[::label_every])
    fmt = (lambda v: f"{v / 1000:,.0f}") if step >= 1000 else (lambda v: f"{v:,.0f}")
    ax.set_xticklabels([f"E {fmt(v)}" for v in xs[::label_every]], fontsize=fs, color=INK2)
    ax.set_yticklabels([f"N {fmt(v)}" for v in ys[::label_every]], fontsize=fs, color=INK2,
                       rotation=90, va="center")
    # PTM labels bottom/left; the WGS84 graticule owns top/right
    ax.tick_params(length=3, width=0.4, color=INK2, top=True, right=True,
                   labeltop=False, labelright=False)


def scale_bar(ax, length_m, segments, x_frac=0.03, y_frac=0.035, fs=8, height_frac=0.006):
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    sx = x0 + (x1 - x0) * x_frac
    sy = y0 + (y1 - y0) * y_frac
    h = (y1 - y0) * height_frac
    seg = length_m / segments
    # white backing
    pad = (x1 - x0) * 0.008
    ax.add_patch(matplotlib.patches.FancyBboxPatch(
        (sx - pad, sy - h * 2.2), length_m + pad * 2 + (x1 - x0) * 0.03, h * 6.2,
        boxstyle="round,pad=0,rounding_size=0", fc="white", ec="none", alpha=0.85, zorder=60))
    for i in range(segments):
        ax.add_patch(matplotlib.patches.Rectangle(
            (sx + i * seg, sy), seg, h, fc=INK if i % 2 == 0 else "white",
            ec=INK, lw=0.6, zorder=61))
    unit = "km" if length_m >= 1000 else "m"
    div = 1000 if unit == "km" else 1
    for i in range(segments + 1):
        v = i * seg / div
        ax.text(sx + i * seg, sy + h * 1.6, f"{v:g}", ha="center", va="bottom",
                fontsize=fs, color=INK, zorder=62)
    ax.text(sx + length_m + (x1 - x0) * 0.006, sy + h * 0.5, unit, ha="left", va="center",
            fontsize=fs, color=INK, zorder=62)


def north_arrow(ax, x_frac=0.965, y_frac=0.9, size_frac=0.05, fs=11):
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    x = x0 + (x1 - x0) * x_frac
    y = y0 + (y1 - y0) * y_frac
    L = (y1 - y0) * size_frac
    w = L * 0.35
    ax.add_patch(matplotlib.patches.Polygon(
        [(x, y + L / 2), (x - w, y - L / 2), (x, y - L / 4)], fc=INK, ec=INK, lw=0.6, zorder=62))
    ax.add_patch(matplotlib.patches.Polygon(
        [(x, y + L / 2), (x + w, y - L / 2), (x, y - L / 4)], fc="white", ec=INK, lw=0.6, zorder=62))
    ax.text(x, y + L / 2 + L * 0.12, "N", ha="center", va="bottom", fontsize=fs,
            fontweight="bold", color=INK, zorder=62)
    ax.text(x, y - L / 2 - L * 0.12, "grid", ha="center", va="top", fontsize=fs * 0.55,
            color=INK2, zorder=62)


# ---- WGS84 latitude / longitude graticule ---------------------------------
GRAT = "#3d2f6b"       # deep violet-ink: distinct from the grey PTM grid, not a series hue

def _dms(v, hemi_pos, hemi_neg, step_min):
    h = hemi_pos if v >= 0 else hemi_neg
    v = abs(v)
    d = int(v)
    m_float = (v - d) * 60
    if step_min >= 1:
        m = int(round(m_float))
        if m == 60:
            d, m = d + 1, 0
        return f"{d}°{m:02d}′{h}"
    m = int(m_float)
    sec = round((m_float - m) * 60)
    if sec == 60:
        m, sec = m + 1, 0
    return f"{d}°{m:02d}′{sec:02d}″{h}"


def graticule(ax, step_min, fs=8, crs_from="EPSG:4326"):
    """Draw a lat/lon graticule (default WGS84) on a PTM axis; label top & right edges."""
    from pyproj import Transformer
    fwd = Transformer.from_crs(crs_from, CRS, always_xy=True)
    inv = Transformer.from_crs(CRS, crs_from, always_xy=True)
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    cx_ = np.array([x0, x1, x0, x1, (x0 + x1) / 2, (x0 + x1) / 2, x0, x1])
    cy_ = np.array([y0, y0, y1, y1, y0, y1, (y0 + y1) / 2, (y0 + y1) / 2])
    lons, lats = inv.transform(cx_, cy_)
    step = step_min / 60.0
    lon0, lon1 = np.floor(lons.min() / step) * step, np.ceil(lons.max() / step) * step
    lat0, lat1 = np.floor(lats.min() / step) * step, np.ceil(lats.max() / step) * step
    style = dict(color=GRAT, lw=0.55, alpha=0.75, dashes=(5, 3.5), zorder=7)
    lab = dict(fontsize=fs, color=GRAT, style="italic", clip_on=False)
    pad_x = (x1 - x0) * 0.004
    pad_y = (y1 - y0) * 0.004
    for lon in np.arange(lon0, lon1 + step / 2, step):
        la = np.linspace(lat0 - step, lat1 + step, 400)
        xs, ys = fwd.transform(np.full_like(la, lon), la)
        ax.plot(xs, ys, **style)
        if ys.min() <= y1 <= ys.max():
            xt = np.interp(y1, ys, xs)
            if x0 < xt < x1:
                ax.plot([xt, xt], [y1, y1 + pad_y * 2.2], color=GRAT, lw=0.8, clip_on=False, zorder=8)
                ax.text(xt, y1 + pad_y * 3.2, _dms(lon, "E", "W", step_min), ha="center", va="bottom", **lab)
    for lat in np.arange(lat0, lat1 + step / 2, step):
        lo = np.linspace(lon0 - step, lon1 + step, 400)
        xs, ys = fwd.transform(lo, np.full_like(lo, lat))
        ax.plot(xs, ys, **style)
        if xs.min() <= x1 <= xs.max():
            yt = np.interp(x1, xs, ys)
            if y0 < yt < y1:
                ax.plot([x1, x1 + pad_x * 2.2], [yt, yt], color=GRAT, lw=0.8, clip_on=False, zorder=8)
                ax.text(x1 + pad_x * 3.2, yt, _dms(lat, "N", "S", step_min), ha="left", va="center",
                        rotation=90, **lab)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
