#!/usr/bin/env python3
"""Assemble the Inocalla civil-registry + identity pack.

Civil-registry entries are CURATED: every one was read off the page image or its
full OCR text and transcribed by hand, so the facts below are verified, not
guessed.  Identity documents are machine-listed from the sweep and marked as
unverified — they are pointers to look at, not transcriptions.
"""
import io, json, os, sys
from collections import defaultdict
from pypdf import PdfReader, PdfWriter
from PIL import Image
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

ROOT = "/Users/jonathanzschoche/landtek/drive_local/01 - Clients/Allan Inocalla - LTC-001/"
HITS, OUTDIR = sys.argv[1], sys.argv[2]
IMG_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}

AGRARIAN = "PGC/Collection Sa Agrarian/"
PHOTOS = "Conversations/Shishir Inocalla/Direct - Shishir Inocalla/photos/"

# person, kind, headline, detail, [(relative path, page), ...]
CURATED = [
 ("Vicente Luna Inocalla Sr.", "Death certificate",
  "LCR Daet, Camarines Norte — Registry No. 84-686",
  "Died 26 November 1984, Provincial Hospital, Daet. Cause: myocardial infarction. "
  "Age 74, married, Filipino; usual residence Batobalani, Paracale. "
  "Informant: Casper Inocalla (son). PSA security-paper copy.",
  [(AGRARIAN + "Scan Mar 21, 2026 at 4.51 PM.pdf", 12)]),

 ("Vicente Luna Inocalla Sr.", "Death record certification (Form 2-A)",
  "LCR Daet — issued 15 January 2015",
  "Certifies the death entry in the Register of Death, Book 10, page 83, "
  "Registry No. 84-686: Vicente S. Inocalla, male, died 26 November 1984 at Daet, "
  "myocardial infarction. Verified by Annie B. Romana, Registrar I.",
  [(AGRARIAN + "Scan Mar 21, 2026 at 4.51 PM.pdf", 24)]),

 ("Beatriz Villafria Inocalla", "Death certificate",
  "LCR Manila — Registry No. 85-16479",
  "Died 12 August 1985 at 2521 G. del Pilar St., Singalong, Manila. "
  "Cause: acute respiratory failure, antecedent cervical CA (metastatic). "
  "Age 70, widowed, Filipino. Informant: Cipriana Cambronero (daughter). "
  "PSA security-paper copy.",
  [(AGRARIAN + "Scan Mar 21, 2026 at 5.02 PM.pdf", 6)]),

 ("Senen Villafria Inocalla", "Death certificate",
  "LCR Paracale, Camarines Norte — Registry No. 2021-51",
  "Died 26 February 2021, 5:17 PM, Purok 1, Batobalani, Paracale. Cause: irreversible "
  "hypovolemic shock, antecedent massive internal and external hemorrhage, underlying "
  "multiple gunshot wound. Born 30 June 1958, age 62, single. Autopsy: YES. "
  "Certified by Bill Wilfredo V. Peralta, MD (RHU Paracale); registered 1 March 2021. "
  "NOTE: the NBI report puts the shooting on 12 February 2021 — the 14-day gap is unresolved.",
  [(PHOTOS + "1751749899573543.jpg", 1)]),

 ("Senen Villafria Inocalla", "Birth record certification (Form 1-A)",
  "LCR Paracale — issued 2 July 2018, Registry No. 340",
  "Register of Births Book 6, page 90; registered 12 July 1958. Senen Villafria Inocalla, "
  "female, born 30 June 1958 at Paracale. Mother Beatriz D. Villafria, father Vicente L. "
  "Inocalla, both Filipino. Remarks: legitimate.",
  [(AGRARIAN + "Scan Mar 21, 2026 at 4.51 PM.pdf", 13)]),

 ("Vicente Villafria Inocalla Jr.", "Death certificate",
  "LCR Jose Panganiban, Camarines Norte — Registry No. 2017-191",
  "Died 11 September 2017, 12:05 PM, P-5 Brgy. Sta. Rosa Sur, Jose Panganiban. "
  "Cause: neurogenic shock, antecedent multiple gunshot wound. Born 22 May 1953, age 64, "
  "widower. Informant: Elena D. Inocalla (daughter); registered 15 September 2017.",
  [(PHOTOS + "1591716549043497.jpg", 1),
   ("PGC/SPA /Vicente Jr. Murder.pdf", 10)]),

 ("Casper Villafria Inocalla", "Death certificate",
  "LCR Quezon City, Metro Manila — Registry No. 2019-01918",
  "Died 21 January 2019. Born 26 November 1937, age 81, married, Hindu, Filipino; "
  "residence Diliman, Quezon City. Father Vicente L. Inocalla, mother Beatriz Dasco "
  "Villafria. Cremation, Zen Gardens Crematory. Registered 23 January 2019. "
  "PSA security-paper copy.",
  [(AGRARIAN + "Scan Mar 21, 2026 at 4.51 PM.pdf", 42)]),

 ("Francisco Villafria Inocalla", "Death registration extract (Canada)",
  "BC Vital Statistics Agency, Victoria — Registration No. 2002-59-014497",
  "Died 2 July 2002 at Surrey, British Columbia. Age 66, male, birthplace Philippines, "
  "residence Surrey BC. Issued 23 December 2013 to Allan Inocalla.",
  [(AGRARIAN + "Scan Mar 21, 2026 at 4.51 PM.pdf", 23)]),

 ("Jesus Villafria Inocalla", "Birth record certification (Form 1-A)",
  "LCR Paracale — issued 2 July 2018, Registry No. 963",
  "Register of Births Book 6, page 58; registered 15 May 1957. Jesus Inocalla, male, "
  "born 13 May 1957 at Batobalani, Paracale. Mother Beatriz D. Villafria, father "
  "Vicente L. Inocalla. Remarks: legitimate.",
  [(AGRARIAN + "Scan Mar 21, 2026 at 4.51 PM.pdf", 14)]),

 ("Allan Villafria Inocalla", "Birth record certification (Form 1-A)",
  "LCR Paracale — issued 9 December 2020, Registry No. 350",
  "Register of Births Book 5, page 87; registered 19 January 1955. Allan V. Inocalla, "
  "male, born 12 January 1955 at Batobalani, Paracale. Mother Beatriz Dasco, father "
  "Vicente L. Inocalla. Remarks: legitimate. Issued to OCRG, PSA, Quezon City.",
  [(AGRARIAN + "Scan Mar 21, 2026 at 4.51 PM.pdf", 27)]),

 ("Allan Villafria Inocalla", "LCR endorsement to PSA",
  "LCR Paracale — 9 December 2020",
  "Forwards Allan's Form 1-A (born 12 January 1955) to the Civil Registrar General, PSA "
  "Quezon City, for records and authentication — i.e. the fix for the PSA negative below.",
  [(AGRARIAN + "Scan Mar 21, 2026 at 4.51 PM.pdf", 29)]),

 ("Allan Villafria Inocalla", "Certificate of Live Birth (form)",
  "Municipal form, page 1 of 1",
  "Certificate of Live Birth naming Allan Inocalla; residence 2531 G. del Pilar St., "
  "Vito Cruz, Malate, Manila; citizenship Canadian. Reads as a late/delayed registration "
  "filing rather than an original 1955 entry — confirm against the LCR book before use.",
  [(AGRARIAN + "Scan Mar 21, 2026 at 4.51 PM.pdf", 32)]),
]

