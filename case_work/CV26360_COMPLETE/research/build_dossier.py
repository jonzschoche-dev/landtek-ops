"""Assemble the Balane bad-faith dossier: summary (HTML -> PDF via Chrome) + annexes extracted page by page.

Spec: research/annex_spec.json = [
  {"id":"A","title":"...","proves":"...","status":"...",
   "parts":[{"label":"short source name","source":"/abs/path.pdf","pages":[3,5,6]}, ...]}
]
Pages are 1-based source pages. Every annex page is stamped with its annex-internal page number and its
source page, so a citation "Annex K, p. 9" in the summary resolves on the page itself.
Output: BALANE_BAD_FAITH_DOSSIER_2026-10.pdf (8.5 x 13 in).

Run:  python3 research/build_dossier.py
"""
import fitz, json, subprocess, os

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
W, H = 612, 936
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

def clean(s):
    """Base-14 fonts lack a few glyphs; keep the divider text printable."""
    return (s.replace("–", "-").replace("—", "-").replace("₱", "P")
             .replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
             .replace("…", "..."))


spec = json.load(open(os.path.join(BASE, "annex_spec.json")))
for a in spec:
    for key in ("title", "proves", "status"):
        a[key] = clean(a[key])
    for part in a["parts"]:
        part["label"] = clean(part["label"])
html = os.path.join(ROOT, "BALANE_BAD_FAITH_SUMMARY_2026-10.html")
tmp = os.path.join(BASE, "_summary.pdf")
subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                f"--print-to-pdf={tmp}", "file://" + html], check=True, capture_output=True)

out = fitz.open()
summ = fitz.open(tmp)
out.insert_pdf(summ)
toc = [[1, "Itemized summary (Parts 1 to 7)", 1]]
n_summary = summ.page_count


def normalize(src_doc, pg_index):
    """Return a new 8.5x13 page in `out` carrying the source page scaled to fit (rotation honoured)."""
    sp = src_doc[pg_index]
    r = sp.rect
    rot = sp.rotation
    sw, sh = (r.height, r.width) if rot in (90, 270) else (r.width, r.height)
    np_ = out.new_page(width=W, height=H)
    margin_top, margin_bottom = 18, 34
    avail_w, avail_h = W - 24, H - margin_top - margin_bottom
    s = min(avail_w / sw, avail_h / sh)
    tw, th = sw * s, sh * s
    x0 = (W - tw) / 2
    y0 = margin_top + (avail_h - th) / 2
    np_.show_pdf_page(fitz.Rect(x0, y0, x0 + tw, y0 + th), src_doc, pg_index, rotate=0)
    return np_


def textbox(page, rect, text, size, font, color=(0, 0, 0)):
    page.insert_textbox(rect, text, fontsize=size, fontname=font, color=color, align=0)


for a in spec:
    total = sum(len(p["pages"]) for p in a["parts"])
    # divider page
    p = out.new_page(width=W, height=H)
    start = out.page_count
    p.insert_text((54, 120), f"ANNEX {a['id']}", fontsize=28, fontname="tibo")
    p.draw_rect(fitz.Rect(54, 132, W - 54, 136), color=(0, 0, 0), fill=(0, 0, 0))
    y = 160
    for label, key in [("Document", "title"), ("What it shows", "proves"), ("Status and how it comes in", "status")]:
        p.insert_text((54, y), label.upper(), fontsize=8.5, fontname="hebo", color=(.35, .35, .35))
        y += 8
        txt = a[key]
        lines = max(1, int(len(txt) / 88) + 1)
        box_h = min(300, lines * 16 + 14)
        textbox(p, fitz.Rect(54, y, W - 54, y + box_h), txt, 11.5, "tiro")
        y += box_h + 10
    # pages list
    p.insert_text((54, y + 6), "PAGES IN THIS ANNEX", fontsize=8.5, fontname="hebo", color=(.35, .35, .35))
    y += 20
    k = 1
    for part in a["parts"]:
        pr = part["pages"]
        rng = f"{k}" if len(pr) == 1 else f"{k} to {k + len(pr) - 1}"
        line = f"Annex pp. {rng}:  {part['label']}, source pp. {', '.join(str(x) for x in pr)}"
        textbox(p, fitz.Rect(54, y, W - 54, y + 40), line, 10, "tiro")
        y += 30 if len(line) > 95 else 16
        k += len(pr)
    p.insert_text((54, H - 20), f"Annex {a['id']} · divider · Zschoche v. Balane, Civil Case No. 26-360 · prepared for counsel, 13 Oct 2026",
                  fontsize=7, fontname="helv", color=(.4, .4, .4))
    # pages
    k = 1
    for part in a["parts"]:
        src = fitz.open(part["source"])
        for pg in part["pages"]:
            if not (1 <= pg <= src.page_count):
                raise SystemExit(f"Annex {a['id']}: page {pg} out of range for {part['source']} ({src.page_count} pp)")
            np_ = normalize(src, pg - 1)
            # white band + footer stamp
            np_.draw_rect(fitz.Rect(0, H - 30, W, H), color=(1, 1, 1), fill=(1, 1, 1))
            np_.insert_text((54, H - 14), f"ANNEX {a['id']}  ·  p. {k} of {total}  ·  source: {part['label']}, p. {pg}  ·  Zschoche v. Balane, Civil Case No. 26-360  ·  prepared for counsel",
                            fontsize=7.2, fontname="helv", color=(.25, .25, .25))
            k += 1
    toc.append([1, f"Annex {a['id']}: {a['title'][:95]}", start])

out.set_toc(toc)
out.set_metadata({"title": "Zschoche v. Balane, Civil Case No. 26-360: the bad faith of the defendants, itemized summary with annexes",
                  "author": "", "subject": "prepared for counsel, 13 Oct 2026"})
dest = os.path.join(ROOT, "BALANE_BAD_FAITH_DOSSIER_2026-10.pdf")
# the source scans are heavy (the ARTA packets alone are ~60 MB); downsample to 120 dpi JPEG for a mailable file
out.rewrite_images(dpi_threshold=140, dpi_target=120, quality=58, lossy=True, lossless=True)
out.save(dest, garbage=4, deflate=True, deflate_images=True, deflate_fonts=True)
sizes = {(round(pg.rect.width), round(pg.rect.height)) for pg in out}
print("summary pages", n_summary, "| total pages", out.page_count, "| sizes", sizes,
      "|", os.path.getsize(dest) // 1024, "KB ->", dest)
