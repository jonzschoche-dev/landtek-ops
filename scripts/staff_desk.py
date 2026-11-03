#!/usr/bin/env python3
"""staff_desk.py — the field-officer desk on Messenger (Kristyle first) + Jonathan's one-at-a-time approvals.

Product interview 2026-11-02/03 (case_work/PRODUCT_INTERVIEW_2026-11/INTERVIEW_LOG.md):
  * first daily user = Kristyle, on Messenger; Jonathan approves on Messenger too;
  * the drip's paper route lands here as a drip_service_task: serve it, photo the stamped receiving copy,
    Jonathan confirms, the clock starts (drip_log.start_clock: no proof, no clock);
  * EARNED autonomy: every yes/no lands in approval_asks under a pattern_key; v_autonomy_record is the
    track record Jonathan promotes on. Nothing here promotes itself.

Routing (called first by leo_instant._process):
  route(cur, mid, channel, uid, text) -> True when this desk handled the message, else False (Leo as usual).
    * an ACTIVE staff_desk_members identity -> the staff desk (tasks, proof photos, voice onboarding);
    * the operator replying yes/no while an approval is asked -> the decision is applied.
SAFE BY CONSTRUCTION: inactive members are ignored (the switch is staff_desk_members.active, seeded false);
messages go only to active staff and the operator; nothing is ever sent to an office from here.

CLI:
  staff_desk.py --tick [--dry-run]            auto-propose paper tasks, ask the next approval, morning briefs
  staff_desk.py propose-task --instrument N --address "..." --due YYYY-MM-DD [--method hand] [--dry-run]
  staff_desk.py --status                      members, open tasks, approvals, autonomy record
  staff_desk.py readiness [--assignee kristyle]   can the bot derive this officer's next steps from the record?
  staff_desk.py activate [--assignee kristyle]    THE SWITCH (Jonathan's go only); refuses unless readiness passes
  staff_desk.py --probe "text" --as messenger:UID [--media-msg ID] [--dry-run]
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, "/root/landtek/scripts")
sys.path.insert(0, "/root/landtek/leo_tools")
import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
OPERATOR = ("messenger", "37446980471566856")      # Jonathan's Messenger PSID (internal_targets, deploy_895)
MANILA = timezone(timedelta(hours=8))
BRIEF_HOUR = 8                                       # morning brief at/after 08:00 Manila
MEDIA_WAIT_S = 45

YES = re.compile(r"^\s*(yes|y|oo|opo|sige|go|ok|okay|approve[d]?)\b[\s.!]*$", re.I)
NO = re.compile(r"^\s*(no|n|hindi|huwag|wag|reject(ed)?|stop)\b[\s.!]*$", re.I)
TASKS = re.compile(r"\b(task|tasks|gawain|gagawin|trabaho|next|sunod|ano na)\b", re.I)
DIGIT = re.compile(r"^\s*#?(\d{1,6})\s*$")
GREETING = re.compile(r"^\s*(hi|hello|hey|good (morning|afternoon|evening)|magandang (umaga|hapon|gabi))\W*$", re.I)

DRY = False                                          # set by the CLI; route() from leo_instant is always live
_outbox = []                                         # dry-run capture


# ── plumbing ───────────────────────────────────────────────────────────────────────────────────────────

def _send(channel, uid, text):
    """Send to an ACTIVE staff member or the operator only. Dry-run prints instead."""
    if DRY:
        _outbox.append((channel, uid, text))
        print(f"  [dry-send {channel}:{uid}] {text}")
        return True
    if channel != "messenger":
        return False
    import channel_adapters as ca
    return bool(ca._messenger_send(uid, text))


def _today_manila():
    return datetime.now(MANILA).date()


def _member(cur, channel, uid, active_only=True):
    cur.execute("SELECT * FROM staff_desk_members WHERE channel=%s AND channel_user_id=%s"
                + (" AND active" if active_only else ""), (channel, str(uid)))
    return cur.fetchone()


def _set_state(cur, m, **kw):
    st = dict(m["state"] or {})
    for k, v in kw.items():
        if v is None:
            st.pop(k, None)
        else:
            st[k] = v
    cur.execute("UPDATE staff_desk_members SET state=%s, updated_at=now() WHERE channel=%s AND channel_user_id=%s",
                (json.dumps(st), m["channel"], m["channel_user_id"]))
    m["state"] = st


def _mark_handled(cur, mid, channel, uid, reason):
    """One ledger row per handled inbound so the leo_service timer never double-processes it."""
    if not mid:
        return
    try:
        import leo_service as ls
        ls._log(cur, msg=mid, channel=channel, uid=str(uid), client=None, cand=None, verdict=None, fails=None,
                warns=0, remed=False, human=None, guard="internal", model=None, action="staff_desk", reason=reason)
    except Exception as e:
        print(f"[staff_desk] ledger skip: {type(e).__name__}: {e}", flush=True)


# ── tasks ──────────────────────────────────────────────────────────────────────────────────────────────
# Two kinds, one list for the officer:
#   serve  = drip_service_task: deliver an approved drip letter; proof = the stamped receiving copy ("Serve 12")
#   errand = staff_task: any other errand from the record (e.g. company registration steps) ("Task 3")

METHOD_WORD = {"hand": "Hand-deliver", "lbc": "Send by LBC", "registered_mail": "Send by registered mail",
               "email": "Email", "efiling": "E-file"}


def _open_tasks(cur, assignee):
    """Open SERVE tasks (drip letters)."""
    cur.execute("""SELECT t.*, i.client_code, s.ladder, s.matter_code, s.addressee
                     FROM drip_service_task t
                     JOIN drip_instrument i ON i.id = t.instrument_id
                     LEFT JOIN step_plan s ON s.id = i.step_plan_id
                    WHERE t.assignee=%s AND t.state IN ('open','served_awaiting_proof')
                    ORDER BY t.due_date NULLS LAST, t.id""", (assignee,))
    return cur.fetchall()


def _open_errands(cur, assignee, include_waiting=False):
    states = ["open", "done_awaiting_check"] if include_waiting else ["open"]
    cur.execute("""SELECT e.*, mt.client_code FROM staff_task e LEFT JOIN matters mt ON mt.matter_code = e.matter_code
                    WHERE e.assignee=%s AND e.state = ANY(%s)
                    ORDER BY e.due_date NULLS LAST, e.seq, e.id""", (assignee, states))
    return cur.fetchall()


def _candidates(cur, assignee):
    """Everything she can act on now, soonest due first: [(kind, row)]."""
    items = [("serve", t) for t in _open_tasks(cur, assignee)] + [("errand", e) for e in _open_errands(cur, assignee)]
    return sorted(items, key=lambda kr: (kr[1]["due_date"] is None, kr[1]["due_date"] or date.max))


def _task_line(t):
    due = t["due_date"].strftime("%a %d %b") if t["due_date"] else "no date set"
    who = t["addressee"] or "the office"
    if t["state"] == "served_awaiting_proof":
        return (f"Serve {t['id']}: you marked the letter to {who} as served. "
                f"Send me a photo of the stamped receiving copy.")
    return (f"Serve {t['id']}: {METHOD_WORD.get(t['method'], t['method'])} the letter to {who} at {t['address']}. "
            f"Due {due}. Once it's received, send me a photo of the stamped receiving copy.")


def _errand_line(e):
    due = e["due_date"].strftime("%a %d %b") if e["due_date"] else "no date set"
    return f"Task {e['id']}: {e['title']}. Due {due}. Reply \"how {e['id']}\" for the steps, \"done {e['id']}\" when finished."


def _lc(t):
    """'The owner's name' -> 'the owner's name' mid-sentence (leave acronyms like 'SEC' alone)."""
    return (t[0].lower() + t[1:]) if t and len(t) > 1 and not t[1].isupper() else t


def _line(kind, row):
    return _task_line(row) if kind == "serve" else _errand_line(row)


def _next_task_text(cur, m):
    items = _candidates(cur, m["assignee_key"])
    if not items:
        return "No open tasks right now. I'll message you when there's one."
    more = f" ({len(items) - 1} more after this; say \"tasks\" for the next.)" if len(items) > 1 else ""
    return _line(*items[0]) + more


def _all_tasks_text(cur, m):
    items = _candidates(cur, m["assignee_key"])
    if not items:
        return "No open tasks right now."
    return "Your open tasks, soonest first: " + " ".join(
        f"{'Serve' if k == 'serve' else 'Task'} {r['id']} ({r['due_date'].strftime('%d %b') if r['due_date'] else 'no date'})"
        for k, r in items) + ". Say \"how N\" for any of them."


# ── staff desk ─────────────────────────────────────────────────────────────────────────────────────────

VOICE_ASK = ("Hi {name}, it's Leo. I'll send you your LandTek tasks here and take your proof photos. "
             "Before we start: how do you want me to talk to you? English, Tagalog, Taglish or Bikol, "
             "short or detailed? Just tell me in your own words.")
DONE = re.compile(r"\b(done|tapos|nagawa|finished|served|naserve|na-serve|nai-serve|delivered)\s*#?\s*(\d+)?\b", re.I)
SERVE_WORDS = ("served", "naserve", "na-serve", "nai-serve", "delivered")
HOW = re.compile(r"^\s*(how|paano)\s*#?\s*(\d+)\s*\??\s*$", re.I)
LIST = re.compile(r"\b(all|lahat|list)\b", re.I)


def _handle_staff(cur, m, mid, text):
    text = (text or "").strip()
    st = m["state"] or {}

    if not (m["voice"] or {}).get("raw"):
        if st.get("awaiting_voice") and text and text != "[media]" and not GREETING.match(text):
            cur.execute("UPDATE staff_desk_members SET voice=%s, updated_at=now() WHERE channel=%s AND channel_user_id=%s",
                        (json.dumps({"raw": text, "recorded_at": str(_today_manila())}), m["channel"], m["channel_user_id"]))
            _set_state(cur, m, awaiting_voice=None)
            _send(m["channel"], m["channel_user_id"], "Got it, noted. " + _next_task_text(cur, m))
            return "voice_recorded"
        if text != "[media]":
            _set_state(cur, m, awaiting_voice=True)
            _send(m["channel"], m["channel_user_id"], VOICE_ASK.format(name=m["name"]))
            return "voice_asked"

    if text == "[media]" or st.get("pending_media") and DIGIT.match(text):
        return _handle_media(cur, m, mid, text)

    hm = HOW.match(text)
    if hm:
        e = next((x for x in _open_errands(cur, m["assignee_key"], True) if x["id"] == int(hm.group(2))), None)
        if not e:
            _send(m["channel"], m["channel_user_id"], "That number isn't one of your open tasks. Say \"tasks\" to see them.")
            return "how_bad"
        _send(m["channel"], m["channel_user_id"],
              f"Task {e['id']}: {e['how'] or e['title']} Send me: {_lc(e['proof_needed']) or 'a short note when done'}.")
        return "how"

    dm = DONE.search(text)
    if dm:
        word, num = dm.group(1).lower(), (int(dm.group(2)) if dm.group(2) else None)
        serves, errands = _open_tasks(cur, m["assignee_key"]), _open_errands(cur, m["assignee_key"])
        if num is None and len(serves) + len(errands) == 1:
            num = (serves or errands)[0]["id"]
        t = next((x for x in serves if x["id"] == num), None) if word in SERVE_WORDS else None
        e = None if t else next((x for x in errands if x["id"] == num), None)
        t = t or (None if e else next((x for x in serves if x["id"] == num), None))
        if t:
            cur.execute("UPDATE drip_service_task SET state='served_awaiting_proof', updated_at=now() WHERE id=%s", (t["id"],))
            _set_state(cur, m, proof_for=f"serve:{t['id']}")
            _send(m["channel"], m["channel_user_id"],
                  f"Thanks. Now send me a clear photo of the stamped receiving copy for Serve {t['id']}.")
            return "served_marked"
        if e:
            _set_state(cur, m, proof_for=f"errand:{e['id']}")
            _send(m["channel"], m["channel_user_id"],
                  f"Great. Send me {_lc(e['proof_needed']) or 'a photo or short note'} for task {e['id']} and I'll pass it to Jonathan.")
            return "errand_done_reported"
        _send(m["channel"], m["channel_user_id"], "Which task number? For example: done 3.")
        return "done_ambiguous"

    if TASKS.search(text):
        _send(m["channel"], m["channel_user_id"], _all_tasks_text(cur, m) if LIST.search(text) else _next_task_text(cur, m))
        return "tasks"

    if st.get("proof_for", "").startswith("errand:") and text:
        # a typed answer IS the proof for errands like "tell Jonathan the owner's name"
        eid = int(st["proof_for"].split(":")[1])
        e = next((x for x in _open_errands(cur, m["assignee_key"]) if x["id"] == eid), None)
        if e:
            return _errand_submitted(cur, m, e, None, text)

    # questions: answer from the record, scoped to the client of her current task; never free-LLM
    items = _candidates(cur, m["assignee_key"])
    if items and text:
        try:
            import leo_service as ls
            route = ls.try_purpose_route(cur, items[0][1]["client_code"], text,
                                         channel=m["channel"], channel_user_id=m["channel_user_id"])
            if route and route.get("text"):
                _send(m["channel"], m["channel_user_id"], route["text"])
                return "answered_from_record"
        except Exception as e:
            print(f"[staff_desk] purpose_route skip: {type(e).__name__}: {e}", flush=True)
    _send(m["channel"], m["channel_user_id"],
          "I can help with your tasks and proof photos for now. Jonathan will see your message.")
    return "fallback"


def _artifacts_for(cur, mid):
    deadline = time.time() + (0 if DRY else MEDIA_WAIT_S)
    while True:
        cur.execute("SELECT * FROM comms_artifacts WHERE channel_message_id=%s ORDER BY id", (mid,))
        rows = cur.fetchall()
        if rows or time.time() >= deadline:
            return rows
        time.sleep(1)


def _land_for_task(cur, art, task):
    """Bind an artifact to the task's client. A held artifact (identity has no client) is re-fetched and
    landed with the task's client as the hint — the client comes from the assigned task, never guessed."""
    if art["status"] in ("landed", "deduped") and art["doc_id"]:
        return art["doc_id"]
    if art["status"] != "held" or not art["media_ref"]:
        return None
    import requests
    from comms_artifact_sink import land_artifact
    try:
        data = requests.get(art["media_ref"], timeout=45).content
    except Exception:
        return None
    res = land_artifact(art["channel"], art["channel_user_id"], art["channel_message_id"],
                        art["original_filename"], data, art["mime_type"], media_ref=art["media_ref"],
                        conn=cur.connection, client_hint=task["client_code"])
    return res.get("doc_id")


