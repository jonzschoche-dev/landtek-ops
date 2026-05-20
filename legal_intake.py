#!/usr/bin/env python3
"""legal_intake — Telegram intake for the legal-profitability foundation.

Three intake flows, all routed through tg_inquiry_queue (one-at-a-time):

  /cost          → enter actual legal spend (counsel/filing/travel/etc.)
  /probability   → counsel's probability estimate per scenario
  /value         → estimated dominion value per matter (low/mid/high band)

Each command takes a matter_code argument; the inquiry composes a structured
ask, the operator's reply is parsed by a small structured-output Haiku call
and persisted to the appropriate table. EVERY row carries source + date.

Also exposes:
  surface_forensic_impact(matter, scenario, rationale, source_evidence)
    — called by forensic_agent when a finding affects an outcome layer.
    Creates a NULL-p_success row tagged "needs counsel adjust" + queues
    an intake item asking counsel for the actual probability.

Per [[feedback_facts_in_chat_are_first_class]] +
[[feedback_no_premature_reports]] (created today): inputs accumulate
in the DB; no synthesis output until the foundation is populated.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/root/landtek")
with open("/root/landtek/.env") as f:
    for line in f:
        if line.startswith("ANTHROPIC_API_KEY="):
            os.environ.setdefault("ANTHROPIC_API_KEY", line.strip().split("=", 1)[1])

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True
    return c


# ─── INTAKE BODIES (the ask templates Jonathan sees in Telegram) ────────────

COST_INTAKE_TEMPLATE = """💰 <b>Cost intake — {matter}</b>
Reply: <code>category | amount | YYYY-MM-DD | description</code>
Categories: counsel_retainer · filing_fee · travel · expert · admin · misc
Or <code>/skip</code>."""

PROBABILITY_INTAKE_TEMPLATE = """🎯 <b>P intake — {matter}</b>
<i>Scenario:</i> {scenario}
{rationale_block}Reply: <code>0.6</code> · <code>0.4-0.7</code> · <code>0.55 source: Barandon</code> · <code>unknown</code> · <code>/skip</code>."""

VALUE_INTAKE_TEMPLATE = """🏠 <b>Value intake — {matter}</b>
<i>Asset:</i> {asset}
Reply: <code>50M</code> · <code>40M-60M</code> · <code>40M/50M/80M</code> · <code>50M basis:zonal-Daet</code> · <code>/skip</code>
Basis: appraisal:NAME:DATE · BIR-zonal:CITY:DATE · comparable:SALE · tax-declaration:ARP · asserted"""


# ─── PARSERS (turn reply text → DB row) ────────────────────────────────

COST_RE = re.compile(
    r"^\s*(counsel_retainer|filing_fee|travel|expert|admin|misc|llm)\s*\|\s*"
    r"([\d,]+(?:\.\d+)?)\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(.+?)\s*$",
    re.IGNORECASE)

VALUE_PHP_RE = re.compile(r"^\s*([\d,]+(?:\.\d+)?)\s*([MmKk]?)\s*$")

def parse_value_token(tok):
    m = VALUE_PHP_RE.match(tok)
    if not m: return None
    n = float(m.group(1).replace(",",""))
    if m.group(2).upper() == "M": n *= 1_000_000
    elif m.group(2).upper() == "K": n *= 1_000
    return n


def parse_cost_reply(text):
    """Returns dict or None."""
    m = COST_RE.match(text.strip().splitlines()[0])
    if not m: return None
    return {"category": m.group(1).lower(),
            "amount_php": float(m.group(2).replace(",","")),
            "incurred_date": m.group(3),
            "description": m.group(4).strip()}


def parse_probability_reply(text):
    """Returns {p, low, high, rationale, source} or None."""
    first = text.strip().splitlines()[0].lower()
    rationale = "\n".join(text.strip().splitlines()[1:]).strip() or None

    if first.startswith("unknown") or first == "?":
        return {"p": None, "low": None, "high": None,
                "rationale": rationale, "source": "operator: unknown"}

    src_m = re.search(r"source:\s*(\S+)", first)
    source = src_m.group(1) if src_m else "operator:telegram-reply"
    main = re.sub(r"source:\s*\S+", "", first).strip()

    # Range "0.4-0.7"
    rm = re.match(r"^([\d.]+)\s*[-–]\s*([\d.]+)\s*$", main)
    if rm:
        lo, hi = float(rm.group(1)), float(rm.group(2))
        return {"p": (lo+hi)/2, "low": lo, "high": hi,
                "rationale": rationale, "source": source}

    # Point "0.55"
    pm = re.match(r"^([\d.]+)\s*$", main)
    if pm:
        p = float(pm.group(1))
        return {"p": p, "low": None, "high": None,
                "rationale": rationale, "source": source}
    return None


BARE_BASIS_WORDS = {"asserted", "zonal", "appraisal", "comparable", "tax-declaration",
                     "tax-dec", "unknown", "guess"}

def parse_value_reply(text):
    """Returns {low, mid, high, basis} or None.
    Accepts: '50M' · '40M-60M' · '40M / 50M / 80M' · '50M asserted'
           · '50M basis: zonal' · '40M-60M basis: zonal-2024-Daet'"""
    first = text.strip().splitlines()[0]

    # 1) Pull out "basis: ..." if present
    basis_m = re.search(r"basis:\s*([^\s]+(?::[^\s]+)*)", first, re.IGNORECASE)
    basis = basis_m.group(1) if basis_m else None
    main = re.sub(r"basis:\s*[^\s]+(?::[^\s]+)*", "", first, flags=re.IGNORECASE).strip()

    # 2) Pull out any bare basis word (asserted / zonal / etc.) as a fallback basis
    if basis is None:
        tokens = main.split()
        keep = []
        for t in tokens:
            if t.lower() in BARE_BASIS_WORDS and basis is None:
                basis = t.lower()
            else:
                keep.append(t)
        main = " ".join(keep).strip()
    if basis is None:
        basis = "asserted"

    # 3) Now parse the cleaned-up `main` for value(s)
    # "40M / 50M / 80M"
    if "/" in main:
        toks = [t.strip() for t in main.split("/")]
        if len(toks) == 3:
            lo, mid, hi = (parse_value_token(t) for t in toks)
            if lo and mid and hi:
                return {"low": lo, "mid": mid, "high": hi, "basis": basis}

    # "40M-60M"
    m_range = re.match(r"^\s*([\d,.]+[MmKk]?)\s*[-–]\s*([\d,.]+[MmKk]?)\s*$", main)
    if m_range:
        lo = parse_value_token(m_range.group(1))
        hi = parse_value_token(m_range.group(2))
        if lo and hi:
            return {"low": lo, "mid": (lo+hi)/2, "high": hi, "basis": basis}

    # Point "50M" (or with trailing space)
    v = parse_value_token(main)
    if v:
        return {"low": None, "mid": v, "high": None, "basis": basis}
    return None


# ─── WRITERS (parsed reply → table row) ────────────────────────────────

def write_cost(matter_code, parsed, source_label):
    with _conn() as c:
        cur = c.cursor()
        cur.execute("""
            INSERT INTO legal_cost_actuals
              (matter_code, category, amount_php, incurred_date, description, source)
            VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
        """, (matter_code, parsed["category"], parsed["amount_php"],
              parsed["incurred_date"], parsed["description"], source_label))
        return cur.fetchone()[0]


def write_probability(matter_code, scenario, parsed):
    with _conn() as c:
        cur = c.cursor()
        # Mark previous active row(s) for this matter+scenario superseded
        cur.execute("""
            UPDATE legal_outcome_estimates SET active=FALSE
             WHERE matter_code=%s AND scenario=%s AND active=TRUE
            RETURNING id
        """, (matter_code, scenario))
        prev = cur.fetchone()
        prev_id = prev[0] if prev else None
        cur.execute("""
            INSERT INTO legal_outcome_estimates
              (matter_code, scenario, p_success, p_success_low, p_success_high,
               rationale, source, supersedes_id, active)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s, TRUE)
            RETURNING id
        """, (matter_code, scenario, parsed["p"], parsed["low"], parsed["high"],
              parsed["rationale"], parsed["source"], prev_id))
        return cur.fetchone()[0]


def write_value(matter_code, asset, parsed):
    with _conn() as c:
        cur = c.cursor()
        cur.execute("""
            UPDATE dominion_value_estimates SET active=FALSE
             WHERE matter_code=%s AND asset_descriptor=%s AND active=TRUE
            RETURNING id
        """, (matter_code, asset))
        prev = cur.fetchone()
        prev_id = prev[0] if prev else None
        cur.execute("""
            INSERT INTO dominion_value_estimates
              (matter_code, asset_descriptor, value_low_php, value_mid_php,
               value_high_php, basis, supersedes_id, active)
            VALUES (%s,%s,%s,%s,%s,%s,%s, TRUE) RETURNING id
        """, (matter_code, asset, parsed["low"], parsed["mid"], parsed["high"],
              parsed["basis"], prev_id))
        return cur.fetchone()[0]


# ─── INTAKE QUEUE ENQUEUERS ────────────────────────────────────────────

def queue_cost_intake(matter_code):
    body = COST_INTAKE_TEMPLATE.format(matter=matter_code)
    with _conn() as c:
        cur = c.cursor()
        cur.execute("""
            INSERT INTO tg_inquiry_queue
              (kind, audience, priority, source_table, matter_code, composed_html, notes)
            VALUES ('intake_item', 'ops', 15, 'legal_intake', %s, %s, %s)
            RETURNING id
        """, (matter_code, body, f"legal_intake:cost:matter={matter_code}"))
        return cur.fetchone()[0]


def queue_probability_intake(matter_code, scenario, rationale=None, source_evidence=None):
    rationale_block = ""
    if rationale:
        rationale_block = f"\n<b>Why this matters:</b> {rationale}\n"
    if source_evidence:
        rationale_block += f"<i>Evidence pointer: {source_evidence}</i>\n"
    body = PROBABILITY_INTAKE_TEMPLATE.format(
        matter=matter_code, scenario=scenario, rationale_block=rationale_block)
    with _conn() as c:
        cur = c.cursor()
        cur.execute("""
            INSERT INTO tg_inquiry_queue
              (kind, audience, priority, source_table, matter_code, composed_html, notes)
            VALUES ('intake_item', 'ops', 15, 'legal_intake', %s, %s, %s)
            RETURNING id
        """, (matter_code, body, f"legal_intake:probability:matter={matter_code}:scenario={scenario[:80]}"))
        return cur.fetchone()[0]


def queue_value_intake(matter_code, asset_descriptor):
    body = VALUE_INTAKE_TEMPLATE.format(matter=matter_code, asset=asset_descriptor)
    with _conn() as c:
        cur = c.cursor()
        cur.execute("""
            INSERT INTO tg_inquiry_queue
              (kind, audience, priority, source_table, matter_code, composed_html, notes)
            VALUES ('intake_item', 'ops', 15, 'legal_intake', %s, %s, %s)
            RETURNING id
        """, (matter_code, body, f"legal_intake:value:matter={matter_code}:asset={asset_descriptor[:80]}"))
        return cur.fetchone()[0]


# ─── FORENSIC → FORECASTER HOOK ────────────────────────────────────────

def surface_forensic_impact(matter_code: str, scenario: str, rationale: str,
                            source_evidence_ref: str | None = None):
    """Called by forensic_agent when a finding affects an outcome layer.
    Creates a NULL-p_success placeholder + queues a counsel-adjust intake.
    Counsel sees the inquiry in Telegram, replies with their probability.
    """
    # 1. Create the placeholder row with NULL probability
    with _conn() as c:
        cur = c.cursor()
        cur.execute("""
            INSERT INTO legal_outcome_estimates
              (matter_code, scenario, p_success, rationale, source, source_evidence_ref)
            VALUES (%s, %s, NULL, %s, 'elite_forensic_agent:surfaced-pending-counsel', %s)
            RETURNING id
        """, (matter_code, scenario, rationale, source_evidence_ref))
        placeholder_id = cur.fetchone()[0]

    # 2. Queue counsel-adjust intake (links to the placeholder via notes)
    inquiry_id = queue_probability_intake(
        matter_code=matter_code, scenario=scenario,
        rationale=rationale, source_evidence=source_evidence_ref)
    return {"placeholder_id": placeholder_id, "inquiry_id": inquiry_id}


# ─── CLI ───────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("cost", help="Queue a cost intake")
    p1.add_argument("--matter", required=True)

    p2 = sub.add_parser("probability", help="Queue a probability intake")
    p2.add_argument("--matter", required=True)
    p2.add_argument("--scenario", required=True)
    p2.add_argument("--rationale")
    p2.add_argument("--evidence")

    p3 = sub.add_parser("value", help="Queue a dominion-value intake")
    p3.add_argument("--matter", required=True)
    p3.add_argument("--asset", required=True)

    p4 = sub.add_parser("surface-impact",
                        help="Forensic agent hook — surface impact + queue counsel adjust")
    p4.add_argument("--matter", required=True)
    p4.add_argument("--scenario", required=True)
    p4.add_argument("--rationale", required=True)
    p4.add_argument("--evidence")

    p5 = sub.add_parser("status", help="Show foundation data state per matter")
    p5.add_argument("--matter", required=True)

    args = ap.parse_args()

    if args.cmd == "cost":
        iid = queue_cost_intake(args.matter)
        print(f"✓ queued cost-intake #{iid} for {args.matter}")
    elif args.cmd == "probability":
        iid = queue_probability_intake(args.matter, args.scenario,
                                        args.rationale, args.evidence)
        print(f"✓ queued probability-intake #{iid} for {args.matter}: {args.scenario}")
    elif args.cmd == "value":
        iid = queue_value_intake(args.matter, args.asset)
        print(f"✓ queued value-intake #{iid} for {args.matter}: {args.asset}")
    elif args.cmd == "surface-impact":
        out = surface_forensic_impact(args.matter, args.scenario,
                                       args.rationale, args.evidence)
        print(f"✓ surfaced impact: placeholder={out['placeholder_id']}, inquiry={out['inquiry_id']}")
    elif args.cmd == "status":
        show_status(args.matter)


def show_status(matter_code):
    """Read-only status — what foundation data we have. NOT a report."""
    conn = _conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print(f"━━━ Foundation data for {matter_code} ━━━\n")

    cur.execute("SELECT COUNT(*) AS n, COALESCE(SUM(amount_php),0) AS total "
                "FROM legal_cost_actuals WHERE matter_code=%s", (matter_code,))
    c = cur.fetchone()
    print(f"Costs:  {c['n']} entries · ₱{c['total']:,.2f} total")

    cur.execute("SELECT scenario, p_success, p_success_low, p_success_high, source, recorded_at "
                "FROM legal_outcome_estimates WHERE matter_code=%s AND active=TRUE "
                "ORDER BY recorded_at DESC", (matter_code,))
    rows = cur.fetchall()
    print(f"\nProbability estimates: {len(rows)}")
    for r in rows:
        if r["p_success"] is None:
            p = "P = unknown (needs counsel input)"
        elif r["p_success_low"] is not None:
            p = f"P = {r['p_success']:.2f} [{r['p_success_low']:.2f}-{r['p_success_high']:.2f}]"
        else:
            p = f"P = {r['p_success']:.2f}"
        print(f"  • {r['scenario'][:70]}")
        print(f"      {p}  ·  source: {r['source']}")

    cur.execute("SELECT asset_descriptor, value_low_php, value_mid_php, value_high_php, basis "
                "FROM dominion_value_estimates WHERE matter_code=%s AND active=TRUE", (matter_code,))
    rows = cur.fetchall()
    print(f"\nDominion value estimates: {len(rows)}")
    for r in rows:
        lo = f"₱{r['value_low_php']:,.0f}" if r['value_low_php'] else "—"
        mid = f"₱{r['value_mid_php']:,.0f}" if r['value_mid_php'] else "—"
        hi = f"₱{r['value_high_php']:,.0f}" if r['value_high_php'] else "—"
        print(f"  • {r['asset_descriptor'][:70]}")
        print(f"      low={lo} · mid={mid} · high={hi}  ·  basis: {r['basis']}")

    conn.close()


if __name__ == "__main__":
    main()
