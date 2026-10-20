#!/usr/bin/env python3
"""drip_card.py — THE PRE-DRAFT GATE: one ordered checklist, run on every drip before it reaches Jonathan.

Substance is checked from DATA, not recall (Jonathan, 20 Oct 2026: "line it up better so our answers are not so
sporadic"). Each line is ✅ pass / ⚠ needs attention / ⛔ blocks. A draft is READY only with no ⛔ and no ⚠ (goal-not-set
is the one ⚠ tolerated until Jonathan sets goals).

  0 CHARTER    case_work/MWK-001/DRIP_CHARTER.md (adopted 20 Oct 2026): capacity line (§2), never speaks for all
               the heirs (§2), cadence ≤1 touch per recipient per 15 working days (§7)
  1 GOAL       the step names the goal element; the matter objective is set by Jonathan (not just proposed)
  2 CUSTODIAN  the addressee is the custodian (or listed alternate) for the record type   → drip_custodian
  3 POSTURE    the addressee is not a respondent in our live proceedings (unless X17-ok)   → matter_track/track_party
  4 HISTORY    prior asks/answers/refusals were read (history_ref present)                 → step_plan.history_ref
  5 FACTS      every peso figure in the letter is in the matter fact sheet               → drip_fact
  6 LAW        every legal premise relied on is verified against the law corpus           → legal_premise/legal_chunks
  7 STRATEGY   the matter's strategy file is named and exists                             → step_plan.strategy_file
  8 LEDGER     Jonathan's past critiques for this ladder/office/global are listed (read them) → drip_feedback
  9 TONE       sleep-doctrine lint                                                          → drip_lint_rule
 10 CHANNEL    account + thread (or paper) + recipient                                      → step_plan

  python3 scripts/drip_card.py --instrument 12          # one card
  python3 scripts/drip_card.py --queue                  # a card line for every draft waiting for comment
"""
import argparse
import os
import re
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drip_draft_queue as q  # noqa: E402  (lint(), posture(), _surnames())

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHARTER = "case_work/MWK-001/DRIP_CHARTER.md"
CAPACITY = {"MWK-001": "Attorney-in-Fact for Patricia Keesey Zschoche"}
HEIRS_RX = re.compile(r"(?i)\b(on|for and on|in) behalf of (all )?the heirs\b|\bwe,? (all )?the heirs\b|\bthe heirs (hereby )?(request|demand|ask)")
STATUTE_RX = re.compile(r"(?i)(Section|Sec\.)\s*\d+[\w()]*|R\.A\.|Republic Act|Rule \d+")


