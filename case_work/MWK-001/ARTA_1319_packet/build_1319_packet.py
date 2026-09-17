#!/usr/bin/env python3
"""Bind the ARTA 1319 record-integrity Manifestation packet: manifestation + Annexes 1-4, 8.5x13."""
import os, sys, io
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "OP_1321_packet"))
from pypdf import PdfReader, PdfWriter
from build_op_packet import normalize, stamp, render_md, S, FOLIO
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.colors import black, Color
from reportlab.lib.units import inch

HERE = os.path.dirname(os.path.abspath(__file__))
MWK = os.path.dirname(HERE)
SRC = os.path.join(HERE, "source")
FOOTER = "Manifestation — ARTA CTN SL-2026-0209-1319 (Zschoche v. Fortuno and Remoto, DENR-PENRO Camarines Norte)"
CART_PAGES = (12, 13)   # 0-based indices into the Resolution PDF (pp. 13-14)

EMAILS = {
    "2": dict(
        title="E-mail printout — as mirrored from the mailbox jonzschoche@gmail.com",
        hdr=[("From", "Litigation Division - ARTA <litigationdivision@arta.gov.ph>"),
             ("To", "Jonathan Zschoche <jonzschoche@gmail.com>"),
             ("Date", "Monday, 29 June 2026, 09:15 AM (Philippine Standard Time) [01:15:04 UTC]"),
             ("Subject", "Re: [NSR] CTN SL-2026-0209-1319 Jonathan Zschoche v PENRO - Camarines Norte"),
             ("Gmail message id", "19f10f1ca4b3b866"),
             ("In reply to", "Complainant's e-mail of 29 June 2026, 08:07 AM PST (Gmail id 19f10b37185a20ef), to litigationdivision@arta.gov.ph, cc penro.camnorte@yahoo.com, penrocamnorte.hotline8888@gmail.com, actioncenter@denr.gov.ph, denrbicol.actioncenter@gmail.com — attachment \"Manifestation Arta 1319 Jun 29, 2026 at 7.56 AM.pdf\" (2,473,377 bytes)")],
        body=["Good day!", "", "This is to acknowledge receipt of this email as well as the attachment. Thank you!", "", "Respectfully,", "",
              "LITIGATION DIVISION", "ANTI-RED TAPE AUTHORITY", "4th Floor, Building I, Ayala Technohub, Diliman, Quezon City 1101", "Tel No.: 1-ARTA (2782) local 1019"],
        quoted=["[Quoted below in the original: Complainant's e-mail of 29 June 2026 —]",
                "\"Confirming receipt. Kindly please include the ATTACHED Manifestation in the case files and forward to the Litigation Officer assigned to this file. Thank you so much. Jonathan\"",
                "[— which in turn quoted the Litigation Division's e-mail of 15 June 2026 transmitting the Notice of Submission for Resolution.]"]),
    "4": dict(
        title="E-mail printout — as mirrored from the mailbox jonzschoche@gmail.com",
        hdr=[("From", "Litigation Division - ARTA <litigationdivision@arta.gov.ph>"),
             ("To", "Jonathan Zschoche <jonzschoche@gmail.com>; DENR-PENRO CAMARINES NORTE <penro.camnorte@yahoo.com>; PENRO CAMARINES NORTE ACTION CENTER & HOTLINE 8888 <penrocamnorte.hotline8888@gmail.com>; DENR Office of the Secretary Atty. Juan Miguel T. Cuna <actioncenter@denr.gov.ph>; DENR Bicol Hotline 8888 <denrbicol.actioncenter@gmail.com>"),
             ("Date", "Monday, 7 September 2026, 04:33 PM (Philippine Standard Time) [08:33:12 UTC]"),
             ("Subject", "[RESOLUTION] CTN SL-2026-0209-1319 Jonathan Zschoche v. Provincial Environment and Natural Resources Office (PENRO) – Camarines Norte"),
             ("Gmail message id", "1a07b007612abff5"),
             ("Attachment", "\"[RESOLUTION] CTN SL-2026-0209-1319 Jonathan Zschoche v Provincial Environment and Natural Resources Office (PENRO) – Camarines Norte.pdf\" (application/pdf, 10,562,662 bytes, 74 pp.)")],
        body=["Greetings from the Anti-Red Tape Authority!", "",
              "Please take notice of the Resolution dated 25 August 2026 in the case of JONATHAN ZSCHOCHE V. PROVINCIAL ENVIRONMENT AND NATURAL RESOURCES OFFICE (PENRO) – CAMARINES NORTE docketed as CTN SL-2026-0209-1319 for violation of R.A. No. 11032.", "",
              "Please see the attached RESOLUTION and its ANNEXES for your reference and perusal.", "", "Respectfully,", "",
              "LITIGATION DIVISION", "ANTI-RED TAPE AUTHORITY", "4th Floor, Building I, Ayala Technohub, Diliman, Quezon City 1101", "Tel No.: 1-ARTA (2782) local 1019"],
        quoted=[]),
}

