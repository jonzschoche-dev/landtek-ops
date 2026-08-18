#!/usr/bin/env python3
"""Build the bound enclosure set for the 18 Aug 2026 DILG supervision letter.

source/ -> stamped/ -> DILG_Enclosures_1-9_bound_8.5x13.pdf
Enclosure 1 (ARTA Referral Tally) is generated here; 9 is a physical-insert divider.
"""
import io, os
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color, black
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_CENTER

HERE = os.path.dirname(os.path.abspath(__file__))
SRC, STAMPED = os.path.join(HERE, "source"), os.path.join(HERE, "stamped")
FOLIO = (8.5 * 72, 13.0 * 72)

F = "/System/Library/Fonts/Supplemental"
pdfmetrics.registerFont(TTFont("TNR", f"{F}/Times New Roman.ttf"))
pdfmetrics.registerFont(TTFont("TNR-Bold", f"{F}/Times New Roman Bold.ttf"))
pdfmetrics.registerFont(TTFont("TNR-Italic", f"{F}/Times New Roman Italic.ttf"))
pdfmetrics.registerFontFamily("TNR", normal="TNR", bold="TNR-Bold", italic="TNR-Italic",
                              boldItalic="TNR-Bold")

ENCLOSURES = [
    ("1", "ARTA Referral Tally — the onward referrals in the ARTA dispositive portions, quoted verbatim", ["_GEN_TALLY"]),
    ("2", "CSC OAC-L Letter No. 270, s. 2026 (23 June 2026) — CSC referral of CTN SL-2026-0423-1891 to the Office of the Ombudsman", ["Enc2_OACL270.pdf"]),
    ("3", "ARTA Notices of Referral / Endorsements: (a) 0690/0792 Endorsement to CSC-RO V with Resolution of 07 April 2026; (b) 1212 Endorsement to the Ombudsman; (c) 1891 Notice of Referral to CSC; (d) 1891 Notice of Referral to DILG", ["Enc3a_trimmed.pdf", "Enc3b_1212_Endorsement_Ombudsman.pdf", "Enc3c_1891_NOR_CSC.pdf", "Enc3d_1891_NOR_DILG.pdf"]),
    ("4", "ARTA Response to Manifestation (21 May 2026) and Formal Response (21 July 2026) — 'more properly addressed to … the appropriate supervisory authority'", ["Enc4_ARTA_Responses.pdf"]),
    ("5", "Records-request chain to the Secretary of the Sangguniang Bayan (11 Feb – 8 Jul 2026) with the SB Secretary's response of 5 March 2026", ["Enc5_Records_Chain_SB_Refusal.pdf"]),
    ("6", "Deed of Absolute Donation (14 April 1979; acceptance per Res. No. 75-79) and SB Resolution No. 103-86", ["Enc6a_Deed_of_Donation.pdf", "Enc6b_Res_103-86.pdf"]),
    ("7", "TCT No. T-32911 (Heirs of Mary Worrick Keesey) and DENR letter LMS-25-550 (26 Nov 2025) — records projection: Lot 2-A, (LRA) Psd-221861 encompasses Lots 401, 403, 405, Cad. 118-D", ["Enc7a_TCT32911.pdf", "Enc7b_DENR_LMS25550.pdf"]),
    ("8", "Sangguniang Bayan Resolution of 13 March 1996 (ad-hoc committee on the 'proposed legal acquisition' of the estate parcel)", ["Enc8_SB_Res_1996.pdf"]),
    ("9", "Apostilled Special Power of Attorney, Patricia K. Zschoche → Jonathan Zschoche (executed 12 Feb 2025; California Apostille No. 61887, 13 Mar 2025; with copy certifications)", ["Enc9_Apostilled_SPA.pdf"]),
]

S = {
    "h1": ParagraphStyle("h1", fontName="TNR-Bold", fontSize=15, leading=19, alignment=TA_CENTER, spaceAfter=4),
    "h2": ParagraphStyle("h2", fontName="TNR", fontSize=11, leading=14, alignment=TA_CENTER, spaceAfter=14),
    "sec": ParagraphStyle("sec", fontName="TNR-Bold", fontSize=12, leading=15, spaceBefore=10, spaceAfter=4),
    "body": ParagraphStyle("body", fontName="TNR", fontSize=10.5, leading=13.6, alignment=TA_JUSTIFY, spaceAfter=6),
    "q": ParagraphStyle("q", fontName="TNR", fontSize=10, leading=13, leftIndent=0.35 * inch,
                        rightIndent=0.2 * inch, alignment=TA_JUSTIFY, spaceAfter=6),
    "cell": ParagraphStyle("cell", fontName="TNR", fontSize=9, leading=11.5),
    "cellb": ParagraphStyle("cellb", fontName="TNR-Bold", fontSize=9, leading=11.5),
}


