#!/usr/bin/env python3
"""Bind the Oct-2026 Barangay 5 packet, 8.5x13 throughout.
  01  Reply to DENR R5 (ARD Astor, DENR-TS-OSS-2026-1092) + Annexes A-J
  02  Records demand to the Municipal Assessor (Abla), cc Provincial Assessor + Annexes A-E
Outputs one bound PDF per letter (send copies) and a REVIEW copy of the whole packet."""
import io, os, sys
from pypdf import PdfReader, PdfWriter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import Color, black
from reportlab.lib.units import inch

HERE = os.path.dirname(os.path.abspath(__file__))
MWK = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(MWK, "OP_1321_packet"))
from build_op_packet import render_md, normalize, stamp, jpeg_to_pdf_page, S, FOLIO  # noqa: E402

SRC = os.path.join(HERE, "source")
OPS = os.path.join(MWK, "OP_1321_packet", "source")
DIL = os.path.join(MWK, "DILG_enclosures", "source")
DRV = os.path.join(os.path.dirname(os.path.dirname(MWK)), "drive_local",
                   "01 - Clients", "Heirs of Mary Worrick Keesey- LTC-002")
PROP = os.path.join(DRV, "Properties")
LGU = os.path.join(DRV, "Correspondence", "LGU MERCEDES")

FLIP = {"Enc8_SB_Res_1996.pdf": [1]}

DENR_ANNEXES = [
    ("A", "TCT No. T-32911 (certified true copy)", [("pdf", os.path.join(DIL, "Enc7a_TCT32911.pdf"))]),
    ("B", "(LRC) Psd-221861 — LRA electronic certified copy", [("jpeg", os.path.join(SRC, "Psd-221861_LRA.jpg"))]),
    ("C", "(LRC) Psd-12802 (1950), plan of TCT No. 111 — LRA electronic certified copy", [("pdf", os.path.join(PROP, "TCT-111 survey.pdf"))]),
    ("D", "Copy of the alleged deed of donation dated 12 July 1953, as furnished (unsigned; never registered)",
     [("pdf", os.path.join(SRC, "Deed1953_alleged.pdf"))]),
    ("E", "Tax Declarations Nos. 1693 (1950), 1698 and 1699 (1954); Barangay 5 transaction history",
     [("pdf", os.path.join(OPS, "AnnexE_doc561_TD1693.pdf")), ("pdf", os.path.join(PROP, "TCN 1698 Brangay 5.pdf")),
      ("pdf", os.path.join(SRC, "TD1699.pdf")), ("pdf", os.path.join(OPS, "AnnexE_doc115_ledger_brgy5.pdf"))]),
    ("F", "The heirs' current Barangay 5 declarations: ARP Nos. GR-2014-HH-07-005-00056, -00067 and -00088",
     [("pdf", os.path.join(OPS, "AnnexE_doc467_brgy5_arps.pdf")), ("pdf", os.path.join(SRC, "TD_heirs_231.pdf"))]),
    ("G", "Deed of Absolute Donation, 14 April 1980; SB Resolution No. 103-86",
     [("pdf", os.path.join(DIL, "Enc6a_Deed_of_Donation.pdf")), ("pdf", os.path.join(DIL, "Enc6b_Res_103-86.pdf"))]),
    ("H", "SB Resolution No. 76-96 (13 March 1996)", [("pdf", os.path.join(DIL, "Enc8_SB_Res_1996.pdf"))]),
    ("I", "ARP Nos. GR-2014-HH-07-005-00045 and -00236 (Municipality) and -00220 (PNP)",
     [("pdf", os.path.join(OPS, "AnnexE_doc151_munhall_arp.pdf")), ("pdf", os.path.join(SRC, "TD_402A.pdf")),
      ("pdf", os.path.join(LGU, "PNP Tax Dec.pdf"))]),
    ("J", "PENRO Camarines Norte, LMS-25-550, 26 November 2025", [("pdf", os.path.join(DIL, "Enc7b_DENR_LMS25550.pdf"))]),
    ("K", "OCT No. 2018000090 (first page; CTC 6 October 2023)", [("jpeg", os.path.join(SRC, "OCT_2018000090_p1.jpg"))]),
    ("L", "Special Power of Attorney, Patricia Keesey Zschoche (apostilled)", [("pdf", os.path.join(DIL, "Enc9_Apostilled_SPA.pdf"))]),
]