def _errand_submitted(cur, m, e, doc_id, note):
    cur.execute("""UPDATE staff_task SET state='done_awaiting_check', proof_doc_id=coalesce(%s, proof_doc_id),
                          updated_at=now() WHERE id=%s""", (doc_id, e["id"]))
    _set_state(cur, m, proof_for=None, pending_media=None)
    what = f"doc {doc_id}" if doc_id else f'her note: "{(note or "")[:200]}"'
    _queue(cur, "staff_task_done", e["id"], f"staff_task_done:{e['matter_code']}",
           f"{m['name']} says task {e['id']} is done ({e['title']}). Proof: {what}. Accept it as done? Reply yes or no.",
           {"doc_id": doc_id, "note": note, "officer": m["name"]})
    _send(m["channel"], m["channel_user_id"], f"Saved for task {e['id']}. Jonathan will check it. " + _next_task_text(cur, m))
    ask_next(cur)
    return "errand_submitted"


def _resolve_choice(cur, m, key):
    """'serve:12' / 'errand:3' / a bare number -> (kind, row) among her open items."""
    items = _candidates(cur, m["assignee_key"])
    if isinstance(key, str) and ":" in key:
        k, i = key.split(":")
        return next(((kk, r) for kk, r in items if kk == k and r["id"] == int(i)), (None, None))
    hits = [(kk, r) for kk, r in items if r["id"] == key]
    return hits[0] if len(hits) == 1 else (None, None)


