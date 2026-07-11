#!/usr/bin/env python3
"""contradiction.py — resident agent: flag internal conflicts in the verified corpus. $0, deterministic.

A clean corpus can still be self-inconsistent — the same legal event carrying two different dates
across documents (e.g. the CV-26360 Deed of Absolute Sale dated Sept-29-2016 in the complaint but
Sept-26-2019 in the judicial affidavit). Those are exactly what opposing counsel exploits. This scans
each matter's VERIFIED facts, groups them by salient legal event, and flags any event that carries
two or more distinct dates (or peso amounts). Findings go to the `contradictions` table per matter for
reconciliation before trial — it never edits facts, only surfaces conflicts.

  python3 scripts/contradiction.py            # scan -> rewrite contradictions table
  python3 scripts/contradiction.py --report    # show open contradictions
"""
import argparse
import re

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

EVENTS = ["deed of absolute sale", "deed of sale", "deed of confirmation", "special power of attorney",
          "revocation", "decision", "resolution", "order", "complaint", "just compensation",
          "extrajudicial settlement", "demand letter", "pre-trial"]
MONTHS = ("january february march april may june july august september october november december")
_MIDX = {m: i + 1 for i, m in enumerate(MONTHS.split())}


def _dates(t):
    """Return a set of normalized (year, month) dates found in text."""
    out = set()
    tl = t.lower()
    for m in re.finditer(r"\b(" + "|".join(_MIDX) + r")\s+\d{1,2},?\s+(\d{4})\b", tl):
        out.add((m.group(2), _MIDX[m.group(1)]))
    for m in re.finditer(r"\b\d{1,2}\s+(" + "|".join(_MIDX) + r")\s+(\d{4})\b", tl):
        out.add((m.group(2), _MIDX[m.group(1)]))
    return out


def _amounts(t):
    out = set()
    for m in re.finditer(r"(?:php|p|₱)\s?([0-9][0-9,]{4,})(?:\.\d{2})?", t.lower()):
        out.add(m.group(1).replace(",", ""))
    return out


def _event_dates(text):
    """{event: {(year, month), ...}} — dates that sit within a ~60-char window of a salient legal
    event phrase (same clause), not merely co-present. The shared core of scan() and the A78
    ingest gate below."""
    ev = {}
    tl = (text or "").lower()
    for e in EVENTS:
        for m in re.finditer(re.escape(e), tl):
            win = tl[max(0, m.start() - 60): m.end() + 80]
            for d in _dates(win):
                ev.setdefault(e, set()).add(d)
    return ev


def verified_event_dates(cur, matter_code):
    """The matter's VERIFIED facts' event→date map: {event: {(y,m): {fact_id,...}}}.
    Load once per matter and pass to conflicts_with_verified for bulk ingest."""
    cur.execute("""SELECT id, statement, excerpt FROM matter_facts
                   WHERE matter_code=%s AND provenance_level='verified'""", (matter_code,))
    agg = {}
    for r in cur.fetchall():
        rid, stmt, exc = (r["id"], r["statement"], r["excerpt"]) if isinstance(r, dict) \
            else (r[0], r[1], r[2])
        for ev, ds in _event_dates((stmt or "") + " " + (exc or "")).items():
            for d in ds:
                agg.setdefault(ev, {}).setdefault(d, set()).add(rid)
    return agg


def conflicts_with_verified(cur, matter_code, text, verified_map=None):
    """A78 INGEST GATE (deterministic, $0, no LLM): does `text` carry an event-date that CONFLICTS
    with this matter's VERIFIED facts? Same event + same date = corroboration (passes); same salient
    event + a DIFFERENT date = conflict → the caller must HOLD/refuse the write, upstream of the
    engine. Returns [] or [{event, incoming, verified, fact_ids}, ...]."""
    vm = verified_map if verified_map is not None else verified_event_dates(cur, matter_code)
    out = []
    for ev, ds in _event_dates(text).items():
        have = vm.get(ev)
        if not have:
            continue
        for d in ds:
            if d not in have:
                out.append({"event": ev,
                            "incoming": f"{d[0]}-{int(d[1]):02d}",
                            "verified": sorted(f"{y}-{int(mo):02d}" for (y, mo) in have),
                            "fact_ids": sorted({i for s in have.values() for i in s})})
    return out


