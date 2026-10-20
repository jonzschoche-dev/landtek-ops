#!/usr/bin/env python3
"""drip_draft_queue.py — CONSTANT MOVEMENT for the drip: there are always drafts waiting for Jonathan's comment.

$0, deterministic, NEVER sends, never stages an e-mail draft, never prints. (Spec: agent_specs/005_drip.md "THE REVIEW
QUEUE"; schema: migrations/DRAFT_drip_v2_delta_review_queue.sql.)

  --load DIR       load ladder JSON files (ops/drip/ladders/*.json) into step_plan (upsert on ladder+seq; never deletes)
  --fill           top the queue up to drip_queue_config.min_awaiting_comment from v_next_baby_step: take the next
                   un-queued routine step whose letter file exists, lint it against the LIVE drip_lint_rule table,
                   require send_account (+ thread_ref unless paper / no prior thread), and insert it as
                   'awaiting_comment'. Steps with no letter yet become a work_order 'drip_draft_needed' for the desk.
  --next           print the ONE next draft to put in front of Jonathan (marks shown_at)
  --comment ID "…" record Jonathan's comment → status 'revising' + work_order 'drip_revise'; then refills
  --revised ID     after the desk edits the file: re-read, re-lint, version+1, resolve comments, back to 'awaiting_comment'
  --ready ID REF   Jonathan said "make the draft": status 'ready_for_draft' with his approval_ref; then refills.
                   (Staging the e-mail draft in the thread's origin account is a separate, explicit step.)
  --status         the queue board
"""
import argparse
import glob
import json
import os
import re
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROUTINE = ("routine_ask", "courtesy_edition")
MAX_WORDS = 250


def conn():
    c = psycopg2.connect(DSN)
    c.autocommit = False
    return c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def cfg(cur, key, default):
    cur.execute("SELECT value FROM drip_queue_config WHERE key=%s", (key,))
    r = cur.fetchone()
    return r["value"] if r else default


def load(cur, d):
    n = 0
    for f in sorted(glob.glob(os.path.join(d, "*.json"))):
        for r in json.load(open(f)):
            cur.execute("""INSERT INTO step_plan (client_code, matter_code, ladder, seq, step_kind, addressee, the_ask,
                             earns_element, goal_element, goal_kind, gate, if_answered, if_silent, instrument_path,
                             history_ref, send_account, thread_ref, notes)
                           VALUES (%(client_code)s,%(matter_code)s,%(ladder)s,%(seq)s,%(step_kind)s,%(addressee)s,%(the_ask)s,
                             %(earns_element)s,%(goal_element)s,%(goal_kind)s,%(gate)s,%(if_answered)s,%(if_silent)s,
                             %(instrument_path)s,%(history_ref)s,%(send_account)s,%(thread_ref)s,%(notes)s)
                           ON CONFLICT (ladder, seq) DO UPDATE SET the_ask=EXCLUDED.the_ask,
                             instrument_path=coalesce(EXCLUDED.instrument_path, step_plan.instrument_path),
                             history_ref=EXCLUDED.history_ref,
                             send_account=coalesce(EXCLUDED.send_account, step_plan.send_account),
                             thread_ref=coalesce(EXCLUDED.thread_ref, step_plan.thread_ref), updated_at=now()""",
                        {k: r.get(k) for k in ("client_code", "matter_code", "ladder", "seq", "step_kind", "addressee",
                                               "the_ask", "earns_element", "goal_element", "goal_kind", "gate",
                                               "if_answered", "if_silent", "instrument_path", "history_ref",
                                               "send_account", "thread_ref", "notes")})
            n += 1
    return n


def lint(cur, text, audience="official", rung=1, cc_override=False, addressee=""):
    """Run the LIVE regex rules + the code checks the sleep doctrine names. Returns {'refuse': [...], 'flag': [...]}."""
    out = {"refuse": [], "flag": []}
    cur.execute("SELECT rule_class, pattern, audiences, max_rung, action FROM drip_lint_rule WHERE pattern IS NOT NULL")
    for r in cur.fetchall():
        if audience not in (r["audiences"] or []) or (r["max_rung"] is not None and rung > r["max_rung"]):
            continue
        pat = r["pattern"].replace(r"\m", r"\b").replace(r"\M", r"\b")
        try:
            hits = re.findall(pat, text, re.I)
        except re.error:
            continue
        if re.search(r"(?i)court|clerk|branch", addressee or ""):
            hits = [h for h in hits if not re.fullmatch(r"(?i)court", h if isinstance(h, str) else h[0])]   # a court's own name is not a tell
        if hits:
            out[r["action"]].append(f"{r['rule_class']}: {sorted({h if isinstance(h, str) else h[0] for h in hits})}")
    words = len(re.findall(r"\w+", text))
    if words > MAX_WORDS + 40:            # letterhead/signature lines counted; body cap ~250
        out["refuse"].append(f"routine_too_long: {words} words")
    if re.search(r"(?i)copy furnished|\bcc\b", text) and not cc_override:
        out["refuse"].append("supervisor_cc_early: cc without Jonathan's per-item instruction")
    if not re.search(r"(?i)gladly|happy to|we will (gladly )?(pay|cover)|collect|e-mail (is|would be) (perfectly )?fine", text):
        out["refuse"].append("missing_easy_yes")
    if "Thank you very much" not in text:
        out["flag"].append("missing_gracious_close")
    return out, words


