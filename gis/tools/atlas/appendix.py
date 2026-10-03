"""Appendices A-G for the tie point atlas — A3 landscape, reportlab."""
import csv
import os
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

from atlas_common import CN_LGUS, DS, HERE, OUT, SYM, load, short_label

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
pdfmetrics.registerFont(TTFont("DV", f"{FONT_DIR}/DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DVB", f"{FONT_DIR}/DejaVuSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("DVI", f"{FONT_DIR}/DejaVuSans-Oblique.ttf"))
pdfmetrics.registerFont(TTFont("DVM", f"{FONT_DIR}/DejaVuSansMono.ttf"))
pdfmetrics.registerFontFamily("DV", normal="DV", bold="DVB", italic="DVI", boldItalic="DVB")

INK = colors.HexColor("#0b0b0b")
INK2 = colors.HexColor("#52514e")
RULE = colors.HexColor("#c9c8c2")
ZEBRA = colors.HexColor("#f4f3ef")

H1 = ParagraphStyle("h1", fontName="DVB", fontSize=24, leading=29, textColor=INK, spaceAfter=4)
KICK = ParagraphStyle("k", fontName="DVB", fontSize=9.5, leading=12, textColor=INK2, spaceAfter=2)
H2 = ParagraphStyle("h2", fontName="DVB", fontSize=13, leading=17, textColor=INK, spaceBefore=10, spaceAfter=4)
BODY = ParagraphStyle("b", fontName="DV", fontSize=10, leading=14.5, textColor=INK, alignment=TA_LEFT)
SMALL = ParagraphStyle("s", fontName="DV", fontSize=8.6, leading=11.5, textColor=INK2)
CELL = ParagraphStyle("c", fontName="DV", fontSize=7.4, leading=9.2, textColor=INK)
CELLB = ParagraphStyle("cb", parent=CELL, fontName="DVB")

pts, adm = load()
SHEETS = {lgu: i + 2 for i, lgu in enumerate(sorted(CN_LGUS))}
pts["sheet"] = pts.lgu.map(SHEETS)

# UTM 51N (WGS84) for drone / GIS work, and nearest PRS92 control for every monument
from pyproj import Transformer
_t = Transformer.from_crs("EPSG:4326", "EPSG:32651", always_xy=True)
pts["utm_e"], pts["utm_n"] = _t.transform(pts.wgs84_lon.values, pts.wgs84_lat.values)
_ctl = pts[pts.mon_type == "PRS92"][["mon_no", "ptm_east", "ptm_north"]].values
def _nearest(r):
    best, bd = "", 1e18
    for name, e, n in _ctl:
        if r.mon_type == "PRS92" and name == r.mon_no:
            continue
        d = (r.ptm_east - e) ** 2 + (r.ptm_north - n) ** 2
        if d < bd:
            best, bd = name, d
    return pd.Series([best, bd ** 0.5])
import pandas as pd
pts[["near_ctl", "near_ctl_m"]] = pts.apply(_nearest, axis=1)
PAGE = landscape(A3)
W = PAGE[0] - 36 * mm


def table(data, widths, header_rows=1, zebra=True, font=7.4, mono_cols=()):
    t = Table(data, colWidths=widths, repeatRows=header_rows)
    st = [
        ("FONT", (0, 0), (-1, header_rows - 1), "DVB", font),
        ("FONT", (0, header_rows), (-1, -1), "DV", font),
        ("TEXTCOLOR", (0, 0), (-1, header_rows - 1), INK2),
        ("LINEBELOW", (0, header_rows - 1), (-1, header_rows - 1), 0.8, INK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    for c in mono_cols:
        st.append(("FONT", (c, header_rows), (c, -1), "DVM", font))
        st.append(("ALIGN", (c, 0), (c, -1), "RIGHT"))
    if zebra:
        for i in range(header_rows, len(data)):
            if (i - header_rows) % 2 == 1:
                st.append(("BACKGROUND", (0, i), (-1, i), ZEBRA))
    t.setStyle(TableStyle(st))
    return t


def footer(c, doc):
    c.saveState()
    c.setFont("DV", 7.5)
    c.setFillColor(INK2)
    c.drawString(18 * mm, 10 * mm,
                 "LandTek Mapping Division · Camarines Norte survey tie points · dataset v1.0.0 · "
                 "reference grade (inferred_strong) — not a certified monument description")
    c.drawRightString(PAGE[0] - 18 * mm, 10 * mm, f"Appendix page {doc.page}")
    c.restoreState()


story = []

# ------------------------------------------------------------------ A ------
story += [Paragraph("APPENDIX A", KICK), Paragraph("Reading this atlas", H1), Spacer(1, 4)]
story.append(Paragraph(
    "Sheet 1 is the province overview at 1:100,000 on a 1350 × 840 mm sheet, sized for a 36-inch plotter "
    "roll. Sheets 2–13 are detail sheets, one per municipality, on A1 — or A0 where a municipality is too "
    "large to label at 1:50,000 on A1 — at the largest standard scale that fits, with every monument labelled. Appendices are A3. All map sheets are drawn on the "
    "PRS92 / Philippine Transverse Mercator Zone IV grid (EPSG:3124), using the published grid coordinates "
    "directly — no datum transformation sits between the source and what you see on the sheet. Over that grid "
    "every sheet carries a WGS84 latitude/longitude graticule (dashed, violet), labelled on the top and right "
    "edges, so a position read off a phone or handheld GPS can be plotted by eye. PTM grid labels run along the "
    "bottom and left edges.", BODY))
story.append(Spacer(1, 6))
story.append(Paragraph(
    "<b>The datum trap.</b> The source publishes latitude and longitude on PRS92 (EPSG:4683), not WGS84, "
    "and does not say so. Reprojecting the published lat/lon from EPSG:4683 to EPSG:3124 reproduces the "
    "published grid to within 5 mm for all 1,076 records; treating them as WGS84 misses by ~150 m per axis. "
    "Anyone who types these lat/lon values into Google Earth will put every monument about 217 m to the "
    "south-east of where it is. Use the WGS84 layer or the KMZ in the corpus for imagery work.", BODY))

story.append(Paragraph("Sheet index", H2))
rows = [["Sheet", "Contents", "Scale", "Monuments", "BLLM", "PRS92"]]
rows.append(["1", "Province overview", "1:100,000", f"{len(pts):,}",
             f"{(pts.mon_type == 'BLLM').sum()}", f"{(pts.mon_type == 'PRS92').sum()}"])
scales = {}
for f in os.listdir(OUT):
    if f.startswith("log_") and f.endswith(".txt") and f != "log_overview.txt":
        for ln in open(os.path.join(OUT, f)):
            if ": 1:" in ln and "zoom" in ln:
                lgu, rest = ln.split(": 1:", 1)
                parts_ = rest.split(" ")
                scales[lgu.strip()] = "1:" + parts_[0].rstrip(",") + (f"  ({parts_[1]})" if parts_[1] in ("A0", "A1") else "")
for lgu in sorted(CN_LGUS):
    s = pts[pts.lgu == lgu]
    rows.append([str(SHEETS[lgu]), lgu, scales.get(lgu, "—"), f"{len(s)}",
                 f"{(s.mon_type == 'BLLM').sum()}", f"{(s.mon_type == 'PRS92').sum()}"])
rows.append(["B", "Boundary QA — flagged positions", "", f"{int(pts.flagged.sum())}", "", ""])
rows.append(["C", "Records published without coordinates", "", "13", "", ""])
rows.append(["D", "Survey project index", "", "", "", ""])
rows.append(["E", "Geodetic control, GNSS and reference systems", "", "", "", f"{(pts.mon_type == 'PRS92').sum()}"])
rows.append(["F", "Gazetteer — every monument, PTM / WGS84 / UTM 51N", "", f"{len(pts):,}", "", ""])
rows.append(["G", "Sources, contacts and next steps", "", "", "", ""])
story.append(table(rows, [18 * mm, 110 * mm, 30 * mm, 28 * mm, 20 * mm, 20 * mm], font=9))

story.append(Paragraph("Monument classes", H2))
counts = pts.mon_type.value_counts()
notes = {
    "BLLM": "Primary location monument of a Pls/Cad project. Technical descriptions usually tie here.",
    "BLBM": "Barrio-level location monument. A different class from BLLM — do not conflate.",
    "BBM": "Barrio boundary monument within a subdivision or cadastral project.",
    "MBM": "Municipal boundary monument.", "PBM": "Provincial boundary monument.",
    "BDRY": "Named boundary monument with no project number.",
    "PRS92": "CMN-series PRS92 geodetic control. Use for GNSS ties.",
    "TRIG": "Triangulation station, mostly US Coast & Geodetic Survey era.",
    "PPM": "US Army 29th Engineer Corps monument (1940s).", "FZM": "Forest zone monument.",
    "P": "Numbered cadastral point. Labo Cad-176 only.",
}
fam_name = {"location": "Location — blue", "boundary": "Boundary — orange",
            "control": "Control — aqua", "other": "Other — grey"}
rows = [["Code", "Class", "Symbol family", "Count", "Notes"]]
for t, (fam, _, _, label) in SYM.items():
    rows.append([t, label.split(" — ", 1)[-1], fam_name[fam], f"{counts.get(t, 0)}",
                 Paragraph(notes[t], CELL)])
story.append(table(rows, [18 * mm, 85 * mm, 42 * mm, 18 * mm, 200 * mm], font=8.6))
story.append(Spacer(1, 6))
story.append(Paragraph(
    "Colour carries the family (three validated categorical hues plus a neutral grey); shape carries the "
    "class within a family, so the map still reads in greyscale print and for colour-vision-deficient "
    "readers.", SMALL))
story.append(PageBreak())

# ------------------------------------------------------------------ B ------
story += [Paragraph("APPENDIX B", KICK), Paragraph("Boundary QA — flagged positions", H1)]
story.append(Paragraph(
    f"Every monument was tested against the municipal polygon of the LGU it is labelled with. "
    f"{(pts.qa == 'inside').sum()} fall inside it, {(pts.qa == 'edge').sum()} fall within 500 m of it "
    f"(expected for boundary monuments and not flagged), and <b>{int(pts.flagged.sum())} are flagged</b>: "
    f"{(pts.qa == 'outside').sum()} sit more than 500 m inside a different LGU, and "
    f"{(pts.qa == 'offshore').sum()} fall outside every polygon.", BODY))
story.append(Spacer(1, 5))
story.append(Paragraph(
    "<b>Read the flags with care.</b> The polygons are geoBoundaries ADM3 (NAMRIA / PSA / OCHA, 2020) — "
    "administrative limits, not cadastral ones. A flag says <i>the position and the label disagree with the "
    "modern administrative map</i>; it does not say which one is wrong. Three patterns explain most of them:", BODY))
story.append(Spacer(1, 4))
for b in [
    "<b>Survey predates the modern municipal limits.</b> The source itself records a “Bo. of Mercedes, "
    "Municipality of Daet”, and lists barrios Colasi, Pambuhan and Matoogtoog under both Daet and Mercedes. "
    "Daet-labelled barrio monuments landing in present-day Mercedes are consistent with surveys made when "
    "those barrios were still part of Daet. The 17 Mercedes Pls-677-D monuments inside present-day Daet may "
    "have the same origin, or may reflect imprecision in the administrative boundary; neither is verified.",
    "<b>Local coordinate systems.</b> Three Capalonga records say “Coord. in B. Basiad System” in their own "
    "reference. Their coordinates are in a local system, not PRS92, so the plotted position is not "
    "meaningful. Two of them land offshore west of the province. Treat them as unlocated.",
    "<b>Offshore positions.</b> Four Daet BLBMs (Bo. of Colasi Nos. 1–2, Bo. of Pambuhan Nos. 1 and 3, "
    "the latter marked “Old”) plot 20 km east in open water. The Mercedes-labelled BLBMs for the same barrios "
    "plot on land. Probably a transcription or local-system problem; unresolved.",
]:
    story.append(Paragraph("•&nbsp;&nbsp;" + b, BODY))
    story.append(Spacer(1, 3))
story.append(Spacer(1, 6))
f = pts[pts.flagged].copy()
f["d"] = f.dist_to_own_m.fillna(0)
f = f.sort_values(["lgu", "qa", "d"], ascending=[True, True, False])
rows = [["Sheet", "Labelled LGU", "Plots in", "Dist. to own LGU", "Type", "Point reference (as published)",
         "PTM E", "PTM N"]]
for r in f.itertuples():
    rows.append([str(r.sheet) if r.sheet == r.sheet else "—", r.lgu or "(unresolved)",
                 r.in_lgu if isinstance(r.in_lgu, str) else "offshore",
                 f"{r.d / 1000:,.1f} km", r.mon_type, Paragraph(r.pointref, CELL),
                 f"{r.ptm_east:,.2f}", f"{r.ptm_north:,.2f}"])
story.append(table(rows, [14 * mm, 30 * mm, 30 * mm, 24 * mm, 14 * mm, 172 * mm, 32 * mm, 34 * mm],
                   mono_cols=(3, 6, 7)))
story.append(PageBreak())

# ------------------------------------------------------------------ C ------
story += [Paragraph("APPENDIX C", KICK), Paragraph("Records published without coordinates", H1)]
story.append(Paragraph(
    "These 13 entries exist in the DENR-LMB tie point table but the service returns no position for them. "
    "They appear on no map sheet. They are retained in the corpus source file.", BODY))
story.append(Spacer(1, 6))
raw = list(csv.DictReader(open(os.path.join(DS, "source", "raw_harvest_2026-09-21.csv"))))
rows = [["Locality (as published)", "Geoportal id", "Point reference (as published)"]]
for r in raw:
    if not r["lat"]:
        rows.append([r["municipality"], r["id"], r["pointref"]])
story.append(table(rows, [60 * mm, 30 * mm, 260 * mm], font=9, mono_cols=(1,)))
story.append(PageBreak())

# ------------------------------------------------------------------ D ------
story += [Paragraph("APPENDIX D", KICK), Paragraph("Survey project index", H1)]
story.append(Paragraph(
    "Every Public Land Subdivision (Pls), Cadastral (Cad), Cadastral Mapping (Cadm) and Group Settlement "
    "(Gss) project represented in the tie point table, with where its monuments fall and where its BLLM No. 1 "
    "sits. Project identifiers are normalised from the published reference (e.g. “Pls 1047 D” → Pls-1047-D) "
    "but deliberately not merged: <i>Pls-819</i> and <i>Pls-819-D</i>, or <i>Cad-456-D</i> and "
    "<i>Cadm-456-D</i>, are probably the same project catalogued twice, and are left as the source wrote them.",
    BODY))
story.append(Spacer(1, 6))
proj = pts[pts.survey_project.fillna("") != ""]
rows = [["Project", "LGU(s)", "Sheet(s)", "Total", "BLLM", "BLBM", "BBM", "MBM", "Other",
         "BLLM No. 1 — PTM E", "BLLM No. 1 — PTM N"]]
def pk(p):
    import re
    m = re.match(r"([A-Za-z]+)-(\d+)", p)
    return (m.group(1), int(m.group(2)), p) if m else (p, 0, p)
for p in sorted(proj.survey_project.unique(), key=pk):
    g = proj[proj.survey_project == p]
    lg = sorted(set(g.lgu.dropna()) - {""})
    sh = sorted({int(x) for x in g.sheet.dropna()})
    c = g.mon_type.value_counts()
    b1 = g[(g.mon_type == "BLLM") & (g.mon_no.astype(str) == "1")]
    b1 = b1[b1.variant.fillna("") == ""] if not b1[b1.variant.fillna("") == ""].empty else b1
    e = f"{b1.iloc[0].ptm_east:,.3f}" if not b1.empty else "—"
    n = f"{b1.iloc[0].ptm_north:,.3f}" if not b1.empty else "—"
    other = len(g) - sum(c.get(k, 0) for k in ("BLLM", "BLBM", "BBM", "MBM"))
    rows.append([p, ", ".join(lg), ", ".join(map(str, sh)), f"{len(g)}", f"{c.get('BLLM', 0)}",
                 f"{c.get('BLBM', 0)}", f"{c.get('BBM', 0)}", f"{c.get('MBM', 0)}", f"{other}", e, n])
noproj = pts[pts.survey_project.fillna("") == ""]
rows.append(["(no project)", "all", "", f"{len(noproj)}", f"{(noproj.mon_type == 'BLLM').sum()}",
             f"{(noproj.mon_type == 'BLBM').sum()}", "", "", f"{len(noproj) - (noproj.mon_type.isin(['BLLM','BLBM'])).sum()}", "", ""])
story.append(table(rows, [28 * mm, 58 * mm, 22 * mm, 16 * mm, 16 * mm, 16 * mm, 16 * mm, 16 * mm,
                          16 * mm, 40 * mm, 42 * mm], font=8.4, mono_cols=(9, 10)))
story.append(Spacer(1, 5))
story.append(Paragraph(
    "“(no project)” rows are municipality-level BLLMs, barrio BLBMs, named boundary monuments, triangulation "
    "stations and PRS92 control, which the source does not tie to a Pls or Cad number.", SMALL))
story.append(PageBreak())

# ------------------------------------------------------------------ E ------
story += [Paragraph("APPENDIX E", KICK), Paragraph("Geodetic control, GNSS and reference systems", H1)]
story.append(Paragraph("Reference systems used in this atlas and the corpus", H2))
rows = [["EPSG", "Name", "Role here", "Definition"],
        ["4683", "PRS92 (geographic)", "Published lat/lon in the source", "Clarke 1866 ellipsoid"],
        ["3124", "PRS92 / Philippines Zone IV (PTM)", "Map grid on every sheet; published E/N",
         "Transverse Mercator · central meridian 123°E · scale factor 0.99995 · FE 500 000 m · FN 0 · Clarke 1866"],
        ["4326", "WGS 84 (geographic)", "Graticule; GPS; Google Earth; KMZ", "WGS 84 ellipsoid"],
        ["32651", "WGS 84 / UTM zone 51N", "Drone mapping, most GIS work (gazetteer columns)",
         "Transverse Mercator · central meridian 123°E · scale factor 0.9996 · FE 500 000 m · FN 0 · WGS 84"],
        ["3857", "WGS 84 / Pseudo-Mercator", "Web basemap tiles only", "Not for measurement"]]
story.append(table(rows, [18 * mm, 70 * mm, 88 * mm, 170 * mm], font=8.6))
story.append(Spacer(1, 6))
story.append(Paragraph(
    "<b>PRS92 → WGS84 transformation used throughout</b> (EPSG operation “PRS92 to WGS 84 (1)”, "
    "7-parameter, coordinate-frame convention): ΔX −127.62 m, ΔY −67.24 m, ΔZ −47.04 m, "
    "rX 3.068″, rY −4.903″, rZ −1.578″, scale −1.06 ppm. On the ground in Camarines Norte this moves "
    "every point 215–218 m on a bearing of about 137°. PTM Zone IV and UTM 51N share the same central "
    "meridian (123°E) and false easting, so their numbers look deceptively alike — they differ in datum, "
    "ellipsoid and scale factor, and must never be mixed.", BODY))

story.append(Paragraph("PAGeNet continuously operating reference stations near the province", H2))
cors = [
    ("PNAG", "Naga City, Camarines Sur", 2016, "GPS | GLONASS", "active", 13.624, 123.185),
    ("PGM2", "Gumaca, Quezon", 2021, "GPS | GLONASS | Galileo | BeiDou | QZSS", "active (replaced PGUM)", 13.921, 122.100),
    ("PIRI", "Iriga City, Camarines Sur", 2024, "GPS | GLONASS | Galileo | BeiDou | QZSS", "active", 13.423, 123.412),
    ("PLG2", "Legazpi City, Albay", 2022, "GPS | GLONASS", "active (replaced PLEG)", 13.139, 123.744),
    ("PSRG", "Sorsogon City, Sorsogon", 2019, "GPS | GLONASS | Galileo | BeiDou | QZSS", "active", 12.974, 124.006),
    ("PGUM", "Gumaca, Quezon", 2018, "", "decommissioned 2021 → PGM2", 13.921, 122.100),
    ("PLEG", "Legazpi City, Albay", 2009, "", "decommissioned 2022 → PLG2", 13.139, 123.744),
]
from pyproj import Geod
_g = Geod(ellps="WGS84")
daet = pts[pts.lgu == "Daet"]
dlat, dlon = daet.wgs84_lat.median(), daet.wgs84_lon.median()
rows = [["Site", "Host city", "Est.", "Constellations", "Status per PAGeNet", "≈ km to Daet"]]
for sid, loc, yr, con, st, la, lo in cors:
    km = _g.inv(dlon, dlat, lo, la)[2] / 1000
    rows.append([sid, loc, str(yr), con, st, f"{km:,.0f}"])
story.append(table(rows, [18 * mm, 60 * mm, 14 * mm, 90 * mm, 70 * mm, 28 * mm], font=8.6, mono_cols=(5,)))
story.append(Spacer(1, 4))
story.append(Paragraph(
    "Station list, constellations and status from the PAGeNet station pages, read 21 Sep 2026. "
    "Distances are approximate — host-city centre to the median Daet monument, ±5 km — because PAGeNet does "
    "not publish antenna coordinates on those pages. There is no CORS inside Camarines Norte; PNAG and PIRI "
    "are the closest. Confirm service coverage and baseline limits with PAGeNet before planning RTK work.",
    SMALL))

story.append(Paragraph("PRS92 geodetic control points in the province", H2))
story.append(Paragraph(
    f"All {int((pts.mon_type == 'PRS92').sum())} CMN-series stations in the table, in every coordinate "
    "system you are likely to need. These are the natural occupation points for tying GNSS work to the "
    "national network. <b>Talisay has none.</b> Recovery status is unknown — obtain a NAMRIA Certification "
    "of Geodetic Control Points before occupying any of them.", BODY))
story.append(Spacer(1, 4))
ctl = pts[pts.mon_type == "PRS92"].copy()
ctl["_n"] = ctl.mon_no.str.extract(r"(\d+)").astype(int)
rows = [["Station", "LGU", "Sheet", "PTM E (m)", "PTM N (m)", "WGS84 lat", "WGS84 lon",
         "UTM 51N E", "UTM 51N N", "QA"]]
for r in ctl.sort_values(["lgu", "_n"]).itertuples():
    rows.append([r.mon_no, r.lgu or "(unresolved)", str(int(r.sheet)) if r.sheet == r.sheet else "—",
                 f"{r.ptm_east:,.3f}", f"{r.ptm_north:,.3f}", f"{r.wgs84_lat:.7f}", f"{r.wgs84_lon:.7f}",
                 f"{r.utm_e:,.2f}", f"{r.utm_n:,.2f}", "⚑" if r.flagged else ""])
story.append(table(rows, [26 * mm, 36 * mm, 14 * mm, 38 * mm, 40 * mm, 32 * mm, 34 * mm, 36 * mm, 38 * mm, 12 * mm],
                   font=7.8, mono_cols=(3, 4, 5, 6, 7, 8)))
story.append(PageBreak())

# ------------------------------------------------------------------ F ------
story += [Paragraph("APPENDIX F", KICK), Paragraph("Gazetteer", H1)]
story.append(Paragraph(
    "Every monument with coordinates, by LGU, then class, then survey project and number. PTM values are "
    "as published (EPSG:3124). WGS84 and UTM 51N values are transformed from the published PRS92 lat/lon — "
    "use them for Google Earth, handheld GPS, drones and general GIS. “Nearest PRS92” is the closest CMN "
    "control station by grid distance, for planning a GNSS tie. <b>⚑</b> marks a boundary-QA flag "
    "(Appendix B); <b>L</b> marks a record whose reference says its coordinates are in a local system.", BODY))
story.append(Spacer(1, 6))
order = {t: i for i, t in enumerate(["BLLM", "BLBM", "PRS92", "TRIG", "PPM", "MBM", "PBM", "BDRY",
                                     "BBM", "FZM", "P"])}


def key(r):
    try:
        n = int(r.mon_no)
    except (TypeError, ValueError):
        n = 10**6
    return (r.lgu or "~", order.get(r.mon_type, 99), r.survey_project or "", n, str(r.mon_no))


rows = [["Sh.", "LGU", "Monument", "Project", "Barrio / variant", "PTM E (m)", "PTM N (m)",
         "WGS84 lat", "WGS84 lon", "UTM 51N E", "UTM 51N N", "Nearest PRS92", "QA", "Geoportal id"]]
for r in sorted(pts.itertuples(), key=key):
    lab = short_label(r._asdict(), with_project=False)
    extra = " · ".join(x for x in [r.barrio or "", r.variant or ""] if x)
    qa = ("⚑" if r.flagged else "") + ("L" if r.local_system else "")
    rows.append([str(int(r.sheet)) if r.sheet == r.sheet else "—", r.lgu or "(unresolved)",
                 lab.split(" (")[0].split(" [")[0], r.survey_project or "", extra[:34],
                 f"{r.ptm_east:,.3f}", f"{r.ptm_north:,.3f}",
                 f"{r.wgs84_lat:.6f}", f"{r.wgs84_lon:.6f}", f"{r.utm_e:,.1f}", f"{r.utm_n:,.1f}",
                 f"{r.near_ctl} · {r.near_ctl_m / 1000:.1f} km", qa, str(r.gp_id)])
story.append(table(rows, [9 * mm, 27 * mm, 30 * mm, 21 * mm, 42 * mm, 29 * mm, 31 * mm, 23 * mm, 25 * mm,
                          27 * mm, 29 * mm, 36 * mm, 9 * mm, 17 * mm],
                   mono_cols=(5, 6, 7, 8, 9, 10, 13), font=6.6))
story.append(PageBreak())

# ------------------------------------------------------------------ G ------
story += [Paragraph("APPENDIX G", KICK), Paragraph("Sources, contacts and next steps", H1)]
story.append(Paragraph("Data sources", H2))
rows = [["Layer", "Source", "Licence / status", "Retrieved"],
        ["Tie points (1,076 + 13 without coordinates)",
         Paragraph("DENR Land Management Bureau tie point table, served by the DENR/NAMRIA Geoportal Lot Plotter "
                   "— geoportal.gov.ph/gpapps/lotplotter — endpoints /lp/gettp and /lp/gettpvalue", CELL),
         Paragraph("Government data. Geoportal banner: viewing only, not for legal purposes.", CELL), "21 Sep 2026"],
        ["Municipal boundaries",
         Paragraph("geoBoundaries PHL ADM3, from NAMRIA / PSA / OCHA Philippines (2020 boundaries)", CELL),
         Paragraph("CC BY 3.0 IGO. Administrative, not cadastral.", CELL), "21 Sep 2026"],
        ["LGU codes", Paragraph("Philippine Statistics Authority, PSGC (as of 31 July 2025)", CELL), "Public", "21 Sep 2026"],
        ["CORS stations", Paragraph("PAGeNet station pages, pagenet.namria.gov.ph", CELL), "Public", "21 Sep 2026"],
        ["Basemaps", Paragraph("Esri World Light Gray Canvas (sheet 1) and World Topographic Map (sheets 2–13)", CELL),
         Paragraph("Esri, HERE, Garmin, Intermap, USGS, NGA, © OpenStreetMap contributors, GIS user community", CELL),
         "21 Sep 2026"]]
story.append(table(rows, [60 * mm, 150 * mm, 100 * mm, 30 * mm], font=8.6))

story.append(Paragraph("Contacts", H2))
rows = [["Office", "For", "Contact (verified 21 Sep 2026)"],
        ["NAMRIA — PAGeNet, Geodesy Division", "CORS data (RINEX), network RTK, station information",
         Paragraph("pagenet@namria.gov.ph · (632) 8884-2849 · (632) 8810-4831 local 615<br/>"
                   "G/F East Wing, NAMRIA Main Building, Lawton Ave., Fort Andres Bonifacio, Taguig City 1634<br/>"
                   "Registration and fees: pagenet.namria.gov.ph (Services and Fees page)", CELL)],
        ["DENR Land Management Bureau / Region V LMS", "Certified monument descriptions, recovery status",
         Paragraph("Via eFOI (foi.gov.ph). Prior request DENRLMB-391438302358 (2020) covers BLLM No. 1, "
                   "Pls-1047-D Paracale — attachment 20200700203.pdf.", CELL)]]
story.append(table(rows, [70 * mm, 90 * mm, 180 * mm], font=8.6))
story.append(Spacer(1, 4))
story.append(Paragraph(
    "Only contact details confirmed against the agency's own website on the retrieval date are listed. Fees "
    "change; check the PAGeNet Services and Fees page rather than relying on any figure quoted elsewhere.",
    SMALL))

story.append(Paragraph("Before any of this is used in a survey or a filing", H2))
for b in [
    "Pull the <b>certified monument description</b> for every monument a technical description ties to. The "
    "coordinates here cannot identify the physical marker; the description can.",
    "Get the <b>recovery status</b>. A monument that was destroyed or disturbed is a coordinate, not a tie.",
    "If a technical description cites “BLLM No. 1” without a project, <b>establish which one</b>. Paracale "
    "alone has four records of BLLM No. 1 (Appendix F).",
    "Resolve any <b>⚑ flag</b> (Appendix B) that touches a parcel of interest before relying on the position.",
    "For GNSS, occupy recovered PRS92 control or process against a PAGeNet CORS, and carry the result in "
    "PRS92 / PTM Zone IV for anything that goes to DENR.",
    "Once a monument is certified, promote it in the corpus (gis_tiepoints.provenance_level = 'verified' with "
    "the document id and quoted excerpt). Only then does it appear in gis_tiepoints_safe.",
]:
    story.append(Paragraph("•&nbsp;&nbsp;" + b, BODY))
    story.append(Spacer(1, 3))

doc = SimpleDocTemplate(os.path.join(OUT, "appendix.pdf"), pagesize=PAGE,
                        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
                        title="Camarines Norte tie point atlas — appendices", author="LandTek Mapping Division")
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print("appendix done", file=sys.stderr)
