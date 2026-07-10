#!/usr/bin/env python3
"""incorporation_gate.py — the A70 identity gate: incorporation precedes decision.

`require_incorporation(cur, matter_code, stakeholder)` answers ONE question before a stakeholder-facing
deliverable emits: *has the client-isolated whole for this matter been assembled, and does it know its own
verified/gap state?* It FUSES what already exists (KISS/DRY — no parallel readiness engine):
  - `scripts/matter_readiness.py::assess/verdict` — the whole + blockers (operative pleading grounded,
    orphans, un-ingested attachments, verified-fact floor),
  - A57/A67 timeline presence (a matter without a date or an explicit dateless class is noted),
  - client resolution via the A5 machinery (the "whole" is the CLIENT-ISOLATED whole; assess() is
    per-matter, so another client's facts can never enter the base).

Verdicts (fail-closed — any doubt HOLDs):
  READY           — base grounded (operative source-read · ≥5 verified facts · no operative orphans /
                    un-ingested material); declared advisories ride along in reasons.
  HOLD:thin       — the base is too thin to decide from (< 5 verified facts, or the operative pleading
                    is unlinked/not source-read). The 1891-at-0-verified lesson.
  HOLD:gap-blind  — the base cannot even see its gaps (unknown matter · assessment error): blind > thin.

Every verdict is RECORDED (`incorporation_verdicts`) so A70's truth-floor can assert "no READY on a thin
base was ever recorded" — count-independent, honest as matters improve. Reads `verified`-tier only via
matter_readiness (provenance sacred: the gate never promotes inferred/proposed facts to satisfy itself).

CLI:  python3 scripts/incorporation_gate.py MWK-ARTA-1891 --stakeholder ombudsman
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matter_readiness as MR

THIN_FACTS = 5           # mirrors matter_readiness's under-grounded floor
# mirrors scripts/deadlines.py::WATCH_RE — an explicit dateless classification satisfies A67
WATCH_RE = re.compile(r"observation_only|advisory|tracking|no_immediate_deadline|asset_development|"
                      r"declared_unrelated|under_review|referred_to_\w+_awaiting", re.I)

_DDL = """CREATE TABLE IF NOT EXISTS incorporation_verdicts (
    id           serial PRIMARY KEY,
    matter_code  text NOT NULL,
    client_code  text,
    stakeholder  text NOT NULL,
    purpose      text,
    verdict      text NOT NULL CHECK (verdict IN ('READY','HOLD:thin','HOLD:gap-blind')),
    verified_count integer,
    reasons      jsonb,
    created_at   timestamptz DEFAULT now()
)"""


def _record(cur, v):
    cur.execute(_DDL)
    cur.execute("""INSERT INTO incorporation_verdicts
                     (matter_code, client_code, stakeholder, purpose, verdict, verified_count, reasons)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (v["matter_code"], v.get("client_code"), v["stakeholder"], v.get("purpose"),
                 v["verdict"], v.get("verified_count"), json.dumps(v.get("reasons", [])[:20])))


def require_incorporation(cur, matter_code, stakeholder, purpose="", record=True):
    """The A70 gate. Fail-closed: an exception or unknown matter is HOLD:gap-blind, never a pass."""
    v = {"matter_code": matter_code, "stakeholder": stakeholder, "purpose": purpose,
         "verdict": "HOLD:gap-blind", "verified_count": None, "client_code": None, "reasons": []}
    try:
        cur.execute("SELECT client_code, next_deadline, coalesce(current_stage,status,'') "
                    "FROM matters WHERE matter_code=%s", (matter_code,))
        row = cur.fetchone()
        if row:
            v["client_code"], next_deadline, stage = row[0], row[1], row[2]
        else:
            next_deadline, stage = None, ""
        a = MR.assess(cur, matter_code)
        if a is None:
            v["reasons"] = [f"unknown matter {matter_code!r} — the base cannot see its own gaps (A70c)"]
        else:
            ready, fixes, advis = MR.verdict(a)
            v["verified_count"] = a["nfacts"]
            v["reasons"] = fixes + advis
            if not next_deadline and not WATCH_RE.search(stage or ""):
                v["reasons"].append("no forward timeline and no dateless classification (A67) — needs-a-date")
            if ready:
                v["verdict"] = "READY"
            elif a["nfacts"] < THIN_FACTS or not a["operative"] or not a["op_grounded"]:
                v["verdict"] = "HOLD:thin"
            else:
                v["verdict"] = "HOLD:thin"   # not-ready for declared material gaps → still not a decision base
    except Exception as e:
        v["reasons"] = [f"incorporation assessment FAILED ({type(e).__name__}: {e}) — fail-closed (A70)"]
        v["verdict"] = "HOLD:gap-blind"
    if record:
        try:
            _record(cur, v)
        except Exception:
            pass   # the verdict itself must not be lost to a ledger hiccup; CLI still prints it
    return v


def main():
    import argparse
    import psycopg2
    ap = argparse.ArgumentParser()
    ap.add_argument("matter")
    ap.add_argument("--stakeholder", default="operator")
    ap.add_argument("--purpose", default="")
    ap.add_argument("--no-record", action="store_true")
    args = ap.parse_args()
    conn = psycopg2.connect(os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"))
    conn.autocommit = True
    with conn.cursor() as cur:
        v = require_incorporation(cur, args.matter, args.stakeholder, args.purpose,
                                  record=not args.no_record)
    print(f"{v['verdict']}  {args.matter} → {args.stakeholder}"
          + (f"  ({v['verified_count']} verified)" if v["verified_count"] is not None else ""))
    for r in v["reasons"][:8]:
        print(f"  - {r}")
    sys.exit(0 if v["verdict"] == "READY" else 1)


if __name__ == "__main__":
    main()