STOPW = {"hon", "atty", "engr", "mayor", "mrs", "ms", "mr", "dir", "rd", "jr", "rea", "treasurer", "assessor",
         "municipal", "provincial", "secretary", "councilor", "vice", "the", "of", "office", "and"}


def _surnames(text):
    toks = [t.lower() for t in re.split(r"[^A-Za-z]+", text or "") if len(t) > 2 and t.lower() not in STOPW]
    return set(toks)


def posture(cur, addressee, client):
    """X17: is the addressee a respondent/duty-holder in a LIVE adversarial track we brought (complaint, appeal,
    referral, judicial)? Returns the live track codes. Matched on surname tokens within the same client (A5)."""
    names = _surnames(addressee)
    if not names:
        return []
    cur.execute("""SELECT DISTINCT t.track_code, p.official FROM track_party p JOIN matter_track t USING (track_code)
                    WHERE t.client_code=%s AND t.kind IN ('complaint','appeal','referral','judicial')
                      AND t.true_status !~* '(closed|dismissed|lapsed|withdrawn|resolved|held|draft|not (yet )?filed|planned|proposed|not sent)'
                      AND p.role IN ('respondent','duty_holder')""", (client,))
    return sorted({r["track_code"] for r in cur.fetchall() if names & _surnames(r["official"])})


def fill(cur, c):
    target = int(cfg(cur, "min_awaiting_comment", "3"))
    cur.execute("SELECT count(*) AS n FROM drip_instrument WHERE status IN ('awaiting_comment','revising')")
    have = cur.fetchone()["n"]
    added, wanted = [], []
    if have >= target:
        return added, wanted
    prio = [x.strip() for x in cfg(cur, "priority_ladders", "").split(",") if x.strip()]
    cur.execute("""SELECT sp.* FROM step_plan sp
                    WHERE sp.state IN ('planned','drafted') AND sp.step_kind = ANY(%s)
                      AND NOT EXISTS (SELECT 1 FROM drip_instrument i WHERE i.step_plan_id = sp.id
                                       AND i.status NOT IN ('superseded','refused_lint'))
                      AND NOT EXISTS (SELECT 1 FROM step_plan p2 WHERE p2.ladder = sp.ladder AND p2.seq < sp.seq
                                       AND p2.state IN ('planned','drafted','approved'))
                      AND coalesce(sp.notes,'') !~* 'barandon route|counsel-gated|posture check'
                    ORDER BY coalesce(array_position(%s::text[], sp.ladder), 999),
                             (sp.goal_kind IN ('financial','both')) DESC, sp.ladder, sp.seq""", (list(ROUTINE), prio))
    for sp in cur.fetchall():
        if have + len(added) >= target:
            break
        path = sp["instrument_path"]
        full = os.path.join(REPO, path) if path else None
        if not full or not os.path.isfile(full):
            wanted.append(sp["ladder"])
            cur.execute("""INSERT INTO work_orders (kind, matter_code, title, status, created_by, target_ref)
                           SELECT 'drip_draft_needed', %s, %s, 'queued', 'drip_draft_queue', %s
                            WHERE NOT EXISTS (SELECT 1 FROM work_orders WHERE kind='drip_draft_needed' AND target_ref=%s
                                               AND status NOT IN ('done','cancelled'))""",
                        (sp["matter_code"], f"Draft step {sp['seq']} of {sp['ladder']}: {sp['the_ask'][:120]}",
                         f"step_plan:{sp['id']}", f"step_plan:{sp['id']}"))
            continue
        live = posture(cur, sp["addressee"], sp["client_code"])
        if live and "X17-ok:" not in (sp["notes"] or ""):
            cur.execute("UPDATE step_plan SET state='skipped', notes=coalesce(notes,'')||%s, updated_at=now() WHERE id=%s",
                        (f" | X17 HELD {sp['ladder']}: addressee is a respondent in live track(s) {live}; route to an alternate"
                         " custodian or mark 'X17-ok: <why uniquely theirs>' after Jonathan reviews", sp["id"]))
            wanted.append(f"{sp['ladder']} (X17 posture: {live})")
            continue
        body = open(full).read()
        res, words = lint(cur, body, cc_override="cc per Jonathan" in (sp["notes"] or ""), addressee=sp["addressee"])
        status = "awaiting_comment" if not res["refuse"] else "refused_lint"
        cur.execute("""INSERT INTO drip_instrument (step_plan_id, kind, audience, client_code, drafted_by, file_path,
                         body_md, word_count, lint_result, status, send_account, thread_ref, queued_at)
                       VALUES (%s,%s,'official',%s,'claude',%s,%s,%s,%s,%s,%s,%s,now()) RETURNING id""",
                    (sp["id"], sp["step_kind"], sp["client_code"], path, body, words, json.dumps(res), status,
                     sp.get("send_account"), sp.get("thread_ref")))
        iid = cur.fetchone()["id"]
        if status == "awaiting_comment":
            cur.execute("UPDATE step_plan SET state='drafted', updated_at=now() WHERE id=%s", (sp["id"],))
            added.append((iid, sp["ladder"]))
        else:
            wanted.append(f"{sp['ladder']} (lint: {res['refuse']})")
    return added, wanted


