#!/usr/bin/env python3
"""Bind the ARTA-1378 Manifestation packet — 8.5x13 folio throughout.

Manifestation + Notice of Filing + Index of Annexes + Annexes "1"-"5", every annex page stamped.

  Annex "1" — CART Resolution No. 05 s. 2026 + CART Referral Report 16 Apr 2026   (doc 716)
  Annex "2" — ARTA-SL e-mail 16 Apr 2026 endorsing the SCA to Litigation          (gmail #73 / doc 1732)
  Annex "3" — Complainant's e-mail transmittal 8 Jun 2026 of the Supplemental     (gmail #89297 -> doc 1082)
  Annex "4" — Citizen's Charter, Municipal Assessor's Office, pp. 166-177,
              as annexed by ARTA in CTN SL-2026-0209-1321 (its Annex "3")         (doc 6907 pp. 72-83)
  Annex "5" — ARTA Resolution 25 Aug 2026 in CTN SL-2026-0209-1321, pertinent pages (doc 6908 pp. 1,5,6,7,10,11)

Run from this directory:  python3 build.py
"""
import io
import os
import re

from pypdf import PdfReader, PdfWriter, PageObject, Transformation
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
MD = os.path.join(os.path.dirname(HERE), "ARTA_1378_MANIFESTATION_INCOMPLETE_RESOLUTION_draft.md")
FOLIO = (8.5 * 72, 13.0 * 72)
FOOTER = "Zschoche v. Engr. Erwin H. Balane — Manifestation, CTN SL-2026-0218-1378"

F = "/System/Library/Fonts/Supplemental"
pdfmetrics.registerFont(TTFont("TNR", f"{F}/Times New Roman.ttf"))
pdfmetrics.registerFont(TTFont("TNR-Bold", f"{F}/Times New Roman Bold.ttf"))
pdfmetrics.registerFont(TTFont("TNR-Italic", f"{F}/Times New Roman Italic.ttf"))
pdfmetrics.registerFont(TTFont("TNR-BoldItalic", f"{F}/Times New Roman Bold Italic.ttf"))
pdfmetrics.registerFontFamily("TNR", normal="TNR", bold="TNR-Bold", italic="TNR-Italic", boldItalic="TNR-BoldItalic")

BASE = dict(fontName="TNR", fontSize=11.5, leading=14.8, spaceAfter=7, alignment=TA_JUSTIFY)
S = {
    "title": ParagraphStyle("title", fontName="TNR-Bold", fontSize=14.5, leading=18, alignment=TA_CENTER, spaceBefore=10, spaceAfter=10),
    "h2": ParagraphStyle("h2", fontName="TNR-Bold", fontSize=12.5, leading=16, alignment=TA_CENTER, spaceBefore=12, spaceAfter=6),
    "body": ParagraphStyle("body", **BASE),
    "sub": ParagraphStyle("sub", **{**BASE, "leftIndent": 0.35 * inch}),
    "num": ParagraphStyle("num", **{**BASE, "leftIndent": 0.5 * inch, "spaceAfter": 5}),
    "cap": ParagraphStyle("cap", fontName="TNR", fontSize=11, leading=13.6, alignment=TA_LEFT),
    "capb": ParagraphStyle("capb", fontName="TNR-Bold", fontSize=11, leading=13.6, alignment=TA_LEFT),
    "sig": ParagraphStyle("sig", **{**BASE, "alignment": TA_LEFT, "spaceAfter": 0, "leading": 14.5}),
    "encl": ParagraphStyle("encl", **{**BASE, "fontSize": 9.6, "leading": 12}),
    "idx": ParagraphStyle("idx", fontName="TNR", fontSize=10.5, leading=13.5),
}


def md_to_rl(s):
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = re.sub(r"\*\*\*(.+?)\*\*\*", r"<b><i>\1</i></b>", s, flags=re.S)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s, flags=re.S)
    s = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<i>\1</i>", s, flags=re.S)
    s = re.sub(r"`\[(.+?)\]`", "", s)          # strip [VERIFY]/[FILL] editorial marks
    s = re.sub(r"\s{2,}", " ", s)
    return s


