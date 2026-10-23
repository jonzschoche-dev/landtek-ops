#!/usr/bin/env python3
"""drip_log.py — the ONE way anything enters the drip. Every channel (chat, Drip UI, rider photos, inbox pull)
records through here, so the five core tables stay fed and agree:

    step_plan (ladders) · drip_event (log) · office_obligation (clocks) · drip_feedback (rules) · drip_ui_draft

Why (Jonathan, 23 Oct 2026): the drip ran from chat and markdown while its tables went stale; the board, the
clock engine and the new UI all saw an empty queue. "Take ownership … the single logging step."

Never sends anything. Clocks start ONLY on a corpus document proving receipt (operator rule 2026-09-12): a
stamped receiving copy, a signed stop sheet, or the office's own e-mail ingested as a document.

  drip_log.py sent     --ladder L --at 2026-10-23 --to addr [--cc a,b] [--channel email|paper|rider|registered|phone|messenger]
                       [--subject S] [--office "Registry of Deeds"] [--matter M] [--note N]
  drip_log.py drafted  --ladder L --at D [--where "jonzschoche Drafts"] [--subject S] [--to addr]
  drip_log.py receipt  --ladder L --at D --proof-doc N [--by "Name"] [--office O] [--matter M]
  drip_log.py reply    --ladder L --at D --from addr --gist G [--doc N] [--outcome ack|answered|partial|performed]
  drip_log.py refused  --ladder L --at D --note N
  drip_log.py rule     --scope global|office|ladder|instrument|charter [--target T] --said "Jonathan's words" --lesson L --enforced-by E
  drip_log.py reconcile [--since 2026-10-15] [--dry-run]   # nightly: logs office mail + our sends nobody logged
  drip_log.py show L                                       # one ladder: events + clock
"""
import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drip_board import add_working_days, UNCERTAIN_NONWORKING, STATUTORY, load_priorities  # noqa: E402

DSN = os.environ.get("PG_DSN") or ("postgresql://n8n:n8npassword@172.18.0.3:5432/n8n" if os.path.isdir("/root/landtek")
                                   else "postgresql://n8n:n8npassword@127.0.0.1:15432/n8n")
OURS = {"jonzschoche@gmail.com", "jonathan@hayuma.org"}
PERIOD = 15
CLOCK_RULE = "RA 6713 §5(a): reply within 15 working days of receipt"
DAY_MATH = "working days; weekends, statutory holidays and uncertain proclamation days skipped (drip_board.py)"
ADDR = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+")


def conn():
    c = psycopg2.connect(DSN)
    return c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def d(s):
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def off_days(cur):
    cur.execute("SELECT day FROM drip_nonworking_day")
    return {r["day"] for r in cur.fetchall()} | set(UNCERTAIN_NONWORKING) | set(STATUTORY)


def matter_for(cur, ladder, given=None):
    if given:
        return given
    pri = load_priorities()
    if ladder in pri.get("ladder_matter", {}):
        return pri["ladder_matter"][ladder]
    cur.execute("SELECT matter_code FROM step_plan WHERE ladder=%s ORDER BY seq LIMIT 1", (ladder,))
    r = cur.fetchone()
    if r:
        return r["matter_code"]
    return "Paracale-001" if ladder.startswith("PAR-") else "MWK-001"


def client_for(matter):
    if matter.startswith("PAR") or matter.startswith("Paracale"):
        return "Paracale-001"
    if matter.startswith("NIBDC"):
        return "NIBDC-001"
    return "MWK-001"


def ensure_ladder(cur, ladder, matter, addressee=None, ask=None):
    """A ladder exists in step_plan the moment anything is logged on it (no more folder-only ladders)."""
    cur.execute("SELECT id, seq FROM step_plan WHERE ladder=%s ORDER BY seq DESC LIMIT 1", (ladder,))
    r = cur.fetchone()
    if r:
        return r["id"]
    cur.execute("""INSERT INTO step_plan (client_code, matter_code, ladder, seq, step_kind, addressee, the_ask,
                                          earns_element, goal_element, goal_kind, gate, state, notes, strategy_file)
                   VALUES (%s,%s,%s,1,'routine_ask',%s,%s,'record element (see ladder folder)','see ladder folder',
                           'legal','Jonathan go (chat)','drafted',%s,%s) RETURNING id""",
                (client_for(matter), matter, ladder, addressee or "(see ladder folder)", ask or "(see ladder folder)",
                 "created by drip_log.py from the first logged event", f"case_work/DRIP_LADDERS_2026-10/{ladder}"))
    return cur.fetchone()["id"]