def _handle_media(cur, m, mid, text):
    st = m["state"] or {}
    items = _candidates(cur, m["assignee_key"])
    media_mid = st.get("pending_media") if DIGIT.match(text or "") else mid
    if not items:
        _send(m["channel"], m["channel_user_id"],
              "I got your file, but you have no open task to match it to. Jonathan will see it.")
        return "media_no_task"
    if DIGIT.match(text or ""):
        kind, task = _resolve_choice(cur, m, int(DIGIT.match(text).group(1)))
        if not task:
            _send(m["channel"], m["channel_user_id"], "That number isn't one of your open tasks. Which one?")
            return "media_choice_bad"
    elif st.get("proof_for"):
        kind, task = _resolve_choice(cur, m, st["proof_for"])
    elif len(items) == 1:
        kind, task = items[0]
    else:
        kind, task = None, None
    if not task:
        _set_state(cur, m, pending_media=mid)
        nums = ", ".join(str(r["id"]) for _, r in items[:6])
        _send(m["channel"], m["channel_user_id"], f"Got it. Which task is this for? Reply with the number ({nums}).")
        return "media_choice_asked"

    arts = _artifacts_for(cur, media_mid)
    doc_id = None
    for a in arts:
        doc_id = _land_for_task(cur, a, task) or doc_id
    _set_state(cur, m, pending_media=None)
    if not doc_id:
        _send(m["channel"], m["channel_user_id"], "I couldn't save that photo. Please send it again.")
        return "media_failed"
    if kind == "errand":
        return _errand_submitted(cur, m, task, doc_id, None)
    cur.execute("""UPDATE drip_service_task SET proof_doc_id=%s, state='served_awaiting_proof', updated_at=now()
                    WHERE id=%s""", (doc_id, task["id"]))
    _set_state(cur, m, proof_for=None)
    served_on = str(_today_manila())
    _queue(cur, "service_proof", task["id"], f"service_proof:{task['method']}",
           f"{m['name']} sent proof for Serve {task['id']} (letter to {task['addressee'] or 'the office'}, "
           f"ladder {task['ladder']}): doc {doc_id}, served {served_on}. "
           f"Is it a valid stamped receiving copy, and should the clock start? Reply yes or no.",
           {"doc_id": doc_id, "served": served_on, "officer": m["name"]})
    _send(m["channel"], m["channel_user_id"],
          f"Saved as proof for Serve {task['id']}. Jonathan will confirm, then the office's clock starts.")
    ask_next(cur)
    return "proof_submitted"