def caption_flowables():
    left = [
        ("**JONATHAN PAUL ZSCHOCHE**,", "capb"),
        ("*Complainant*,", "cap"),
        ("", "cap"),
        ("— versus —", "cap"),
        ("", "cap"),
        ("**ENGR. ERWIN H. BALANE**, in his capacity as", "capb"),
        ("Municipal Engineer, **OFFICE OF THE MUNICIPAL**", "capb"),
        ("**ENGINEER**, Mercedes, Camarines Norte,", "capb"),
        ("*Respondent*.", "cap"),
    ]
    right = [
        ("", "cap"),
        ("**CTN SL-2026-0218-1378**", "capb"),
        ("", "cap"),
        ("*For:* Violation of Sections 21(b)", "cap"),
        ("and (e) of R.A. No. 11032", "cap"),
    ]
    head = [
        Paragraph("REPUBLIC OF THE PHILIPPINES", ParagraphStyle("c1", fontName="TNR", fontSize=11, leading=13.5, alignment=TA_CENTER)),
        Paragraph("OFFICE OF THE PRESIDENT", ParagraphStyle("c2", fontName="TNR", fontSize=11, leading=13.5, alignment=TA_CENTER)),
        Paragraph("<b>ANTI-RED TAPE AUTHORITY</b>", ParagraphStyle("c3", fontName="TNR-Bold", fontSize=12.5, leading=15.5, alignment=TA_CENTER)),
        Paragraph("Litigation Division, Diliman, Quezon City", ParagraphStyle("c4", fontName="TNR", fontSize=10.5, leading=13, alignment=TA_CENTER, spaceAfter=12)),
    ]
    lcol = [Paragraph(md_to_rl(t), S[st]) for t, st in left]
    rcol = [Paragraph(md_to_rl(t), S[st]) for t, st in right]
    tbl = Table([[lcol, rcol]], colWidths=[3.9 * inch, 2.6 * inch])
    tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
    rule = Paragraph("x — — — — — — — — — — — — — — — — — — — — — — — — — — x",
                     ParagraphStyle("rule", fontName="TNR", fontSize=10, leading=13, alignment=TA_LEFT, spaceBefore=4, spaceAfter=2))
    return head + [tbl, rule]


SIG_BLOCK = ["**JONATHAN PAUL ZSCHOCHE**", "Complainant",
             "Dasmariñas Street, Barangay 8, Daet, Camarines Norte",
             "jonzschoche@gmail.com · 0966-698-1448"]


def body_story():
    raw = open(MD).read().split("\n")
    story = caption_flowables()
    i = 0
    started = False
    while i < len(raw):
        line = raw[i].rstrip()
        if line.startswith("> **INTERNAL"):
            break
        if not started:
            if line.startswith("# MANIFESTATION"):
                started = True
                story.append(Paragraph("MANIFESTATION", S["title"]))
            i += 1
            continue
        if not line.strip() or line.strip() == "---":
            i += 1
            continue
        if line.startswith("## "):
            story.append(Paragraph(md_to_rl(line[3:]), S["h2"]))
            i += 1
            continue
        m = re.match(r"^\s{2,}(\d+)\.\s+(.*)$", line)          # prayer / sub-numbered items
        if m:
            txt = m.group(2)
            i += 1
            while i < len(raw) and raw[i].strip() and raw[i].startswith("  ") and not re.match(r"^\s{2,}(\d+|\*\*\()", raw[i]):
                txt += " " + raw[i].strip()
                i += 1
            story.append(Paragraph(f"<b>{m.group(1)}.</b> " + md_to_rl(txt), S["num"]))
            continue
        if line.startswith(("**THE ARTA", "**ENGR. ERWIN")):            # notice-of-filing addressees
            story.append(Paragraph(md_to_rl(line), S["sig"]))
            i += 1
            continue
        if line.lstrip().startswith("**(") and line.startswith("  "):   # lettered sub-paragraphs
            story.append(Paragraph(md_to_rl(line.strip()), S["sub"]))
            i += 1
            continue
        block = [line.strip()]
        i += 1
        while i < len(raw) and raw[i].strip() and not raw[i].startswith(("#", "  ", ">")) and raw[i].strip() != "---":
            block.append(raw[i].strip())
            i += 1
        text = " ".join(block)
        if text.startswith("*Annexes:*"):
            story.append(Spacer(1, 6))
            story.append(Paragraph(md_to_rl(text), S["encl"]))
        elif text.startswith("**JONATHAN PAUL ZSCHOCHE**"):
            story.append(Spacer(1, 40))
            for part in SIG_BLOCK:
                story.append(Paragraph(md_to_rl(part), S["sig"]))
            story.append(Spacer(1, 10))
            # skip the md's own signature detail lines
            while i < len(raw) and raw[i].strip() and not raw[i].startswith(("#", "*Annexes", "---")):
                i += 1
        elif text.startswith("GREETINGS:"):
            story.append(Paragraph("GREETINGS:", S["body"]))
        else:
            story.append(Paragraph(md_to_rl(text), S["body"]))
    return story