def set_step(cur, ladder, state):
    order = ["planned", "drafted", "approved", "served", "answered", "done"]
    cur.execute("SELECT id, state FROM step_plan WHERE ladder=%s ORDER BY seq DESC LIMIT 1", (ladder,))
    r = cur.fetchone()
    if r and (r["state"] not in order or order.index(state) > order.index(r["state"])):
        cur.execute("UPDATE step_plan SET state=%s, updated_at=now() WHERE id=%s", (state, r["id"]))


def event(cur, kind, **detail):
    detail = {k: v for k, v in detail.items() if v not in (None, "", [])}
    cur.execute("INSERT INTO drip_event (kind, detail) VALUES (%s, %s) RETURNING id", (kind, json.dumps(detail, default=str)))
    return cur.fetchone()["id"]


def start_clock(cur, ladder, matter, served, proof_doc, office=None, by=None, source="receipt"):
    """Proof of receipt (a corpus document) → the 15-working-day clock runs. A5 wall: proof must be this client's."""
    cur.execute("SELECT id, case_file, matter_code, coalesce(document_title, original_filename) t FROM documents WHERE id=%s",
                (proof_doc,))
    doc = cur.fetchone()
    if not doc:
        raise SystemExit(f"REFUSED: doc {proof_doc} is not in the corpus; ingest the proof first (no proof, no clock).")
    fam = client_for(matter).split("-")[0][:3]
    if doc["case_file"] and not (doc["case_file"] or "").startswith(fam) and not (doc["matter_code"] or "").startswith(fam):
        raise SystemExit(f"REFUSED: proof doc {proof_doc} belongs to {doc['case_file']!r}, not {client_for(matter)} (A5 wall).")
    due = add_working_days(served, PERIOD, off_days(cur))
    cur.execute("SELECT id, served_at FROM office_obligation WHERE ladder=%s AND state = ANY(%s) ORDER BY id DESC LIMIT 1",
                (ladder, ["served_running", "replied_not_performed", "partial", "draft_held", "approved"]))
    ob = cur.fetchone()
    proof_txt = f"doc:{proof_doc} {doc['t'] or ''}".strip()[:300] + (f" (received by {by})" if by else "")
    if ob and ob["served_at"] and ob["served_at"] <= served:
        return ob["id"], ob["served_at"], None   # earliest proof wins; a later proof does not restart the clock
    if ob:
        cur.execute("""UPDATE office_obligation SET served_at=%s, service_proof=%s, service_proof_doc_id=%s, due_at=%s,
                              clock_rule=%s, day_math=%s, state='served_running', updated_at=now() WHERE id=%s""",
                    (served, proof_txt, proof_doc, due, CLOCK_RULE, DAY_MATH, ob["id"]))
        oid = ob["id"]
    else:
        cur.execute("""INSERT INTO office_obligation (matter_code, officer, office, obligation, instrument_ref, served_at,
                              service_proof, service_proof_doc_id, clock_rule, due_at, day_math, state, ladder, intake_source, notes)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'served_running',%s,'drip_log',%s)
                       ON CONFLICT (matter_code, officer, instrument_ref) DO UPDATE SET served_at=EXCLUDED.served_at,
                              service_proof=EXCLUDED.service_proof, service_proof_doc_id=EXCLUDED.service_proof_doc_id,
                              clock_rule=EXCLUDED.clock_rule, due_at=EXCLUDED.due_at, state='served_running', updated_at=now()
                       RETURNING id""",
                    (matter, ladder, office or ladder, f"Reply / action on our request (ladder {ladder})",
                     f"{ladder}:{served}", served, proof_txt, proof_doc, CLOCK_RULE, due, DAY_MATH, ladder,
                     f"clock started from {source}"))
        oid = cur.fetchone()["id"]
    cur.execute("UPDATE step_plan SET obligation_id=%s WHERE ladder=%s AND obligation_id IS NULL", (oid, ladder))
    event(cur, "state_change", ladder=ladder, obligation_id=oid, to="served_running", served=served, due=due,
          proof_doc_id=proof_doc)
    return oid, served, due