ASSESSOR_ANNEXES = [
    ("A", "Barangay 5 transaction history (TCT 4497) — Office of the Provincial Assessor (Engr. Oscar V. Albos)", [("pdf", os.path.join(OPS, "AnnexE_doc115_ledger_brgy5.pdf"))]),
    ("B", "Tax Declarations Nos. 1693, 1698 and 1699 — as released by the Office of the Provincial Assessor (Engr. Maximo D. Magaña Jr.)",
     [("pdf", os.path.join(OPS, "AnnexE_doc561_TD1693.pdf")), ("pdf", os.path.join(PROP, "TCN 1698 Brangay 5.pdf")),
      ("pdf", os.path.join(SRC, "TD1699.pdf"))]),
    ("C", "The heirs' present declarations: ARP Nos. GR-2014-HH-07-005-00056, -00067 and -00088",
     [("pdf", os.path.join(OPS, "AnnexE_doc467_brgy5_arps.pdf")), ("pdf", os.path.join(SRC, "TD_heirs_231.pdf"))]),
    ("D", "ARP Nos. GR-2014-HH-07-005-00236 (Lot 402-A) and -00220 (Lot 402-B)",
     [("pdf", os.path.join(SRC, "TD_402A.pdf")), ("pdf", os.path.join(LGU, "PNP Tax Dec.pdf"))]),
    ("E", "Special Power of Attorney, Patricia Keesey Zschoche (apostilled)", [("pdf", os.path.join(DIL, "Enc9_Apostilled_SPA.pdf"))]),
]


def annex_pages(annexes):
    out, idx = [], []
    for letter, desc, parts in annexes:
        pages = []
        for kind, src in parts:
            if not os.path.exists(src):
                raise FileNotFoundError(src)
            got = [jpeg_to_pdf_page(src)] if kind == "jpeg" else list(PdfReader(src).pages)
            for pi in FLIP.get(os.path.basename(src), []):  # scans stored upside down
                got[pi].rotate(180)
                got[pi].transfer_rotation_to_content()
            pages += got
        pages = [stamp(normalize(p), letter) for p in pages]
        out.append(pages)
        idx.append((letter, desc, len(pages)))
    return out, idx


def table_page(title, subtitle, rows, widths, note=None):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=FOLIO, leftMargin=1.0 * inch, rightMargin=1.0 * inch,
                            topMargin=1.0 * inch, bottomMargin=0.9 * inch)
    st = [Paragraph(title, S["h1"]),
          Paragraph(subtitle, ParagraphStyle("sub", fontName="TNR", fontSize=11, leading=14, alignment=1, spaceAfter=14))]
    t = Table([[Paragraph(str(c), S["cell"]) for c in r] for r in rows], colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.6, black), ("BACKGROUND", (0, 0), (-1, 0), Color(0.92, 0.92, 0.92)),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    st.append(t)
    if note:
        st += [Spacer(1, 10), Paragraph(note, S["body"])]
    doc.build(st)
    buf.seek(0)
    return list(PdfReader(buf).pages)


# Signed pages scanned back in: {letter md: {page index: (scan file, text that must open that page)}}
SIGNED = {"01_DENR_R5_Reply_Astor.md": {1: ("DENR_letter_p2_SIGNED.pdf", "1954:")}}


# Letters e-signed with Jonathan's signature image (assets/signature/jpz_signature.png), at his direction 2026-10-05
SIG_IMG = os.path.join(os.path.dirname(os.path.dirname(MWK)), "assets", "signature", "jpz_signature.png")
ESIGN = {"02_Assessor_Records_Demand_Abla.md"}


def esign(pdf_path):
    import fitz
    doc = fitz.open(pdf_path)
    for page in doc:
        hits = page.search_for("JONATHAN PAUL ZSCHOCHE")
        resp = page.search_for("Respectfully,")
        if hits and resp:
            name, r = hits[-1], resp[-1]
            h = name.y0 - r.y1 + 6           # fill the gap between "Respectfully," and the name
            w = h * 2383 / 1266              # keep the image's aspect ratio
            box = fitz.Rect(name.x0 - 4, name.y0 - h + 4, name.x0 - 4 + w, name.y0 + 4)
            page.insert_image(box, filename=SIG_IMG, overlay=True)
            tmp = pdf_path + ".tmp"
            doc.save(tmp)
            doc.close()
            os.replace(tmp, pdf_path)
            return True
    raise RuntimeError(f"no signature block found in {pdf_path}")


