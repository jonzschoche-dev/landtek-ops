#!/usr/bin/env python3
"""drip_sweep.py — the Drip (agent_specs/005): obligation-clock engine. $0, deterministic, NEVER sends.

Offices stay on their toes because nothing lapses silently — not because they get mail on a schedule.
  · Demand clocks: served (proof of receipt) → clock runs → on LAPSE the PRE-BUILT consequence is
    staged as an outward_action work order. NO letter-generation path exists for a lapsed clock
    (standing rule 3: "no further letters to that officer").
  · Editions: the Schedule-of-Continuing-Default cadence — same schedule, counters advanced from
    anchor dates in the record, staged as a GMAIL DRAFT for Jonathan (the operator's formula:
    a very concise letter with attachments; annexes carry the weight).
  · Reactive: --record-reply marks replied_not_performed / partial / performed; partial stages the
    same-day "partial is not compliance" reply draft.

A21: everything STAGES (Gmail drafts + work orders). The sweep contains no send path at all —
drafts.create only; no send endpoint is ever called from this module (truth-test greps for it).

  python3 scripts/drip_sweep.py --status                      # the clock board
  python3 scripts/drip_sweep.py --tick                        # daily sweep (lapses + due editions)
  python3 scripts/drip_sweep.py --draft-edition DILG-supervision [--date YYYY-MM-DD]
  python3 scripts/drip_sweep.py --record-service <id> --date YYYY-MM-DD --proof "received-stamp ..."
  python3 scripts/drip_sweep.py --record-reply <id> --kind replied_not_performed|partial|performed
"""
import argparse
import base64
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
ENV = "/root/landtek/.env"
OAUTH_CLIENT_FILES = ("/root/landtek/gmail_oauth_client.json", "/root/landtek/gemini_oauth_client.json")
DRAFT_FALLBACK_DIR = "/root/landtek/case_work/MWK-001/drip_drafts"
DEMAND_PERIOD_DAYS = 15          # D+15 per the instruments; day_math stays NEEDS-COUNSEL on every row

TICKING = ("served_running", "replied_not_performed", "partial")   # states whose clocks can lapse
NEVER_TICK = ("draft_held", "held_counsel_route", "withdrawn", "performed",
              "lapsed", "consequence_staged", "consequence_filed")


def _conn():
    c = psycopg2.connect(DSN)
    c.autocommit = False
    return c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _event(cur, kind, obligation_id=None, edition_id=None, **detail):
    cur.execute("INSERT INTO drip_event (kind, obligation_id, edition_id, detail) VALUES (%s,%s,%s,%s)",
                (kind, obligation_id, edition_id, json.dumps(detail, default=str)))


# ── Gmail DRAFTS (staging surface — drafts.create ONLY; there is no send in this file) ─────────────
def _env_val(key):
    v = os.environ.get(key)
    if v:
        return v
    try:
        for line in open(ENV):
            s = line.strip()
            if s.startswith(key + "=") and not s.startswith("#"):
                return s.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return None


def _gmail_access_token():
    """Raw token POST (the lib chokes on Google reordering scopes — standing memory)."""
    tok = _env_val("GMAIL_REFRESH_TOKEN")
    cid = _env_val("GMAIL_CLIENT_ID")
    sec = _env_val("GMAIL_CLIENT_SECRET")
    if not (cid and sec):
        for f in OAUTH_CLIENT_FILES:
            try:
                d = json.load(open(f))
                d = d.get("installed", d.get("web", d))
                cid, sec = d.get("client_id"), d.get("client_secret")
                if cid and sec:
                    break
            except Exception:
                continue
    if not (tok and cid and sec):
        return None, "gmail_creds_missing"
    body = urllib.parse.urlencode({"client_id": cid, "client_secret": sec,
                                   "refresh_token": tok, "grant_type": "refresh_token"}).encode()
    try:
        req = urllib.request.Request("https://oauth2.googleapis.com/token", data=body, method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read()).get("access_token"), None
    except Exception as e:
        return None, f"token:{type(e).__name__}"