# ── operator approvals (one at a time) ─────────────────────────────────────────────────────────────────

def _queue(cur, kind, ref_id, pattern_key, prompt, payload):
    cur.execute("""INSERT INTO approval_asks (kind, ref_id, pattern_key, prompt, payload)
                   VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id""",
                (kind, ref_id, pattern_key, prompt, json.dumps(payload)))
    r = cur.fetchone()
    return r["id"] if r else None


def ask_next(cur):
    """Ask Jonathan the oldest queued approval — only when none is outstanding (no double-tap)."""
    cur.execute("SELECT 1 FROM approval_asks WHERE state='asked'")
    if cur.fetchone():
        return None
    cur.execute("SELECT * FROM approval_asks WHERE state='queued' ORDER BY id LIMIT 1")
    a = cur.fetchone()
    if not a:
        return None
    if _send(*OPERATOR, a["prompt"]):
        cur.execute("UPDATE approval_asks SET state='asked', asked_at=now(), asked_via='messenger' WHERE id=%s", (a["id"],))
        return a["id"]
    return None


def _member_by_assignee(cur, assignee):
    cur.execute("SELECT * FROM staff_desk_members WHERE assignee_key=%s AND active LIMIT 1", (assignee,))
    return cur.fetchone()


def _apply_yes(cur, a):
    p = a["payload"] or {}
    if a["kind"] == "task_assign":
        cur.execute("""INSERT INTO drip_service_task (instrument_id, assignee, address, due_date, method)
                       VALUES (%s,%s,%s,%s,%s) RETURNING id""",
                    (a["ref_id"], p["assignee"], p["address"], p.get("due"), p["method"]))
        tid = cur.fetchone()["id"]
        m = _member_by_assignee(cur, p["assignee"])
        if m and not (m["voice"] or {}).get("raw"):
            _set_state(cur, m, awaiting_voice=True)     # first contact asks how they want to be talked to
            _send(m["channel"], m["channel_user_id"], VOICE_ASK.format(name=m["name"]))
        elif m:
            cur.execute("""SELECT t.*, i.client_code, s.ladder, s.matter_code, s.addressee FROM drip_service_task t
                             JOIN drip_instrument i ON i.id=t.instrument_id LEFT JOIN step_plan s ON s.id=i.step_plan_id
                            WHERE t.id=%s""", (tid,))
            _send(m["channel"], m["channel_user_id"], "New task. " + _task_line(cur.fetchone()))
        return f"Task {tid} assigned."
    if a["kind"] == "staff_task_done":
        cur.execute("UPDATE staff_task SET state='done', updated_at=now() WHERE id=%s RETURNING assignee, title",
                    (a["ref_id"],))
        r = cur.fetchone()
        m = _member_by_assignee(cur, r["assignee"]) if r else None
        if m:
            _send(m["channel"], m["channel_user_id"], f"Jonathan confirmed task {a['ref_id']}. Thank you. "
                  + _next_task_text(cur, m))
        return f"Task {a['ref_id']} marked done."
    if a["kind"] == "service_proof":
        cur.execute("""SELECT t.*, i.client_code, s.ladder, s.matter_code, s.addressee FROM drip_service_task t
                         JOIN drip_instrument i ON i.id=t.instrument_id LEFT JOIN step_plan s ON s.id=i.step_plan_id
                        WHERE t.id=%s""", (a["ref_id"],))
        t = cur.fetchone()
        import drip_log
        oid, served, due = drip_log.start_clock(cur, t["ladder"], t["matter_code"], date.fromisoformat(p["served"]),
                                                p["doc_id"],
                                                office=t["addressee"], by=f"{p.get('officer') or t['assignee']} (field officer)",
                                                source="field_officer_proof")
        cur.execute("UPDATE drip_service_task SET state='proof_ingested', updated_at=now() WHERE id=%s", (t["id"],))
        cur.execute("UPDATE drip_instrument SET status='served', updated_at=now() WHERE id=%s AND approval_ref IS NOT NULL",
                    (t["instrument_id"],))
        drip_log.set_step(cur, t["ladder"], "served")
        due_txt = due.strftime("%a %d %b") if due else "already running from an earlier proof"
        m = _member_by_assignee(cur, t["assignee"])
        if m:
            _send(m["channel"], m["channel_user_id"],
                  f"Jonathan confirmed task {t['id']}. The office's reply is now due {due_txt}. Thank you.")
        return f"Clock started on {t['ladder']} (obligation {oid}), due {due_txt}."
    return "Recorded."


