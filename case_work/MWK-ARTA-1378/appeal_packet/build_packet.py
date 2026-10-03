#!/usr/bin/env python3
"""Bind the full 1378 OP filing: Petition (built by build.py) + Index of Annexes + Annexes "A"-"J".

Every annex gets a divider page and a boxed ANNEX stamp on each page. Where a source page carries an
earlier annex marking of its own (ARTA's annex letters, the complaint's annex letters), the source is NOT
altered: the divider and a footline say which marking governs in this filing.

  python3 build.py && python3 build_packet.py
"""
import io
import os

from pypdf import PageObject, PdfReader, PdfWriter, Transformation
from reportlab.lib.colors import Color, black
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "source")
MAN_SRC = os.path.join(os.path.dirname(HERE), "manifestation_packet", "source")
PETITION = os.path.join(HERE, "ARTA_1378_OP_Petition_Supervisory_Review_8.5x13.pdf")
OUT = os.path.join(HERE, "ARTA_1378_OP_Petition_PACKET_8.5x13.pdf")  # slim edition, 28 Sep 2026
FOLIO = (8.5 * 72, 13.0 * 72)
FOOTER = "Zschoche v. Engr. Erwin H. Balane — Petition for Supervisory Review (alt. Notice of Appeal), CTN SL-2026-0218-1378"

F = "/System/Library/Fonts/Supplemental"
for nm, fn in (("TNR", "Times New Roman.ttf"), ("TNR-Bold", "Times New Roman Bold.ttf"),
               ("TNR-Italic", "Times New Roman Italic.ttf"), ("TNR-BoldItalic", "Times New Roman Bold Italic.ttf")):
    pdfmetrics.registerFont(TTFont(nm, f"{F}/{fn}"))
pdfmetrics.registerFontFamily("TNR", normal="TNR", bold="TNR-Bold", italic="TNR-Italic", boldItalic="TNR-BoldItalic")

BASE = dict(fontName="TNR", fontSize=11.5, leading=14.8, spaceAfter=7, alignment=TA_JUSTIFY)
S = {
    "title": ParagraphStyle("title", fontName="TNR-Bold", fontSize=14.5, leading=18, alignment=TA_CENTER, spaceBefore=6, spaceAfter=10),
    "body": ParagraphStyle("body", **BASE),
    "num": ParagraphStyle("num", **{**BASE, "leftIndent": 0.42 * inch}),
    "sub": ParagraphStyle("sub", **{**BASE, "leftIndent": 0.75 * inch, "spaceAfter": 5}),
    "idx": ParagraphStyle("idx", fontName="TNR", fontSize=10.2, leading=13),
    "sig": ParagraphStyle("sig", **{**BASE, "alignment": TA_LEFT, "spaceAfter": 0, "leading": 14.4}),
}


def render(story, out, paginate=False):
    class NC(pdfcanvas.Canvas):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._saved = []

        def showPage(self):
            self._saved.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            n = len(self._saved)
            for st in self._saved:
                self.__dict__.update(st)
                if paginate:
                    self.setFont("TNR", 9)
                    self.drawCentredString(FOLIO[0] / 2, 0.5 * inch, f"Page {self._pageNumber} of {n}")
                self.setFont("TNR-Italic", 7.3)
                self.drawCentredString(FOLIO[0] / 2, 0.36 * inch, FOOTER)
                super().showPage()
            super().save()
    SimpleDocTemplate(out, pagesize=FOLIO, leftMargin=1.0 * inch, rightMargin=1.0 * inch,
                      topMargin=0.9 * inch, bottomMargin=0.85 * inch, title=FOOTER).build(story, canvasmaker=NC)
    return out


def pages_of(path, only=None):
    r = PdfReader(path)
    idx = only if only else range(1, len(r.pages) + 1)
    return [r.pages[i - 1] for i in idx]


