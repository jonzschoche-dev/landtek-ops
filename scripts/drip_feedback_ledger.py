#!/usr/bin/env python3
"""drip_feedback_ledger.py — the LIVE corpus for the drip (Jonathan, 20 Oct 2026: "my feedback should be somewhere in
the corpus for next time … we need a LIVE corpus").

Rebuilds two internal documents from the database and pushes them into the corpus (documents, internal/not_for_trial):
  1. DRIP FEEDBACK LEDGER: every critique Jonathan has given (drip_feedback + any drip_comment not yet distilled), newest
     first, grouped global / office / ladder, each with his words, the lesson and where it is enforced.
  2. MWK DRIP STEERING GUIDE: the doctrine block (kept from the repo file) + the live ladders from step_plan.
Runs after every comment (called by drip_draft_queue.py) and hourly from cron on the VPS. On the VPS it writes the corpus
only (no repo files, so the git tree stays clean); with --write-files (Mac) it also refreshes the repo copies.

  python3 scripts/drip_feedback_ledger.py [--write-files]
  python3 scripts/drip_feedback_ledger.py --add SCOPE TARGET "Jonathan's words" "lesson" "enforced by"   # record + rebuild
"""
import argparse
import collections
import datetime
import os
import re
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingest_strategy_docs import upsert  # noqa: E402

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = "case_work/MWK-001/DRIP_FEEDBACK_LEDGER.md"
GUIDE = "case_work/MWK-001/DRIP_STEERING_GUIDE_MWK.md"
PHT = datetime.timezone(datetime.timedelta(hours=8))


def ledger_text(cur):
    # pull any new drip_comment into the ledger as instrument-scoped feedback (lesson pending until distilled)
    cur.execute("""INSERT INTO drip_feedback (given_at, source, scope, target, feedback_verbatim, lesson, enforced_by, drip_comment_id)
                   SELECT c.created_at, 'drip_comment', 'instrument',
                          coalesce(sp.ladder || ' step ' || sp.seq, 'drip #' || c.instrument_id), c.comment,
                          '(to distil: revision v' || coalesce(c.resolved_in_version::text, 'pending') || ' shows how it was applied)',
                          'drip_comment #' || c.id, c.id
                     FROM drip_comment c LEFT JOIN drip_instrument i ON i.id = c.instrument_id
                     LEFT JOIN step_plan sp ON sp.id = i.step_plan_id
                    WHERE NOT EXISTS (SELECT 1 FROM drip_feedback f WHERE f.drip_comment_id = c.id)
                      AND coalesce(sp.ladder, '') NOT LIKE 'TEST-%'
                   ON CONFLICT DO NOTHING""")
    cur.execute("SELECT * FROM drip_feedback WHERE status='active' ORDER BY given_at DESC")
    rows = cur.fetchall()
    now = datetime.datetime.now(PHT).strftime("%d %b %Y %H:%M PHT")
    out = [f"# DRIP FEEDBACK LEDGER (internal, never outward)\n",
           f"*Live, regenerated {now} from `drip_feedback`. Read this before drafting, revising or even considering a drip. "
           "Jonathan's own words are quoted; the lesson is the rule the stack now follows; 'enforced by' says where.*\n"]
    groups = collections.OrderedDict([("global", "Rules for every drip"), ("office", "By office / official"),
                                      ("ladder", "By ladder"), ("instrument", "On specific drafts")])
    for key, title in groups.items():
        g = [r for r in rows if r["scope"] == key]
        if not g:
            continue
        out.append(f"## {title}\n")
        for r in g:
            when = r["given_at"].astimezone(PHT).strftime("%d %b %Y %H:%M")
            tgt = f" · **{r['target']}**" if r["target"] else ""
            out.append(f"- {when}{tgt} · Jonathan: “{r['feedback_verbatim']}”  \n"
                       f"  **Lesson:** {r['lesson']}  \n  *Enforced by:* {r['enforced_by'] or '—'}")
        out.append("")
    return "\n".join(out)


def guide_text(cur):
    base = open(os.path.join(REPO, GUIDE), encoding="utf-8").read()
    head = base.split("## 2.")[0].rstrip()
    tail = "## 3." + base.split("## 3.", 1)[1] if "## 3." in base else ""
    if "DRIP_FEEDBACK_LEDGER" not in head:
        head += ("\n11. **Feedback ledger first.** Before drafting or considering any drip, read "
                 "`case_work/MWK-001/DRIP_FEEDBACK_LEDGER.md` (live in the corpus): every past critique from Jonathan, "
                 "for that office and ladder and in general.\n")
    cur.execute("""SELECT ladder, matter_code, seq, step_kind, addressee, the_ask, goal_element, goal_kind,
                          coalesce(send_account,'') AS send_account, state, coalesce(notes,'') AS notes
                     FROM step_plan WHERE client_code='MWK-001' AND ladder NOT LIKE 'TEST-%' ORDER BY ladder, seq""")
    lad = collections.OrderedDict()
    for r in cur.fetchall():
        lad.setdefault(r["ladder"], []).append(r)
    rx = re.compile(r"(?i)barandon route|posture check|counsel-gated|counsel route|X17 HELD")
    now = datetime.datetime.now(PHT).strftime("%d %b %Y %H:%M PHT")
    sec = [f"## 2. Live ladders (regenerated {now} from `step_plan`)\n"]
    for k, v in lad.items():
        flags = [bool(rx.search(f"{r['addressee']} {r['the_ask']} {r['notes']}")) for r in v]
        tag = "  · ⚠ COUNSEL ROUTE / HELD" if flags[0] else ("  · ⚠ later steps counsel-routed" if any(flags) else "")
        sec.append(f"### {k} · {v[0]['matter_code']}{tag}")
        for r in v:
            sec.append(f"- **{r['seq']}. {r['step_kind']}** → {r['addressee']}: {r['the_ask']}  \n"
                       f"  *serves:* {r['goal_element']} ({r['goal_kind']}) · *send:* {r['send_account'] or 'per history'} · *state:* {r['state']}")
        sec.append("")
    return head + "\n\n" + "\n".join(sec) + "\n" + tail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-files", action="store_true")
    ap.add_argument("--add", nargs=5, metavar=("SCOPE", "TARGET", "WORDS", "LESSON", "ENFORCED_BY"))
    a = ap.parse_args()
    c = psycopg2.connect(DSN)
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if a.add:
        sc, tg, words, lesson, enf = a.add
        cur.execute("""INSERT INTO drip_feedback (scope, target, feedback_verbatim, lesson, enforced_by)
                       VALUES (%s, nullif(%s,''), %s, %s, %s) ON CONFLICT DO NOTHING""", (sc, tg, words, lesson, enf))
    led, gui = ledger_text(cur), guide_text(cur)
    r1 = upsert(cur, LEDGER, "MWK-001", "MWK-001", "DRIP FEEDBACK LEDGER: every critique from Jonathan, live (internal)", led)
    r2 = upsert(cur, GUIDE, "MWK-001", "MWK-001", "MWK DRIP STEERING GUIDE: how every communication to an office is steered (internal)", gui)
    c.commit()
    if a.write_files:
        for p, t in ((LEDGER, led), (GUIDE, gui)):
            with open(os.path.join(REPO, p), "w", encoding="utf-8") as f:
                f.write(t)
    print("ledger", r1, "| guide", r2)


if __name__ == "__main__":
    sys.exit(main())
