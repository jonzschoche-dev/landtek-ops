#!/usr/bin/env python3
"""staff_exam.py — the field-officer bot's exam (deploy_1326).

Jonathan, 3 Nov 2026: "we need to train our bot to be well informed on all the necessary subjects".
Training here = sourced knowledge cards (staff_knowledge) + this exam over real officer questions (staff_exam).

Each question is put through the real staff desk handler (staff_desk._handle_staff) with the right task in
focus, inside a transaction that is rolled back: nothing is sent, logged or changed. The reply is graded
mechanically (must contain / must not contain / handler route / honest "not in the papers"); no LLM judge.
Results go to staff_exam_run. With --promote, a topic's draft cards go live once every exam question on that
topic passes. A failing live topic is reported, never auto-demoted.

  python3 scripts/staff_exam.py                 # run all active questions, print the score
  python3 scripts/staff_exam.py --promote       # nightly: run, record, promote passing topics
  python3 scripts/staff_exam.py --topic bir -v  # one topic, show every reply
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import sys
import uuid

import psycopg2
import psycopg2.extras
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import staff_desk as sd  # noqa: E402

UNKNOWN = ("materials_not_in_sources", "materials_rejected_unsupported", "fallback")


def _matches(reply, item):
    r = (reply or "").lower()
    return any(alt.strip().lower() in r for alt in item.split("|") if alt.strip())


def grade(ex, handled, reply):
    """(passed, why_failed)."""
    if ex["expect"] == "unknown":
        return (handled in UNKNOWN, None if handled in UNKNOWN else f"answered ({handled}) where the papers are silent")
    if ex["expect"] == "route" and not (handled or "").startswith(ex["route_prefix"] or ""):
        return False, f"went to {handled}, expected {ex['route_prefix']}"
    if ex["expect"] == "answer" and handled in UNKNOWN:
        return (True, None) if ex["unknown_ok"] else (False, f"no answer ({handled})")
    bad = [w for w in ex["must_not"] if _matches(reply, w)]
    if bad:
        return False, f"contains forbidden {bad}"
    miss = [w for w in ex["must_all"] if not _matches(reply, w)]
    if miss:
        return False, f"missing {miss}"
    return True, None


def ask(cur, ex):
    """Put one question through the live handler with its task in focus; roll everything back."""
    m = sd._member_by_assignee(cur, ex["assignee"])
    if not m:
        return None, "assignee not active"
    focus = None
    if ex["focus_seq"] is not None:
        cur.execute("SELECT id FROM staff_task WHERE assignee=%s AND matter_code=%s AND seq=%s ORDER BY id LIMIT 1",
                    (ex["assignee"], ex["matter_code"], ex["focus_seq"]))
        row = cur.fetchone()
        focus = row["id"] if row else None
    m = dict(m)
    m["state"] = {k: v for k, v in (m["state"] or {}).items() if k not in ("skipped", "proof_for", "pending_media")}
    m["state"]["focus"] = focus
    cur.execute("UPDATE staff_desk_members SET state=%s WHERE channel=%s AND channel_user_id=%s",
                (psycopg2.extras.Json(m["state"]), m["channel"], m["channel_user_id"]))
    sd._outbox.clear()
    with contextlib.redirect_stdout(io.StringIO()):
        handled = sd._handle_staff(cur, m, None, ex["question"])
    reply = " / ".join(t for (_c, _u, t) in sd._outbox)
    return handled, reply


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--assignee", default="kristyle")
    ap.add_argument("--topic")
    ap.add_argument("--promote", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    sd.DRY = True
    sd.INCLUDE_DRAFTS = True
    run_id = uuid.uuid4().hex[:12]
    conn = psycopg2.connect(sd.DSN)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    log = psycopg2.connect(sd.DSN)
    log.autocommit = True
    lcur = log.cursor()

    cur.execute("SELECT * FROM staff_exam WHERE active AND assignee=%s AND (%s::text IS NULL OR topic=%s) ORDER BY topic, id",
                (a.assignee, a.topic, a.topic))
    exams = cur.fetchall()
    conn.rollback()

    try:
        requests.get(f"{sd.OLLAMA_URL}/api/tags", timeout=8).raise_for_status()
    except Exception as e:
        for ex in exams:
            lcur.execute("INSERT INTO staff_exam_run (run_id, exam_id, passed, why_failed) VALUES (%s,%s,NULL,%s)",
                         (run_id, ex["id"], f"skipped: local model unreachable ({type(e).__name__})"))
        print(f"exam {run_id}: SKIPPED, local model unreachable at {sd.OLLAMA_URL} ({type(e).__name__})")
        return 0

    by_topic, failed = {}, []
    for ex in exams:
        try:
            handled, reply = ask(cur, ex)
            ok, why = grade(ex, handled, reply) if handled else (False, reply)
        except Exception as e:
            handled, reply, ok, why = "error", "", False, f"{type(e).__name__}: {e}"[:300]
        finally:
            conn.rollback()
        lcur.execute("""INSERT INTO staff_exam_run (run_id, exam_id, passed, handled, reply, why_failed)
                        VALUES (%s,%s,%s,%s,%s,%s)""", (run_id, ex["id"], ok, handled, reply, why))
        by_topic.setdefault(ex["topic"], []).append(ok)
        if not ok:
            failed.append((ex, handled, reply, why))
        if a.verbose or not ok:
            print(f"{'PASS' if ok else 'FAIL'} [{ex['topic']}] (task {ex['focus_seq']}) {ex['question']}\n"
                  f"     -> {handled}: {reply[:400]}" + (f"\n     why: {why}" if why else ""))

    total = sum(len(v) for v in by_topic.values())
    passed = sum(sum(v) for v in by_topic.values())
    print(f"\nexam {run_id}: {passed}/{total} passed")
    for t, v in sorted(by_topic.items()):
        print(f"  {t:10s} {sum(v)}/{len(v)}")

    if a.promote and not a.topic:
        for t, v in by_topic.items():
            if all(v):
                lcur.execute("""UPDATE staff_knowledge SET state='live', updated_at=now()
                                 WHERE state='draft' AND topic=%s AND (assignee IS NULL OR assignee=%s)
                                 RETURNING id""", (t, a.assignee))
                ids = [r[0] for r in lcur.fetchall()]
                if ids:
                    print(f"  promoted {t}: cards {ids} now live")
    cur.close(); conn.close(); log.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