class NC(pdfcanvas.Canvas):
    paginate = True

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
            if self.paginate:
                self.setFont("TNR", 9)
                self.drawCentredString(FOLIO[0] / 2, 0.5 * inch, f"Page {self._pageNumber} of {n}")
            self.setFont("TNR-Italic", 7.5)
            self.drawCentredString(FOLIO[0] / 2, 0.36 * inch, FOOTER)
            super().showPage()
        super().save()


def render_doc(story, out, paginate=True):
    maker = NC if paginate else type("NCplain", (NC,), {"paginate": False})
    doc = SimpleDocTemplate(out, pagesize=FOLIO, leftMargin=1.0 * inch, rightMargin=1.0 * inch,
                            topMargin=0.85 * inch, bottomMargin=0.85 * inch, title=FOOTER)
    doc.build(story, canvasmaker=maker)
    return out


EMAIL2 = dict(
    title='ANNEX "2" — E-mail of the ARTA Southern Luzon Regional Field Office, 16 April 2026',
    rows=[("From", "Southern Luzon - Complaints Handling &lt;complaints.southernluzon@arta.gov.ph&gt;"),
          ("To", "jonpeezee@hotmail.com; jonzschoche@gmail.com; lourdestotanes@yahoo.com; mercedesmunicipality@gmail.com"),
          ("Subject", "Re: ARTA CART INDORSEMENT - CTN SL-2026-0218-1378"),
          ("Received", "16 April 2026, 09:52 UTC (17:52 Philippine Standard Time) — Gmail internalDate")],
    body=["Dear All,", "Greetings!",
          "We would like to respectfully inform everyone that the Sworn Complaint Affidavit (SCA) which was "
          "submitted by Mr. Jonathan Zschoche has been assessed and endorsed to ARTA's Litigation Division for "
          "the next process.",
          "For your information and reference.",
          "Best regards,",
          "ANTI-RED TAPE AUTHORITY — SOUTHERN LUZON REGIONAL FIELD OFFICE"],
    note="Retrieved from the mailbox of the Complainant. The same thread carries the Regional Field Office's "
         "transmittals of 23 February 2026 and 26 March 2026 in this docket.")

EMAIL3 = dict(
    title='ANNEX "3" — Complainant\'s e-mail transmittal of the Supplemental Affidavit and Manifestation, 8 June 2026',
    rows=[("From", "Jonathan Zschoche &lt;jonzschoche@gmail.com&gt;"),
          ("To", "Litigation Division - ARTA &lt;litigationdivision@arta.gov.ph&gt;"),
          ("Cc", "Bayan Ng Mercedes &lt;mercedesmunicipality@gmail.com&gt;; helpdesk@mercedes.gov.ph; MEO Mercedes &lt;meo_mercedescn@yahoo.com&gt;"),
          ("Subject", "Re: [NSR] CTN SL-2026-0218-1378 Jonathan Paul Zschoche v. Municipal Engineer's Office - Mercedes, Camarines Norte"),
          ("Sent / Received", "8 June 2026, 04:52 UTC = 12:52 p.m. Philippine Standard Time (Gmail internalDate)"),
          ("Attachment", "Supplemental Affidavit and Manifestation 1378.pdf — 8,721,331 bytes")],
    body=["Dear Honorable Litigation Division:", "Greetings of peace.",
          "With deepest respect … the Complainant respectfully transmits herewith for filing and consideration "
          "in ARTA Case No. CTN SL-2026-0218-1378 … the following:",
          "1. SUPPLEMENTAL AFFIDAVIT AND MANIFESTATION, duly subscribed and sworn before a notary public; and",
          "2. ANNEXES \"E\" through \"I\" thereto …",
          "The Complainant is mindful that the case stands submitted for resolution under the Notice of "
          "Submission for Resolution dated 04 June 2026, and respectfully begs this Honorable Authority's "
          "indulgence in admitting the foregoing Supplemental for its limited purposes …"],
    note="The Resolution dated 09 September 2026 records this Supplemental as received on 17 June 2026. "
         "The 17 June 2026 communication in the same thread was a follow-up to this transmittal.")