def _apply_no(cur, a):
    if a["kind"] == "staff_task_done":
        cur.execute("""UPDATE staff_task SET state='open', updated_at=now() WHERE id=%s RETURNING assignee""", (a["ref_id"],))
        r = cur.fetchone()
        m = _member_by_assignee(cur, r["assignee"]) if r else None
        if m:
            _send(m["channel"], m["channel_user_id"],
                  f"Jonathan says task {a['ref_id']} isn't finished yet. Say \"how {a['ref_id']}\" to see what's needed.")
        return "Noted, task reopened."
    if a["kind"] == "service_proof":
        cur.execute("""UPDATE drip_service_task SET proof_doc_id=NULL, state='served_awaiting_proof', updated_at=now()
                        WHERE id=%s RETURNING assignee""", (a["ref_id"],))
        r = cur.fetchone()
        m = _member_by_assignee(cur, r["assignee"]) if r else None
        if m:
            _send(m["channel"], m["channel_user_id"],
                  f"Jonathan needs a different photo for task {a['ref_id']}: the copy with the office's received "
                  f"stamp, date and signature clearly visible. Please send it again.")
    return "Noted, not done."


def handle_operator(cur, mid, text):
    """Consume Jonathan's yes/no only when an approval is outstanding; anything else goes to Leo."""
    if not (YES.match(text or "") or NO.match(text or "")):
        return False
    cur.execute("SELECT * FROM approval_asks WHERE state='asked' LIMIT 1")
    a = cur.fetchone()
    if not a:
        return False
    yes = bool(YES.match(text))
    try:
        outcome = _apply_yes(cur, a) if yes else _apply_no(cur, a)
    except SystemExit as e:                       # drip_log refusals (no corpus proof, A5 wall) surface, never crash
        outcome = f"Refused: {e}"
        yes = False
    cur.execute("""UPDATE approval_asks SET state=%s, decided_at=now(), decided_by='jonathan', decision_text=%s
                    WHERE id=%s""", ("yes" if yes else "no", text.strip(), a["id"]))
    _send(*OPERATOR, outcome)
    ask_next(cur)
    return True