def card(cur, iid):
    cur.execute("""SELECT i.id, i.status, i.body_md, i.version, sp.* FROM drip_instrument i
                    JOIN step_plan sp ON sp.id = i.step_plan_id WHERE i.id = %s""", (iid,))
    s = cur.fetchone()
    if not s:
        return None, [("—", "⛔", f"draft #{iid} not found / no step")]
    body = s["body_md"] or ""
    lines = []

    # 0 CHARTER
    probs = []
    cap = CAPACITY.get(s["client_code"])
    if cap and cap.lower() not in re.sub(r"\s+", " ", body).lower():
        probs.append("⛔ capacity line missing (§2)")
    if HEIRS_RX.search(body):
        probs.append("⛔ speaks for all the heirs (§2)")
    cur.execute("""SELECT count(*) AS n FROM drip_instrument i JOIN step_plan sp ON sp.id = i.step_plan_id
                    WHERE i.id <> %s AND sp.addressee = %s AND NOT coalesce(i.is_test, false)
                    AND i.status IN ('draft_staged','sent') AND i.updated_at > now() - interval '21 days'""", (iid, s["addressee"]))
    if cur.fetchone()["n"]:
        probs.append("⚠ another touch to this recipient within 15 working days (§7)")
    if not os.path.isfile(os.path.join(REPO, CHARTER)):
        probs.append("⛔ Charter file missing")
    mark = "⛔" if any(p.startswith("⛔") for p in probs) else ("⚠" if probs else "✅")
    lines.append(("0 CHARTER", mark, "; ".join(p[2:] for p in probs) or "capacity · heirs · cadence OK"))

    # 1 GOAL
    cur.execute("SELECT goal_set_by FROM matter_objectives WHERE matter_code=%s ORDER BY id LIMIT 1", (s["matter_code"],))
    g = cur.fetchone()
    set_by = (g or {}).get("goal_set_by") or ""
    if not s["goal_element"]:
        lines.append(("1 GOAL", "⛔", "no goal element on the step"))
    elif set_by.startswith("jonathan"):
        lines.append(("1 GOAL", "✅", f"{s['goal_element'][:90]}"))
    else:
        lines.append(("1 GOAL", "⚠", f"serves: {s['goal_element'][:80]} (matter goal still PROPOSED; set it)"))

    # 2 CUSTODIAN
    if not s["record_type"]:
        lines.append(("2 CUSTODIAN", "⚠", "record type not tagged; can't confirm this office holds it"))
    else:
        cur.execute("SELECT * FROM drip_custodian WHERE record_type=%s", (s["record_type"],))
        cu = cur.fetchone()
        names = q._surnames(s["addressee"])
        ok = bool(names & (q._surnames(cu["custodian"]) | q._surnames(cu["alternate"] or ""))) or \
            any(w in s["addressee"].lower() for w in re.findall(r"[a-z]{5,}", (cu["custodian"] + " " + (cu["alternate"] or "")).lower()))
        lines.append(("2 CUSTODIAN", "✅" if ok else "⛔",
                      f"{s['record_type']} → {cu['custodian']}{' (alt: ' + cu['alternate'] + ')' if cu['alternate'] else ''}"
                      f"{'' if cu['verified'] else ' [basis unverified]'}"))

    # 3 POSTURE
    live = q.posture(cur, s["addressee"], s["client_code"])
    if live and "X17-ok:" not in (s["notes"] or ""):
        lines.append(("3 POSTURE", "⛔", f"respondent in {live}; route elsewhere or approve 'uniquely theirs'"))
    else:
        lines.append(("3 POSTURE", "✅", "clear" if not live else "X17 exception approved"))

    # 4 HISTORY
    lines.append(("4 HISTORY", "✅" if (s["history_ref"] or "").strip() else "⛔",
                  (s["history_ref"] or "no history read")[:110]))

    # 5 FACTS
    figs = set(re.findall(r"₱\s?[\d,]+(?:\.\d\d)?", body))
    cur.execute("SELECT value FROM drip_fact WHERE matter_code IN (%s, %s)", (s["matter_code"], s["client_code"]))
    facts = " ".join(r["value"] for r in cur.fetchall())
    missing = [f for f in figs if f.replace(" ", "") not in facts.replace(" ", "")]
    lines.append(("5 FACTS", "✅" if not missing else "⚠",
                  "no figures, or all in the fact sheet" if not missing else f"not in the fact sheet: {missing}"))

    # 6 LAW
    cites = sorted(set(m.group(0) for m in STATUTE_RX.finditer(body)))
    keys = s["premise_keys"] or []
    if keys:
        cur.execute("SELECT key, verified FROM legal_premise WHERE key = ANY(%s)", (keys,))
        unver = [r["key"] for r in cur.fetchall() if not r["verified"]]
    else:
        unver = []
    if cites and not keys:
        lines.append(("6 LAW", "⚠", f"letter cites {cites} but no verified premise is attached"))
    elif unver:
        lines.append(("6 LAW", "⚠", f"unverified premise(s): {unver}"))
    else:
        lines.append(("6 LAW", "✅", f"premises: {keys or 'none relied on'}"))

    # 7 STRATEGY
    sf = s["strategy_file"]
    lines.append(("7 STRATEGY", "✅" if sf and os.path.isfile(os.path.join(REPO, sf)) else "⚠", sf or "no strategy file named"))

    # 8 LEDGER
    cur.execute("""SELECT count(*) AS n FROM drip_feedback WHERE status='active' AND (scope='global' OR target ILIKE %s
                     OR target ILIKE %s)""", (f"%{s['ladder']}%", f"%{(sorted(q._surnames(s['addressee'])) or ['~'])[0]}%"))
    lines.append(("8 LEDGER", "✅", f"{cur.fetchone()['n']} critiques apply (global + this ladder/office); read before drafting"))

    # 9 TONE
    res, words = q.lint(cur, body, cc_override="cc per Jonathan" in (s["notes"] or ""), addressee=s["addressee"])
    if "statute" in " ".join(res["refuse"]).lower() or "R.A." in " ".join(res["refuse"]):
        pass
    lines.append(("9 TONE", "✅" if not res["refuse"] else "⛔",
                  f"{words} words" + (f"; refuse: {res['refuse']}" if res["refuse"] else "") + (f"; flag: {res['flag']}" if res["flag"] else "")))

    # 10 CHANNEL
    acct = s["send_account"]
    ok = acct == "paper" or (acct and (s["thread_ref"] or s["to_address"] or s["reply_subject"]))
    lines.append(("10 CHANNEL", "✅" if ok else "⚠", f"{acct or 'account?'} · {s['thread_ref'] or s['to_address'] or s['reply_subject'] or ('paper' if acct == 'paper' else 'recipient/thread?')}"[:110]))
    return s, lines


def verdict(lines):
    hard = [l for l in lines if l[1] == "⛔"]
    soft = [l for l in lines if l[1] == "⚠" and not l[0].startswith("1 GOAL")]
    return "READY" if not hard and not soft else ("BLOCKED" if hard else "NEEDS ATTENTION")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instrument", type=int)
    ap.add_argument("--queue", action="store_true")
    a = ap.parse_args()
    c = psycopg2.connect(DSN)
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ids = [a.instrument] if a.instrument else []
    if a.queue:
        cur.execute("SELECT id FROM v_review_queue")
        ids = [r["id"] for r in cur.fetchall()]
    for iid in ids:
        s, lines = card(cur, iid)
        print(f"\n#{iid} {s['ladder'] if s else ''} step {s['seq'] if s else ''} → {s['addressee'] if s else ''}   [{verdict(lines)}]")
        for name, mark, msg in lines:
            print(f"  {mark} {name:<12} {msg}")


if __name__ == "__main__":
    sys.exit(main())
