"""Merge sheets + appendices into one atlas PDF with bookmarks."""
import glob
import os
import sys

from pypdf import PdfReader, PdfWriter

from atlas_common import CN_LGUS, HERE, OUT

ATLAS = os.path.join(OUT, "cn_tiepoints_atlas_v1.0.0.pdf")
w = PdfWriter()

sheets = sorted(glob.glob(os.path.join(OUT, "sheet_*.pdf")))
assert len(sheets) == 13, f"expected 13 sheets, found {len(sheets)}"
page_of = {}
for f in sheets:
    r = PdfReader(f)
    page_of[os.path.basename(f)] = len(w.pages)
    for p in r.pages:
        w.add_page(p)

app = PdfReader(os.path.join(OUT, "appendix.pdf"))
app_start = len(w.pages)
for p in app.pages:
    w.add_page(p)

# Outline
maps = w.add_outline_item("Map sheets", page_of["sheet_01_overview.pdf"])
w.add_outline_item("Sheet 1 — Province overview (1:100,000)", page_of["sheet_01_overview.pdf"], parent=maps)
for i, lgu in enumerate(sorted(CN_LGUS)):
    key = f"sheet_{i + 2:02d}_{lgu.replace(' ', '_')}.pdf"
    w.add_outline_item(f"Sheet {i + 2} — {lgu}", page_of[key], parent=maps)

# Appendix bookmarks: find each appendix's first page by its kicker text
apx = w.add_outline_item("Appendices", app_start)
titles = {
    "APPENDIX A": "A — Reading this atlas",
    "APPENDIX B": "B — Boundary QA: flagged positions",
    "APPENDIX C": "C — Records without coordinates",
    "APPENDIX D": "D — Survey project index",
    "APPENDIX E": "E — Geodetic control, GNSS, reference systems",
    "APPENDIX F": "F — Gazetteer",
    "APPENDIX G": "G — Sources, contacts, next steps",
}
found = {}
for i, p in enumerate(app.pages):
    txt = (p.extract_text() or "")[:200]
    for k in titles:
        if k in txt and k not in found:
            found[k] = app_start + i
for k, label in titles.items():
    if k in found:
        w.add_outline_item(label, found[k], parent=apx)
missing = [k for k in titles if k not in found]

w.add_metadata({
    "/Title": "Camarines Norte Survey Tie Point Atlas v1.0.0",
    "/Author": "LandTek Mapping Division",
    "/Subject": "1,076 DENR-LMB survey tie points, 12 LGUs. PRS92 / PTM Zone IV with WGS84 graticule. "
                "Reference grade - not a certified monument description.",
    "/Keywords": "Camarines Norte, BLLM, BLBM, PRS92, PTM, tie points, LandTek",
})
w.page_mode = "/UseOutlines"
with open(ATLAS, "wb") as fh:
    w.write(fh)
print(f"{ATLAS}: {len(w.pages)} pages, appendix bookmarks found {len(found)}/7 {missing}", file=sys.stderr)