# ── proposals + daily tick ─────────────────────────────────────────────────────────────────────────────

def propose_task(cur, instrument_id, address, due, method="hand", assignee="kristyle"):
    cur.execute("""SELECT i.*, s.addressee, s.ladder FROM drip_instrument i LEFT JOIN step_plan s ON s.id=i.step_plan_id
                    WHERE i.id=%s""", (instrument_id,))
    i = cur.fetchone()
    if not i:
        raise SystemExit(f"no instrument {instrument_id}")
    if i["status"] not in ("approved", "printed"):
        raise SystemExit(f"REFUSED: instrument {instrument_id} is '{i['status']}'; only an approved letter can be "
                         f"assigned for service.")
    due_txt = date.fromisoformat(due).strftime("%a %d %b") if due else "no date"
    cur.execute("SELECT name FROM staff_desk_members WHERE assignee_key=%s LIMIT 1", (assignee,))
    who = (cur.fetchone() or {}).get("name") or assignee
    return _queue(cur, "task_assign", instrument_id, f"task_assign:{method}",
                  f"Assign {who} to {METHOD_WORD.get(method, method).lower()} the approved letter to "
                  f"{i['addressee'] or 'the office'} ({i['ladder']}) at {address}, due {due_txt}? "
                  f"This includes printing it. Reply yes or no.",
                  {"assignee": assignee, "address": address, "due": due, "method": method})


