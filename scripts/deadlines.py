#!/usr/bin/env python3
"""deadlines.py — the never-miss-a-date engine. $0, deterministic, no LLM.

WHY (operator, 2026-06-20): "the stack is missing every important date — it's almost useless."
True: 28/31 active matters had NO tracked deadline, and the few that existed were already
overdue with nothing flagging them. A legal-ops stack's first job (Principle 2) is to never
miss a date. This surfaces EVERY dated obligation, ranks by urgency vs today, and screams about
overdue + imminent ones. It also extracts dates buried in free-text next_event / stage_notes /
goal text that were never structured.

Sources (all grounded): matters.next_deadline, dates parsed from matters.next_event +
stage_notes, client_goals.target_date, escalations deadlines, arta_cases appeal windows.

  python3 scripts/deadlines.py                 # urgency digest to stdout
  python3 scripts/deadlines.py --today 2026-06-20
  python3 scripts/deadlines.py --write          # also persist to surfaced_deadlines (for the daily push)
"""
import argparse
import re
import sys
from datetime import date, datetime

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
NORTH_STAR = (date(2026, 8, 12), "Jonathan testifies as Patricia's witness — CV-26360 (MTC Mercedes)")

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
ISO_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
MDY_RE = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2}),?\s+(20\d{2})\b", re.I)


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True
    return c


# A prose date is a DEADLINE only if its surrounding text carries a forward-obligation marker.
# Otherwise it's a TIMELINE/context date (a filing, a death, an ingest) — NOT something due,
# and counting it as overdue is false urgency. Precision over recall here on purpose.
FORWARD_RE = re.compile(
    r"(deadline|due\b|deadline|appeal|window|respond|reply by|file by|filing deadline|"
    r"within \d+ days|pending send|pending_send|to send|send (?:the )?demand|demand_letter|"
    r"hearing|manifestation|comply|expire|lapse|follow ?up|escalate|submit by|next event)", re.I)
PAST_RE = re.compile(
    r"(filed|\bdated\b|died|death|created|ingested|retroactively|merged|resolved|"
    r"posture-verified|verified|corrected|received|issued|executed|recorded|registered|"
    r"ordered|order ingested|likely the|not yet|bundled)", re.I)


def extract_dated_spans(text):
    """[(date, snippet)] for each date in free text, snippet = ±45 chars of context."""
    out = []
    if not text:
        return out
    for rx, build in ((ISO_RE, lambda g: date(int(g[0]), int(g[1]), int(g[2]))),
                      (MDY_RE, lambda g: date(int(g[2]), MONTHS[g[0][:3].lower()], int(g[1])))):
        for m in rx.finditer(text):
            try:
                d = build(m.groups())
            except (ValueError, KeyError):
                continue
            s, e = max(0, m.start() - 45), min(len(text), m.end() + 45)
            out.append((d, text[s:e]))
    return out


def is_deadline_context(snippet):
    """True iff the prose around the date signals a forward obligation, not a past event."""
    return bool(FORWARD_RE.search(snippet)) and not PAST_RE.search(snippet)


def gather(cur):
    """Return list of obligations: {date, matter, label, kind, source}."""
    obs = []
    timeline = 0   # context dates we deliberately did NOT treat as deadlines
    cur.execute("""SELECT matter_code, case_file, coalesce(current_stage,status) stage,
                          next_deadline, next_event, stage_notes
                   FROM matters WHERE (status IS NULL OR status NOT IN ('closed','archived'))""")
    matters = cur.fetchall()
    dated_matters = set()
    for m in matters:
        if m["next_deadline"]:
            obs.append({"date": m["next_deadline"], "matter": m["matter_code"],
                        "label": m["stage"], "kind": "deadline", "source": "next_deadline"})
            dated_matters.add(m["matter_code"])
        for fld in ("next_event", "stage_notes"):
            for dt, snip in extract_dated_spans(m[fld]):
                if is_deadline_context(snip):
                    obs.append({"date": dt, "matter": m["matter_code"],
                                "label": snip.strip()[:70], "kind": "obligation", "source": fld})
                    dated_matters.add(m["matter_code"])
                else:
                    timeline += 1
    cur.execute("""SELECT case_file, goal_text, target_date FROM client_goals
                   WHERE target_date IS NOT NULL AND status='active'""")
    for g in cur.fetchall():
        obs.append({"date": g["target_date"], "matter": g["case_file"],
                    "label": (g["goal_text"] or "")[:70], "kind": "goal", "source": "client_goals"})
    # matters with no date at all = the awareness gap
    no_date = [m["matter_code"] for m in matters if m["matter_code"] not in dated_matters]
    return obs, no_date, len(matters), timeline


