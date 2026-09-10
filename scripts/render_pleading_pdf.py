#!/usr/bin/env python3
"""render_pleading_pdf.py — LandTek pleading renderer, PDF backend (reportlab).

Same source conventions as scripts/render_pleading.js (the .docx backend), so one
markdown draft renders to both. Page and type per A.M. No. 11-9-4-SC: 8.5" x 13"
long bond, 14 pt, single-spaced with 1.5 spaces between paragraphs, margins
L 1.5" / T 1.2" / R 1.0" / B 1.0", every page numbered.

Markers:  ( ? ) / ( hint ? ) -> blank (+ gray hint) · ⟦note⟧ -> gray note ·
          [V …] / [O …] -> gray note · **bold** · *italic*
Directives (HTML comments in the .md):
  <!-- caption:full|short|none -->  caption block from the job (full/short title)
  <!-- align:right|center|reset --> · <!-- pagebreak --> ·
  <!-- filing:skip --> … <!-- /filing:skip --> · <!-- section:NAME --> … <!-- /section -->
Job keys: source, output, court[], captionFull[], captionShort[], captionRight[],
          footer, section (optional), noBanner (optional)

Usage: python3 scripts/render_pleading_pdf.py <job.json> [...]
"""
import json
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (BaseDocTemplate, Frame, PageBreak, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

PAGE = (8.5 * inch, 13 * inch)
MARGIN = dict(left=1.5 * inch, top=1.2 * inch, right=1.0 * inch, bottom=1.0 * inch)
CONTENT_W = PAGE[0] - MARGIN["left"] - MARGIN["right"]
BODY_PT, NOTE_PT, LEAD = 14, 10, 17
GAP = 1.5 * LEAD
NOTE_COLOR = "#7A7A7A"
BLANK = "__________"
NOTE_OPEN, NOTE_CLOSE = "⟦", "⟧"
FONT = "Times-Roman"

S = dict(
    body=ParagraphStyle("body", fontName=FONT, fontSize=BODY_PT, leading=LEAD,
                        alignment=TA_JUSTIFY, spaceAfter=GAP),
    num=ParagraphStyle("num", fontName=FONT, fontSize=BODY_PT, leading=LEAD,
                       alignment=TA_JUSTIFY, spaceAfter=GAP, firstLineIndent=0.5 * inch),
    center=ParagraphStyle("center", fontName=FONT, fontSize=BODY_PT, leading=LEAD,
                          alignment=TA_CENTER, spaceAfter=0),
    right=ParagraphStyle("right", fontName=FONT, fontSize=BODY_PT, leading=LEAD,
                         alignment=TA_LEFT, leftIndent=CONTENT_W * 0.42, spaceAfter=0),
    h2=ParagraphStyle("h2", fontName="Times-Bold", fontSize=BODY_PT, leading=LEAD,
                      alignment=TA_CENTER, spaceAfter=GAP, spaceBefore=6),
    h3=ParagraphStyle("h3", fontName="Times-Bold", fontSize=BODY_PT, leading=LEAD,
                      alignment=TA_CENTER, spaceAfter=GAP, spaceBefore=4),
    bullet=ParagraphStyle("bullet", fontName=FONT, fontSize=BODY_PT, leading=LEAD,
                          alignment=TA_JUSTIFY, leftIndent=0.5 * inch,
                          firstLineIndent=-0.25 * inch, spaceAfter=GAP / 2),
    banner=ParagraphStyle("banner", fontName=FONT, fontSize=11, leading=13,
                          alignment=TA_LEFT, borderColor=colors.grey, borderWidth=0.5,
                          borderPadding=6, backColor=colors.HexColor("#F4F4F4"),
                          spaceAfter=GAP),
    cap=ParagraphStyle("cap", fontName=FONT, fontSize=BODY_PT, leading=LEAD, alignment=TA_LEFT),
)


# ---------- inline ----------

def note(t):
    return f'<font color="{NOTE_COLOR}" size="{NOTE_PT}"><i> {escape(t)} </i></font>'


TOKEN = re.compile(
    r"(\*\*[^*]+\*\*)"
    r"|(\*[^*\n]+\*)"
    rf"|({NOTE_OPEN}[\s\S]*?{NOTE_CLOSE})"
    r"|(\[(?:V|O|inferred_strong|inferred_weak)\b[^\]]*\])"
    r"|(\([^()]*\?[^()]*\))"
)


def clean(s):
    return re.sub(r"(^|[\s(])\*([^*]+)\*", r"\1\2", s.replace("**", "")).replace("`", "").strip()


def inline(text):
    text = text.replace("₱", "PhP")   # Times-Roman has no peso glyph; renders as a box
    out, last = [], 0
    for m in TOKEN.finditer(text):
        out.append(escape(text[last:m.start()].replace("`", "")))
        last = m.end()
        bold, ital, drafter, prov, blank = m.groups()
        if bold:
            out.append(f"<b>{inline(bold[2:-2])}</b>")      # blanks/notes inside bold
        elif ital:
            out.append(f"<i>{inline(ital[1:-1])}</i>")
        elif drafter:
            out.append(note("[" + clean(drafter[1:-1]) + "]"))
        elif prov:
            out.append(note(prov))
        else:
            inner = re.sub(r"^[—–-]\s*", "", blank[1:-1].replace("?", "").strip())
            out.append(BLANK + (note("[" + clean(inner) + "]") if inner else ""))
    out.append(escape(text[last:].replace("`", "")))
    return "".join(out)


def para(text, style):
    return Paragraph(inline(text), style)


# ---------- caption ----------

def caption(job, kind):
    if kind == "none" or not job.get("court"):
        return []
    left = job["captionFull"] if kind == "full" else job["captionShort"]
    flow = [para(l, S["center"]) for l in job["court"]] + [Spacer(1, GAP)]
    lcell = [para(l, S["cap"]) if l else Spacer(1, LEAD) for l in left]
    rcell = [para(l, S["cap"]) for l in job["captionRight"]]
    t = Table([[lcell, rcell]], colWidths=[CONTENT_W * 0.6, CONTENT_W * 0.4])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (0, 0), 10)]))
    flow += [t, Spacer(1, LEAD / 2), para("x" + "- " * 28 + "x", S["center"]), Spacer(1, GAP)]
    return flow