def show_next(cur):
    cur.execute("SELECT * FROM v_review_queue LIMIT 1")
    r = cur.fetchone()
    if not r:
        print("Queue empty — run --fill.")
        return
    cur.execute("SELECT body_md, lint_result FROM drip_instrument WHERE id=%s", (r["id"],))
    i = cur.fetchone()
    cur.execute("UPDATE drip_instrument SET shown_at=now() WHERE id=%s", (r["id"],))
    print(f"#{r['id']} v{r['version']} · {r['ladder']} step {r['seq']} · {r['addressee']} · {r['goal_kind']} · "
          f"{r['word_count']} words · send: {r['send_account'] or '[TO SET]'} · thread: {r['thread_ref'] or '—'} · "
          f"open comments: {r['open_comments']}\n")
    print(i["body_md"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--load")
    ap.add_argument("--fill", action="store_true")
    ap.add_argument("--next", action="store_true")
    ap.add_argument("--comment", nargs=2, metavar=("ID", "TEXT"))
    ap.add_argument("--revised", type=int)
    ap.add_argument("--ready", nargs=2, metavar=("ID", "APPROVAL_REF"))
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    c, cur = conn()
    if a.load:
        print("loaded", load(cur, a.load), "steps")
    if a.comment:
        iid, text = int(a.comment[0]), a.comment[1]
        cur.execute("SELECT version, step_plan_id FROM drip_instrument WHERE id=%s", (iid,))
        v = cur.fetchone()
        cur.execute("INSERT INTO drip_comment (instrument_id, on_version, comment) VALUES (%s,%s,%s)", (iid, v["version"], text))
        cur.execute("UPDATE drip_instrument SET status='revising', updated_at=now() WHERE id=%s", (iid,))
        cur.execute("""INSERT INTO work_orders (kind, title, status, created_by, target_ref)
                       VALUES ('drip_revise', %s, 'queued', 'drip_draft_queue', %s)""",
                    (f"Revise drip draft #{iid}: {text[:150]}", f"drip_instrument:{iid}"))
        a.fill = True
    if a.revised:
        cur.execute("SELECT file_path, version FROM drip_instrument WHERE id=%s", (a.revised,))
        r = cur.fetchone()
        body = open(os.path.join(REPO, r["file_path"])).read()
        res, words = lint(cur, body, cc_override=True)
        cur.execute("""UPDATE drip_instrument SET body_md=%s, word_count=%s, lint_result=%s, version=version+1,
                         status=%s, updated_at=now() WHERE id=%s""",
                    (body, words, json.dumps(res), "awaiting_comment" if not res["refuse"] else "revising", a.revised))
        cur.execute("UPDATE drip_comment SET resolved_in_version=%s WHERE instrument_id=%s AND resolved_in_version IS NULL",
                    (r["version"] + 1, a.revised))
        cur.execute("""UPDATE work_orders SET status='done', updated_at=now() WHERE kind='drip_revise'
                         AND target_ref=%s AND status='queued'""", (f"drip_instrument:{a.revised}",))
    if a.ready:
        cur.execute("UPDATE drip_instrument SET status='ready_for_draft', approval_ref=%s, updated_at=now() WHERE id=%s",
                    (a.ready[1], int(a.ready[0])))
        cur.execute("""INSERT INTO work_orders (kind, title, status, created_by, target_ref)
                       VALUES ('drip_stage_draft', %s, 'awaiting_handoff', 'drip_draft_queue', %s)""",
                    (f"Stage e-mail draft (or print set) for drip #{a.ready[0]} in its thread's origin account",
                     f"drip_instrument:{a.ready[0]}"))
        a.fill = True
    if a.fill:
        added, wanted = fill(cur, c)
        print("queued:", added or "—", "| needs drafting / lint:", wanted or "—")
    if a.next:
        show_next(cur)
    if a.status:
        cur.execute("SELECT status, count(*) FROM drip_instrument GROUP BY 1 ORDER BY 1")
        for r in cur.fetchall():
            print(f"{r['status']:18} {r['count']}")
        cur.execute("SELECT count(*) AS n FROM work_orders WHERE kind IN ('drip_draft_needed','drip_revise') AND status='queued'")
        print("desk work orders open:", cur.fetchone()["n"])
    c.commit()


if __name__ == "__main__":
    sys.exit(main())