def build_tally():
    out = os.path.join(SRC, "Enc1_Referral_Tally.pdf")
    doc = SimpleDocTemplate(out, pagesize=FOLIO, leftMargin=0.9 * inch, rightMargin=0.9 * inch,
                            topMargin=0.9 * inch, bottomMargin=0.9 * inch)
    st = []
    st.append(Paragraph("ARTA REFERRAL TALLY", S["h1"]))
    st.append(Paragraph("Onward referrals contained in the dispositive portions of the ARTA dispositions<br/>concerning officials of the Municipality of Mercedes, Camarines Norte — quoted verbatim", S["h2"]))

    rows = [[Paragraph("<b>#</b>", S["cellb"]), Paragraph("<b>From → To</b>", S["cellb"]), Paragraph("<b>Docket</b>", S["cellb"]),
             Paragraph("<b>Official(s) referred</b>", S["cellb"]), Paragraph("<b>Alleged law</b>", S["cellb"])]]
    data = [
        ("1", "ARTA → CSC-RO V", "CTN SL-2025-1008-0690", "Engr. Erwin H. Balane (Municipal Engineer)", "R.A. 6713 §5(a)"),
        ("2", "ARTA → CSC-RO V", "CTN SL-2025-1104-0792", "Engr. Erwin H. Balane (Municipal Engineer)", "R.A. 6713 §5(a)"),
        ("3", "ARTA → Ombudsman", "CTN SL-2026-0128-1212", "Hon. Princess B. Torralba (Councilor)", "R.A. 6713"),
        ("4", "ARTA → Ombudsman", "CTN SL-2026-0128-1212", "Mr. Tony Teope (Assistant to the Municipal Mayor)", "R.A. 3019 §3(i)"),
        ("5", "ARTA → CSC", "CTN SL-2026-0423-1891", "The Committee on Anti-Red Tape (CART), Mayor Alexander Pajarillo as Chairperson", "R.A. 6713"),
        ("6", "ARTA → DILG", "CTN SL-2026-0423-1891", "The Committee on Anti-Red Tape (CART) — the LGU's R.A. 11032 compliance body", "R.A. 11032 §17(d)"),
        ("7", "CSC → Ombudsman", "CTN SL-2026-0423-1891", "Hon. Alexander Pajarillo (Municipal Mayor / CART Chairperson) and the CART members", "R.A. 6713"),
    ]
    for r in data:
        rows.append([Paragraph(r[0], S["cell"]), Paragraph(r[1], S["cell"]), Paragraph(r[2], S["cell"]),
                     Paragraph(r[3], S["cell"]), Paragraph(r[4], S["cell"])])
    t = Table(rows, colWidths=[0.32 * inch, 1.35 * inch, 1.55 * inch, 2.55 * inch, 0.93 * inch])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.6, black),
        ("BACKGROUND", (0, 0), (-1, 0), Color(0.92, 0.92, 0.92)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    st.append(t)
    st.append(Spacer(1, 10))

    st.append(Paragraph("A. CTN SL-2025-1008-0690 and SL-2025-1104-0792 — Resolution dated 07 April 2026 (Enclosure 3(a)), dispositive portion:", S["sec"]))
    st.append(Paragraph('"RECOMMENDATIONS — In view of the foregoing, ARTA recommends the following: 1. CLOSURE of this complaint against ENGR. ERWIN H. BALANE … there being no prima facie evidence of a violation of Section 21(a), (b), (d), and (e) of R.A. No. 11032; and 2. REFERRAL of this case to the CIVIL SERVICE COMMISSION – REGIONAL OFFICE V for its appropriate action against ENGR. ERWIN H. BALANE … on the alleged violation of Section 5(a) of R.A. No. 6713."', S["q"]))
    st.append(Paragraph("B. CTN SL-2026-0128-1212 — Resolution dated 01 June 2026, dispositive portion, and Endorsement to the Ombudsman (Enclosure 3(b)):", S["sec"]))
    st.append(Paragraph('"… 2. REFERRAL of this case to the OFFICE OF THE OMBUDSMAN for its appropriate action against HON. PRINCESS B. TORRALBA, in her capacity as the Councilor … for the alleged violation of R.A. 6713; and 3. REFERRAL of this case to the OFFICE OF THE OMBUDSMAN for its appropriate action against TONY TEOPE, in his capacity as the Assistant to the Municipal Mayor … for the alleged violation of Section 3(i) of R.A. No. 3019."', S["q"]))
    st.append(Paragraph('Endorsement: "we hereby formally ENDORSE for your further investigation our RESOLUTION … docketed CTN SL-2026-0128-1212 … for possible violation of Republic Act No. 6713 and 3019 …"', S["q"]))
    st.append(Paragraph("C. CTN SL-2026-0423-1891 — Notices of Referral dated 04 May 2026 (Enclosures 3(c), 3(d)) and CSC OAC-L Letter No. 270, s. 2026 (Enclosure 2):", S["sec"]))
    st.append(Paragraph('ARTA → CSC / DILG: "in accordance with Section 17 (d) of Republic Act No. 11032 … the Authority has the power to refer complaints to the appropriate agency, we are hereby referring the above complaint to your office for appropriate action."', S["q"]))
    st.append(Paragraph('CSC → Ombudsman (OAC-L Letter No. 270, s. 2026, 23 June 2026): the referral is transmitted "against the members of the Committee on Anti-Red Tape (CART) of the Municipal Government of Mercedes, Camarines Norte, with Hon. Alexander Pajarillo, in his capacity as the Municipal Mayor and as the CART Chairperson, for violation of … R.A. 6713," the CSC noting that "the official involved is an elective official and thus within the disciplinary jurisdiction of" the Office of the Ombudsman.', S["q"]))
    st.append(Spacer(1, 6))
    st.append(Paragraph("Note on scope: dockets CTN SL-2025-1021-0747 and SL-2026-0128-1210 were closed without onward referral; dockets SL-2026-0209-1319, -1321 and SL-2026-0218-1378 remain pending. This tally reproduces only dispositions whose received instruments accompany this letter.", S["body"]))
    doc.build(st)
    return out


# (source_filename, 0-based page index) -> rotation in degrees CCW-positive
# Enc8 p2: portrait text scanned lying CCW -> rotate CW (-90) to upright.
# Enc7b p3: genuine landscape sketch -> rotate CCW (+90), top to binding edge.
ROTATE = {
    ("Enc8_SB_Res_1996.pdf", 1): -90,
    ("Enc7b_DENR_LMS25550.pdf", 2): 90,
}


def normalize(pg, rot):
    """Rotate (optionally) then scale-fit + center onto an 8.5x13 portrait page."""
    from pypdf import Transformation, PageObject
    pw, ph = float(pg.mediabox.width), float(pg.mediabox.height)
    tgt = PageObject.create_blank_page(width=FOLIO[0], height=FOLIO[1])
    t = Transformation()
    if rot == -90:      # clockwise
        t = t.rotate(-90).translate(0, pw)
        pw, ph = ph, pw
    elif rot == 90:     # counter-clockwise
        t = t.rotate(90).translate(ph, 0)
        pw, ph = ph, pw
    s = min(FOLIO[0] / pw, FOLIO[1] / ph)
    t = t.scale(s).translate((FOLIO[0] - pw * s) / 2, (FOLIO[1] - ph * s) / 2)
    tgt.merge_transformed_page(pg, t)
    return tgt


def stamp(src_paths, letter):
    """Merge src_paths, normalize every page to 8.5x13 portrait, stamp ENCLOSURE 'N'."""
    pages = []
    for p in src_paths:
        r = PdfReader(os.path.join(SRC, p))
        for idx, pg in enumerate(r.pages):
            rot = ROTATE.get((p, idx), 0)
            w0, h0 = float(pg.mediabox.width), float(pg.mediabox.height)
            if rot == 0 and w0 > h0:
                rot = 90  # default: landscape content, top to binding edge
            pages.append(normalize(pg, rot))
    out = PdfWriter()
    for pg in pages:
        pw, ph = float(pg.mediabox.width), float(pg.mediabox.height)
        ov = io.BytesIO()
        c = canvas.Canvas(ov, pagesize=(pw, ph))
        text = f'ENCLOSURE "{letter}"'
        fs = max(11, min(18, pw * 0.026))
        pad = fs * 0.5
        c.setFont("Helvetica-Bold", fs)
        tw = c.stringWidth(text, "Helvetica-Bold", fs)
        bw, bh = tw + 2 * pad, fs + 2 * pad
        m = max(12, pw * 0.028)
        x, y = pw - bw - m, m
        c.setFillColor(Color(1, 1, 1, alpha=0.85))
        c.setStrokeColor(black)
        c.setLineWidth(1.3)
        c.roundRect(x, y, bw, bh, radius=3, stroke=1, fill=1)
        c.setFillColor(black)
        c.drawCentredString(x + bw / 2, y + pad, text)
        c.showPage()
        c.save()
        ov.seek(0)
        pg.merge_page(PdfReader(ov).pages[0])
        out.add_page(pg)
    path = os.path.join(STAMPED, f"Enclosure_{letter}.pdf")
    with open(path, "wb") as f:
        out.write(f)
    return path


def divider(letter, desc, note):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=FOLIO)
    W, H = FOLIO
    c.setFont("TNR-Bold", 22)
    c.drawCentredString(W / 2, H * 0.62, f'ENCLOSURE "{letter}"')
    c.setFont("TNR", 12)
    y = H * 0.56
    for line in _wraptext(c, desc, "TNR", 12, W - 2.4 * inch):
        c.drawCentredString(W / 2, y, line)
        y -= 16
    c.setFont("TNR-Italic", 11)
    y -= 12
    for line in _wraptext(c, note, "TNR-Italic", 11, W - 2.8 * inch):
        c.drawCentredString(W / 2, y, line)
        y -= 15
    c.showPage()
    c.save()
    buf.seek(0)
    return PdfReader(buf).pages[0]