def bucket(delta):
    if delta < 0:
        return "OVERDUE"
    if delta <= 7:
        return "THIS WEEK"
    if delta <= 30:
        return "THIS MONTH"
    if delta <= 90:
        return "UPCOMING"
    return "LATER"


def digest(cur, today, write=False):
    obs, no_date, n_matters, timeline = gather(cur)
    # dedup identical (date, matter, source-bucket) keeping one
    seen = set(); uniq = []
    for o in sorted(obs, key=lambda x: x["date"]):
        k = (o["date"], o["matter"], o["kind"])
        if k in seen:
            continue
        seen.add(k); uniq.append(o)

    order = ["OVERDUE", "THIS WEEK", "THIS MONTH", "UPCOMING", "LATER"]
    icon = {"OVERDUE": "🔴", "THIS WEEK": "🟠", "THIS MONTH": "🟡", "UPCOMING": "🔵", "LATER": "⚪"}
    by_bucket = {b: [] for b in order}
    for o in uniq:
        delta = (o["date"] - today).days
        by_bucket[bucket(delta)].append((o, delta))

    L = [f"LANDTEK — IMPORTANT DATES (as of {today.isoformat()})", "=" * 60]
    ns_delta = (NORTH_STAR[0] - today).days
    L.append(f"★ NORTH STAR: {NORTH_STAR[0].isoformat()} ({ns_delta:+d}d) — {NORTH_STAR[1]}")
    L.append("")
    for b in order:
        items = by_bucket[b]
        if not items:
            continue
        L.append(f"{icon[b]} {b} ({len(items)})")
        for o, delta in items:
            when = f"{-delta}d ago" if delta < 0 else (f"in {delta}d" if delta else "TODAY")
            L.append(f"   {o['date'].isoformat()} ({when})  {o['matter']} — {o['label']}")
        L.append("")
    L.append(f"⚠ AWARENESS GAP: {len(no_date)}/{n_matters} active matters have NO tracked deadline.")
    L.append("   " + ", ".join(no_date[:24]) + (" …" if len(no_date) > 24 else ""))
    L.append(f"   ({timeline} historical/filing dates in prose were correctly NOT counted as deadlines.)")
    out = "\n".join(L)
    print(out)

    if write:
        cur.execute("""CREATE TABLE IF NOT EXISTS surfaced_deadlines (
            id serial PRIMARY KEY, due_date date, matter_code text, label text, kind text,
            bucket text, days_out int, as_of date, created_at timestamptz DEFAULT now())""")
        cur.execute("DELETE FROM surfaced_deadlines WHERE as_of=%s", (today,))
        for o in uniq:
            delta = (o["date"] - today).days
            cur.execute("""INSERT INTO surfaced_deadlines(due_date,matter_code,label,kind,bucket,days_out,as_of)
                           VALUES(%s,%s,%s,%s,%s,%s,%s)""",
                        (o["date"], o["matter"], o["label"], o["kind"], bucket(delta), delta, today))
        print(f"\n[write] persisted {len(uniq)} dated obligations to surfaced_deadlines (as_of {today}).")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--today")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    today = datetime.strptime(a.today, "%Y-%m-%d").date() if a.today else date.today()
    c = _conn()
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    digest(cur, today, write=a.write)


if __name__ == "__main__":
    main()