def stage_gmail_draft(subject, body_text, to_addr=""):
    """Create a DRAFT in the case Gmail (jonzschoche@gmail.com). Returns (draft_id, err).
    Degrade path: drafts.create needs gmail.compose/modify — if the token was minted send+readonly
    it 403s; caller falls back to a file + work order and surfaces the re-mint need. NEVER sends."""
    at, err = _gmail_access_token()
    if not at:
        return None, err
    raw = f"To: {to_addr}\r\nSubject: {subject}\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n{body_text}"
    payload = json.dumps({"message": {"raw": base64.urlsafe_b64encode(raw.encode()).decode()}}).encode()
    try:
        req = urllib.request.Request("https://gmail.googleapis.com/gmail/v1/users/me/drafts",
                                     data=payload, method="POST",
                                     headers={"Authorization": f"Bearer {at}",
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read()).get("id"), None
    except urllib.error.HTTPError as e:
        return None, f"drafts.create HTTP {e.code} (403 ⇒ token needs gmail.compose re-mint)"
    except Exception as e:
        return None, f"drafts.create {type(e).__name__}"


def _stage_draft_with_fallback(cur, subject, body, ref_kind, ref_id):
    did, err = stage_gmail_draft(subject, body)
    if did:
        _event(cur, "edition_drafted" if ref_kind == "edition" else "draft_staged",
               edition_id=ref_id if ref_kind == "edition" else None,
               obligation_id=ref_id if ref_kind == "obligation" else None,
               gmail_draft_id=did, subject=subject)
        return f"gmail-draft:{did}"
    os.makedirs(DRAFT_FALLBACK_DIR, exist_ok=True)
    path = os.path.join(DRAFT_FALLBACK_DIR,
                        f"{date.today().isoformat()}_{ref_kind}{ref_id}_{subject[:40].replace(' ', '_')}.txt")
    open(path, "w").write(f"Subject: {subject}\n\n{body}")
    _event(cur, "draft_staged_file", edition_id=ref_id if ref_kind == "edition" else None,
           obligation_id=ref_id if ref_kind == "obligation" else None, path=path, gmail_err=err)
    return f"file:{path} (gmail: {err})"


# ── the edition letter (the operator's formula: very concise letter; annexes carry the weight) ─────
def render_edition(ed, as_of):
    counters = ed["counters"] or {}
    rows = []
    for label, anchor in sorted(counters.items(), key=lambda kv: kv[1]):
        days = (as_of - date.fromisoformat(str(anchor))).days
        rows.append(f"  {days:>4} days   {label}   (of record since {anchor})")
    schedule = "\n".join(rows)
    body = (
        f"[DRAFT — edition {as_of.isoformat()} · {ed['track']} · STAGED BY THE DRIP, NOT SERVED]\n\n"
        "Dear Sir/Madam:\n\n"
        "This reiterates the pending matters of record in the attached Schedule of Continuing\n"
        "Default. No new request is made. Each counter below runs from a documented instrument\n"
        "or letter already before your office; performed items, if any, are so marked.\n\n"
        f"Annex A — Schedule of Continuing Default (as of {as_of.isoformat()}):\n{schedule}\n\n"
        "The prior instruments, proofs of receipt, and the verbatim provisions are re-enclosed as\n"
        "Annexes B–D. On continued default through the next schedule date, the record supports the\n"
        "elevation already described in the instrument of 10 September 2026.\n\n"
        "Respectfully,\n[for Jonathan's review — attach annex PDFs before sending; nothing has been sent]\n"
    )
    subject = f"[DRIP DRAFT] {ed['track']} — Schedule of Continuing Default, edition {as_of.isoformat()}"
    return subject, body


# ── core verbs ──────────────────────────────────────────────────────────────────────────────────────
def tick(cur, today=None):
    today = today or date.today()
    staged = []
    # 1) LAPSES → stage the pre-built consequence. There is deliberately NO letter path here.
    cur.execute("SELECT * FROM office_obligation WHERE state = ANY(%s) AND due_at IS NOT NULL AND due_at < %s",
                (list(TICKING), today))
    for ob in cur.fetchall():
        cur.execute("UPDATE office_obligation SET state='lapsed', updated_at=now() WHERE id=%s", (ob["id"],))
        _event(cur, "lapse", obligation_id=ob["id"], due_at=ob["due_at"], officer=ob["officer"])
        steps = json.dumps([{"name": "prepare", "agent": "domain-agent", "mode": "handoff", "tier": "T2"},
                            {"name": "approve", "agent": "human", "mode": "handoff", "tier": "T3"}])
        cur.execute("""INSERT INTO work_orders (kind, matter_code, title, status, steps, current_step,
                                                governed, created_by, target_ref)
                       VALUES ('outward_action', %s, %s, 'queued', %s, 0, true, 'drip', %s)""",
                    (ob["matter_code"],
                     f"DRIP lapse — {ob['officer']}: file pre-built consequence ({(ob['consequence_ref'] or '?')[:80]}) — {ob['counsel_gate'] or 'NEEDS-COUNSEL'}",
                     steps, f"drip:{ob['officer']}:{ob['id']}"))
        cur.execute("UPDATE office_obligation SET state='consequence_staged', updated_at=now() WHERE id=%s", (ob["id"],))
        _event(cur, "stage_consequence", obligation_id=ob["id"], consequence=ob["consequence_ref"])
        staged.append(f"LAPSED→consequence staged: {ob['officer']} ({ob['obligation'][:50]}…)")
    # 2) EDITIONS due → concise letter draft into Gmail drafts.
    cur.execute("SELECT * FROM drip_edition WHERE next_edition_due IS NOT NULL AND next_edition_due <= %s", (today,))
    for ed in cur.fetchall():
        subject, body = render_edition(ed, today)
        where = _stage_draft_with_fallback(cur, subject, body, "edition", ed["id"])
        cur.execute("UPDATE drip_edition SET next_edition_due=%s WHERE id=%s",
                    (today + timedelta(days=15), ed["id"]))
        staged.append(f"EDITION drafted ({ed['track']}) → {where}")
    return staged


def status(cur, today=None):
    today = today or date.today()
    cur.execute("SELECT id, officer, state, served_at, due_at, left(obligation,60) AS what "
                "FROM office_obligation ORDER BY id")
    print(f"\nDRIP BOARD — {today.isoformat()}  (clocks start ONLY at proof of receipt)")
    print("-" * 100)
    for r in cur.fetchall():
        clock = ("no clock (unserved)" if not r["served_at"] else
                 f"due {r['due_at']} ({(r['due_at'] - today).days:+d}d)" if r["due_at"] else "served, no rule?")
        print(f"  #{r['id']:<3} {r['officer']:<18} {r['state']:<22} {clock:<26} {r['what']}")
    cur.execute("SELECT track, edition_date, next_edition_due, state FROM drip_edition ORDER BY id")
    for e in cur.fetchall():
        print(f"  ── edition {e['track']}: last {e['edition_date']}, next due {e['next_edition_due']} "
              f"({(e['next_edition_due'] - today).days:+d}d) [{e['state']}]")
    print("-" * 100)


def record_service(cur, oid, served, proof):
    cur.execute("SELECT * FROM office_obligation WHERE id=%s", (oid,))
    ob = cur.fetchone()
    if not ob:
        raise SystemExit(f"no obligation #{oid}")
    if ob["state"] in ("withdrawn", "held_counsel_route"):
        raise SystemExit(f"#{oid} is {ob['state']} — it cannot be served/ticked (ledger rule).")
    if not proof:
        raise SystemExit("service requires --proof (received-stamp / registry card). Drafting never starts a clock.")
    due = date.fromisoformat(served) + timedelta(days=DEMAND_PERIOD_DAYS)
    cur.execute("""UPDATE office_obligation SET served_at=%s, service_proof=%s, due_at=%s,
                         state='served_running', updated_at=now() WHERE id=%s""",
                (served, proof, due, oid))
    _event(cur, "state_change", obligation_id=oid, to="served_running", served=served, due=str(due), proof=proof)
    print(f"#{oid} served {served} (proof: {proof}) → clock runs, D+{DEMAND_PERIOD_DAYS} = {due} "
          f"(day math: {ob['day_math']})")


def record_reply(cur, oid, kind):
    assert kind in ("replied_not_performed", "partial", "performed")
    cur.execute("UPDATE office_obligation SET state=%s, updated_at=now() WHERE id=%s RETURNING officer, obligation",
                (kind, oid))
    ob = cur.fetchone()
    _event(cur, "reply_recorded", obligation_id=oid, kind=kind)
    if kind == "partial":   # same-day "partial ≠ compliance" reply — staged, never sent
        body = ("[DRAFT — same-day response, STAGED NOT SENT]\n\nDear Sir/Madam:\n\n"
                "We acknowledge receipt of a partial response. Partial performance is not compliance "
                "with the demand of record; the specific items outstanding remain due and the period "
                "stated in our instrument continues to run.\n\nRespectfully,\n")
        where = _stage_draft_with_fallback(cur, f"[DRIP DRAFT] Partial is not compliance — {ob['officer']}",
                                           body, "obligation", oid)
        print(f"partial recorded → same-day reply staged: {where}")
    print(f"#{oid} → {kind}  (a reply is not performance; the consequence path survives a paper reply)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--tick", action="store_true")
    ap.add_argument("--draft-edition", metavar="TRACK")
    ap.add_argument("--date")
    ap.add_argument("--record-service", type=int, metavar="ID")
    ap.add_argument("--proof")
    ap.add_argument("--record-reply", type=int, metavar="ID")
    ap.add_argument("--kind")
    a = ap.parse_args()
    conn, cur = _conn()
    try:
        if a.status:
            status(cur)
        elif a.tick:
            for line in (tick(cur) or ["tick clean — no lapses, no editions due"]):
                print(f"  {line}")
            conn.commit()
        elif a.draft_edition:
            as_of = date.fromisoformat(a.date) if a.date else date.today()
            cur.execute("SELECT * FROM drip_edition WHERE track=%s ORDER BY edition_date DESC LIMIT 1",
                        (a.draft_edition,))
            ed = cur.fetchone() or sys.exit(f"no edition track {a.draft_edition!r}")
            subject, body = render_edition(ed, as_of)
            print(f"  → {_stage_draft_with_fallback(cur, subject, body, 'edition', ed['id'])}")
            conn.commit()
        elif a.record_service:
            record_service(cur, a.record_service, a.date or date.today().isoformat(), a.proof)
            conn.commit()
        elif a.record_reply:
            record_reply(cur, a.record_reply, a.kind or "replied_not_performed")
            conn.commit()
        else:
            status(cur)
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close(); conn.close()


if __name__ == "__main__":
    main()