NEGATIVES = [
 ("Allan Villafria Inocalla", "PSA NEGATIVE certification of birth", "2 December 2020",
  "PSA holds NO record of birth for Allan Villafria Inocalla, date of birth given as "
  "1 December 1955, Paracale. ⚠ The LCR Form 1-A above gives 12 January 1955 — the two "
  "dates do not agree; the negative may simply have been searched on the wrong date.",
  [(AGRARIAN + "Scan Mar 21, 2026 at 4.51 PM.pdf", 28)]),
 ("Casper Villafria Inocalla", "PSA NEGATIVE certification of birth", "28 September 2018",
  "PSA holds NO record of birth for Casper Villafria Inocalla, b. 26 November 1937, "
  "Paracale. Requested by Senen V. Inocalla. Remedy: LCR Paracale endorsement, or "
  "delayed registration.",
  [(AGRARIAN + "Scan Mar 21, 2026 at 4.51 PM.pdf", 50)]),
 ("Marilou Villafria Inocalla", "PSA NEGATIVE certification of birth", "16 July 2018",
  "PSA holds NO record of birth for Marilou Villafria Inocalla, b. 6 February 1949, "
  "Labo, Camarines Norte. A delayed-registration worksheet naming Senen V. Inocalla as "
  "informant (sibling) is filed with it.",
  [(AGRARIAN + "Scan Mar 21, 2026 at 4.50 PM.pdf", 3),
   (AGRARIAN + "Scan Mar 21, 2026 at 4.50 PM.pdf", 1)]),
 ("Francisco Villafria Inocalla", "NSO NEGATIVE certification of death", "19 December 2013",
  "NSO holds NO Philippine record of death for Francisco V. Inocalla, d. 2 July 2002 in "
  "Canada. Requested by Senen Inocalla \"for Court Award\". The BC extract above is the "
  "record; report of death via DFA/consulate would put it on the PH register.",
  [(AGRARIAN + "Scan Mar 21, 2026 at 4.51 PM.pdf", 37)]),
]

