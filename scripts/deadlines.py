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
    r"(deadline|due\b|appeal|window|\brespond\b|reply by|file by|filing deadline|"
    r"within \d+ days|pending send|pending_send|to send|send (?:the )?demand|demand_letter|"
    r"hearing|manifestation|comply|expire|lapse|follow ?up|escalate|submit by|next event)", re.I)
# NB (deploy_655): `respond` was unbounded, so the NOUN "Respondent" (opposing party) matched as a
# forward "respond" obligation — that false-positive is what promoted MWK-ARTA-1378's historical
# "PERJURY POINT (2026-06-07)" narrative date into a phantom OVERDUE. `\brespond\b` fixes it, and
# the narrative/editorial markers below (perjury/swore/correction/defaulted/contaminated…) mark such
# case-history prose as TIMELINE, not a forward obligation — same discipline as the CV-26360 phantom.
PAST_RE = re.compile(
    r"(filed|\bdated\b|died|death|created|ingested|retroactively|merged|resolved|"
    r"correction|corrected|admission|\bswore\b|\bsworn\b|non-receipt|perjury|defaulted|contaminated|"
    r"posture-verified|verified|received|issued|executed|recorded|registered|"
    r"ordered|order ingested|likely the|not yet|bundled)", re.I)


# §4B inline provenance tags must never be rendered half-open. A naive label[:70] truncation
# severed "[HUMAN VERIFY]" into "[HUMAN VERIF" (deploy_642 bug) which a client-facing view then
# renders verbatim. Cap the label, but if the cap lands inside an open bracket-tag, back up to
# before the tag opened (or, if that would lose everything, drop the broken tail entirely).
LABEL_CAP = 70
TAG_OPEN_RE = re.compile(r"\[[^\]]*$")  # an unclosed '[...' running to end of the (capped) string


def _tag_safe_label(text):
    """Truncate to LABEL_CAP chars without leaving a severed §4B tag like '[HUMAN VERIF'."""
    if not text:
        return text
    if len(text) <= LABEL_CAP:
        return text
    cut = text[:LABEL_CAP]
    m = TAG_OPEN_RE.search(cut)
    if m:
        # the cap fell inside an open '[' tag — back up to just before the bracket
        cut = cut[:m.start()].rstrip()
    return cut


# A surfaced label is CLIENT-FACING. The prose harvester grabs a ±45-char window around a date, which
# can begin mid-word/mid-sentence and can straddle the internal "||" segment separator we use in
# stage_notes to fence off distinct case-history blocks. Rendering that verbatim leaked
# "s docs from other matters. || PERJURY POINT (2026-06-07): Respondent s" to the client (deploy_655).
# Rule: never emit a label that carries the "||" internal separator or starts lowercase mid-word.
# Repair, in order: (1) drop everything from the first "||" on; (2) if the remainder still starts
# lowercase (i.e. we're mid-sentence), advance to the next sentence boundary; (3) if nothing clean
# survives, fall back to the matter's stage token (always a presentable snake_case status).
SENT_START_RE = re.compile(r"(?<=[.;:])\s+(?=[A-Z0-9\[])")


def _clean_label(snippet, fallback=""):
    """Return a presentable label from a harvested prose window, or the stage fallback."""
    s = (snippet or "").strip()
    if "||" in s:
        s = s.split("||", 1)[0].strip()
    # If it starts lowercase (a severed mid-word/mid-sentence fragment), align to a sentence boundary.
    if s and s[0].islower():
        m = SENT_START_RE.search(s)
        s = s[m.end():].strip() if m else ""
    if not s or s[0].islower():
        return _tag_safe_label((fallback or "").strip())
    return _tag_safe_label(s)


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
        # ROOT-CAUSE GATE (deploy_644): only harvest prose dates for a matter that ALREADY carries a
        # structured next_deadline. A NULL next_deadline is the operator's explicit "this matter is
        # NEEDS-A-DATE" signal — a historical date sitting in next_event/stage_notes prose (a mediation
        # that was held, a filing, a death) must NEVER be promoted into a phantom forward deadline that
        # overrides that. This is the exact trap that bit CV-26360 in deploy_642: we set next_deadline
        # NULL (correct — Aug-1 discredited) but the prose's historical "2026-06-06" mediation date got
        # parsed back into a surfaced OVERDUE row. Prose harvest is a SECONDARY enrichment of an already-
        # dated matter, never a primary source that can date an intentionally dateless one.
        if not m["next_deadline"]:
            continue
        for fld in ("next_event", "stage_notes"):
            for dt, snip in extract_dated_spans(m[fld]):
                if is_deadline_context(snip):
                    obs.append({"date": dt, "matter": m["matter_code"],
                                "label": _clean_label(snip, fallback=m["stage"]), "kind": "obligation", "source": fld})
                    dated_matters.add(m["matter_code"])
                else:
                    timeline += 1
    cur.execute("""SELECT case_file, goal_text, target_date FROM client_goals
                   WHERE target_date IS NOT NULL AND status='active'""")
    for g in cur.fetchall():
        obs.append({"date": g["target_date"], "matter": g["case_file"],
                    "label": _tag_safe_label(g["goal_text"] or ""), "kind": "goal", "source": "client_goals"})
    # matters with no date at all = the awareness gap (carry the stage so we can classify honestly)
    no_date = [(m["matter_code"], m["stage"]) for m in matters if m["matter_code"] not in dated_matters]
    return obs, no_date, len(matters), timeline