def _auto_propose(cur):
    """Approved paper letters with no service task -> a proposed task (date PROPOSED, Jonathan decides)."""
    cur.execute("""SELECT i.id, s.addressee FROM drip_instrument i JOIN step_plan s ON s.id=i.step_plan_id
                    WHERE i.status='approved' AND coalesce(i.send_account, s.send_account)='paper'
                      AND NOT EXISTS (SELECT 1 FROM drip_service_task t WHERE t.instrument_id=i.id)
                      AND NOT EXISTS (SELECT 1 FROM approval_asks a WHERE a.kind='task_assign' AND a.ref_id=i.id)""")
    n = 0
    for r in cur.fetchall():
        from drip_board import add_working_days
        import drip_log
        due = add_working_days(_today_manila(), 2, drip_log.off_days(cur))
        propose_task(cur, r["id"], r["addressee"] or "the office (address to confirm)", str(due))
        n += 1
    return n


def morning_briefs(cur):
    if datetime.now(MANILA).hour < BRIEF_HOUR:
        return 0
    cur.execute("SELECT * FROM staff_desk_members WHERE active AND (last_brief_on IS NULL OR last_brief_on < %s)",
                (_today_manila(),))
    n = 0
    for m in cur.fetchall():
        if not (m["voice"] or {}).get("raw") or not _candidates(cur, m["assignee_key"]):
            continue
        if _send(m["channel"], m["channel_user_id"], "Good morning. " + _next_task_text(cur, m)):
            cur.execute("UPDATE staff_desk_members SET last_brief_on=%s WHERE channel=%s AND channel_user_id=%s",
                        (_today_manila(), m["channel"], m["channel_user_id"]))
            n += 1
    return n


def tick(cur):
    p = _auto_propose(cur)
    a = ask_next(cur)
    b = morning_briefs(cur)
    print(f"[staff_desk] tick: proposed={p} asked={a} briefs={b}")


# ── entry point from leo_instant ───────────────────────────────────────────────────────────────────────

def route(cur, mid, channel, uid, text):
    uid = str(uid)
    m = _member(cur, channel, uid)
    if m:
        how = _handle_staff(cur, m, mid, text)
        _mark_handled(cur, mid, channel, uid, f"staff:{how}")
        print(f"[staff_desk] msg {mid} staff {m['name']}: {how}", flush=True)
        return True
    if (channel, uid) == OPERATOR and handle_operator(cur, mid, text):
        _mark_handled(cur, mid, channel, uid, "operator_decision")
        return True
    return False


