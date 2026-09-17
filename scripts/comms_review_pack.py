#!/usr/bin/env python3
"""comms_review_pack.py — render EVERY outward communication that is currently due, in draft form,
into ONE bound PDF for Jonathan to read, mark up and critique.

Wider than `drip_review_pack.py` (which renders only the drip engine's own staged emails): this pack
covers every lane — government offices, counsel, courts, clients, partners — across all matters, and
it is honest about what is NOT going out and why.

Content comes from a JSON manifest so the letters are authored once, reviewed, and then (after
markup) turned into the generators that own them. Nothing here sends anything; the renderer has no
network path at all.

  python3 scripts/comms_review_pack.py <manifest.json> [-o out.pdf] [--open]

Manifest shape (all text is plain; \\n\\n separates paragraphs in bodies):
{
  "title": "...", "as_of": "2026-09-16", "standfirst": "...",
  "sections": [{"client": "MWK — …", "blurb": "…", "items": [ITEM, …]}],
  "not_sending": [{"what": "...", "why": "..."}],
  "gaps": [{"need": "...", "blocks": "...", "who": "Jonathan"}]
}
ITEM = {
  "ref": "A1", "verdict": "SEND-READY|DRIP EDITION|STAGE-HOLD|GAP|DO NOT SEND",
  "to": "Name, Office", "email": "x@y | — to source —", "email_source": "…",
  "matter": "MWK-001 · track", "duty": "the ONE thing this letter is about",
  "driver": "what makes it time-sensitive (with its source) or 'no clock'",
  "record": "what the corpus shows: served/not served + proof doc id",
  "gates": "counsel / operator holds", "annexes": ["Annex A — …"],
  "subject": "…", "body": "…",
  "sources": ["doc 6705 — …", "case_work/…"],
  "why_this_shape": "one paragraph: why this letter, why now, why not more"
}
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date

from reportlab.lib.colors import Color, black
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

F = "/System/Library/Fonts/Supplemental"
GREY = Color(0.42, 0.42, 0.42)
RULE = Color(0.75, 0.75, 0.75)
BOXBG = Color(0.955, 0.955, 0.95)
HOTBG = Color(0.98, 0.93, 0.88)

for name, fn in (("TNR", "Times New Roman.ttf"), ("TNR-Bold", "Times New Roman Bold.ttf"),
                 ("TNR-Italic", "Times New Roman Italic.ttf")):
    pdfmetrics.registerFont(TTFont(name, f"{F}/{fn}"))
pdfmetrics.registerFontFamily("TNR", normal="TNR", bold="TNR-Bold", italic="TNR-Italic")

S_TITLE = ParagraphStyle("t", fontName="TNR-Bold", fontSize=18, leading=22, spaceAfter=3)
S_SUB = ParagraphStyle("s", fontName="TNR-Italic", fontSize=10, leading=13.5, textColor=GREY, spaceAfter=10)
S_H = ParagraphStyle("h", fontName="TNR-Bold", fontSize=13, leading=16, spaceBefore=12, spaceAfter=5)
S_H2 = ParagraphStyle("h2", fontName="TNR-Bold", fontSize=11, leading=14, spaceBefore=9, spaceAfter=4)
S_BODY = ParagraphStyle("b", fontName="TNR", fontSize=10.5, leading=14.5, alignment=TA_LEFT)
S_LETTER = ParagraphStyle("l", fontName="TNR", fontSize=10.5, leading=15, leftIndent=10, rightIndent=10)
S_MONO = ParagraphStyle("m", fontName="Courier", fontSize=8.2, leading=11.2, leftIndent=10)
S_NOTE = ParagraphStyle("n", fontName="TNR-Italic", fontSize=9.2, leading=12.2, textColor=GREY)
S_CELL = ParagraphStyle("c", fontName="TNR", fontSize=9.2, leading=12)
S_CELLB = ParagraphStyle("cb", fontName="TNR-Bold", fontSize=9.2, leading=12)


def esc(t):
    return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def kv_box(rows, hot=False):
    data = [[Paragraph(f"<b>{esc(k)}</b>", S_CELLB), Paragraph(esc(v), S_CELL)] for k, v in rows if v]
    t = Table(data, colWidths=[1.25 * inch, 5.5 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), HOTBG if hot else BOXBG),
        ("BOX", (0, 0), (-1, -1), 0.6, RULE), ("INNERGRID", (0, 0), (-1, -1), 0.3, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return t


def letter_block(body, title=None):
    """The letter/email body verbatim, in a ruled box so markup has somewhere to go."""
    flow = []
    for chunk in (body or "").split("\n\n"):
        chunk = chunk.rstrip()
        if not chunk:
            continue
        mono = chunk.lstrip().startswith(("Annex", "  ", "|")) or "\t" in chunk
        flow.append(Paragraph(esc(chunk).replace("\n", "<br/>"), S_MONO if mono else S_LETTER))
        flow.append(Spacer(1, 6))
    t = Table([[flow]], colWidths=[6.85 * inch])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, black),
                           ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                           ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
    out = []
    if title:
        out += [Paragraph(title, S_NOTE), Spacer(1, 4)]
    out.append(t)
    return out


def grid(headers, rows, widths, hot_col=None, hot_values=()):
    data = [[Paragraph(f"<b>{esc(h)}</b>", S_CELLB) for h in headers]]
    for r in rows:
        data.append([Paragraph(esc(c), S_CELL) for c in r])
    t = Table(data, colWidths=[w * inch for w in widths], repeatRows=1)
    style = [("BOX", (0, 0), (-1, -1), 0.7, black),
             ("INNERGRID", (0, 0), (-1, -1), 0.3, RULE),
             ("BACKGROUND", (0, 0), (-1, 0), BOXBG),
             ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5)]
    if hot_col is not None:
        for i, r in enumerate(rows, start=1):
            if r[hot_col] in hot_values:
                style.append(("BACKGROUND", (0, i), (-1, i), HOTBG))
    t.setStyle(TableStyle(style))
    return t


def footer(canv, doc):
    canv.saveState()
    canv.setFont("TNR-Italic", 8)
    canv.setFillColor(GREY)
    canv.drawString(0.8 * inch, 0.5 * inch,
                    "Outward communications review pack — DRAFTS ONLY. Nothing has been sent, filed or "
                    "printed. LandTek builds; Jonathan + counsel pull.")
    canv.drawRightString(7.7 * inch, 0.5 * inch, f"p. {canv.getPageNumber()}")
    canv.restoreState()


def build(man, out_path):
    as_of = man.get("as_of") or date.today().isoformat()
    story = [Paragraph(esc(man.get("title", "Outward Communications — Review Pack")), S_TITLE),
             Paragraph(esc(man.get("standfirst", "")), S_SUB)]

    # ── the board ────────────────────────────────────────────────────────────────────────────────
    rows, n = [], 0
    for sec in man["sections"]:
        for it in sec["items"]:
            n += 1
            rows.append([it["ref"], sec["client"].split("—")[0].strip(), it["to"], it["duty"],
                         it.get("driver_short", it.get("driver", "")), it["verdict"]])
    story += [Paragraph(f"The board — {n} items", S_H),
              grid(["#", "Client", "To", "The one thing it asks or notices", "Timing", "Verdict"],
                   rows, [0.32, 0.72, 1.45, 2.35, 1.0, 1.0],
                   hot_col=5, hot_values=("SEND-READY", "DO NOT SEND", "DECISION DUE")),
              Spacer(1, 10),
              Paragraph("Verdicts: <b>SEND-READY</b> = the record supports it today and it only needs "
                        "your go · <b>DECISION DUE</b> = a call only you can make, and a date is running · "
                        "<b>DRIP EDITION</b> = fires on its own cadence date · "
                        "<b>STAGE-HOLD</b> = built, deliberately not going yet · <b>GAP</b> = a fact or "
                        "address is missing first · <b>DO NOT SEND</b> = my recommendation against, with "
                        "the reason on its page.", S_NOTE),
              Spacer(1, 8),
              Paragraph("How to mark this up: strike, annotate, or tell me the change in words. Each "
                        "correction goes into the generator that owns the letter, so it persists into "
                        "every future cycle instead of being re-typed.", S_NOTE)]

    # ── one page per item ────────────────────────────────────────────────────────────────────────
    for sec in man["sections"]:
        story += [PageBreak(), Paragraph(esc(sec["client"]), S_H)]
        if sec.get("blurb"):
            story += [Paragraph(esc(sec["blurb"]), S_BODY)]
        first = True
        for it in sec["items"]:
            if not first:
                story.append(PageBreak())
            first = False
            story += [Paragraph(f"{esc(it['ref'])} · {esc(it['to'])}", S_H2),
                      kv_box([("VERDICT", it["verdict"]),
                              ("TO", f"{it['to']}  ·  {it.get('email', '— to source —')}"),
                              ("ADDRESS", it.get("email_source", "")),
                              ("MATTER", it["matter"]),
                              ("THE DUTY", it["duty"]),
                              ("TIMING", it["driver"]),
                              ("THE RECORD", it["record"]),
                              ("GATES", it.get("gates", "")),
                              ("ANNEXES", "; ".join(it.get("annexes", [])) or "none — letter stands alone"),
                              ("SUBJECT", it.get("subject", ""))],
                             hot=(it["verdict"] in ("SEND-READY", "DO NOT SEND", "DECISION DUE"))),
                      Spacer(1, 9)]
            if it.get("body"):
                story += letter_block(it["body"], "The letter, verbatim as it would go:")
                story.append(Spacer(1, 8))
            if it.get("why_this_shape"):
                story += [Paragraph("<b>Why this letter, this shape, now</b>", S_BODY), Spacer(1, 2),
                          Paragraph(esc(it["why_this_shape"]), S_BODY), Spacer(1, 6)]
            if it.get("sources"):
                story += [Paragraph("<b>What it rests on</b>", S_BODY), Spacer(1, 2)]
                for s in it["sources"]:
                    story.append(Paragraph("— " + esc(s), S_NOTE))
                story.append(Spacer(1, 4))

    # ── not sending ──────────────────────────────────────────────────────────────────────────────
    if man.get("not_sending"):
        story += [PageBreak(), Paragraph("Not going out — and why", S_H),
                  Paragraph("An honest pack has to say what it is holding back. Each of these exists, "
                            "and each is deliberately not in the board above.", S_BODY), Spacer(1, 6),
                  grid(["What", "Why it is not going"],
                       [[x["what"], x["why"]] for x in man["not_sending"]], [2.5, 4.35])]

    # ── gaps ─────────────────────────────────────────────────────────────────────────────────────
    if man.get("gaps"):
        story += [Spacer(1, 14), Paragraph("Gaps — what is needed before some of these can move", S_H),
                  grid(["Need", "What it blocks", "Who"],
                       [[x["need"], x["blocks"], x.get("who", "")] for x in man["gaps"]],
                       [2.6, 3.15, 1.1])]

    if man.get("closing"):
        story += [Spacer(1, 14), Paragraph(esc(man["closing"]), S_NOTE)]

    SimpleDocTemplate(out_path, pagesize=letter,
                      leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                      topMargin=0.8 * inch, bottomMargin=0.75 * inch,
                      title=f"Outward communications review — {as_of}").build(
        story, onFirstPage=footer, onLaterPages=footer)
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("-o", "--out")
    ap.add_argument("--open", action="store_true")
    a = ap.parse_args()
    with open(a.manifest) as fh:
        man = json.load(fh)
    out = a.out or a.manifest.replace(".json", ".pdf")
    build(man, out)
    print(out)
    if a.open:
        subprocess.run(["open", out])


if __name__ == "__main__":
    main()