# ---------- generated exhibits ----------
def email_A1(out):
    rows = [("From", "Litigation Division - ARTA &lt;litigationdivision@arta.gov.ph&gt;"),
            ("To", "Jonathan Zschoche &lt;jonzschoche@gmail.com&gt;; Bayan Ng Mercedes &lt;mercedesmunicipality@gmail.com&gt;; helpdesk@mercedes.gov.ph"),
            ("Subject", "[RESOLUTION] CTN SL-2026-0218-1378 Jonathan Paul Zschoche v. Municipal Engineer's Office - Mercedes, Camarines Norte"),
            ("Received", "15 September 2026, 08:04 UTC = 4:04 p.m. Philippine Standard Time (Gmail internalDate)"),
            ("Attachment", "[Resolution] Jonathan Paul Zschoche v. Municipal Engineer's Office - Mercedes, Camarines Norte (CTN SL-2026-0218-1378).pdf — 20,896,794 bytes")]
    st = [Paragraph('ANNEX "A-1" — Transmittal of the Resolution by the ARTA Litigation Division, 15 September 2026',
                    ParagraphStyle("t", fontName="TNR-Bold", fontSize=12, leading=15, alignment=TA_CENTER, spaceAfter=12))]
    t = Table([[Paragraph(f"<b>{k}</b>", S["idx"]), Paragraph(v, S["idx"])] for k, v in rows], colWidths=[1.1 * inch, 5.4 * inch])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, black), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (0, -1), Color(0.94, 0.94, 0.94)),
                           ("LEFTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    st += [t, Spacer(1, 12), Paragraph("<b>Text of the message:</b>", S["idx"]), Spacer(1, 4)]
    for p in ["Greetings from the Anti-Red Tape Authority!",
              "Please take notice of the Resolution dated 09 September 2026 in the case of JONATHAN PAUL ZSCHOCHE v. "
              "ENGR. ERWIN H. BALANE, in his capacity as Municipal Engineer of the OFFICE OF THE MUNICIPAL ENGINEER – "
              "Mercedes, Camarines Norte, docketed as CTN: SL-2026-0218-1378 for violation of R.A. No. 11032.",
              "Please see the attached RESOLUTION and its ANNEXES for your reference and perusal.",
              "Respectfully, LITIGATION DIVISION, ANTI-RED TAPE AUTHORITY"]:
        st.append(Paragraph(p, ParagraphStyle("e", **{**BASE, "fontSize": 10.5, "leading": 13.5, "leftIndent": 0.3 * inch})))
    st += [Spacer(1, 10), Paragraph("<i>Retrieved from the Petitioner's mailbox (jonzschoche@gmail.com). This is the date of notice "
                                    "from which the fifteen-day period is counted.</i>", S["idx"])]
    return render(st, out)


def placeholder_F(out):
    st = [Spacer(1, 170), Paragraph('ANNEX "F"', ParagraphStyle("d", fontName="TNR-Bold", fontSize=26, leading=32, alignment=TA_CENTER, spaceAfter=18)),
          Paragraph("Official Receipt for the appeal fee under A.O. No. 22, s. 2011", ParagraphStyle("x", fontName="TNR", fontSize=13, leading=17, alignment=TA_CENTER, spaceAfter=18)),
          Paragraph("<i>No fee is tendered with this Petition, the primary filing being a petition for supervisory review and not an appeal "
                    "under A.O. No. 22 (Petition, Part I.D). Should this Office deem A.O. No. 22 applicable, Petitioner undertakes to pay "
                    "the prescribed fee of ₱1,500.00 immediately upon notice, and the Official Receipt will be filed as this Annex.</i>",
                    ParagraphStyle("y", fontName="TNR-Italic", fontSize=11, leading=15, alignment=TA_CENTER))]
    return render(st, out)


def affidavit_G(out):
    st = [Paragraph('ANNEX "G"', ParagraphStyle("g", fontName="TNR-Bold", fontSize=12, leading=15, alignment=TA_CENTER)),
          Paragraph("AFFIDAVIT OF SERVICE", S["title"]),
          Paragraph("REPUBLIC OF THE PHILIPPINES )<br/>________________________ ) S.S.", ParagraphStyle("v", **{**BASE, "alignment": TA_LEFT})),
          Paragraph("I, <b>JONATHAN PAUL ZSCHOCHE</b>, of legal age, American citizen, with service address at Dasmariñas Street, "
                    "Barangay 8, Daet, Camarines Norte, after having been duly sworn in accordance with law, depose and state:", S["body"])]
    items = [
        "On ______ September 2026 I served copies of the foregoing <b>Petition for Supervisory Review and Corrective Action, with Notice of "
        "Appeal in the alternative</b>, in ARTA Case No. CTN SL-2026-0218-1378, together with its Annexes, upon the following:",
    ]
    for t in items:
        st.append(Paragraph("<b>1.</b> " + t, S["num"]))
    for t in [
        "<b>(a) Anti-Red Tape Authority</b>, Office of the Director General and Litigation Division, 4th Floor, UP Ayala Land TechnoHub "
        "Building I, Commonwealth Avenue, Quezon City — by courier / registered mail, Waybill / Registry Receipt No. ____________________, "
        "and by electronic mail to litigationdivision@arta.gov.ph on ______ September 2026;",
        "<b>(b) Engr. Erwin H. Balane</b>, Municipal Engineer, Municipal Engineering Office, Eco Avenue, Barangay 5, Mercedes, Camarines "
        "Norte — by courier / registered mail, Waybill / Registry Receipt No. ____________________, and by electronic mail to "
        "meo_mercedescn@yahoo.com on ______ September 2026."]:
        st.append(Paragraph(t, S["sub"]))
    st.append(Paragraph("<b>2.</b> The courier waybills / registry receipts and the electronic-mail transmittals are attached hereto.", S["num"]))
    st.append(Paragraph("<b>3.</b> I execute this affidavit to attest to the truth of the foregoing and in compliance with Section 2 of "
                        "Administrative Order No. 22, s. 2011.", S["num"]))
    st += [Paragraph("IN WITNESS WHEREOF, I have hereunto set my hand this ______ day of September 2026 at ______________________.", S["body"]),
           Spacer(1, 34)]
    for l in ["<b>JONATHAN PAUL ZSCHOCHE</b>", "Affiant", "Passport No. 583107536, issued at California, USA"]:
        st.append(Paragraph(l, S["sig"]))
    st += [Spacer(1, 16),
           Paragraph("<b>SUBSCRIBED AND SWORN</b> to before me this ______ day of September 2026 at ______________________, affiant "
                     "exhibiting to me the competent evidence of identity stated above.", S["body"]),
           Spacer(1, 6), Paragraph("Doc. No. ________; Page No. ________; Book No. ________; Series of 2026.", S["sig"])]
    return render(st, out)


# ---------- annex table ----------
# (label, description, list of (pdf, page-list or None), inherited-marking note or None)
def annexes():
    R = os.path.join(SRC, "src_res1378.pdf")
    return [
        ("A", "ARTA Resolution dated 09 September 2026, CTN SL-2026-0218-1378 (pp. 1–10), with its Annex \"D\" (Respondent's "
              "Counter-Affidavit of 21 May 2026) and Annex \"G\" (Citizen's Charter, Municipal Engineering Office, pp. 242–250). "
              "Its remaining annexes are omitted, being part of the Authority's own record. <i>The annex letters \"D\" and \"G\" "
              "printed on these pages are the Authority's own.</i>",
         [(R, list(range(1, 11)) + [32, 33, 34] + list(range(43, 52)))], True),
        ("A-1", "Transmittal e-mail of the ARTA Litigation Division, 15 September 2026 (date of notice)",
         [(os.path.join(SRC, "_A1.pdf"), None)], None),
        ("B", "Petitioner's written request of 24 January 2026 to the Municipal Engineer (item A.1: Certificate of No Record), "
              "with the transmittal e-mail of 26 January 2026. <i>The e-mail page bears the marking \"ANNEX A\" from the "
              "Complaint-Affidavit below.</i>",
         [(os.path.join(SRC, "src_doc838.pdf"), None), (R, [16])],
         True),
        ("C", "Respondent's letter received 5 February 2026 (dated on its face \"February 5, 2025\"), as annexed to the Complaint-Affidavit",
         [(R, [18])], None),
        ("D", "Respondent's letter of 21 October 2025", [(os.path.join(SRC, "src_doc837.pdf"), None)], None),
        ("E", "CART Resolution No. 05, s. 2026 (6 April 2026), with the CART Referral Report of 16 April 2026",
         [(os.path.join(MAN_SRC, "annex1_cart_res05.pdf"), None)], None),
        ("F", "Official Receipt for the appeal fee — not tendered (Petition, Part I.D); to be filed upon notice, should this Office require it",
         [], None),
        ("G", "Affidavit of Service (to be executed upon service, with courier / registry receipts)",
         [(os.path.join(SRC, "_G.pdf"), None)], None),
        ("H", "ARTA Resolution dated 25 August 2026 in CTN SL-2026-0209-1321, pertinent pages (caption; pp. 5–7 findings; pp. 10–11 recommendation and action)",
         [(os.path.join(MAN_SRC, "annex5_1321_resolution.pdf"), None)], None),
        ("H-1", "Citizen's Charter of the Municipality of Mercedes — Municipal Assessor's Office, pp. 166–169 (list of services; "
                "certified-copy issuance; Certification of No Improvement, No Property Holdings and Aggregate Landholdings), as annexed by "
                "the Authority in CTN SL-2026-0209-1321. <i>The marking ANNEX \"3\" on these pages is the Authority's own in that docket.</i>",
         [(os.path.join(MAN_SRC, "annex4_charter_assessor.pdf"), [1, 2, 3, 4])], True),
        ("I", "Letter of the Chief, ARTA Litigation Division, 27 April 2026 (no motion for reconsideration; findings \"merely recommendatory\")",
         [(os.path.join(SRC, "src_doc707.pdf"), None)], None),
        ("J", "Notice of Pre-Trial Conference, Municipal Trial Court of Mercedes, Civil Case No. 26-360 (caption naming Engr. Erwin Balane among the defendants)",
         [(os.path.join(SRC, "annexJ_mtc_pretrial_notice_26-360.pdf"), None)], None),
    ]


def normalize(pg):
    pw, ph = float(pg.mediabox.width), float(pg.mediabox.height)
    rot = 90 if pw > ph else 0
    tgt = PageObject.create_blank_page(width=FOLIO[0], height=FOLIO[1])
    t = Transformation()
    if rot:
        t = t.rotate(90).translate(ph, 0)
        pw, ph = ph, pw
    s = min(FOLIO[0] / pw, FOLIO[1] / ph)
    t = t.scale(s).translate((FOLIO[0] - pw * s) / 2, (FOLIO[1] - ph * s) / 2)
    tgt.merge_transformed_page(pg, t)
    return tgt


def stamp(pg, label, footline=None):
    pw, ph = float(pg.mediabox.width), float(pg.mediabox.height)
    ov = io.BytesIO()
    c = pdfcanvas.Canvas(ov, pagesize=(pw, ph))
    text = f'ANNEX "{label}"'
    fs, pad, m = 13, 6.5, 18
    c.setFont("Helvetica-Bold", fs)
    bw, bh = c.stringWidth(text, "Helvetica-Bold", fs) + 2 * pad, fs + 2 * pad
    x, y = pw - bw - m, m
    c.setFillColor(Color(1, 1, 1, alpha=0.85)); c.setStrokeColor(black); c.setLineWidth(1.3)
    c.roundRect(x, y, bw, bh, radius=3, stroke=1, fill=1)
    c.setFillColor(black); c.drawCentredString(x + bw / 2, y + pad, text)
    if footline:
        c.setFont("Times-Italic", 7.2); c.drawString(m, m + 3, footline)
    c.showPage(); c.save(); ov.seek(0)
    pg.merge_page(PdfReader(ov).pages[0])
    return pg


def divider(lbl, desc, note, out):
    st = [Spacer(1, 190),
          Paragraph(f'ANNEX "{lbl}"', ParagraphStyle("dl", fontName="TNR-Bold", fontSize=30, leading=36, alignment=TA_CENTER, spaceAfter=20)),
          Paragraph(desc, ParagraphStyle("dd", fontName="TNR", fontSize=12.5, leading=17, alignment=TA_CENTER))]
    if note:
        st += [Spacer(1, 22), Paragraph(note, ParagraphStyle("dn", fontName="TNR-Italic", fontSize=10.5, leading=14, alignment=TA_CENTER))]
    return render(st, out)


def index_page(rows, out):
    st = [Paragraph("INDEX OF ANNEXES", S["title"]),
          Paragraph("Petition for Supervisory Review and Corrective Action, with Notice of Appeal in the alternative — CTN SL-2026-0218-1378",
                    ParagraphStyle("s", fontName="TNR", fontSize=10.5, leading=13.5, alignment=TA_CENTER, spaceAfter=14))]
    data = [[Paragraph("<b>Annex</b>", S["idx"]), Paragraph("<b>Document</b>", S["idx"]), Paragraph("<b>Pages</b>", S["idx"])]]
    for lbl, desc, n in rows:
        data.append([Paragraph(f'<b>"{lbl}"</b>', S["idx"]), Paragraph(desc, S["idx"]), Paragraph(str(n), S["idx"])])
    t = Table(data, colWidths=[0.7 * inch, 5.0 * inch, 0.8 * inch], repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, black), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (-1, 0), Color(0.93, 0.93, 0.93)),
                           ("LEFTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    st.append(t)
    return render(st, out)


def main():
    email_A1(os.path.join(SRC, "_A1.pdf"))
    affidavit_G(os.path.join(SRC, "_G.pdf"))

    built, rows = [], []
    for lbl, desc, parts, note in annexes():
        pgs = []
        for path, only in parts:
            pgs += [normalize(p) for p in pages_of(path, only)]
        built.append((lbl, desc, note, pgs))
        rows.append((lbl, desc, len(pgs) if pgs else "—"))

    out = PdfWriter()
    for p in PdfReader(PETITION).pages:
        out.add_page(p)
    idx = index_page(rows, os.path.join(HERE, "_index.pdf"))
    for p in PdfReader(idx).pages:
        out.add_page(p)
    os.remove(idx)
    for lbl, desc, note, pgs in built:
        foot = f'ANNEX "{lbl}" of this Petition' if note else None
        for p in pgs:
            out.add_page(stamp(p, lbl, foot))
    with open(OUT, "wb") as fh:
        out.write(fh)
    r = PdfReader(OUT)
    print("BOUND:", OUT, len(r.pages), "pp ·", round(os.path.getsize(OUT) / 1e6, 1), "MB")
    for lbl, _d, n in rows:
        print(f'  Annex "{lbl}": {n} pp')


if __name__ == "__main__":
    main()