def email_page(spec, out):
    st = [Paragraph(spec["title"], ParagraphStyle("t", fontName="TNR-Bold", fontSize=12, leading=15, alignment=TA_CENTER, spaceAfter=12))]
    rows = [[Paragraph(f"<b>{k}</b>", S["idx"]), Paragraph(v, S["idx"])] for k, v in spec["rows"]]
    t = Table(rows, colWidths=[1.1 * inch, 5.4 * inch])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, black), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (0, -1), Color(0.94, 0.94, 0.94)),
                           ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    st += [t, Spacer(1, 12), Paragraph("<b>Text of the message:</b>", S["idx"]), Spacer(1, 4)]
    for p in spec["body"]:
        st.append(Paragraph(p, ParagraphStyle("e", **{**BASE, "fontSize": 10.5, "leading": 13.5, "leftIndent": 0.3 * inch})))
    st += [Spacer(1, 10), Paragraph(f"<i>{spec['note']}</i>", S["idx"])]
    return render_doc(st, out)


# (label, description, file, per-page note about any marking inherited from the source)
INDEX = [
    ("1", "CART Resolution No. 05, s. 2026 (6 April 2026), with the CART Referral Report transmitted 16 April 2026 "
          "over the signature of the Municipal Mayor as CART Chairperson", "annex1_cart_res05.pdf", None),
    ("2", "E-mail of the ARTA Southern Luzon Regional Field Office, 16 April 2026, endorsing the Sworn "
          "Complaint-Affidavit to the Litigation Division", "_annex2.pdf", None),
    ("3", "Complainant's e-mail transmittal of 8 June 2026, with the Supplemental Affidavit and Manifestation attached", "_annex3.pdf", None),
    ("4", "Citizen's Charter of the Municipality of Mercedes, Camarines Norte — Municipal Assessor's Office, "
          "pp. 166–177, as annexed by the Authority in CTN SL-2026-0209-1321",
     "annex4_charter_assessor.pdf",
     'The marking ANNEX "3" at the head of this page is the Authority\'s own marking in CTN SL-2026-0209-1321. '
     'In this Manifestation these pages are ANNEX "4".'),
    ("5", "Resolution dated 25 August 2026 in CTN SL-2026-0209-1321, pertinent pages (caption; pp. 5–7 findings; "
          "pp. 10–11 recommendation and action)", "annex5_1321_resolution.pdf", None),
]


def index_page(counts, out):
    st = [Paragraph("INDEX OF ANNEXES", S["title"]),
          Paragraph("Manifestation in CTN SL-2026-0218-1378 — <i>Zschoche v. Engr. Erwin H. Balane</i>",
                    ParagraphStyle("s", fontName="TNR", fontSize=11, leading=14, alignment=TA_CENTER, spaceAfter=14))]
    rows = [[Paragraph("<b>Annex</b>", S["idx"]), Paragraph("<b>Document</b>", S["idx"]), Paragraph("<b>Pages</b>", S["idx"])]]
    for lbl, desc, fn, note in INDEX:
        d = desc + (f' <i>(these pages bear the Authority\'s own ANNEX "3" marking from that docket)</i>' if note else "")
        rows.append([Paragraph(f'<b>"{lbl}"</b>', S["idx"]), Paragraph(d, S["idx"]), Paragraph(str(counts[lbl]), S["idx"])])
    t = Table(rows, colWidths=[0.7 * inch, 4.9 * inch, 0.9 * inch], repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, black), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (-1, 0), Color(0.93, 0.93, 0.93)),
                           ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                           ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5)]))
    st.append(t)
    return render_doc(st, out, paginate=False)