def scan(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS contradictions (
        matter_code text, event text, kind text, values text, fact_ids text,
        status text DEFAULT 'open', created_at timestamptz DEFAULT now(),
        UNIQUE(matter_code, event, kind))""")
    cur.execute("DELETE FROM contradictions WHERE status='open'")
    cur.execute("""SELECT matter_code, id, statement, excerpt FROM matter_facts
                   WHERE provenance_level='verified' ORDER BY matter_code""")
    rows = cur.fetchall()
    by = {}
    for r in rows:
        by.setdefault(r["matter_code"], []).append(r)
    flagged = 0
    for mc, facts in by.items():
        # proximity-based: a date counts for an event only if it sits within a ~60-char window of the
        # event phrase (same clause), not merely co-present in the fact. Kills the false positives.
        ev_dates = {}
        for f in facts:
            tl = (f["statement"] or "") + " " + (f["excerpt"] or "")
            for ev, ds in _event_dates(tl).items():
                for d in ds:
                    ev_dates.setdefault(ev, {}).setdefault(d, set()).add(f["id"])
        for ev, dm in ev_dates.items():
            if len(dm) >= 2:
                vals = ", ".join(f"{y}-{mo:02d}" for (y, mo) in sorted(dm))
                ids = ",".join(str(i) for s in dm.values() for i in s)
                cur.execute("""INSERT INTO contradictions (matter_code,event,kind,values,fact_ids)
                    VALUES (%s,%s,'date',%s,%s) ON CONFLICT (matter_code,event,kind)
                    DO UPDATE SET values=EXCLUDED.values, fact_ids=EXCLUDED.fact_ids, status='open'""",
                    (mc, ev, vals, ids)); flagged += 1
                _challenge(cur, mc, ev, vals, ids)
    return flagged


def _challenge(cur, matter_code, event, vals, fact_ids):
    """A78 'facts don't rot': verified facts caught in a contradiction are CHALLENGED — one
    idempotent open holes_findings row per (matter, event) carrying an A74-style machine-checkable
    recheck_condition, so the challenge routes to resolution instead of rotting in a table.
    Best-effort: challenge logging never breaks the scan."""
    try:
        key = f"verified_fact_challenged|{matter_code}|{event}"
        cur.execute("""INSERT INTO holes_findings (routine_name, routine_version, finding_id_hash,
                         severity, hole_type, matter_code, description, metadata, status)
                       SELECT 'contradiction_challenge', 'v1', md5(%s), 'high',
                              'verified_fact_challenged', %s, %s,
                              jsonb_build_object('event', %s, 'fact_ids', %s,
                                 'recheck_condition',
                                 'contradictions row (matter_code=' || %s || ', event=' || %s ||
                                 ', kind=date) is no longer open — verified facts re-verified/resolved'),
                              'open'
                       WHERE NOT EXISTS (SELECT 1 FROM holes_findings
                          WHERE finding_id_hash = md5(%s) AND status = 'open')""",
                    (key, matter_code,
                     f"A78 challenge: VERIFIED facts (ids {fact_ids}) carry CONFLICTING dates for "
                     f"'{event}' in {matter_code} ({vals}). A verified fact under contradiction is "
                     f"challenged, not trusted — resolve which date the record proves, re-tier the "
                     f"loser. The equilibrium engine must not compute on this until resolved.",
                     event, fact_ids, matter_code, event, key))
    except Exception:
        pass


def close_resolved_challenges(cur):
    """A74 recheck sweep: a challenge's recheck_condition is 'its contradictions row is no longer
    open' — machine-check it and close satisfied challenges. Runs right after scan() (which rewrites
    the open set), so a reconciled contradiction auto-releases its challenge."""
    cur.execute("""UPDATE holes_findings hf
                      SET status='remediated', remediated_at=now(),
                          remediated_via='contradiction_recheck_sweep'
                    WHERE hf.routine_name='contradiction_challenge' AND hf.status='open'
                      AND NOT EXISTS (SELECT 1 FROM contradictions c
                         WHERE c.matter_code = hf.matter_code AND c.event = hf.metadata->>'event'
                           AND c.kind='date' AND c.status='open')""")
    return cur.rowcount


def report(cur):
    cur.execute("""SELECT matter_code, event, kind, values FROM contradictions
                   WHERE status='open' ORDER BY matter_code, event""")
    rows = cur.fetchall()
    print("=" * 72); print(f"CONTRADICTIONS — internal conflicts in the verified corpus ({len(rows)})"); print("=" * 72)
    for mc, ev, kind, vals in rows:
        print(f"  ⚠ [{mc}] {ev} — conflicting {kind}s: {vals}")
    if not rows:
        print("  (none — corpus internally consistent on dates/amounts)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    c = psycopg2.connect(DSN); c.autocommit = True
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if not a.report:
        n = scan(cur)
        closed = close_resolved_challenges(cur)
        print(f"[contradiction] flagged {n} conflicts; {closed} resolved challenge(s) auto-closed")
    report(c.cursor())


if __name__ == "__main__":
    main()
