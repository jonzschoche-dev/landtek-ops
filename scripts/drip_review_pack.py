#!/usr/bin/env python3
"""drip_review_pack.py — render EVERY pending drip email to one PDF for operator review/markup.

Runs on the Mac (reportlab + fonts); reads the live drip state on the VPS over ssh. The letter text
comes from drip_sweep's own pure renderers (render_edition / PARTIAL_REPLY_BODY), so what you read
here is byte-identical to what would stage — no drifting copy.

Shows, per pending item: WHEN it fires · TO · SUBJECT · the body verbatim · annexes to attach · where
it stages. Plus an honest "not in this pack and why" page (clocks with no service, held rows).

  python3 scripts/drip_review_pack.py                 # → case_work/MWK-001/DRIP_PENDING_REVIEW_<date>.pdf
  python3 scripts/drip_review_pack.py --open          # and open it
"""
from __future__ import annotations

import json
import subprocess
import sys
import os
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import drip_sweep as DRIP

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import black, Color
from reportlab.lib.enums import TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                PageBreak, KeepTogether)

VPS = "root@100.85.203.58"
PSQL = "docker exec -i n8n-postgres-1 psql -U n8n -d n8n -t -A -F '|' -c"
OUTDIR = "/Users/jonathanzschoche/landtek/case_work/MWK-001"
F = "/System/Library/Fonts/Supplemental"
GREY = Color(0.42, 0.42, 0.42)
RULE = Color(0.75, 0.75, 0.75)
BOXBG = Color(0.955, 0.955, 0.95)

for name, fn in (("TNR", "Times New Roman.ttf"), ("TNR-Bold", "Times New Roman Bold.ttf"),
                 ("TNR-Italic", "Times New Roman Italic.ttf")):
    pdfmetrics.registerFont(TTFont(name, f"{F}/{fn}"))
pdfmetrics.registerFontFamily("TNR", normal="TNR", bold="TNR-Bold", italic="TNR-Italic")

S_TITLE = ParagraphStyle("t", fontName="TNR-Bold", fontSize=17, leading=21, spaceAfter=2)
S_SUB = ParagraphStyle("s", fontName="TNR-Italic", fontSize=10, leading=13, textColor=GREY, spaceAfter=10)
S_H = ParagraphStyle("h", fontName="TNR-Bold", fontSize=12.5, leading=15, spaceBefore=12, spaceAfter=5)
S_BODY = ParagraphStyle("b", fontName="TNR", fontSize=10.5, leading=14.5, alignment=TA_LEFT)
S_LETTER = ParagraphStyle("l", fontName="TNR", fontSize=10.5, leading=15, leftIndent=10, rightIndent=10)
S_MONO = ParagraphStyle("m", fontName="Courier", fontSize=8.4, leading=11.4, leftIndent=10)
S_NOTE = ParagraphStyle("n", fontName="TNR-Italic", fontSize=9.2, leading=12, textColor=GREY)
S_CELL = ParagraphStyle("c", fontName="TNR", fontSize=9.2, leading=12)
S_CELLB = ParagraphStyle("cb", fontName="TNR-Bold", fontSize=9.2, leading=12)


def q(sql):
    out = subprocess.run(["ssh", "-o", "ConnectTimeout=25", VPS, f'{PSQL} "{sql}"'],
                         capture_output=True, text=True, timeout=120)
    if out.returncode:
        sys.exit(f"query failed: {out.stderr[:300]}")
    return [l.split("|") for l in out.stdout.strip().splitlines() if l.strip()]


