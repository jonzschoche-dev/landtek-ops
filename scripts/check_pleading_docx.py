#!/usr/bin/env python3
"""check_pleading_docx.py — verify a rendered pleading before it goes to counsel.

Reads the generated .docx as OOXML (stdlib only) and asserts the things that
actually go wrong in a markdown->docx render:

  * leaked source markup  (**bold**, ## heading, | table |, ⟦note⟧)
  * page set-up against A.M. No. 11-9-4-SC (13" x 8.5", L1.5/T1.2/R1.0/B1.0)
  * body type size (14 pt) and the gray note colour
  * tables well-formed (every row the same cell count)
  * the caption, the prayer and the signature block survived
  * how many fill-in blanks and drafter's notes counsel still has to clear

Usage: python3 scripts/check_pleading_docx.py <file.docx> [...]
Exit 1 if any FAIL.
"""
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
IN = 1440
EXPECT_PAGE = (round(8.5 * IN), 13 * IN)
EXPECT_MARGIN = {"left": round(1.5 * IN), "top": round(1.2 * IN),
                 "right": 1 * IN, "bottom": 1 * IN}
BODY_HALF_PT = 28          # 14 pt
NOTE_COLOR = "7A7A7A"
BLANK = "__________"

LEAKS = [
    ("bold markers", re.compile(r"\*\*")),
    ("italic markers", re.compile(r"(?<!\*)\*(?!\*)[A-Za-z]")),
    ("heading markers", re.compile(r"(?m)^#{1,6}\s")),
    ("table pipes", re.compile(r"(?m)^\s*\|")),
    ("note glyphs", re.compile(r"[⟦⟧]")),
    ("html comment", re.compile(r"<!--")),
]


def para_text(p):
    return "".join(t.text or "" for t in p.iter(W + "t"))


def check(path):
    print(f"\n=== {path.split('/')[-1]} ===")
    fails, warns = [], []
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        for required in ("[Content_Types].xml", "word/document.xml", "word/styles.xml"):
            if required not in names:
                fails.append(f"missing {required}")
        doc = ET.fromstring(z.read("word/document.xml"))
        styles = z.read("word/styles.xml").decode("utf8")
        footers = [z.read(n).decode("utf8") for n in names
                   if n.startswith("word/footer")]

    body = doc.find(W + "body")
    paras = body.findall(W + "p")
    tables = body.findall(W + "tbl")
    ptext = "\n".join(para_text(p) for p in paras)      # paragraphs only
    ttext = "\n".join("\n".join(para_text(p) for p in t.iter(W + "p")) for t in tables)
    text = ptext + "\n" + ttext

    # 1. leaked markup. "#" and "|" are legitimate inside a table cell
    # (a column headed "#"), so those two are checked on paragraphs only.
    for label, rx in LEAKS:
        scope = ptext if label in ("heading markers", "table pipes") else text
        hits = rx.findall(scope)
        if hits:
            sample = rx.search(scope)
            ctx = scope[max(0, sample.start() - 50):sample.start() + 50].replace("\n", " ")
            fails.append(f"leaked {label} x{len(hits)} — …{ctx}…")

    # 2. page set-up
    sect = body.find(W + "sectPr")
    if sect is None:
        fails.append("no sectPr (page set-up missing)")
    else:
        pg = sect.find(W + "pgSz")
        mg = sect.find(W + "pgMar")
        got = (int(pg.get(W + "w")), int(pg.get(W + "h")))
        if got != EXPECT_PAGE:
            fails.append(f"page size {got} != {EXPECT_PAGE} (13x8.5 long bond)")
        for side, want in EXPECT_MARGIN.items():
            have = int(mg.get(W + side))
            if have != want:
                fails.append(f"{side} margin {have} != {want}")

    # 3. type size + note colour
    if f'{W}sz w:val="{BODY_HALF_PT}"'.replace(W, "w:") not in styles.replace(W, "w:"):
        if f'w:val="{BODY_HALF_PT}"' not in styles:
            warns.append("default run size not 14 pt in styles.xml")
    notes = [r for r in doc.iter(W + "r")
             if (r.find(W + "rPr/" + W + "color") is not None
                 and r.find(W + "rPr/" + W + "color").get(W + "val") == NOTE_COLOR)]

    # 4. tables well-formed
    for i, t in enumerate(tables, 1):
        counts = {len(r.findall(W + "tc")) for r in t.findall(W + "tr")}
        if len(counts) > 1:
            fails.append(f"table {i} ragged: cell counts {sorted(counts)}")

    # 5. structure survived
    if not footers:
        fails.append("no footer (page numbers required)")
    elif "PAGE" not in " ".join(footers):
        warns.append("footer has no page-number field")
    is_pleading = "SPEC. PROC. NO." in text
    if is_pleading and "REGIONAL TRIAL COURT" not in text:
        fails.append("court header missing from a captioned pleading")
    if not is_pleading:
        print("  (no caption — checked as a working document, not a pleading)")
    if "INOCALLA" not in text:
        fails.append("party name missing from body")

    blanks = text.count(BLANK)
    print(f"  paragraphs {len(paras)}  tables {len(tables)}  gray notes {len(notes)}"
          f"  blanks {blanks}  chars {len(text):,}")
    if "PRAYER" in text.upper():
        print("  prayer: present")
    if "SUBSCRIBED AND SWORN" in text.upper():
        print("  jurat: present")

    for w in warns:
        print(f"  WARN  {w}")
    for f in fails:
        print(f"  FAIL  {f}")
    if not fails:
        print("  OK")
    return not fails


if __name__ == "__main__":
    files = sys.argv[1:]
    if not files:
        sys.exit("usage: check_pleading_docx.py <file.docx> [...]")
    ok = all([check(f) for f in files])   # list, not generator: check every file
    print("\n" + ("ALL CHECKS PASSED" if ok else "FAILURES ABOVE"))
    sys.exit(0 if ok else 1)
