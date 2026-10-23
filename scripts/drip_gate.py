#!/usr/bin/env python3
"""drip_gate.py — the pre-draft gate for ANY draft text, from any channel (chat, Drip UI, stager).

drip_card.py gates step_plan instruments; this gates free text (a Drip UI draft, a chat draft) with the same rules,
so nothing reaches Jonathan's Drafts without passing them (Jonathan, 23 Oct 2026: "drafts through the gate and cadence").

  gate(cur, body, to_addr=None, client="MWK-001", addressee=None, cc_override=False)
    → {"mark": "✅"|"⚠"|"⛔", "lines": [[check, mark, note], ...]}

Checks: CHARTER capacity + never-for-all-heirs (§2) · POSTURE X17 (respondents in our live tracks) · BR41 hold
(no drips to RTC Branch 41 while SP 2680 is pending) · CADENCE one touch per office per 21 days unless the office
replied since · TONE sleep-doctrine lint (drip_lint_rule) · FOLLOWS (no new legal position in a routine drip).
⛔ blocks Go unless Jonathan overrides in writing; ⚠ shows but does not block.

  python3 scripts/drip_gate.py --to addr --file draft.txt
"""
import argparse
import json
import os
import re
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drip_draft_queue as dq  # noqa: E402  (lint, posture)
from drip_card import CAPACITY, HEIRS_RX  # noqa: E402

BR41_RX = re.compile(r"(?i)\b(branch|br\.)\s*41\b|rtc1daeo?br41|sp\.?\s*(no\.?\s*)?2680")
POSITION_RX = re.compile(r"(?i)\b(we (hereby )?demand|final demand|we will (file|sue|bring)|in violation of|"
                         r"you are (hereby )?(directed|ordered)|liable|r\.?a\.? (no\.? )?11032|graft|anti-red tape)\b")
ADDR = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+")
OURS = {"jonzschoche@gmail.com", "jonathan@hayuma.org"}


def cadence(cur, to_addr):
    """One touch per office per 21 days, unless the office has replied since our last touch."""
    addrs = [a.lower() for a in ADDR.findall(to_addr or "") if a.lower() not in OURS]
    out = []
    for a in addrs:
        cur.execute("""SELECT max(coalesce(event_date, created_at::date)) d FROM drip_event_v
                        WHERE kind IN ('sent','dispatched') AND detail::text ILIKE %s""", (f"%{a}%",))
        last = cur.fetchone()["d"]
        if not last or (date.today() - last).days >= 21:
            continue
        cur.execute("""SELECT max(coalesce(event_date, created_at::date)) d FROM drip_event_v
                        WHERE kind = 'reply' AND detail::text ILIKE %s""", (f"%{a}%",))
        rep = cur.fetchone()["d"]
        if rep and rep >= last:
            continue
        out.append(f"{a}: last touch {last:%d %b}, no reply since (next e-mail after {last + timedelta(days=21):%d %b}; call instead)")
    return out


def posture_by_address(cur, to_addr, client):
    """X17 on an e-mail address: a live respondent's surname inside the address's local part (ablagemma@ → Abla)."""
    locs = [a.split("@")[0].lower() for a in ADDR.findall(to_addr or "") if a.lower() not in OURS]
    if not locs:
        return []
    cur.execute("""SELECT DISTINCT t.track_code, p.official FROM track_party p JOIN matter_track t USING (track_code)
                    WHERE t.client_code=%s AND t.kind IN ('complaint','appeal','referral','judicial')
                      AND t.true_status !~* '(closed|dismissed|lapsed|withdrawn|resolved|held|draft|not (yet )?filed|planned|proposed|not sent)'
                      AND p.role IN ('respondent','duty_holder')""", (client,))
    hits = set()
    for r in cur.fetchall():
        for sn in dq._surnames(r["official"]):
            if len(sn) >= 4 and any(sn in loc for loc in locs):
                hits.add(r["track_code"])
    return sorted(hits)


def gate(cur, body, to_addr=None, client="MWK-001", addressee=None, cc_override=False):
    body = body or ""
    lines = []
    flat = re.sub(r"\s+", " ", body).lower()
    cap = CAPACITY.get(client)
    probs = []
    if cap and cap.lower() not in flat:
        probs.append(("⛔", "capacity line missing: sign as " + cap))
    if HEIRS_RX.search(body):
        probs.append(("⛔", "speaks for all the heirs (Charter §2)"))
    lines.append(["CHARTER", "⛔" if probs else "✅", "; ".join(p[1] for p in probs) or "capacity · heirs OK"])
    live = dq.posture(cur, addressee or to_addr or "", client) if (addressee or to_addr) else []
    live = sorted(set(live) | set(posture_by_address(cur, to_addr, client)))
    lines.append(["POSTURE", "⛔" if live else "✅", f"respondent in live track(s) {live}: route elsewhere" if live else "clear"])
    br41 = BR41_RX.search(f"{to_addr or ''} {addressee or ''} {body}")
    lines.append(["BR41 HOLD", "⛔" if br41 else "✅", "no drips to RTC Br. 41 while SP 2680 is pending" if br41 else "clear"])
    cad = cadence(cur, to_addr)
    lines.append(["CADENCE", "⚠" if cad else "✅", "; ".join(cad) or "no touch to this office in 21 days (or it replied)"])
    res, words = dq.lint(cur, body, cc_override=cc_override, addressee=addressee or to_addr or "")
    lines.append(["TONE", "⛔" if res["refuse"] else ("⚠" if res["flag"] else "✅"),
                  f"{words} words" + (f"; refuse: {res['refuse']}" if res["refuse"] else "") + (f"; flag: {res['flag']}" if res["flag"] else "")])
    pos = sorted({m.group(0).lower() for m in POSITION_RX.finditer(body)})
    lines.append(["FOLLOWS", "⚠" if pos else "✅",
                  f"reads like a legal position ({', '.join(pos)}): the drip follows decided positions only" if pos else "routine follow-up"])
    marks = [l[1] for l in lines]
    return {"mark": "⛔" if "⛔" in marks else ("⚠" if "⚠" in marks else "✅"), "lines": lines}


def main():
    import psycopg2
    import psycopg2.extras
    ap = argparse.ArgumentParser()
    ap.add_argument("--to")
    ap.add_argument("--file", required=True)
    ap.add_argument("--client", default="MWK-001")
    a = ap.parse_args()
    dsn = os.environ.get("PG_DSN") or ("postgresql://n8n:n8npassword@172.18.0.3:5432/n8n" if os.path.isdir("/root/landtek")
                                       else "postgresql://n8n:n8npassword@127.0.0.1:15432/n8n")
    cur = psycopg2.connect(dsn).cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    print(json.dumps(gate(cur, open(a.file).read(), a.to, a.client), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