# Stages that legitimately have NO deadline — surfacing them as "missing" is false alarm.
WATCH_RE = re.compile(
    r"observation_only|advisory|tracking|no_immediate_deadline|asset_development|"
    r"declared_unrelated|under_review", re.I)


def classify_gap(code, stage):
    if code.startswith("AUTO-"):
        return "orphan"
    if WATCH_RE.search(stage or ""):
        return "watch"
    return "needs_date"   # an action/litigation stage that SHOULD carry a date


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
    gaps = {"needs_date": [], "watch": [], "orphan": []}
    for code, stage in no_date:
        gaps[classify_gap(code, stage)].append((code, stage))
    L.append(f"📋 NEEDS A DATE ({len(gaps['needs_date'])}) — action-stage matters with no tracked deadline:")
    for code, stage in sorted(gaps["needs_date"]):
        L.append(f"   {code} — {stage}")
    L.append("")
    L.append(f"👁 watch-only, no deadline by design: {len(gaps['watch'])}"
             + (" (" + ", ".join(c for c, _ in gaps["watch"]) + ")" if gaps["watch"] else ""))
    L.append(f"🗑 orphan/auto-promoted (not real matters): {len(gaps['orphan'])}")
    L.append(f"   ({timeline} historical/filing dates in prose correctly excluded — not deadlines.)")
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


def summary_text(cur, today=None):
    """Concise plain-text block for the daily digest (S14-safe: short, one topic). $0."""
    today = today or date.today()
    obs, no_date, n_matters, timeline = gather(cur)
    seen, uniq = set(), []
    for o in sorted(obs, key=lambda x: x["date"]):
        k = (o["date"], o["matter"], o["kind"])
        if k not in seen:
            seen.add(k); uniq.append(o)
    overdue = [(o, (o["date"] - today).days) for o in uniq if (o["date"] - today).days < 0]
    soon = [(o, (o["date"] - today).days) for o in uniq if 0 <= (o["date"] - today).days <= 45]
    needs = sum(1 for c, s in no_date if classify_gap(c, s) == "needs_date")
    L = [f"DUE DATES (as of {today.isoformat()})",
         f"North star: testimony in {(NORTH_STAR[0]-today).days}d (Aug 12)."]
    if overdue:
        L.append("OVERDUE — confirm status:")
        for o, d in overdue[:6]:
            L.append(f"  - {o['matter']}: {-d}d past ({o['label'][:48]})")
    if soon:
        L.append("UPCOMING (next 45d):")
        for o, d in soon[:6]:
            L.append(f"  - {o['matter']}: in {d}d ({o['label'][:48]})")
    L.append(f"{needs} action-stage matters still need a deadline set.")
    return "\n".join(L)


def _severity_for(delta):
    """Proximity → alert severity. The escalation ladder: closer = louder."""
    if delta < 0 or delta <= 7:
        return "high"      # overdue, or due within a week
    if delta <= 14:
        return "medium"
    return None            # >14d: lives in the digest, not an alert


def escalate(cur, today=None):
    """Emit overdue + imminent (≤14d) deadlines into agent_audit with proximity-severity, so the
    deadline clock surfaces in the digest and (when alerts are live) fires HIGH for the urgent ones.
    Idempotent per (matter, date, severity-tier) — re-emits only when a deadline crosses into a louder
    tier. $0. Returns the number of new escalations logged."""
    import os as _os, sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    from agent_alert import emit
    today = today or date.today()
    obs, _no_date, _n, _tl = gather(cur)
    seen, n = set(), 0
    for o in sorted(obs, key=lambda x: x["date"]):
        k = (o["date"], o["matter"], o["kind"])
        if k in seen:
            continue
        seen.add(k)
        delta = (o["date"] - today).days
        sev = _severity_for(delta)
        if sev is None:
            continue
        when = f"{-delta}d overdue" if delta < 0 else (f"due in {delta}d" if delta else "due TODAY")
        summary = f"{o['matter']}: {o['label'][:60]} — {when} ({o['date'].isoformat()})"
        if emit("deadlines", "deadline", summary, matter=o["matter"], severity=sev,
                grounding=o.get("kind"),
                dedup_key=f"deadline:{o['matter']}:{o['date'].isoformat()}:{sev}"):
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--today")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--escalate", action="store_true", help="emit overdue/imminent deadlines to agent_audit")
    a = ap.parse_args()
    today = datetime.strptime(a.today, "%Y-%m-%d").date() if a.today else date.today()
    c = _conn()
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if a.escalate:
        print(f"[escalate] {escalate(cur, today)} overdue/imminent deadlines → agent_audit")
    else:
        digest(cur, today, write=a.write)


if __name__ == "__main__":
    main()
