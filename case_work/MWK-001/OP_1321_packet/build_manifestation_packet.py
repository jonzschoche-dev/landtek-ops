#!/usr/bin/env python3
"""Bind the ARTA 1321 Manifestation service packet: manifestation + Annexes 1-5, 8.5x13."""
import os
from pypdf import PdfReader, PdfWriter
from build_op_packet import normalize, stamp, jpeg_to_pdf_page, index_page, render_md, S
from reportlab.platypus import Paragraph

HERE = os.path.dirname(os.path.abspath(__file__))
MWK = os.path.dirname(HERE)
SRC = os.path.join(HERE, "source")

ANNEXES = [
    ("1", "Respondent's letter of 16 June 2025 (undertaking the 1948-book history; \"cannot possibly be done in just 15 working days\")",
     [("jpeg", os.path.join(SRC, "AnnexC_doc895_16jun_letter.jpeg"))]),
    ("2", "Specimen productions of the Provincial Assessor's Office: TD No. 1693 (Provincial Form 140); Brgy 5 and Brgy 1 transaction-history ledgers; representative computerized Declarations of Real Property (Brgys 1, 3, 5)",
     [("pdf", os.path.join(SRC, "AnnexE_doc561_TD1693.pdf")),
      ("pdf", os.path.join(SRC, "AnnexE_doc115_ledger_brgy5.pdf")),
      ("pdf", os.path.join(SRC, "AnnexE_doc116_ledger_brgy1.pdf")),
      ("pdf", os.path.join(SRC, "AnnexE_doc467_brgy5_arps.pdf")),
      ("pdf", os.path.join(SRC, "AnnexE_doc151_munhall_arp.pdf")),
      ("pdf", os.path.join(SRC, "AnnexE_doc105.pdf"))]),
    ("3", "Comparator Exhibit — the Respondent's positions vs. the Provincial Assessor's actual productions (timeline; verbatim quotes)",
     [("pdf", os.path.join(HERE, "AnnexB_comparator.pdf"))]),
    ("4", "Complainant's email to the Respondent, 1 October 2025 (records obtained from the Provincial Assessor's Office, predecessor Albos)",
     [("pdf", os.path.join(HERE, "AnnexD_email.pdf"))]),
    ("5", "Respondent's Counter-Affidavit, sworn 28 May 2026",
     [("pdf", os.path.join(SRC, "AnnexF_doc1046_counter_affidavit.pdf"))]),
]

# stamp + count
stamped, entries = [], []
for letter, desc, parts in ANNEXES:
    pages = []
    for kind, src in parts:
        if kind == "pdf":
            pages += list(PdfReader(src).pages)
        else:
            pages.append(jpeg_to_pdf_page(src))
    pages = [stamp(normalize(p), letter) for p in pages]
    stamped.append(pages)
    entries.append((letter, desc, len(pages)))

out = PdfWriter()
for pg in PdfReader(os.path.join(MWK, "ARTA_1321_MANIFESTATION.pdf")).pages:
    out.add_page(normalize(pg))

# index page (reuse index_page but retitle via simple wrapper: rebuild with custom title)
import io
from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.colors import black, Color
from reportlab.lib.units import inch

FOLIO = (8.5 * 72, 13.0 * 72)
buf = io.BytesIO()
doc = SimpleDocTemplate(buf, pagesize=FOLIO, leftMargin=1.0 * inch, rightMargin=1.0 * inch,
                        topMargin=1.0 * inch, bottomMargin=0.9 * inch)
st = [Paragraph("INDEX OF ANNEXES", S["h1"]),
      Paragraph("Manifestation — ARTA CTN SL-2026-0209-1321<br/>(Zschoche v. Abla, Municipal Assessor, Mercedes, Camarines Norte)",
                ParagraphStyle("sub", fontName="TNR", fontSize=11, leading=14, alignment=TA_CENTER, spaceAfter=14))]
rows = [[Paragraph("<b>Annex</b>", S["cell"]), Paragraph("<b>Document</b>", S["cell"]), Paragraph("<b>Pages</b>", S["cell"])]]
for letter, desc, pages in entries:
    rows.append([Paragraph(f'"{letter}"', S["cell"]), Paragraph(desc, S["cell"]), Paragraph(str(pages), S["cell"])])
t = Table(rows, colWidths=[0.7 * inch, 5.2 * inch, 0.7 * inch])
t.setStyle(TableStyle([
    ("GRID", (0, 0), (-1, -1), 0.6, black),
    ("BACKGROUND", (0, 0), (-1, 0), Color(0.92, 0.92, 0.92)),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
st.append(t)
st.append(Spacer(1, 8))
st.append(Paragraph("Each annex page carries a boxed ANNEX label at the lower right.", S["body"]))
doc.build(st)
buf.seek(0)
for pg in PdfReader(buf).pages:
    out.add_page(normalize(pg))

for pages in stamped:
    for pg in pages:
        out.add_page(pg)

OUT = os.path.join(MWK, "ARTA_1321_Manifestation_Packet_8.5x13.pdf")
with open(OUT, "wb") as f:
    out.write(f)
r = PdfReader(OUT)
sizes = {(round(float(p.mediabox.width)), round(float(p.mediabox.height))) for p in r.pages}
print("BOUND:", OUT, len(r.pages), "pp, sizes:", sizes)
for e in entries:
    print("  Annex", e[0], "-", e[2], "pp")