def bind(md, footer, annexes, subtitle, out_name):
    letter_pdf = render_md(os.path.join(HERE, md), os.path.join(HERE, md.replace(".md", "_letter.pdf")), footer, letter_mode=True)
    if md in ESIGN:
        esign(letter_pdf)
    stamped, idx = annex_pages(annexes)
    rows = [["<b>Annex</b>", "<b>Document</b>", "<b>Pages</b>"]] + [[f'"{a}"', d, n] for a, d, n in idx]
    letter_pages = list(PdfReader(letter_pdf).pages)
    for pi, (scan, opener) in SIGNED.get(md, {}).items():
        typed = (letter_pages[pi].extract_text() or "").lstrip("\u2022\x7f \n")
        assert typed.startswith(opener), f"page {pi + 1} no longer opens with {opener!r}; re-sign before swapping"
        letter_pages[pi] = PdfReader(os.path.join(SRC, scan)).pages[0]
    pages = [normalize(p) for p in letter_pages]
    pages += table_page("INDEX OF ANNEXES", subtitle, rows, [0.7 * inch, 5.2 * inch, 0.7 * inch],
                        "Each annex page carries a boxed ANNEX label at the lower right.")
    for grp in stamped:
        pages += grp
    w = PdfWriter()
    for p in pages:
        w.add_page(p)
    path = os.path.join(HERE, out_name)
    with open(path, "wb") as f:
        w.write(f)
    return path, pages, idx


def main():
    d_path, d_pages, d_idx = bind("01_DENR_R5_Reply_Astor.md",
                                  "Zschoche — Reply to DENR R5, Ref. DENR-TS-OSS-2026-1092",
                                  DENR_ANNEXES, "Reply to DENR Region V — Ref. Code DENR-TS-OSS-2026-1092",
                                  "01_DENR_R5_Reply_Astor_BOUND_8.5x13.pdf")
    a_path, a_pages, a_idx = bind("02_Assessor_Records_Demand_Abla.md",
                                  "Zschoche — Records demand to the Municipal Assessor, Barangay 5",
                                  ASSESSOR_ANNEXES, "Records demand — Municipal Assessor, Mercedes (Barangay 5)",
                                  "02_Assessor_Records_Demand_Abla_BOUND_8.5x13.pdf")
    cover = table_page(
        "BARANGAY 5 PACKET — REVIEW COPY",
        "INTERNAL — NOT SENT. For Jonathan's review. Built " + __import__("datetime").date.today().isoformat(),
        [["<b>Part</b>", "<b>Item</b>", "<b>To</b>", "<b>Pages</b>"],
         ["1", "Reply to ARD Astor, DENR-TS-OSS-2026-1092, with Annexes A–L", "smd.r5@denr.gov.ph; cc legal.r5, PENRO CN", len(d_pages)],
         ["2", "Records demand, Lot 402 declarations, with Annexes A–E", "Mun. Assessor Abla; cc Prov. Assessor Magaña", len(a_pages)]],
        [0.5 * inch, 3.3 * inch, 2.1 * inch, 0.7 * inch],
        "Open before sending: (1) confirm on the ground that the cadastre's 'Barangay Road' east of Lot 402 is "
        "Doña Marciana Moreno Street; (2) Annex B (Psd-221861) is a photograph of the LRA e-copy — replace with a "
        "clean print if available; (3) Annex I is page 1 of 4 of the OCT CTC; (4) date the letters on signing.")
    w = PdfWriter()
    for p in cover + d_pages + a_pages:
        w.add_page(normalize(p))
    rv = os.path.join(HERE, "REVIEW_Barangay5_Packet_2026-10_8.5x13.pdf")
    with open(rv, "wb") as f:
        w.write(f)
    for path, idx in [(d_path, d_idx), (a_path, a_idx)]:
        print(os.path.basename(path), len(PdfReader(path).pages), "pp;", ", ".join(f"{a}:{n}" for a, _, n in idx))
    print(os.path.basename(rv), len(PdfReader(rv).pages), "pp")


if __name__ == "__main__":
    main()