def banner(job):
    if job.get("noBanner") or job.get("bannerBox") is False:   # bannerBox:false keeps the DRAFT footer, drops the box
        return []
    txt = ("<b>DRAFT — NOT FOR FILING IN THIS FORM.</b> Prepared by LandTek as work product "
           "for counsel; no counsel of record has adopted it. Before filing: fill every "
           + BLANK + " blank, delete every gray italic note, delete this box, verify the "
           "rule and case citations. Page set-up per A.M. No. 11-9-4-SC.")
    return [Paragraph(txt, S["banner"])]


# ---------- body ----------

def table(rows):
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    cells = [cells[0]] + cells[2:]
    n = len(cells[0])
    st = ParagraphStyle("tc", fontName=FONT, fontSize=10, leading=12)
    data = [[Paragraph(inline(c.replace("**", "") if i == 0 else c), st)
             for c in (r + [""] * n)[:n]] for i, r in enumerate(cells)]
    t = Table(data, colWidths=[CONTENT_W / n] * n, repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDEDED")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return [t, Spacer(1, GAP)]


def body(md, job):
    lines = md.splitlines()
    flow, mode, skipping, section = [], None, False, None
    want = job.get("section")
    i = 0
    while i < len(lines):
        t = lines[i].strip()
        d = re.match(r"^<!--\s*(.+?)\s*-->$", t)
        if d:
            d = d.group(1)
            if d == "filing:skip":
                skipping = True
            elif d == "/filing:skip":
                skipping = False
            elif d == "/section":
                section = None
            elif d.startswith("section:"):
                section = d[8:]
            elif not skipping and (not want or section == want):
                if d == "pagebreak":
                    flow.append(PageBreak())
                elif d.startswith("caption:"):
                    flow += caption(job, d[8:])
                elif d == "align:reset":
                    mode = None
                elif d.startswith("align:"):
                    mode = d[6:]
            i += 1
            continue
        if skipping or (want and section != want) or not t or t.startswith(("> ", "# ")) \
                or re.fullmatch(r"-{3,}", t):
            i += 1
            continue
        if t.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            if len(rows) >= 3:
                flow += table(rows)
            continue
        if t.startswith(("## ", "### ")):
            h2 = t.startswith("## ")
            txt = re.sub(r"^#{2,3}\s+", "", t)
            notes = re.findall(rf"{NOTE_OPEN}([\s\S]*?){NOTE_CLOSE}", txt)
            txt = clean(re.sub(rf"{NOTE_OPEN}[\s\S]*?{NOTE_CLOSE}", "", txt)).upper()
            flow.append(Paragraph(("<u>%s</u>" if h2 else "%s") % escape(txt), S["h2" if h2 else "h3"]))
            for n in notes:
                flow.append(Paragraph(note("[" + clean(n) + "]"), S["center"]))
            mode = None
            i += 1
            continue
        if re.match(r"^[-*]\s+", t):
            flow.append(para("— " + re.sub(r"^[-*]\s+", "", t), S["bullet"]))
            i += 1
            continue
        numbered = re.match(r"^(\d+\.\d*\.?|\([a-z]\)|\d+\.)\s+", t) is not None
        style = S["right"] if mode == "right" else S["center"] if mode == "center" \
            else S["num"] if numbered else S["body"]
        flow.append(para(t, style))
        i += 1
    return flow


# ---------- page numbers ----------

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *a, footer="", draft=True, **k):
        super().__init__(*a, **k)
        self._saved, self._footer, self._draft = [], footer, draft

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        for st in self._saved:
            self.__dict__.update(st)
            self.setFont(FONT, 9)
            self.setFillColor(colors.HexColor("#666666"))
            txt = f"{self._footer}  —  page {self._pageNumber} of {total}" + \
                  ("  —  DRAFT" if self._draft else "")
            self.drawCentredString(PAGE[0] / 2, 0.55 * inch, txt)
            super().showPage()
        super().save()


def render(job_path):
    jp = Path(job_path).resolve()
    job = json.loads(jp.read_text())
    src = (jp.parent / job["source"]).resolve()
    out = (jp.parent / job["output"]).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    md = src.read_text(encoding="utf8")

    doc = BaseDocTemplate(str(out), pagesize=PAGE, leftMargin=MARGIN["left"],
                          rightMargin=MARGIN["right"], topMargin=MARGIN["top"],
                          bottomMargin=MARGIN["bottom"], title=job.get("docTitle", ""),
                          author="LandTek")
    frame = Frame(MARGIN["left"], MARGIN["bottom"], CONTENT_W,
                  PAGE[1] - MARGIN["top"] - MARGIN["bottom"], id="f", leftPadding=0,
                  rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="p", frames=[frame])])
    flow = banner(job) + body(md, job)
    footer, draft = job.get("footer", ""), not job.get("noBanner")
    doc.build(flow, canvasmaker=lambda *a, **k: NumberedCanvas(*a, footer=footer, draft=draft, **k))
    print("wrote", out, f"{out.stat().st_size // 1024}KB")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: render_pleading_pdf.py <job.json> [...]")
    for j in sys.argv[1:]:
        render(j)