MISSING = [
 ("Beatriz Villafria Inocalla", "Birth certificate", "b. 29 February 1916 (per Marilou's "
  "delayed-registration worksheet). No record found in any source."),
 ("Vicente Luna Inocalla Sr.", "Birth certificate", "b. 5 April 1905 (per the same "
  "worksheet). No record found in any source."),
 ("Vicente Villafria Inocalla Jr.", "Birth certificate", "A 1953 certificate of birth "
  "appears in the NBI murder file (NBI Report Inocalla Murders.pdf p.40) but is too "
  "degraded to transcribe — pull a fresh PSA copy."),
 ("Cipriana, Herbert, Melvin, Robert", "Birth and death records",
  "Nothing located. Not yet requested, as far as the files show."),
 ("Whole family", "Marriage certificates",
  "None found — including Vicente Sr. × Beatriz, whose Form 1-A entries record "
  "\"N/A\" for date and place of marriage of parents."),
]

# ---------- machine-listed identity documents ----------
ID_LABEL = {"ID_PASSPORT": "Passport", "ID_DRIVER": "Driver's licence",
            "ID_UMID": "UMID", "ID_PHILHEALTH": "PhilHealth",
            "ID_OTHER": "Other government ID"}
CIVIL = {"BIRTH_CERT", "DEATH_CERT", "MARRIAGE_CERT"}
# the LandBank CARP letters list a birth certificate as a REQUIREMENT; not a record
SKIP = {("Scan Mar 21, 2026 at 5.02 PM.pdf", 8), ("Scan Mar 21, 2026 at 5.02 PM.pdf", 10)}

ids = []
for line in open(HITS):
    r = json.loads(line)
    if (os.path.basename(r["file"]), r["page"]) in SKIP:
        continue
    idt = [t for t in r["types"] if t not in CIVIL]
    if not idt:
        continue
    ids.append((r["file"], r["page"], idt, r["names"]))
ids.sort(key=lambda x: (x[0], x[1]))


def rel(p):
    return p[len(ROOT):] if p.startswith(ROOT) else p


# ---------- markdown index ----------
L = ["# Inocalla family — civil registry & identity documents", "",
     "Every birth, death and identity record found across the LTC-001 (Allan Inocalla)",
     "Drive tree — 1,237 files, 2,697 pages, read page by page with OCR.", "",
     "Paths are relative to `drive_local/01 - Clients/Allan Inocalla - LTC-001/`.",
     "The bound PDF `INOCALLA_CIVIL_REGISTRY.pdf` carries these same pages in this order.", "",
     "---", "", "## 1. Civil registry records held (verified)", "",
     "Each entry below was read off the page image or its full text and transcribed by hand.", ""]
cur = defaultdict(list)
for person, kind, head, detail, srcs in CURATED:
    cur[person].append((kind, head, detail, srcs))
for person in cur:
    L += [f"### {person}", ""]
    for kind, head, detail, srcs in cur[person]:
        L.append(f"**{kind}** — {head}")
        L.append("")
        L.append(detail)
        L.append("")
        for f, pg in srcs:
            L.append(f"- `{f}` p.{pg}")
        L.append("")

L += ["---", "", "## 2. Negative certifications — the record does NOT exist", "",
      "These prove absence. Never cite one as the certificate itself.", ""]
for person, kind, date, detail, srcs in NEGATIVES:
    L += [f"**{person} — {kind}, {date}**", "", detail, ""]
    for f, pg in srcs:
        L.append(f"- `{f}` p.{pg}")
    L.append("")