def divider(lbl, desc, note, out):
    st = [Spacer(1, 190),
          Paragraph(f'ANNEX "{lbl}"', ParagraphStyle("dl", fontName="TNR-Bold", fontSize=30, leading=36, alignment=TA_CENTER, spaceAfter=20)),
          Paragraph(desc, ParagraphStyle("dd", fontName="TNR", fontSize=12.5, leading=17, alignment=TA_CENTER))]
    if note:
        st += [Spacer(1, 22), Paragraph(note, ParagraphStyle("dn", fontName="TNR-Italic", fontSize=10.5, leading=14, alignment=TA_CENTER))]
    return render_doc(st, out, paginate=False)


def normalize(pg, rot=0):
    pw, ph = float(pg.mediabox.width), float(pg.mediabox.height)
    if rot == 0 and pw > ph:
        rot = 90
    tgt = PageObject.create_blank_page(width=FOLIO[0], height=FOLIO[1])
    t = Transformation()
    if rot == 90:
        t = t.rotate(90).translate(ph, 0)
        pw, ph = ph, pw
    s = min(FOLIO[0] / pw, FOLIO[1] / ph)
    t = t.scale(s).translate((FOLIO[0] - pw * s) / 2, (FOLIO[1] - ph * s) / 2)
    tgt.merge_transformed_page(pg, t)
    return tgt


def stamp(pg, label, note=None):
    pw, ph = float(pg.mediabox.width), float(pg.mediabox.height)
    ov = io.BytesIO()
    c = pdfcanvas.Canvas(ov, pagesize=(pw, ph))
    text = f'ANNEX "{label}"'
    fs, pad, m = 13, 6.5, 18
    c.setFont("Helvetica-Bold", fs)
    bw, bh = c.stringWidth(text, "Helvetica-Bold", fs) + 2 * pad, fs + 2 * pad
    x, y = pw - bw - m, m
    c.setFillColor(Color(1, 1, 1, alpha=0.85))
    c.setStrokeColor(black)
    c.setLineWidth(1.3)
    c.roundRect(x, y, bw, bh, radius=3, stroke=1, fill=1)
    c.setFillColor(black)
    c.drawCentredString(x + bw / 2, y + pad, text)
    if note:
        c.setFont("Times-Italic", 7.2)
        c.setFillColor(black)
        c.drawString(m, m + 3, note)
    c.showPage()
    c.save()
    ov.seek(0)
    pg.merge_page(PdfReader(ov).pages[0])
    return pg


def main():
    body = render_doc(body_story(), os.path.join(HERE, "_manifestation.pdf"))
    email_page(EMAIL2, os.path.join(SRC, "_annex2.pdf"))
    email_page(EMAIL3, os.path.join(SRC, "_annex3.pdf"))

    counts, annex_pages = {}, []
    for lbl, desc, fn, note in INDEX:
        pages = [normalize(p) for p in PdfReader(os.path.join(SRC, fn)).pages]
        counts[lbl] = len(pages)
        annex_pages.append((lbl, desc, note, pages))

    idx = index_page(counts, os.path.join(HERE, "_index.pdf"))

    out = PdfWriter()
    for p in PdfReader(body).pages:
        out.add_page(p)
    for p in PdfReader(idx).pages:
        out.add_page(p)
    for lbl, desc, note, pages in annex_pages:
        div = divider(lbl, desc, note, os.path.join(HERE, f"_div_{lbl}.pdf"))
        for p in PdfReader(div).pages:
            out.add_page(p)
        os.remove(div)
        short = f'ANNEX "{lbl}" of this Manifestation' if note else None
        for p in pages:
            out.add_page(stamp(p, lbl, short))

    dest = os.path.join(HERE, "ARTA_1378_Manifestation_Packet_8.5x13.pdf")
    with open(dest, "wb") as fh:
        out.write(fh)
    r = PdfReader(dest)
    sizes = {(round(float(p.mediabox.width)), round(float(p.mediabox.height))) for p in r.pages}
    print("BOUND:", dest, len(r.pages), "pp, sizes:", sizes)
    print("  manifestation:", len(PdfReader(body).pages), "pp · index: 1 pp")
    for lbl, _d, _f, _n in INDEX:
        print(f'  Annex "{lbl}" - {counts[lbl]} pp (+1 divider)')


if __name__ == "__main__":
    main()