def cmd_sent(cur, a):
    m = matter_for(cur, a.ladder, a.matter)
    ensure_ladder(cur, a.ladder, m, a.office or a.to, a.subject)
    eid = event(cur, "sent", ladder=a.ladder, at=a.at, to=a.to, cc=a.cc, channel=a.channel, subject=a.subject,
                office=a.office, note=a.note, client=client_for(m), source=a.source)
    set_step(cur, a.ladder, "approved")
    return f"sent logged #{eid} · {a.ladder} · {a.at}"


def cmd_drafted(cur, a):
    m = matter_for(cur, a.ladder, a.matter)
    ensure_ladder(cur, a.ladder, m, a.to, a.subject)
    eid = event(cur, "drafted", ladder=a.ladder, at=a.at, where=a.where, subject=a.subject, to=a.to, note=a.note)
    set_step(cur, a.ladder, "drafted")
    return f"drafted logged #{eid} · {a.ladder}"


def cmd_receipt(cur, a):
    m = matter_for(cur, a.ladder, a.matter)
    ensure_ladder(cur, a.ladder, m, a.office)
    eid = event(cur, "receipt", ladder=a.ladder, at=a.at, proof_doc_id=a.proof_doc, received_by=a.by, office=a.office,
                note=a.note)
    oid, served, due = start_clock(cur, a.ladder, m, d(a.at), a.proof_doc, a.office, a.by)
    set_step(cur, a.ladder, "served")
    return f"receipt logged #{eid} · clock #{oid} served {served}" + (f" · due {due}" if due else " (earlier proof kept)")


def cmd_reply(cur, a):
    m = matter_for(cur, a.ladder, a.matter)
    ensure_ladder(cur, a.ladder, m, a.frm)
    eid = event(cur, "reply", ladder=a.ladder, at=a.at, **{"from": a.frm}, gist=a.gist, doc_id=a.doc, outcome=a.outcome,
                next=a.next, source=a.source)
    out = f"reply logged #{eid} · {a.ladder}"
    if a.doc:   # an office's own reply proves it received our request
        oid, served, due = start_clock(cur, a.ladder, m, d(a.at), a.doc, a.frm, source="office reply")
        out += f" · clock #{oid} from {served}" + (f" due {due}" if due else "")
    if a.outcome in ("answered", "performed", "partial"):
        state = {"answered": "replied_not_performed", "performed": "performed", "partial": "partial"}[a.outcome]
        cur.execute("UPDATE office_obligation SET state=%s, updated_at=now() WHERE ladder=%s AND state='served_running'",
                    (state, a.ladder))
        set_step(cur, a.ladder, "answered")
    return out


def cmd_refused(cur, a):
    m = matter_for(cur, a.ladder, a.matter)
    ensure_ladder(cur, a.ladder, m)
    eid = event(cur, "field", ladder=a.ladder, at=a.at, outcome="REFUSED_TO_RECEIVE", note=a.note)
    return f"refusal logged #{eid} · {a.ladder} (no receipt, no clock)"


def cmd_rule(cur, a):
    cur.execute("""INSERT INTO drip_feedback (given_at, source, scope, target, feedback_verbatim, lesson, enforced_by, status)
                   VALUES (coalesce(%s::timestamptz, now()), 'chat', %s, %s, %s, %s, %s, 'active') RETURNING id""",
                (a.at, a.scope, a.target, a.said, a.lesson, a.enforced_by))
    return f"rule #{cur.fetchone()['id']} logged ({a.scope})"