def esc(t):
    return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def kv_box(rows):
    data = [[Paragraph(f"<b>{esc(k)}</b>", S_CELLB), Paragraph(esc(v), S_CELL)] for k, v in rows]
    t = Table(data, colWidths=[1.35 * inch, 5.4 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BOXBG),
        ("BOX", (0, 0), (-1, -1), 0.6, RULE), ("INNERGRID", (0, 0), (-1, -1), 0.3, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return t


def letter_block(body):
    """The email body verbatim, in a ruled box so markup has somewhere to go."""
    paras = []
    for chunk in body.split("\n\n"):
        chunk = chunk.rstrip()
        if not chunk:
            continue
        if chunk.lstrip().startswith(("Annex A", "  ")) or "days   " in chunk:
            paras.append(Paragraph(esc(chunk).replace("\n", "<br/>"), S_MONO))
        else:
            paras.append(Paragraph(esc(chunk).replace("\n", "<br/>"), S_LETTER))
        paras.append(Spacer(1, 6))
    t = Table([[paras]], colWidths=[6.9 * inch])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, black),
                           ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                           ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
    return t


def footer(canv, doc):
    canv.saveState()
    canv.setFont("TNR-Italic", 8)
    canv.setFillColor(GREY)
    canv.drawString(0.85 * inch, 0.5 * inch,
                    "DRIP pending-email review pack — DRAFTS ONLY. Nothing has been sent. "
                    "LandTek builds; Jonathan + counsel pull.")
    canv.drawRightString(7.65 * inch, 0.5 * inch, f"p. {canv.getPageNumber()}")
    canv.restoreState()


def main():
    today = date.today()
    eds = q("SELECT id,track,matter_code,edition_date,next_edition_due,state,counters FROM drip_edition ORDER BY id")
    obs = q("SELECT id,officer,state,coalesce(served_at::text,''),coalesce(due_at::text,''),"
            "left(obligation,70),coalesce(consequence_ref,''),coalesce(counsel_gate,'') "
            "FROM office_obligation ORDER BY id")

    story = []
    # ── cover ─────────────────────────────────────────────────────────────────────────────────────
    story += [Paragraph("THE DRIP — Pending Email Review Pack", S_TITLE),
              Paragraph(f"Generated {today.isoformat()} · MWK-001 · every item below is a DRAFT for your "
                        "review and markup. Nothing sends itself.", S_SUB)]

    pending = []
    for e in eds:
        _id, track, matter, ed_date, nxt, state, counters = e
        pending.append(("Edition letter", f"{track} — Schedule of Continuing Default",
                        nxt or "—", "drafts to Gmail (file fallback until compose scope)"))
    pending.append(("Same-day reply", "Partial is not compliance (template)",
                    "on any recorded partial", "drafts on --record-reply … --kind partial"))

    rows = [[Paragraph("<b>Type</b>", S_CELLB), Paragraph("<b>Item</b>", S_CELLB),
             Paragraph("<b>Fires</b>", S_CELLB), Paragraph("<b>Stages to</b>", S_CELLB)]]
    for p in pending:
        rows.append([Paragraph(esc(p[0]), S_CELL), Paragraph(esc(p[1]), S_CELL),
                     Paragraph(esc(p[2]), S_CELL), Paragraph(esc(p[3]), S_CELL)])
    t = Table(rows, colWidths=[1.15 * inch, 2.75 * inch, 1.25 * inch, 1.75 * inch])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.7, black),
                           ("INNERGRID", (0, 0), (-1, -1), 0.3, RULE),
                           ("BACKGROUND", (0, 0), (-1, 0), BOXBG),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story += [t, Spacer(1, 12),
              Paragraph("How to mark this up: strike or annotate anything on the letter pages; tell me the "
                        "change and I edit the generator, so the correction persists into every future "
                        "edition rather than being re-typed each cycle.", S_NOTE)]

    # ── one page per pending email ────────────────────────────────────────────────────────────────
    for e in eds:
        _id, track, matter, ed_date, nxt, state, counters_raw = e
        fire = date.fromisoformat(nxt) if nxt else today
        ed = {"track": track, "counters": json.loads(counters_raw) if counters_raw else {}}
        subject, body = DRIP.render_edition(ed, fire)
        story += [PageBreak(), Paragraph(f"1. Edition letter — {esc(track)}", S_H),
                  kv_box([("FIRES", f"{nxt} (in {(fire - today).days} days) — then every 15 days"),
                          ("TO", "— not on file — office address needed before send"),
                          ("SUBJECT", subject),
                          ("MATTER", f"{matter} · edition state: {state}"),
                          ("STAGES TO", "Gmail Drafts (currently file fallback: case_work/MWK-001/drip_drafts/)"),
                          ("SOURCE", "drip_sweep.render_edition — counters recomputed from the record")]),
                  Spacer(1, 10), Paragraph("Body as it would send:", S_NOTE), Spacer(1, 4),
                  letter_block(body), Spacer(1, 10),
                  Paragraph("<b>ANNEX A — Schedule of Continuing Default</b> (travels as an ATTACHMENT; "
                            "kept out of the letter so the letter is always one page):", S_BODY),
                  Spacer(1, 4), letter_block(DRIP.render_schedule_annex(ed, fire)), Spacer(1, 8),
                  Paragraph("Annexes B–D — <b>not yet auto-built</b> (attach manually this cycle): "
                            "B the prior instruments of record · C proofs of receipt · D verbatim "
                            "provisions relied on.", S_NOTE)]

    # partial-reply template
    story += [PageBreak(), Paragraph("2. Same-day reply — “Partial is not compliance”", S_H),
              kv_box([("FIRES", "the day you record a partial response (--record-reply … --kind partial)"),
                      ("TO", "— the responding office —"),
                      ("SUBJECT", "[DRIP DRAFT] Partial is not compliance — <officer>"),
                      ("STAGES TO", "Gmail Drafts (file fallback until compose scope)"),
                      ("SOURCE", "drip_sweep.PARTIAL_REPLY_BODY — one string, shared with the sender")]),
              Spacer(1, 10), Paragraph("Body as it would send:", S_NOTE), Spacer(1, 4),
              letter_block(DRIP.PARTIAL_REPLY_BODY)]

    # ── what is NOT here, and why ─────────────────────────────────────────────────────────────────
    story += [PageBreak(), Paragraph("Not in this pack — and why", S_H),
              Paragraph("Lapse consequences are <b>not emails</b>: a lapsed clock stages a work order for a "
                        "pre-built filing (Ombudsman / CSC / LBAA), which counsel pulls. None are pending "
                        "because <b>no clock is running</b> — service exists only as a corpus document:", S_BODY),
              Spacer(1, 6)]
    orows = [[Paragraph("<b>#</b>", S_CELLB), Paragraph("<b>Officer</b>", S_CELLB),
              Paragraph("<b>State</b>", S_CELLB), Paragraph("<b>Clock</b>", S_CELLB),
              Paragraph("<b>On lapse</b>", S_CELLB)]]
    for o in obs:
        oid, officer, st, served, due, what, conseq, gate = (o + [""] * 8)[:8]
        clock = f"due {due}" if due else "no clock (unserved)"
        orows.append([Paragraph(oid, S_CELL), Paragraph(esc(officer), S_CELL),
                      Paragraph(esc(st), S_CELL), Paragraph(clock, S_CELL),
                      Paragraph(esc((conseq or "—")[:60]), S_CELL)])
    t2 = Table(orows, colWidths=[0.3 * inch, 1.25 * inch, 1.45 * inch, 1.35 * inch, 2.55 * inch])
    t2.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.7, black),
                            ("INNERGRID", (0, 0), (-1, -1), 0.3, RULE),
                            ("BACKGROUND", (0, 0), (-1, 0), BOXBG),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    story += [t2, Spacer(1, 10),
              Paragraph("Also excluded on purpose: (a) the 2026-09-11 file in drip_drafts/ — a go-live "
                        "<i>demo</i> artifact, superseded by the 25 Sep edition; (b) the held instruments in "
                        "case_work (BLGF / CSC / ARTA / Guerrero drafts) — those are other lanes under the "
                        "8 Sep process flag, not drip output. Say the word if you want them in a second pack.",
                        S_NOTE)]

    out = f"{OUTDIR}/DRIP_PENDING_REVIEW_{today.isoformat()}.pdf"
    SimpleDocTemplate(out, pagesize=letter,
                      leftMargin=0.85 * inch, rightMargin=0.85 * inch,
                      topMargin=0.8 * inch, bottomMargin=0.75 * inch,
                      title=f"DRIP pending email review — {today.isoformat()}").build(
        story, onFirstPage=footer, onLaterPages=footer)
    print(out)
    if "--open" in sys.argv:
        subprocess.run(["open", out])


if __name__ == "__main__":
    main()