def readiness(cur, assignee):
    """Jonathan, 2026-11-03: if the bot cannot work out the officer's next steps from the record, the record is
    not current, and the bot must not talk about what it does not know. READY = at least one next step is
    derivable from the record (an open task, or an approved paper letter that will become one)."""
    tasks = _open_tasks(cur, assignee)
    cur.execute("""SELECT i.id, i.status, s.ladder, s.addressee FROM drip_instrument i JOIN step_plan s ON s.id=i.step_plan_id
                    WHERE coalesce(i.send_account, s.send_account)='paper' AND NOT i.is_test
                      AND i.status NOT IN ('superseded','served','refused_lint')
                      AND NOT EXISTS (SELECT 1 FROM drip_service_task t WHERE t.instrument_id=i.id)
                    ORDER BY i.id""")
    paper = cur.fetchall()
    ready_paper = [r for r in paper if r["status"] in ("approved", "printed")]
    blocked = [r for r in paper if r["status"] not in ("approved", "printed")]
    errands = _open_errands(cur, assignee)
    ok = bool(tasks or ready_paper or errands)
    return {"ready": ok, "open_tasks": [t["id"] for t in tasks],
            "open_errands": [f"#{e['id']} {e['title']} (due {e['due_date'] or 'no date'})" for e in errands],
            "approved_paper_letters": [f"#{r['id']} {r['ladder']} -> {r['addressee']}" for r in ready_paper],
            "paper_letters_blocked_on_jonathan": [f"#{r['id']} {r['ladder']} ({r['status']})" for r in blocked]}


def activate(cur, assignee):
    """Switch an officer ON — only on Jonathan's go, and only when readiness passes. The bot then opens with them."""
    rd = readiness(cur, assignee)
    if not rd["ready"]:
        raise SystemExit("REFUSED: no next step for this officer is derivable from the record "
                         f"(the bot would talk about what it doesn't know): {json.dumps(rd)}")
    cur.execute("UPDATE staff_desk_members SET active=true, updated_at=now() WHERE assignee_key=%s RETURNING *", (assignee,))
    m = cur.fetchone()
    if m and not (m["voice"] or {}).get("raw"):
        _set_state(cur, m, awaiting_voice=True)
        _send(m["channel"], m["channel_user_id"], VOICE_ASK.format(name=m["name"]))
    return rd


def status(cur):
    for q, title in [("SELECT channel, channel_user_id, name, assignee_key, active, voice, state, last_brief_on FROM staff_desk_members", "members"),
                     ("SELECT id, instrument_id, assignee, address, due_date, method, proof_doc_id, state FROM drip_service_task WHERE state<>'proof_ingested' ORDER BY id", "open tasks"),
                     ("SELECT id, kind, ref_id, pattern_key, state, asked_at, decided_at FROM approval_asks WHERE state IN ('queued','asked') ORDER BY id", "approvals"),
                     ("SELECT * FROM v_autonomy_record ORDER BY pattern_key", "autonomy record")]:
        cur.execute(q)
        rows = cur.fetchall()
        print(f"── {title} ({len(rows)})")
        for r in rows:
            print("  ", json.dumps(r, default=str))


def main():
    global DRY
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", choices=["propose-task", "readiness", "activate"])
    ap.add_argument("--assignee", default="kristyle")
    ap.add_argument("--instrument", type=int)
    ap.add_argument("--address")
    ap.add_argument("--due")
    ap.add_argument("--method", default="hand")
    ap.add_argument("--tick", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--probe")
    ap.add_argument("--as", dest="ident")
    ap.add_argument("--media-msg", type=int)
    ap.add_argument("--dry-run", action="store_true", help="roll back everything and print instead of sending")
    a = ap.parse_args()
    DRY = a.dry_run
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        if a.status:
            status(cur)
        elif a.tick:
            tick(cur)
        elif a.cmd == "readiness":
            print(json.dumps(readiness(cur, a.assignee), indent=2))
        elif a.cmd == "activate":
            print(json.dumps(activate(cur, a.assignee), indent=2))
        elif a.cmd == "propose-task":
            print("queued approval", propose_task(cur, a.instrument, a.address, a.due, a.method))
        elif a.probe is not None:
            ch, _, uid = (a.ident or "").partition(":")
            print("handled:", route(cur, a.media_msg, ch, uid, a.probe))
        if DRY:
            conn.rollback()
            print("[dry-run] rolled back")
        else:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close(); conn.close()


if __name__ == "__main__":
    main()