STOP = {"the", "and", "for", "from", "with", "request", "your", "our", "letter", "camarines", "norte", "mercedes",
        "re", "fwd", "of", "on", "to", "in", "a", "an", "copy", "copies", "certified", "records"}


def _words(t):
    return {w for w in re.findall(r"[a-z0-9-]{3,}", (t or "").lower()) if w not in STOP}


def cmd_reconcile(cur, a):
    """Nightly safety net: office mail and our own sends that nobody logged are logged automatically, so the
    tables stay fed even when a step is done outside the drip. Office mail becomes a reply (outcome ack) whose
    corpus document (ingest_email_bodies.py) starts the clock."""
    since = a.since or str(date.today() - timedelta(days=10))
    pri = load_priorities()
    cur.execute("""SELECT ladder, kind, event_date, detail FROM drip_event_v WHERE ladder IS NOT NULL
                    AND kind IN ('sent','reply','drafted')""")
    office, first_send, words = {}, {}, {}
    for r in cur.fetchall():
        dt = r["detail"] or {}
        for k in ("to", "from"):
            for x in ADDR.findall(json.dumps(dt.get(k, ""))):
                if x.lower() not in OURS:
                    office.setdefault(x.lower(), set()).add(r["ladder"])
        if r["kind"] == "sent" and r["event_date"]:
            tm = re.search(r"\b(\d{1,2}):(\d{2})", str(dt.get("at", "")))
            sdt = datetime.combine(r["event_date"], datetime.min.time()) + (
                timedelta(hours=int(tm.group(1)), minutes=int(tm.group(2))) if tm else timedelta())
            first_send[r["ladder"]] = min(first_send.get(r["ladder"], sdt), sdt)
        words.setdefault(r["ladder"], set()).update(_words(json.dumps(dt)))
    cur.execute("SELECT ladder, to_address FROM step_plan WHERE to_address IS NOT NULL")
    for r in cur.fetchall():
        if r["to_address"].lower() not in OURS:
            office.setdefault(r["to_address"].lower(), set()).add(r["ladder"])
    office = {k: {l for l in v if not l.startswith("TEST-")} for k, v in office.items()}

    def choose(cands, subject, label):
        cands = sorted(set(cands))
        if len(cands) <= 1:
            return cands
        sw = _words(subject or "")
        scored = sorted(((len(sw & words.get(l, set())), l) for l in cands), reverse=True)
        if scored[0][0] >= 3 and scored[0][0] > scored[1][0]:
            return [scored[0][1]]
        print(f"  AMBIGUOUS, not logged ({label}): '{(subject or '')[:60]}' could be {cands}")
        return []
    cur.execute("""SELECT g.id, g.from_addr, g.to_addrs, g.subject, g.received_at, g.labels, e.doc_id
                     FROM gmail_messages g LEFT JOIN email_documents e ON e.message_id = g.message_id AND e.role='body'
                    WHERE g.received_at >= %s ORDER BY g.received_at""", (since,))
    logged = 0
    for g in cur.fetchall():
        if "DRAFT" in (g["labels"] or []):
            continue
        frm = (ADDR.findall(g["from_addr"] or "") or [""])[0].lower()
        when = (g["received_at"] + timedelta(hours=8)).date()
        if frm in OURS:
            tos = {x.lower() for t in (g["to_addrs"] or []) for x in ADDR.findall(t)}
            for t in tos:
                for lad in choose(office.get(t, []), g["subject"], f"sent to {t}"):
                    cur.execute("SELECT 1 FROM drip_event_v WHERE ladder=%s AND kind IN ('sent','dispatched') AND event_date=%s",
                                (lad, when))
                    if not cur.fetchone():
                        logged += 1
                        if a.dry_run:
                            print(f"  would log sent  · {lad} · {when} · to {t} · {(g['subject'] or '')[:60]}")
                        else:
                            event(cur, "sent", ladder=lad, at=str(when), to=t, subject=(g["subject"] or "")[:120],
                                  source=f"reconcile gmail_messages:{g['id']}")
            continue
        when_dt = g["received_at"] + timedelta(hours=8)   # PHT
        cands = [l for l in office.get(frm, []) if l in first_send and first_send[l] <= when_dt]
        for lad in choose(cands, g["subject"], f"reply from {frm} {when}"):
            cur.execute("SELECT 1 FROM drip_event_v WHERE ladder=%s AND kind='reply' AND event_date=%s", (lad, when))
            if cur.fetchone():
                continue
            logged += 1
            if a.dry_run:
                print(f"  would log reply · {lad} · {when} · {frm} · {(g['subject'] or '')[:60]} · doc {g['doc_id']}")
                continue
            m = matter_for(cur, lad)
            event(cur, "reply", ladder=lad, at=str(when), **{"from": frm}, gist=(g["subject"] or "")[:140],
                  doc_id=g["doc_id"], outcome="ack", source=f"reconcile gmail_messages:{g['id']}")
            if g["doc_id"]:
                try:
                    start_clock(cur, lad, m, when, g["doc_id"], frm, source="office reply (reconcile)")
                except SystemExit as e:
                    print(f"  {lad}: {e}")
    return f"reconcile since {since}: {logged} item(s) {'would be ' if a.dry_run else ''}logged"