L += ["---", "", "## 3. Still missing — nothing in any source", ""]
for person, kind, note in MISSING:
    L.append(f"- **{person} — {kind}.** {note}")
L.append("")

L += ["---", "", "## 4. Identity documents (machine-detected, unverified)", "",
      "Pages that read as a passport, licence or government ID and carry the Inocalla",
      "surname. Names are OCR guesses — open the page before relying on any of them.", ""]
for f, pg, idt, names in ids:
    labels = ", ".join(ID_LABEL.get(t, t) for t in idt)
    who = ", ".join(names) if names else "unidentified"
    L.append(f"- {labels} — `{rel(f)}` p.{pg} · names on page: {who}")
L += ["", "---", "",
      "## How this was built", "",
      "`pdftotext` for the text layer, `tesseract` OCR at 150 dpi for every page without one,",
      "then a keyword classifier over the result. The cached page text lives beside this file",
      "and can be re-classified without re-OCR.", "",
      "**Why the database missed these:** the loose Messenger photos — including Senen's death",
      "certificate — were never OCR'd into the corpus, so no amount of database searching would",
      "have found them. Google Drive's own search box does OCR them, and finds them in seconds.", ""]

os.makedirs(OUTDIR, exist_ok=True)
open(os.path.join(OUTDIR, "INOCALLA_CIVIL_REGISTRY_INDEX.md"), "w").write("\n".join(L))

# ---------- bound PDF ----------
order = []
for person, kind, head, detail, srcs in CURATED:
    order.append((person, kind, head, srcs[0]))
for person, kind, date, detail, srcs in NEGATIVES:
    order.append((person, f"{kind} ({date})", "PSA/NSO says NO record exists", srcs[0]))
for f, pg, idt, names in ids:
    order.append((", ".join(names) if names else "unidentified",
                  ", ".join(ID_LABEL.get(t, t) for t in idt), "", (rel(f), pg)))

writer = PdfWriter()
buf = io.BytesIO()
c = canvas.Canvas(buf, pagesize=LETTER)
W, H = LETTER
y = H - 0.9 * inch
c.setFont("Helvetica-Bold", 15)
c.drawString(0.9 * inch, y, "Inocalla — civil registry & identity documents")
y -= 0.28 * inch
c.setFont("Helvetica", 8.5)
for s in ["Assembled from the LTC-001 Drive tree: 1,237 files, 2,697 pages read by OCR.",
          "Sections 1-2 are hand-verified transcriptions. Identity pages are machine-detected and unverified.",
          "Negative certifications prove a record is MISSING - never cite one as the record."]:
    c.drawString(0.9 * inch, y, s)
    y -= 0.17 * inch
y -= 0.12 * inch
n = 0
last = None
for person, kind, head, (f, pg) in order:
    n += 1
    if y < 0.9 * inch:
        c.showPage(); y = H - 0.9 * inch
        last = None
    if person != last:
        y -= 0.10 * inch
        c.setFont("Helvetica-Bold", 9.5)
        c.drawString(0.9 * inch, y, person)
        y -= 0.17 * inch
        last = person
    c.setFont("Helvetica", 7.5)
    c.drawString(1.05 * inch, y, f"{n:>3}.  {kind}"[:105])
    y -= 0.13 * inch
    if head:
        c.setFont("Helvetica-Oblique", 7)
        c.drawString(1.35 * inch, y, head[:100])
        y -= 0.15 * inch
c.showPage(); c.save(); buf.seek(0)
for p in PdfReader(buf).pages:
    writer.add_page(p)

skipped = []
for person, kind, head, (f, pg) in order:
    path = f if os.path.isabs(f) else ROOT + f
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".pdf":
            writer.add_page(PdfReader(path).pages[pg - 1])
        elif ext in IMG_EXT:
            im = Image.open(path).convert("RGB")
            b = io.BytesIO(); im.save(b, "PDF", resolution=150); b.seek(0)
            writer.add_page(PdfReader(b).pages[0])
    except Exception as e:
        skipped.append((f, pg, str(e)))

with open(os.path.join(OUTDIR, "INOCALLA_CIVIL_REGISTRY.pdf"), "wb") as fh:
    writer.write(fh)
print(f"entries: {len(order)}   pdf pages: {len(writer.pages)}   skipped: {len(skipped)}")
for s in skipped:
    print("  SKIP", s)
