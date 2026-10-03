#!/usr/bin/env python3
"""LandTek investor overview — plain-language DRAFT for Jonathan's review (2026-09-26).

Grounded in MASTER_PLAN §0 + §4A and the live VPS state on 2026-09-26. Clients are described
generically (no names, no case particulars). Every "built" claim is live; everything else is
labelled building / planned / target. Not for external distribution until Jonathan says ready.

    python3 build.py   ->  LandTek_Investor_Overview_DRAFT_2026-09-26.pdf
"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, NextPageTemplate, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)

HERE = Path(__file__).parent
OUT = HERE / "LandTek_Investor_Overview_DRAFT_2026-09-26.pdf"
F = "/System/Library/Fonts/Supplemental/"
pdfmetrics.registerFont(TTFont("Body", F + "Arial.ttf"))
pdfmetrics.registerFont(TTFont("Body-B", F + "Arial Bold.ttf"))
pdfmetrics.registerFont(TTFont("Body-I", F + "Arial Italic.ttf"))
pdfmetrics.registerFont(TTFont("Head", F + "Georgia Bold.ttf"))
pdfmetrics.registerFont(TTFont("Head-I", F + "Georgia Italic.ttf"))
pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-B", italic="Body-I", boldItalic="Body-B")

INK = colors.HexColor("#1d2b36")
NAVY = colors.HexColor("#17324d")
EARTH = colors.HexColor("#5b7f3a")
SAND = colors.HexColor("#f3efe6")
MUTE = colors.HexColor("#5f6b73")
LINE = colors.HexColor("#d5d0c4")
AMBER = colors.HexColor("#b7791f")

W, H = A4
M = 20 * mm

S = {
    "h1": ParagraphStyle("h1", fontName="Head", fontSize=21, leading=26, textColor=NAVY, spaceAfter=4),
    "kicker": ParagraphStyle("k", fontName="Body-B", fontSize=8.5, leading=11, textColor=EARTH,
                             spaceAfter=2),
    "lede": ParagraphStyle("lede", fontName="Head-I", fontSize=12.5, leading=18, textColor=INK,
                           spaceAfter=10),
    "h2": ParagraphStyle("h2", fontName="Body-B", fontSize=11.5, leading=15, textColor=NAVY,
                         spaceBefore=8, spaceAfter=3),
    "p": ParagraphStyle("p", fontName="Body", fontSize=10, leading=14.6, textColor=INK, spaceAfter=6),
    "small": ParagraphStyle("s", fontName="Body", fontSize=8.5, leading=12, textColor=MUTE),
    "cell": ParagraphStyle("c", fontName="Body", fontSize=9, leading=12.4, textColor=INK),
    "cellb": ParagraphStyle("cb", fontName="Body-B", fontSize=9, leading=12.4, textColor=NAVY),
    "step": ParagraphStyle("st", fontName="Body-B", fontSize=8.6, leading=11, textColor=colors.white,
                           alignment=TA_CENTER),
    "bullet": ParagraphStyle("b", fontName="Body", fontSize=10, leading=14.6, textColor=INK,
                             leftIndent=12, bulletIndent=0, spaceAfter=3),
}


def P(t, s="p"):
    return Paragraph(t, S[s])


def bullets(items):
    return [Paragraph(i, S["bullet"], bulletText="•") for i in items]


def table(rows, widths, header=True, zebra=True):
    data = [[P(c, "cellb" if (header and r == 0) else "cell") if isinstance(c, str) else c
             for c in row] for r, row in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
          ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
          ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), SAND), ("LINEBELOW", (0, 0), (-1, 0), 1, NAVY)]
    if zebra:
        for r in range(2 if header else 1, len(rows), 2):
            st.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#faf8f3")))
    t.setStyle(TableStyle(st))
    return t


def status(word):
    col = {"Live": EARTH, "Connecting": AMBER, "Planned": MUTE, "Target": MUTE}[word]
    return Paragraph(f'<font color="{col.hexval()}"><b>{word}</b></font>', S["cell"])


def loop_strip():
    steps = ["Client goal", "Fronts", "Next move", "Approve", "Serve", "Proof of receipt",
             "Clock runs", "Result"]
    cells, widths = [], []
    for i, s in enumerate(steps):
        cells.append(P(s, "step"))
        widths.append(19.2 * mm)
        if i < len(steps) - 1:
            cells.append(Paragraph('<font color="#5b7f3a"><b>›</b></font>',
                                   ParagraphStyle("a", fontName="Body-B", fontSize=13, alignment=TA_CENTER)))
            widths.append(2.9 * mm)
    t = Table([cells], colWidths=widths, rowHeights=[15 * mm])
    st = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 2),
          ("RIGHTPADDING", (0, 0), (-1, -1), 2)]
    for i in range(0, len(cells), 2):
        st.append(("BACKGROUND", (i, 0), (i, 0), NAVY if i < 12 else EARTH))
    t.setStyle(TableStyle(st))
    return t


def on_page(c, doc):
    c.saveState()
    c.setFillColor(NAVY)
    c.rect(0, H - 9 * mm, W, 9 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Body-B", 8)
    c.drawString(M, H - 6 * mm, "LANDTEK")
    c.setFont("Body", 8)
    c.drawRightString(W - M, H - 6 * mm, "Investor overview  ·  DRAFT for internal review  ·  26 Sep 2026")
    c.setFillColor(MUTE)
    c.setFont("Body", 7.5)
    c.drawString(M, 10 * mm, "Confidential draft. Figures marked Target are goals, not results.")
    c.drawRightString(W - M, 10 * mm, f"{doc.page}")
    c.restoreState()


def on_cover(c, doc):
    c.saveState()
    c.setFillColor(NAVY)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setFillColor(EARTH)
    c.rect(0, H * 0.36, W, 3, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Body-B", 11)
    c.drawString(M, H - 30 * mm, "LANDTEK")
    c.setFont("Head", 34)
    c.drawString(M, H * 0.58, "We keep land, business")
    c.drawString(M, H * 0.58 - 42, "and legal matters moving —")
    c.setFont("Head-I", 34)
    c.setFillColor(colors.HexColor("#b9d49a"))
    c.drawString(M, H * 0.58 - 84, "until they land a result.")
    c.setFillColor(colors.white)
    c.setFont("Body", 12)
    c.drawString(M, H * 0.36 - 30, "What LandTek is building, in plain language.")
    c.setFont("Body", 9.5)
    c.setFillColor(colors.HexColor("#c9d3dc"))
    c.drawString(M, 30 * mm, "Investor overview  ·  DRAFT for Jonathan's review  ·  26 September 2026")
    c.drawString(M, 24 * mm, "Not for distribution until approved.")
    c.restoreState()


doc = BaseDocTemplate(str(OUT), pagesize=A4, leftMargin=M, rightMargin=M, topMargin=18 * mm,
                      bottomMargin=18 * mm, title="LandTek — Investor Overview (DRAFT)",
                      author="LandTek")
frame = Frame(M, 16 * mm, W - 2 * M, H - 34 * mm, id="f")
doc.addPageTemplates([PageTemplate("cover", [frame], onPage=on_cover),
                      PageTemplate("body", [frame], onPage=on_page)])
CW = W - 2 * M
story = [NextPageTemplate("body"), PageBreak()]

# ---- 1. The problem --------------------------------------------------------------------------
story += [
    P("THE PROBLEM", "kicker"),
    P("In the Philippines, land and business rights stall — not because owners are wrong, but because nobody keeps them moving.", "h1"),
    P("Owners often have the law on their side and still lose years. The obstacle is rarely a single "
      "decisive fight; it is a thousand small stalls.", "lede"),
]
story += bullets([
    "<b>Records are scattered and unreliable.</b> Titles, deeds, tax declarations and surveys sit in "
    "different offices, often damaged, mis-copied or incomplete. A fraudulent transfer can hide for decades.",
    "<b>Offices don't answer.</b> Requests to registries, assessors and local governments go unanswered "
    "for months. Without steady, documented pressure, nothing happens.",
    "<b>Deadlines slip.</b> Appeal windows of 15 days, response periods, hearing dates — miss one and a "
    "strong position is gone.",
    "<b>Owners are far away or overwhelmed.</b> Heirs abroad, families with many co-owners, small "
    "operators juggling permits — no one has the time to run every thread.",
    "<b>Help is fragmented.</b> A lawyer for the case, a fixer for the permit, a surveyor for the lot, "
    "a bookkeeper for the tax — and nobody who owns the whole picture.",
])
story += [Spacer(1, 6),
          P("<b>The result:</b> valuable land sits idle, occupied by others, or under clouded title; "
            "businesses wait on permits; money that is legally owed is never collected.", "p")]

# ---- 2. What LandTek is -------------------------------------------------------------------------
story += [PageBreak(),
          P("WHAT LANDTEK IS", "kicker"),
          P("A full-service management company for land, business, legal and development.", "h1"),
          P("LandTek takes over the administration of a client's affairs — and keeps every front moving "
            "until it produces a result: possession, payment, or a clean, usable right.", "lede"),
          table([
              ["Line of service", "What we do for the client"],
              ["<b>Property &amp; estate management</b>",
               "Recover and secure land; deal with occupants; collect rents and compensation (held in "
               "trust); pay property taxes; fix titles, surveys and maps."],
              ["<b>Business management</b>",
               "Form and register companies (SEC, BIR, DTI, local permits); obtain operating and "
               "environmental permits; structure deals; prepare investor materials; coordinate development."],
              ["<b>Legal</b> (core expertise)",
               "Research and case strategy; draft demands, affidavits, petitions and pleadings; run "
               "administrative cases before government agencies; manage litigation with partner counsel, "
               "who sign and appear in court."],
              ["<b>Distressed assets &amp; development</b>",
               "Find land the market has written off — clouded, occupied, stuck in an estate — clear it, "
               "and create value with developers and government housing programs."],
          ], [48 * mm, CW - 48 * mm]),
          Spacer(1, 10),
          P("What makes it different", "h2")]
story += bullets([
    "<b>One owner of the whole picture.</b> The client has one company running every thread — not five "
    "providers who never talk to each other.",
    "<b>Truth first.</b> Every fact we rely on is traced to a source document. Where records conflict, "
    "we reconcile them before we act. We measure a case against what the law requires — not against "
    "what the client hopes.",
    "<b>Built to outpace the technology.</b> Each new generation of AI plugs in as it arrives, so the "
    "service keeps getting better and cheaper.",
    "<b>Relentless follow-through.</b> Every demand runs on a clock. When an office misses its deadline, "
    "the next step is already prepared. Nothing lapses quietly.",
])

# ---- 3. How it works --------------------------------------------------------------------------
story += [PageBreak(),
          P("HOW IT WORKS", "kicker"),
          P("Administration is the core: goals in, fronts moving, results out.", "h1"),
          P("Every client goal is broken into fronts. Every front always has a dated next move and an "
            "owner. The loop below runs on every front, every week.", "lede"),
          Spacer(1, 2), loop_strip(), Spacer(1, 12),
          table([
              ["Step", "In plain language"],
              ["<b>Client goal</b>", "What the client actually wants — e.g. \"recover the family land and get "
               "paid for its use\", \"get the processing plant permitted\"."],
              ["<b>Fronts</b>", "The separate paths to that goal — a court case, a records request, a permit, "
               "a negotiation. Each has an objective, the remedy sought, the office or court, the next move, "
               "a date and an owner."],
              ["<b>Next move → Approve</b>", "LandTek drafts the next document or action. A human approves "
               "anything that goes outside the company — always."],
              ["<b>Serve → Proof of receipt</b>", "The document is delivered and the stamped receiving copy "
               "is captured. Only proof of receipt starts the clock."],
              ["<b>Clock runs</b>", "The office's legal deadline counts down. If it performs — done. If it "
               "doesn't — the pre-prepared consequence (escalation, complaint, appeal) is ready the same day."],
              ["<b>Result</b>", "Possession, payment, a registered right, a permit — or the next front opens."],
          ], [42 * mm, CW - 42 * mm]),
          Spacer(1, 10),
          P("The drip", "h2"),
          P("We call the follow-through <b>the drip</b>: a steady, documented stream of correspondence to the "
            "offices that hold a client's rights hostage. Pressure comes from inevitability, not volume — "
            "every office knows the clock is running, the record is being kept, and the next step is already "
            "written.")]

# ---- 4. The Chief of Staff --------------------------------------------------------------------
story += [PageBreak(),
          P("THE PRODUCT", "kicker"),
          P("The Chief of Staff: one assistant that runs the administration for everyone involved.", "h1"),
          P("At the centre of LandTek is an AI Chief of Staff. It watches every goal, front and deadline, "
            "prepares the next move, assigns the work to the right person, and chases until it is done. "
            "Each person sees only what concerns them, in plain language.", "lede"),
          table([
              ["Who", "What they see", "What they do"],
              ["<b>LandTek owner</b>", "\"Today\": what moved, what stalled, what needs a decision",
               "Approve or reject with one tap"],
              ["<b>Field staff</b>", "A task list: print, deliver, collect the stamped copy — with address "
               "and deadline", "Mark done and upload proof"],
              ["<b>Clients</b>", "Their goals, progress, next steps, money recovered and collected",
               "Answer questions; approve what needs their signature"],
              ["<b>Partner lawyers</b>", "Only their cases: a complete, bound case file and what is due",
               "Review, sign, appear in court"],
              ["<b>The system's own agents</b>", "Work assigned to them", "Research, draft, check, report back"],
          ], [34 * mm, 78 * mm, CW - 112 * mm]),
          Spacer(1, 10),
          P("Its daily rhythm", "h2")]
story += bullets([
    "<b>Morning</b> — sets each person's one to three moves for the day.",
    "<b>All day</b> — files every incoming email, scan and reply against the right front and moves it forward.",
    "<b>Evening</b> — reports what moved and what slipped, and chases whoever owns the slipped items.",
    "<b>Weekly</b> — reviews every goal with the owner; anything stalled for a week is re-planned or escalated.",
])
story += [Spacer(1, 6), P("Its rules", "h2")]
story += bullets([
    "Nothing leaves the company without a human's approval.",
    "It never presents a guess as a fact — anything unverified is labelled as such.",
    "Each client's information is walled off from every other client's.",
])

# ---- 5. What's built vs. building -------------------------------------------------------------
story += [PageBreak(),
          P("WHERE WE ARE", "kicker"),
          P("The engine is largely built. What we are building now is the part people touch.", "h1"),
          P("An honest status of each piece, as of September 2026.", "lede"),
          table([
              ["Piece", "What it does", "Status"],
              ["Evidence library", "Every client document read, indexed and searchable (2,277 documents "
               "today), each fact traced to its source", status("Live")],
              ["Title &amp; records engine", "Reconstructs chains of title and flags broken or suspicious "
               "transfers", status("Live")],
              ["Deadline &amp; calendar engine", "Finds dates in documents and turns approaching deadlines "
               "into work", status("Live")],
              ["Truth checks", "Hundreds of automatic checks that stop invented or unsupported facts", status("Live")],
              ["Private AI", "Most AI work runs on our own hardware at near-zero cost, keeping client files in-house by default",
               status("Live")],
              ["Parcel maps", "Draws a client's land on a map; shows the owner whether they stand inside "
               "their boundary (internal use so far)", status("Live")],
              ["The drip", "Tracks every demand on a clock from proof of receipt", status("Connecting")],
              ["Chief of Staff", "Runs the goal → front → result loop and the daily rhythm", status("Connecting")],
              ["Stakeholder views", "Plain-language screens for owner, staff, clients and lawyers",
               status("Connecting")],
              ["Model router", "Sends each task to the best AI for it; swap models by setting",
               status("Connecting")],
              ["Standard tool interface", "Lets any AI agent operate the platform under its rules",
               status("Planned")],
              ["Distressed-asset scoring", "Scores properties on six readiness axes and queues preparation "
               "moves", status("Live")],
              ["Developer &amp; housing partnerships", "Joint ventures and program sales on cleared land",
               status("Planned")],
              ["Client portal &amp; mobile app", "Clients follow their own matters and maps", status("Planned")],
              ["Property management", "Tenants, rents, leases, maintenance", status("Planned")],
              ["Finance", "Per-client accounting, billing and return on each matter", status("Planned")],
          ], [44 * mm, CW - 44 * mm - 26 * mm, 26 * mm]),
          Spacer(1, 8),
          P("<b>Live</b> = running today.  <b>Connecting</b> = the parts exist and are being joined into the "
            "product.  <b>Planned</b> = designed, not yet built.", "small")]

# ---- 5b. Built to outpace the technology -------------------------------------------------------
story += [PageBreak(),
          P("BUILT TO OUTPACE THE TECHNOLOGY", "kicker"),
          P("Every new generation of AI makes LandTek better — not obsolete.", "h1"),
          P("AI models, reading engines and chat apps change every few months. The law, the land records, "
            "the client's goals and the work of driving them to a result do not. LandTek owns the part that "
            "lasts and rents the part that changes.", "lede"),
          table([
              ["What LandTek owns and hardens", "What LandTek rents and replaces"],
              ["The verified record — every fact traced to its source", "AI models — whichever is best this month"],
              ["The Chief of Staff loop — goals, fronts, clocks, results", "Document-reading and vision engines"],
              ["The safety rules — sources, client walls, human approval", "Agent frameworks"],
              ["Philippine know-how — law, agency playbooks, title logic", "Channels — chat apps, email, web, mobile"],
              ["The original documents and text", "Search indexes — rebuilt from the text at any time"],
          ], [CW / 2, CW / 2]),
          Spacer(1, 10),
          P("How it stays ahead", "h2")]
story += bullets([
    "<b>Any AI can plug in.</b> Work is routed by the task it needs — read, extract, draft, reason — not by a "
    "vendor's name. Switching to a better model is a setting, not a rebuild.",
    "<b>Any AI agent can run it.</b> The platform exposes its work as standard tools, so the best agent "
    "available can operate LandTek — under the same safety rules — the day it is released.",
    "<b>New technology earns its place.</b> Every new model is tested against a fixed set of real, verified "
    "LandTek tasks and goes live only if it scores better.",
    "<b>Few moving parts.</b> One brain, one scheduler, one record of work — so change is fast and safe.",
])
story += [Spacer(1, 6), P("The measures we hold ourselves to", "h2"),
          table([
              ["Measure", "Target"],
              ["A better AI model is live on LandTek's work", "within 7 days of release"],
              ["A change goes from idea to live", "the same day"],
              ["Moving parts in the system", "fewer every month"],
          ], [CW - 60 * mm, 60 * mm]),
          Spacer(1, 4),
          P('<font color="#b7791f"><b>Status:</b></font> the design is set; the model router is being connected and the '
            "standard tool interface is next. Today most AI work already runs on owned hardware at "
            "near-zero cost.", "small")]

# ---- 6. Proof clients -------------------------------------------------------------------------
story += [PageBreak(),
          P("PROOF CLIENTS", "kicker"),
          P("Three live engagements prove the model across land, mining and development.", "h1"),
          P("Described generically to protect client confidentiality.", "lede"),
          table([
              ["Client", "The situation", "What LandTek runs"],
              ["<b>A heritage estate</b>",
               "A family estate of about 14 hectares, subdivided into dozens of lots over decades — many "
               "transferred under an authority the family says was exceeded and later revoked. Heirs live abroad.",
               "Title reconstruction; a civil case with partner counsel; guardianship; collection of a "
               "court-awarded land compensation; accountability cases against unresponsive offices; "
               "demands to occupants."],
              ["<b>A landholding family in a mining district</b>",
               "Family land, farm and a small gold-processing operation; an estate needing administration; "
               "tenants and occupants; a government land-reform compensation claim.",
               "Business registration and permits for the processing plant; estate administration; "
               "compensation claim; tenancy and occupant matters."],
              ["<b>An exploration-stage developer</b>",
               "A company holding an exploration application in a mineral district, seeking partners.",
               "Permit tracking (endorsed by the regional mining bureau for an exploration permit); "
               "deal structuring; investor materials."],
          ], [36 * mm, 64 * mm, CW - 100 * mm]),
          Spacer(1, 10),
          P("<b>Scale today:</b> 3 clients · 26 active matters · 2,277 documents under management. "
            "The same engine serves each client without mixing their data.", "p")]

def tag(t, kind):
    col = {"V": "#5b7f3a", "EST": "#b7791f", "SET": "#b7791f", "OPEN": "#5f6b73", "VERIFY": "#b7791f"}[kind]
    return f'{t} <font color="{col}" size="7"><b>[{kind}]</b></font>'


# ---- 6b. Distressed assets -> value ----------------------------------------------------------
story += [PageBreak(),
          P("THE GROWTH ENGINE", "kicker"),
          P("Find distressed land, clear it, and turn it into development value.", "h1"),
          P("The same skills that recover a family's estate can unlock land that the market has written "
            "off. Distressed land is cheap because it is hard — and hard is what LandTek is built for.", "lede"),
          P("What makes land \"distressed\"", "h2"),
          table([
              ["Problem", "Why the market avoids it", "What LandTek does"],
              ["Clouded or broken title", "Fraudulent transfers, lost annotations, missing links in the chain",
               "Reconstructs the chain, finds the void instruments, clears or quiets the title"],
              ["Estate in limbo", "Heirs abroad, no administrator, no one with authority to sign",
               "Assembles authority — special powers, guardianship, administration"],
              ["Occupied land", "Informal settlers, bad-faith builders, a government office on private land",
               "Maps every occupant; negotiates compensation, relocation, regularisation or sale"],
              ["Tax-delinquent or unassessed", "Arrears, penalties, auction risk, wrong assessment",
               "Reconciles the tax record, settles or contests, corrects the assessment roll"],
              ["Unsurveyed or unmapped", "No reliable boundaries, overlaps with neighbours",
               "Plots boundaries from the survey record; flags overlaps and encroachment"],
          ], [40 * mm, 58 * mm, CW - 98 * mm]),
          Spacer(1, 10),
          P("The value ladder", "h2"),
          table([
              ["1. Identify", "2. Secure control", "3. Clear", "4. Package", "5. Partner", "6. Share the uplift"],
              ["Score each property on documents, status, occupants, ownership, title and mapping",
               "Management agreement, special power of attorney, option or joint-venture commitment from the owners",
               "Title, taxes, occupants, survey",
               "A ready-to-build file: clean title, map, valuation, zoning, occupant plan",
               "Developer, government housing program, buyer or long-term tenant",
               "Fee plus an agreed share of the value created"],
          ], [CW / 6] * 6, zebra=False),
          Spacer(1, 8),
          P(f"<b>Already running:</b> the identification step is live. The engine scores every property in "
            f"its inventory on six readiness axes and queues the next preparation move automatically — "
            f"{tag('83 properties scored; 1,127 preparation moves queued', 'V')} across current clients. "
            "Opening it to properties outside the client base is the next step.")]

# ---- 6c. Developers & government housing -----------------------------------------------------
story += [PageBreak(),
          P("PARTNERS IN DEVELOPMENT", "kicker"),
          P("Working with developers and government housing programs.", "h1"),
          P("LandTek does not need to build. It delivers what builders cannot easily get: land that is "
            "clean, mapped, occupant-resolved and ready to develop — and it runs the paperwork with the "
            "government on both sides.", "lede"),
          table([
              ["Partner", "What they need", "What LandTek brings"],
              ["<b>Private developers</b>",
               "Development-ready land; sites to meet their legal duty to provide socialized housing "
               f"alongside their projects {tag('', 'VERIFY')}",
               "Sourcing, title clearing, occupant resolution, joint-venture structuring, permit administration"],
              ["<b>National housing programs</b> (DHSUD and its partner agencies)",
               f"Land for mass housing under the national housing program {tag('', 'VERIFY')}",
               "Packaged sites; coordination with local government and the program's requirements"],
              ["<b>Housing finance agencies</b> (e.g. Pag-IBIG, community mortgage programs)",
               f"Organised occupant-buyers and clean collateral {tag('', 'VERIFY')}",
               "Turning existing occupants into buyers of the land they live on — instead of eviction"],
              ["<b>Local governments</b>",
               "Land for public use and relocation; a lawful exit from occupying private land",
               "Negotiated sale or compensation at fair value; land-banking packages"],
          ], [40 * mm, 60 * mm, CW - 100 * mm]),
          Spacer(1, 10),
          P("Deal forms", "h2")]
story += bullets([
    "<b>Joint venture</b> — the landowner contributes cleared land, the developer builds; the owner receives "
    "an agreed share of units or revenue, and LandTek a fee plus a share.",
    "<b>Sale to a program or government</b> — at fair value, with LandTek paid on the value it unlocked.",
    "<b>Occupant-to-owner</b> — long-time occupants buy their lots through a community mortgage program; "
    "conflict becomes a sale.",
    "<b>Long lease</b> — for land the family wants to keep.",
])
story += [Spacer(1, 6), P("Candidates already in hand", "h2"),
          table([
              ["Property (current clients)", "Why it fits"],
              ["About 14 ha of estate land in a provincial town, partly occupied", "Occupied lots → occupant-to-owner or "
               "socialized housing; clean core → joint venture"],
              ["Estate land occupied by the local government", "Negotiated sale or compensation instead of years of litigation"],
              ["13-ha ricefield and a 23-ha lot (second client)", "Land-banking or development joint venture"],
          ], [70 * mm, CW - 70 * mm]),
          Spacer(1, 4),
          P('<font color="#b7791f"><b>Status:</b></font> planned. No developer or housing-program partnership '
            "exists yet; the candidates above are internal assessments, not deals.", "small")]

# ---- 7. The financial arrangement ------------------------------------------------------------
story += [PageBreak(),
          P("THE FINANCIAL ARRANGEMENT", "kicker"),
          P("Who pays whom, for what — and who owns what.", "h1"),
          P("One rule runs through it: client money is held in trust and accounted for; LandTek is paid for "
            "running the work and for the value it recovers; the platform's owner is paid a licence royalty.",
            "lede"),
          table([
              ["Money moves", "From → To", "What it is", "Basis"],
              ["<b>1. Management fee</b>", "Client → LandTek (operating co.)",
               "Monthly fee for running the client's affairs", tag("₱__ /month or __% of collections", "OPEN")],
              ["<b>2. Success fee</b>", "Client → LandTek",
               "Share of value actually recovered or collected — land compensation, back-rent, sale proceeds",
               tag("__% of net recovered", "OPEN")],
              ["<b>3. Retainers</b>", "Business / legal clients → LandTek",
               "Monthly retainer for business and legal management", tag("target ₱15–50k /month", "EST")],
              ["<b>4. Expense advances</b>", "LandTek or client → costs, repaid from proceeds",
               "Government fees, taxes, travel, records, counsel — advanced, then reimbursed from what is recovered",
               tag("charged against proceeds", "SET")],
              ["<b>5. Trust collections</b>", "Occupants / debtors → client trust account",
               "Rents, compensation and judgment money collected for the client; never LandTek's money; each "
               "co-owner's share kept separate; quarterly accounting", tag("held in trust", "SET")],
              ["<b>6. Licence royalty</b>", "LandTek → platform owner",
               "LandTek licenses the technology platform; the platform and its IP stay with its owner",
               tag("__% of revenue or ₱__ /month", "OPEN")],
              ["<b>7. Development share</b>", "Developer / program → owner and LandTek",
               "On joint ventures and sales of cleared land: the owner's share of units or proceeds, and "
               "LandTek's fee plus agreed share of the uplift", tag("per deal", "OPEN")],
              ["<b>8. Operating profit</b>", "LandTek → its owner",
               "What remains after costs and the royalty", tag("residual", "SET")],
          ], [30 * mm, 38 * mm, CW - 30 * mm - 38 * mm - 36 * mm, 36 * mm]),
          Spacer(1, 8),
          P('<font color="#5b7f3a"><b>[V]</b></font> verified from source documents · '
            '<font color="#b7791f"><b>[EST]</b></font> estimate · '
            '<font color="#b7791f"><b>[SET]</b></font> set in the draft agreement · '
            '<font color="#5f6b73"><b>[OPEN]</b></font> number not yet decided', "small"),
          Spacer(1, 8),
          P("Mining is a separate vehicle", "h2"),
          P("Mining and processing assets sit in their own companies (a Philippine operating company with a "
            "Canadian partner company holding a minority stake), never mixed with estate money. LandTek's role "
            "there is paid services — permits, registrations, administration — at arm's length. The founders' "
            "participation in those projects (royalty share, project shares) is negotiated separately "
            f"{tag('', 'OPEN')}.")]

# ---- 8. Value in motion -----------------------------------------------------------------------
story += [PageBreak(),
          P("VALUE IN MOTION", "kicker"),
          P("What LandTek's fees are a share of.", "h1"),
          P("The flagship estate alone carries a mapped, source-traced revenue picture. These are the "
            "<i>client's</i> amounts — LandTek earns its fee on what is actually collected.", "lede"),
          P("Flagship heritage estate — money that can come to the client", "h2"),
          table([
              ["Stream", "Verified floor", "With estimates", "What unlocks it"],
              ["Court-awarded land compensation (a government bank owes it)", tag("₱5.1M principal", "V"),
               tag("₱15–25M with 30+ years' interest", "EST"), "Authority to collect (guardianship / SPA) + writ of execution"],
              ["Local government's use of estate land (compensation + back-rental)", tag("₱10.4M", "V"),
               tag("₱25–29M", "EST"), "Negotiation or case; the town's own 1996 record admits the defect"],
              ["Back-rent from bad-faith occupants", "—", tag("₱0.75–1.5M (one occupant)", "EST"),
               "Added to cases already running"],
              ["Rent on whole parcels", "—", tag("₱150–280k /month", "EST"), "Court-approved lease after guardianship"],
              ["Sale of the clean residential core", tag("₱48M", "V"), "—", "Court-approved sale after guardianship"],
          ], [56 * mm, 30 * mm, 42 * mm, CW - 128 * mm]),
          Spacer(1, 4),
          P("Land base behind the sale and recovery streams: about ₱90.9M assessed market value. "
            "Verified floors alone come to about ₱64M; estimates run higher. Timing depends on the court "
            "and on authority to act for all co-owners — these are not promised cash dates.", "small"),
          Spacer(1, 6),
          P("Second client — family assets under management (owner's estimates)", "h2"),
          table([
              ["Asset", "Est. value", "Est. income", "Path"],
              ["10-unit apartment building, Manila", tag("₱40M", "EST"), tag("₱200k /month", "EST"), "Lease now; sale option"],
              ["Beach resort property", tag("₱60M", "EST"), "—", "Development or sale"],
              ["23-ha lot with mineral potential", tag("₱25M", "EST"), "—", "Development"],
              ["13-ha ricefield", tag("₱13M", "EST"), tag("₱50k /month", "EST"), "Lease after rehabilitation"],
              ["Residential lot", tag("₱2.5M", "EST"), tag("₱15k /month", "EST"), "Sale"],
          ], [60 * mm, 30 * mm, 34 * mm, CW - 124 * mm]),
          Spacer(1, 8),
          P("Illustration only — what a success fee would mean", "h2"),
          table([
              ["If LandTek collects for the flagship estate…", "at 10% success fee", "at 15%", "at 20%"],
              ["Verified floors only (~₱64M over time)", "₱6.4M", "₱9.6M", "₱12.8M"],
              ["Compensation + back-rental streams only (₱15.5M verified → ~₱40–55M est.)",
               "₱1.6–5.5M", "₱2.3–8.3M", "₱3.1–11M"],
          ], [80 * mm, 30 * mm, 30 * mm, CW - 140 * mm]),
          P('<font color="#b7791f"><b>Fee percentages are not set.</b></font> This table shows scale, not a forecast.',
            "small")]

# ---- 9. Costs & margin ------------------------------------------------------------------------
story += [PageBreak(),
          P("COSTS &amp; MARGIN", "kicker"),
          P("The software is nearly free to run. People and government fees are the real costs.", "h1"),
          Spacer(1, 2),
          table([
              ["Cost", "Today", "Notes"],
              ["Cloud server (database, bots, web)", tag("about US$16 /month", "V"), "One server runs the whole engine"],
              ["AI processing", tag("about ₱0", "V"), "About 99% runs on owned hardware; paid AI is capped and nearly unused"],
              ["People", tag("1 filing assistant + founder", "V"), "Field service, delivery, filing; the main cost that grows with clients"],
              ["Partner lawyers", "per case", "Paid per engagement; recoverable from proceeds where the agreement allows"],
              ["Government fees, taxes, travel", "per matter", "Advanced, then reimbursed from proceeds"],
          ], [52 * mm, 44 * mm, CW - 96 * mm]),
          Spacer(1, 10),
          P("Already invested in the flagship estate", "h2"),
          P(f"About {tag('₱2.0M', 'V')} has been advanced on the flagship estate so far — property taxes "
            "(₱1.09M), travel and lodging (₱0.38M), professional fees (₱0.23M), office and administration "
            "(₱0.20M), research and tools (₱0.10M). It is recorded, receipt by receipt, as reimbursable from "
            "the estate's proceeds under the co-owners' duty to share preservation costs."),
          Spacer(1, 6),
          P("Why the margin can be high", "h2")]
story += bullets([
    "The expensive work — reading documents, tracking deadlines, drafting — is done by software on owned "
    "hardware at near-zero marginal cost.",
    "People are used only where only people can act: approving, delivering, appearing in court.",
    "Direct matter costs are advanced and reimbursed, not absorbed.",
    f"Target: operating margin above 85% per client once the product is fully connected {tag('', 'EST')} — "
    "a goal, not a result yet.",
])

# ---- 10. Where an investor fits ---------------------------------------------------------------
story += [PageBreak(),
          P("WHERE AN INVESTOR FITS", "kicker"),
          P("Three possible entry points — to be decided.", "h1"),
          P("The structure keeps client money, the operating company and the technology separate, so an "
            "investor can choose what they are buying into.", "lede"),
          table([
              ["Entry point", "The investor owns a share of…", "Earns from", "Considerations"],
              ["<b>A. The platform company</b>", "The technology and IP licensed to LandTek (and later to others)",
               "Licence royalties; future licensing to other operators", "Cleanest for foreign investors; value "
               "grows with every client served"],
              ["<b>B. The operating company</b>", "LandTek Property Services OPC",
               "Management fees, success fees, retainers after royalty",
               "Philippine ownership rules limit foreign stakes; would need restructuring from a one-person company"],
              ["<b>C. A specific recovery</b>", "The funding of one matter or collection",
               "An agreed return from that matter's proceeds", "Tied to court timing and authority; "
               "must not interfere with client trust money"],
          ], [34 * mm, 44 * mm, 44 * mm, CW - 122 * mm]),
          Spacer(1, 10),
          P("What the money would do", "h2")]
story += bullets([
    '<font color="#b7791f"><b>[To decide]</b></font> amount and use of funds. Candidates: field staff for '
    "service and delivery; finishing the Chief of Staff and the stakeholder views; funding authority and "
    "collection steps on the flagship estate; onboarding the next clients.",
])
story += [Spacer(1, 6), P("Key financial risks — stated plainly", "h2")]
story += bullets([
    "<b>Authority.</b> Several of the largest streams need court-granted authority to act for all co-owners.",
    "<b>Timing.</b> Courts and agencies are slow; recovered value arrives over years, not months.",
    "<b>Collectibility.</b> A strong claim against a party with no reachable assets is worth little.",
    "<b>Unset terms.</b> Fees, royalty and investor terms are not yet agreed.",
    "<b>Estimates.</b> Many asset values are owner estimates pending formal appraisal.",
])

# ---- 11. Roadmap -------------------------------------------------------------------------------
story += [PageBreak(),
          P("THE ROADMAP", "kicker"),
          P("From a working engine to a product every stakeholder can use.", "h1"),
          Spacer(1, 4),
          table([
              ["Stage", "What happens", "Outcome"],
              ["<b>Now</b><br/>Q4 2026",
               "Win and collect on the live proof-client matters; every client goal dated; the drip "
               "running with real clocks; Chief of Staff v1 running the daily rhythm internally.",
               "Every front has a dated next move; first collections."],
              ["<b>Next</b><br/>H1 2027",
               "Plain-language views for staff, clients and partner lawyers; client portal and parcel maps "
               "switched on client by client; fee agreements signed.",
               "Clients see their own progress; recurring revenue."],
              ["<b>Then</b><br/>H2 2027",
               "Property management (tenants, rents, leases); per-client finance and billing; first developer / housing-program joint venture on cleared client land; onboarding new clients.",
               "Repeatable service; more clients per staff member."],
              ["<b>Later</b>",
               "Acquire or option distressed land outside the client base; more regions; the platform licensed to other operators.",
               "A scalable administration platform."],
          ], [26 * mm, 90 * mm, CW - 116 * mm]),
          Spacer(1, 12),
          P("The opportunity", "h2"),
          P("Idle, clouded and occupied land — and stalled permits — lock up enormous value across the "
            "Philippines. The owners have rights but no one to run them. LandTek is built to be that "
            "someone: a single, tireless administrator that turns rights into results."),
          Spacer(1, 6),
          P("The ask", "h2"),
          P('<font color="#b7791f"><b>[To decide]</b></font> — amount, entry point, use of funds and terms '
            '(see "Where an investor fits").')]

# ---- 12. Review notes (internal) --------------------------------------------------------------
story += [PageBreak(),
          P("FOR JONATHAN — REMOVE BEFORE SENDING", "kicker"),
          P("Points to confirm or adjust.", "h1")]
story += bullets([
    "<b>Headline</b> — does \"We keep land, business and legal matters moving — until they land a result\" say it?",
    "<b>Legal line</b> — wording says partner lawyers sign and appear in court. Right emphasis for investors?",
    "<b>Proof clients</b> — generic descriptions OK? Any client who must be left out entirely, or who "
    "would agree to be named?",
    "<b>Numbers</b> — 3 clients, 26 active matters and 2,277 documents are live counts (26 Sep). The "
    "₱15–50k retainer range and 85% margin are internal targets from the master plan; no fee agreement "
    "is signed yet. Keep, change or drop?",
    "<b>Structure</b> — the platform-licensed-to-OPC paragraph: include, soften, or remove?",
    "<b>Roadmap dates</b> — Q4 2026 / H1 2027 / H2 2027 are my proposal, not commitments. Adjust.",
    "<b>The ask</b> — amount, entry point (platform / operating co. / a specific recovery), use of funds, terms.",
    "<b>Fees</b> — the management fee, success % and royalty are blank in the draft agreements. Pick numbers "
    "and the illustration page becomes a real projection.",
    "<b>Flagship figures</b> — from the estate's revenue map (verified floors vs estimates). Showing client "
    "amounts to investors needs the client's consent — or keep them as ranges only.",
    "<b>Second-client asset values</b> are owner estimates (7 of 83 assets valued) — appraise before relying.",
    "<b>Mining</b> — kept to one paragraph as a separate vehicle; the ₱5M plant financing and founders' "
    "royalty/share positions are deliberately NOT described. Include?",
    "<b>Development line</b> — housing-program facts are from general knowledge, marked VERIFY: confirm the "
    "current national housing program, the developers' socialized-housing duty (the balanced-housing rule) "
    "and community-mortgage terms before this goes out. Should LandTek also BUY or option distressed land "
    "itself (needs capital), or only work for owners?",
    "<b>Missing?</b> — team page (who runs LandTek), traction numbers (money collected so far), or a "
    "single case story told end to end.",
])

doc.build(story)
print(OUT)