def cmd_show(cur, ladder):
    cur.execute("SELECT id, kind, event_date, left(detail::text, 160) d FROM drip_event_v WHERE ladder=%s ORDER BY id", (ladder,))
    for r in cur.fetchall():
        print(f"  #{r['id']} {r['kind']:<12} {r['event_date'] or '':<10} {r['d']}")
    cur.execute("SELECT id, state, served_at, due_at, service_proof_doc_id FROM office_obligation WHERE ladder=%s", (ladder,))
    for r in cur.fetchall():
        print(f"  clock #{r['id']} {r['state']} served {r['served_at']} due {r['due_at']} proof doc {r['service_proof_doc_id']}")
    return ""


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("sent", "drafted", "receipt", "reply", "refused"):
        p = sp.add_parser(name)
        p.add_argument("--ladder", required=True)
        p.add_argument("--at", required=True)
        p.add_argument("--matter")
        p.add_argument("--note")
        p.add_argument("--office")
        p.add_argument("--source", default="chat")
        if name in ("sent", "drafted"):
            p.add_argument("--to")
            p.add_argument("--subject")
        if name == "sent":
            p.add_argument("--cc")
            p.add_argument("--channel", default="email")
        if name == "drafted":
            p.add_argument("--where")
        if name == "receipt":
            p.add_argument("--proof-doc", type=int, required=True)
            p.add_argument("--by")
        if name == "reply":
            p.add_argument("--from", dest="frm", required=True)
            p.add_argument("--gist", required=True)
            p.add_argument("--doc", type=int)
            p.add_argument("--outcome", choices=["ack", "answered", "partial", "performed"], default="ack")
            p.add_argument("--next")
    p = sp.add_parser("rule")
    p.add_argument("--scope", required=True, choices=["global", "office", "ladder", "instrument", "charter"])
    p.add_argument("--target")
    p.add_argument("--said", required=True)
    p.add_argument("--lesson", required=True)
    p.add_argument("--enforced-by", default="drip_feedback ledger")
    p.add_argument("--at")
    p = sp.add_parser("reconcile")
    p.add_argument("--since")
    p.add_argument("--dry-run", action="store_true")
    p = sp.add_parser("show")
    p.add_argument("ladder")
    a = ap.parse_args()
    c, cur = conn()
    try:
        out = {"sent": cmd_sent, "drafted": cmd_drafted, "receipt": cmd_receipt, "reply": cmd_reply, "refused": cmd_refused,
               "rule": cmd_rule, "reconcile": cmd_reconcile}.get(a.cmd)
        msg = out(cur, a) if out else cmd_show(cur, a.ladder)
        if a.cmd == "reconcile" and a.dry_run:
            c.rollback()
        else:
            c.commit()
        if msg:
            print(msg)
    except Exception:
        c.rollback()
        raise


if __name__ == "__main__":
    main()