def esc(x):
    return x.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def email_pdf(spec, out_path):
    doc = SimpleDocTemplate(out_path, pagesize=FOLIO, leftMargin=1.0 * inch, rightMargin=1.0 * inch, topMargin=1.0 * inch, bottomMargin=0.9 * inch)
    mono = ParagraphStyle("m", fontName="TNR", fontSize=10.5, leading=13.5, alignment=TA_LEFT, spaceAfter=2)
    st = [Paragraph(spec["title"], ParagraphStyle("t", fontName="TNR-Italic", fontSize=9.5, leading=12, spaceAfter=10))]
    rows = [[Paragraph(f"<b>{k}</b>", S["cell"]), Paragraph(esc(v), S["cell"])] for k, v in spec["hdr"]]
    t = Table(rows, colWidths=[1.3 * inch, 5.2 * inch])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, black), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (0, -1), Color(0.94, 0.94, 0.94))]))
    st += [t, Spacer(1, 14)]
    for ln in spec["body"]:
        st.append(Paragraph(esc(ln) or "&nbsp;", mono))
    if spec["quoted"]:
        st.append(Spacer(1, 12))
        for ln in spec["quoted"]:
            st.append(Paragraph(esc(ln), ParagraphStyle("q", fontName="TNR-Italic", fontSize=10, leading=13, leftIndent=0.3 * inch, spaceAfter=4)))
    st.append(Spacer(1, 16))
    st.append(Paragraph("Printed from the Complainant's mailbox mirror on 8 September 2026. Original retained in Gmail; headers available on request.", ParagraphStyle("f", fontName="TNR-Italic", fontSize=8.5, leading=11)))
    doc.build(st)
    return out_path

def index_pdf(entries):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=FOLIO, leftMargin=1.0 * inch, rightMargin=1.0 * inch, topMargin=1.0 * inch, bottomMargin=0.9 * inch)
    st = [Paragraph("INDEX OF ANNEXES", S["h1"]),
          Paragraph("Manifestation — ARTA CTN SL-2026-0209-1319<br/>(Zschoche v. Fortuno and Remoto, DENR-PENRO Camarines Norte)",
                    ParagraphStyle("sub", fontName="TNR", fontSize=11, leading=14, alignment=TA_CENTER, spaceAfter=14))]
    rows = [[Paragraph("<b>Annex</b>", S["cell"]), Paragraph("<b>Document</b>", S["cell"]), Paragraph("<b>Pages</b>", S["cell"])]]
    for letter, desc, n in entries:
        rows.append([Paragraph(f'"{letter}"', S["cell"]), Paragraph(desc, S["cell"]), Paragraph(str(n), S["cell"])])
    t = Table(rows, colWidths=[0.7 * inch, 5.2 * inch, 0.7 * inch])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.6, black), ("BACKGROUND", (0, 0), (-1, 0), Color(0.92, 0.92, 0.92)),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    st += [t, Spacer(1, 8), Paragraph("Each annex page carries a boxed ANNEX label at the lower right.", S["body"])]
    doc.build(st); buf.seek(0)
    return buf

def main():
    man_pdf = render_md(os.path.join(HERE, "_manifestation_filing.md"), os.path.join(MWK, "ARTA_1319_MANIFESTATION.pdf"), FOOTER)
    a2 = email_pdf(EMAILS["2"], os.path.join(HERE, "Annex2_email_29jun_ack.pdf"))
    a4 = email_pdf(EMAILS["4"], os.path.join(HERE, "Annex4_email_07sep_transmittal.pdf"))
    res = PdfReader(os.path.join(SRC, "Annex3_src_doc8160_resolution.pdf"))
    annexes = [
        ("1", "Complainant's Manifestation dated 29 June 2026 (\"Narrowing the issues submitted for resolution; reservation of the property and records issues\"), as filed by e-mail with the Litigation Division on 29 June 2026", list(PdfReader(os.path.join(SRC, "Annex1_doc1238_manifestation_29jun.pdf")).pages)),
        ("2", "Litigation Division e-mail of 29 June 2026, 09:15 AM, acknowledging receipt of Complainant's e-mail and its attachment (the Manifestation, Annex \"1\")", list(PdfReader(a2).pages)),
        ("3", "CART Indorsement Form dated 13 February 2026, ARTA Southern Luzon (Annex \"A\" to the Resolution dated 25 August 2026), showing the violations marked as alleged", [res.pages[i] for i in CART_PAGES]),
        ("4", "Litigation Division e-mail of 7 September 2026, 04:33 PM, transmitting the Resolution dated 25 August 2026 and its Annexes (date of notice)", list(PdfReader(a4).pages)),
    ]
    out = PdfWriter()
    n_man = 0
    for pg in PdfReader(man_pdf).pages:
        out.add_page(normalize(pg)); n_man += 1
    entries = [(l, d, len(p)) for l, d, p in annexes]
    for pg in PdfReader(index_pdf(entries)).pages:
        out.add_page(normalize(pg))
    for letter, _, pages in annexes:
        for pg in pages:
            out.add_page(stamp(normalize(pg), letter))
    OUT = os.path.join(MWK, "ARTA_1319_Manifestation_Packet_8.5x13.pdf")
    with open(OUT, "wb") as f:
        out.write(f)
    total = n_man + 1 + sum(e[2] for e in entries)
    print(f"manifestation {n_man} pp · index 1 · " + " · ".join(f'Annex {l}: {n}' for l, _, n in entries) + f" · TOTAL {total} pp → {OUT}")

if __name__ == "__main__":
    main()