def _wraptext(c, text, font, size, width):
    words, line, out = text.split(), "", []
    for w in words:
        t = (line + " " + w).strip()
        if c.stringWidth(t, font, size) <= width:
            line = t
        else:
            out.append(line)
            line = w
    if line:
        out.append(line)
    return out


def cover(entries):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=FOLIO, leftMargin=1.0 * inch, rightMargin=1.0 * inch,
                            topMargin=1.0 * inch, bottomMargin=0.9 * inch)
    st = [Paragraph("INDEX OF ENCLOSURES", S["h1"]),
          Paragraph("Response to the MLGOO letter of 31 July 2026 and Request for Exercise of General Supervision<br/>(Zschoche, AIF for Patricia Keesey Zschoche — 18 August 2026)", S["h2"])]
    rows = [[Paragraph("<b>Enclosure</b>", S["cellb"]), Paragraph("<b>Document</b>", S["cellb"]), Paragraph("<b>Pages</b>", S["cellb"])]]
    for letter, desc, pages in entries:
        rows.append([Paragraph(f'"{letter}"', S["cell"]), Paragraph(desc, S["cell"]), Paragraph(str(pages), S["cell"])])
    t = Table(rows, colWidths=[0.8 * inch, 5.1 * inch, 0.8 * inch])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.6, black),
        ("BACKGROUND", (0, 0), (-1, 0), Color(0.92, 0.92, 0.92)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    st.append(t)
    st.append(Spacer(1, 10))
    st.append(Paragraph("Each enclosure page carries a boxed ENCLOSURE label at the lower right.", S["body"]))
    doc.build(st)
    buf.seek(0)
    return PdfReader(buf)


def main():
    os.makedirs(STAMPED, exist_ok=True)
    tally = build_tally()
    print("tally:", tally)

    bound = PdfWriter()
    index_entries = []
    stamped_readers = []
    for letter, desc, srcs in ENCLOSURES:
        if srcs is None:
            index_entries.append((letter, desc, "insert"))
            stamped_readers.append(("DIV", letter, desc))
            continue
        srcs = ["Enc1_Referral_Tally.pdf" if s == "_GEN_TALLY" else s for s in srcs]
        path = stamp(srcs, letter)
        n = len(PdfReader(path).pages)
        index_entries.append((letter, desc, n))
        stamped_readers.append(("PDF", path, desc))
        print(f"Enclosure {letter}: {n} pp")

    for pg in cover(index_entries).pages:
        bound.add_page(pg)
    for kind, a, b in stamped_readers:
        if kind == "DIV":
            bound.add_page(divider(a, b, "Executed and apostilled original — inserted at filing by the affiant."))
        else:
            for pg in PdfReader(a).pages:
                bound.add_page(pg)

    out = os.path.join(HERE, "DILG_Enclosures_1-9_bound_8.5x13.pdf")
    with open(out, "wb") as f:
        bound.write(f)
    print("BOUND:", out, len(PdfReader(out).pages), "pp")


if __name__ == "__main__":
    main()
