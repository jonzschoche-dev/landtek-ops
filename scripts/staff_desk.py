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
TASKS = re.compile(r"^\s*(tasks?|task list|next|sunod|susunod|gawain|trabaho|ano na|ano gagawin( ko)?)"
                   r"(\s+(lahat|all|list))?\s*[?.!]*\s*$", re.I)    # whole short command only, never inside a question
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
    cur.execute("""SELECT e.*, mt.client_code,
                          EXISTS (SELECT 1 FROM staff_task d WHERE d.id = e.depends_on AND d.state <> 'done') AS dep_open
                     FROM staff_task e LEFT JOIN matters mt ON mt.matter_code = e.matter_code
                    WHERE e.assignee=%s AND e.state = ANY(%s)
                    ORDER BY e.due_date NULLS LAST, e.seq, e.id""", (assignee, states))
    return cur.fetchall()


def _candidates(cur, assignee, skip=None):
    """Everything she can act on now, soonest due first: [(kind, row)]. `skip` = errand ids she passed on today."""
    items = [("serve", t) for t in _open_tasks(cur, assignee)] + \
            [("errand", e) for e in _open_errands(cur, assignee) if e["id"] not in (skip or ())]
    return sorted(items, key=lambda kr: (kr[1]["due_date"] is None, kr[1]["due_date"] or date.max))


def _skipped_today(m):
    sk = ((m or {}).get("state") or {}).get("skipped") or {}
    return set(sk.get("ids", [])) if sk.get("on") == str(_today_manila()) else set()


# ── voice: speak the way the officer asked (stored in their own words at onboarding) ──────────────────────
# Kristyle, 3 Nov 2026: "Taglish and make everything detailed". Deterministic templates, no LLM.

def _voice(m):
    raw = ((m or {}).get("voice") or {}).get("raw", "").lower()
    lang = "tl" if any(w in raw for w in ("taglish", "tagalog", "filipino", "bikol", "bicol")) else "en"
    detailed = any(w in raw for w in ("detail", "detalyado", "mahaba", "long", "full", "everything"))
    return lang, detailed


MSG = {
    "noted":      {"en": "Got it, noted. ", "tl": "Sige, noted! "},
    "no_tasks":   {"en": "No open tasks right now. I'll message you when there's one.",
                   "tl": "Wala kang open na task ngayon. Ime-message kita pag may bago."},
    "more":       {"en": " ({n} more after this; say \"tasks\" for the next.)",
                   "tl": " ({n} pa ang kasunod nito; sabihin mo lang \"tasks\" para sa susunod.)"},
    "list_head":  {"en": "Your open tasks, soonest first: ", "tl": "Mga open tasks mo, pinakamalapit ang due: "},
    "list_tail":  {"en": ". Say \"how N\" for any of them.", "tl": ". Reply ka ng \"how N\" para sa steps ng kahit alin."},
    "due":        {"en": "Due {d}.", "tl": "Due: {d}."},
    "no_date":    {"en": "no date set", "tl": "wala pang date"},
    "steps":      {"en": "Steps: {how}", "tl": "Steps: {how}"},
    "send_back":  {"en": "Send me: {p}.", "tl": "Ang i-send mo sa akin: {p}."},
    "reply_how":  {"en": "Reply \"how {i}\" for the steps, \"done {i}\" when finished.",
                   "tl": "Reply ka ng \"how {i}\" para sa steps, at \"done {i}\" pag tapos na."},
    "reply_done": {"en": "Reply \"done {i}\" when finished.", "tl": "Reply ka ng \"done {i}\" pag tapos na."},
    "not_open":   {"en": "That number isn't one of your open tasks. Say \"tasks\" to see them.",
                   "tl": "Hindi kasama sa open tasks mo ang number na 'yan. Sabihin mo lang \"tasks\" para makita mo."},
    "which_num":  {"en": "Which task number? For example: done 3.", "tl": "Anong task number? Halimbawa: done 3."},
    "send_proof": {"en": "Great. Send me {p} for task {i} and I'll pass it to Jonathan.",
                   "tl": "Ayos! I-send mo lang sa akin ang {p} para sa task {i}, tapos ipapasa ko kay Jonathan."},
    "saved":      {"en": "Saved for task {i}. Jonathan will check it. ", "tl": "Na-save ko na para sa task {i}. Iche-check ni Jonathan. "},
    "confirmed":  {"en": "Jonathan confirmed task {i}. Thank you. ", "tl": "Confirmed na ni Jonathan ang task {i}. Salamat! "},
    "reopened":   {"en": "Jonathan says task {i} isn't finished yet. Say \"how {i}\" to see what's needed.",
                   "tl": "Sabi ni Jonathan, hindi pa tapos ang task {i}. Reply ka ng \"how {i}\" para makita ulit kung ano ang kailangan."},
    "fallback":   {"en": "I can help with your tasks and proof photos for now. Jonathan will see your message.",
                   "tl": "Sa ngayon, tasks at proof photos lang ang kaya kong asikasuhin. Makikita ni Jonathan ang message mo."},
    "which_photo":{"en": "Got it. Which task is this for? Reply with the number ({nums}).",
                   "tl": "Natanggap ko. Para saang task 'to? Reply ka ng number ({nums})."},
    "photo_fail": {"en": "I couldn't save that photo. Please send it again.", "tl": "Hindi ko na-save ang photo. Pakisend ulit."},
    "no_task_file":{"en": "I got your file, but you have no open task to match it to. Jonathan will see it.",
                   "tl": "Natanggap ko ang file mo, pero wala kang open task na pwedeng pagtapatan nito. Makikita ni Jonathan."},
    "morning":    {"en": "Good morning. ", "tl": "Good morning! "},
    "dep_note":   {"en": " Note: per the source, task {d} comes first.",
                   "tl": " Paalala: ayon sa source, dapat matapos muna ang task {d} bago ito."},
    "skipped":    {"en": "OK, skipping task {i} for today. ", "tl": "Sige, laktaw muna ang task {i} ngayon. "},
    "not_found":  {"en": "I can't find that in the papers for your tasks. I've noted your question for Jonathan.",
                   "tl": "Hindi ko makita 'yan sa mga papel ng tasks mo. Na-note ko ang tanong mo para kay Jonathan."},
    "why":        {"en": "Why task {i}: {w}", "tl": "Bakit kailangan ang task {i}: {w}"},
    "why_none":   {"en": "The record doesn't say why for task {i}. Jonathan will see your question.",
                   "tl": "Walang nakasulat sa record kung bakit para sa task {i}. Makikita ni Jonathan ang tanong mo."},
    "new_task":   {"en": "New task. ", "tl": "May bagong task ka. "},
}


def _say(m, key, **kw):
    lang, _ = _voice(m)
    if lang == "tl" and isinstance(kw.get("p"), str):
        kw["p"] = re.sub(r"^(the|a|an)\s+", "", kw["p"], flags=re.I)   # "ang the owner's name" -> "ang owner's name"
    return MSG[key][lang].format(**kw)


def _task_line(t):
    due = t["due_date"].strftime("%a %d %b") if t["due_date"] else "no date set"
    who = t["addressee"] or "the office"
    if t["state"] == "served_awaiting_proof":
        return (f"Serve {t['id']}: you marked the letter to {who} as served. "
                f"Send me a photo of the stamped receiving copy.")
    return (f"Serve {t['id']}: {METHOD_WORD.get(t['method'], t['method'])} the letter to {who} at {t['address']}. "
            f"Due {due}. Once it's received, send me a photo of the stamped receiving copy.")


def _errand_line(e, m=None):
    _, detailed = _voice(m)
    dep = _say(m, "dep_note", d=e["depends_on"]) if e.get("depends_on") and e.get("dep_open") else ""
    due = e["due_date"].strftime("%a %d %b") if e["due_date"] else _say(m, "no_date")
    head = f"Task {e['id']}: {e['title']}. " + _say(m, "due", d=due)
    if detailed:
        parts = [head]
        if e.get("how"):
            parts.append(_say(m, "steps", how=e["how"]))
        if e.get("proof_needed"):
            parts.append(_say(m, "send_back", p=_lc(e["proof_needed"])))
        parts.append(_say(m, "reply_done", i=e["id"]))
        return " ".join(parts) + dep
    return head + " " + _say(m, "reply_how", i=e["id"]) + dep


def _lc(t):
    """'The owner's name' -> 'the owner's name' mid-sentence (leave acronyms like 'SEC' alone)."""
    return (t[0].lower() + t[1:]) if t and len(t) > 1 and not t[1].isupper() else t


def _line(kind, row, m=None):
    return _task_line(row) if kind == "serve" else _errand_line(row, m)


def _next_task_text(cur, m):
    items = _candidates(cur, m["assignee_key"], _skipped_today(m)) or _candidates(cur, m["assignee_key"])
    if not items:
        return _say(m, "no_tasks")
    if items[0][0] == "errand" and m.get("channel"):
        _set_state(cur, m, focus=items[0][1]["id"])      # "why?" with no number = the task just shown
    more = _say(m, "more", n=len(items) - 1) if len(items) > 1 else ""
    return _line(*items[0], m) + more


def _all_tasks_text(cur, m):
    items = _candidates(cur, m["assignee_key"])
    if not items:
        return _say(m, "no_tasks")
    return _say(m, "list_head") + " ".join(
        f"{'Serve' if k == 'serve' else 'Task'} {r['id']} ({r['due_date'].strftime('%d %b') if r['due_date'] else 'no date'})"
        for k, r in items) + _say(m, "list_tail")


# ── grounded answers from a task's own source material ─────────────────────────────────────────────────
# Kristyle, 3 Nov: "What is the subject for email?" — answerable from the letter attached to Task 1, but no
# command covered it. Free questions are answered ONLY from staff_task.materials by the local model ($0),
# then checked mechanically: every email, link and number in the answer must appear in the sources, or the
# answer is dropped. Every question is logged (staff_question) so the unanswered ones reach Jonathan.

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://100.117.118.47:11434")
QA_MODEL = os.environ.get("STAFF_QA_MODEL", "qwen2.5:14b-instruct")
_TOKEN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|https?://\S+|\b[\w-]+\.(?:gov|com|org|ph)(?:\.ph)?\b|\d[\d,./-]*\d|\d")


def _norm(t):
    return re.sub(r"\s+", " ", (t or "").lower())


def _unsupported(answer, sources):
    """Tokens in the answer (emails, links, domains, numbers) that the sources do not contain."""
    src = _norm(sources).replace(",", "")
    return [tok for tok in _TOKEN.findall(answer or "") if _norm(tok).replace(",", "").rstrip(".") not in src]


def _ask_model(question, sources, lang, task=None):
    import requests
    tongue = "Taglish (natural mix of Tagalog and English)" if lang == "tl" else "plain English"
    focus = (f"THE TASK SHE IS DOING NOW: {task['title']}. Steps: {task.get('how') or ''}\n"
             "Read the question as being about this task first.\n") if task else ""
    prompt = ("You help a LandTek field officer with her assigned task. Answer ONLY from SOURCES below. "
              "Copy names, subjects, emails, addresses, numbers and amounts exactly and IN FULL as written in "
              "SOURCES (a 'Re:' subject line runs to the end of that paragraph). Add nothing that SOURCES do not say. "
              "The question may use other words than SOURCES (bill = invoice, resibo = receipt). "
              "Never give advice or next steps that SOURCES do not state: if the question asks what to do in a "
              "situation SOURCES do not cover (what if, paano kung, kung hindi), that is not in SOURCES. "
              "If SOURCES do not contain the answer, reply with exactly NOT_IN_SOURCES and nothing else. "
              f"Answer in {tongue}, at most 4 sentences, no lists, no bullets, no markdown.\n\n"
              f"{focus}SOURCES:\n{sources[:20000]}\n\nQUESTION: {question}\nANSWER:")
    r = requests.post(f"{OLLAMA_URL}/api/generate", timeout=90,
                      json={"model": QA_MODEL, "prompt": prompt, "stream": False,
                            "options": {"temperature": 0, "num_ctx": 12288}})
    r.raise_for_status()
    return (r.json().get("response") or "").strip()


INCLUDE_DRAFTS = False                               # staff_exam sets True to test draft cards before promotion


def _cards(cur, m, matters):
    """Knowledge cards (deploy_1326) for this officer's matters, as SOURCES text. Live only, unless examining."""
    states = ["live", "draft"] if INCLUDE_DRAFTS else ["live"]
    cur.execute("""SELECT topic, fact, source_ref, checked_on FROM staff_knowledge
                    WHERE state = ANY(%s) AND (assignee IS NULL OR assignee=%s) AND matter_code = ANY(%s)
                    ORDER BY topic, id""", (states, m["assignee_key"], list(matters)))
    return "\n\n".join(f"SOURCE: LandTek card [{c['topic']}] (basis: {c['source_ref']}; checked {c['checked_on']})\n{c['fact']}"
                       for c in cur.fetchall())


def _answer_from_materials(cur, m, question):
    """(text_to_send or None, outcome). Knowledge cards first, then the task in focus (else all open tasks)."""
    errands = _open_errands(cur, m["assignee_key"], True)
    focus = (m.get("state") or {}).get("focus")
    pool = [e for e in errands if e["id"] == focus] or errands
    cards = _cards(cur, m, {e["matter_code"] for e in errands})
    sources = "\n\n".join([cards] * bool(cards) + list(dict.fromkeys(e["materials"] for e in pool if e.get("materials"))))
    task_id = pool[0]["id"] if len(pool) == 1 else focus
    if not sources:
        return None, "not_in_sources"
    lang, _ = _voice(m)
    try:
        ans = _ask_model(question, sources, lang, pool[0] if len(pool) == 1 else None)
        if (not ans or "NOT_IN_SOURCES" in ans) and cards and len(sources) > len(cards):
            ans = _ask_model(question, cards, lang)      # long papers can drown a short card; ask the cards alone
        ans = re.sub(r"\s*\n\s*[-•*]\s*", "; ", ans).replace("\n", " ").strip()   # never a list on Messenger
    except Exception as ex:
        cur.execute("""INSERT INTO staff_question (assignee, task_id, question, outcome, detail)
                       VALUES (%s,%s,%s,'error',%s)""", (m["assignee_key"], task_id, question, f"{type(ex).__name__}: {ex}"[:300]))
        return None, "error"
    if not ans or "NOT_IN_SOURCES" in ans:
        outcome, send, detail = "not_in_sources", None, None
    else:
        bad = _unsupported(ans, sources)
        outcome, send, detail = (("rejected_unsupported", None, f"unsupported: {bad}") if bad
                                 else ("answered", ans, None))
    cur.execute("""INSERT INTO staff_question (assignee, task_id, question, answer, outcome, detail)
                   VALUES (%s,%s,%s,%s,%s,%s)""", (m["assignee_key"], task_id, question, ans, outcome, detail))
    return send, outcome


# ── officer -> Jonathan relay ──────────────────────────────────────────────────────────────────────────
JONATHAN_TG = "6513067717"
RELAY = re.compile(r"\b(notify|tell|inform|ask|message|i-?message)\s+(sir\s+)?jonathan\b|\bcheck it\b|\bpaki-?check\b|"
                   r"\bpakisabi\b|\bsabihin (mo )?(kay|si) (sir )?jonathan\b|\bpatingnan (mo )?kay jonathan\b", re.I)


def _relay(cur, m, text):
    """Pass the officer's request to Jonathan: log it (board) and push one Telegram line (S14-paced)."""
    st = m.get("state") or {}
    eid = st.get("focus")
    e = next((x for x in _open_errands(cur, m["assignee_key"], True) if x["id"] == eid), None) if eid else None
    cur.execute("""SELECT text_content FROM channel_messages WHERE channel_id=(SELECT id FROM channels WHERE name=%s)
                    AND channel_user_id=%s AND direction='inbound' ORDER BY id DESC LIMIT 3""",
                (m["channel"], m["channel_user_id"]))
    recent = " / ".join(reversed([r["text_content"] for r in cur.fetchall() if r["text_content"]]))[:300]
    about = f"task {e['id']} ({e['title']})" if e else "her current work"
    line = f"{m['name']} asks you to check something on {about}. Her words: \"{recent}\". Reply to her on Messenger."
    via = "board"
    if not DRY:
        try:
            import tg_send
            ok, _info = tg_send.send(chat_id=JONATHAN_TG, text=line, source="leo", human_readable=True)
            via = "telegram" if ok else "board (telegram held by pacing)"
        except Exception as ex:
            via = f"board (telegram error {type(ex).__name__})"
    else:
        print(f"  [dry-telegram {JONATHAN_TG}] {line}")
    cur.execute("""INSERT INTO staff_question (assignee, task_id, question, outcome, relayed_via)
                   VALUES (%s,%s,%s,'relay',%s)""", (m["assignee_key"], e["id"] if e else None, recent or text, via))
    lang, _ = _voice(m)
    _send(m["channel"], m["channel_user_id"],
          "Sige, sinabihan ko na si Jonathan na i-check. Ime-message ka niya." if lang == "tl"
          else "Done, I've told Jonathan to check. He'll message you.")
    return f"relay:{via}"


# ── case questions (Jonathan, 3 Nov: "cases too") ─────────────────────────────────────────────────────
# Answered straight from the matters table, never through leo_service.try_purpose_route (on 3 Nov that router
# returned title lists for court-date questions and MWK rows under other clients). A question gets a case
# answer only when it names exactly ONE matter, by docket number or a listed name; two or more -> ask which.

CASE_NAMES = {   # names people actually use for a matter; matched as whole words (docket numbers are automatic)
    "MWK-CV26360": ["balane", "accion", "reinvindicatoria", "reivindicatoria", "26-360"],
    "MWK-GUARDIANSHIP": ["guardianship", "guardian"],
    "MWK-CV6839": ["6839", "just compensation", "landbank", "land bank"],
    "MWK-ESTATE": ["estate administration"],
    "MWK-LGU-RECOVERY": ["lgu recovery", "void donation"],
    "MWK-OP-PETITION": ["supervisory review", "op petition"],
    "LANDTEK-OPC-FORMATION": ["sec registration", "opc formation", "incorporation"],
    "PAR-VITO-CRUZ": ["vito cruz"], "PAR-CAPACUAN": ["capacuan"], "PAR-GOLDEN-SAND": ["golden sand"],
    "NIBDC-EXPA-000250": ["expa", "exploration permit"], "NIBDC-APSA-000322": ["apsa"],
}
CASE_EXPLICIT = re.compile(r"\b(case|kaso|hearing|court|korte|trial|docket|arta|ombudsman|guardianship|balane|"
                           r"cv ?\d+|sp\.? ?proc|\d{2}-\d{3})\b", re.I)


def _matter_keys(r):
    keys = set(n.lower() for n in CASE_NAMES.get(r["matter_code"], []))
    for src in [r["matter_code"], r["docket_number"] or ""] + list(r["docket_aliases"] or []):
        keys |= {k for k in re.findall(r"\d{2}-\d{3}|\d{4,}", src)    # 26-360, 2680, 1378, 88750 ...
                 if not re.fullmatch(r"(19|20)\d\d", k)}                 # a bare year is never a case key
    return keys


def _find_matters(cur, text):
    cur.execute("""SELECT matter_code, client_code, title, docket_number, docket_aliases, current_stage, next_event,
                          next_deadline, lead_counsel, status FROM matters
                    WHERE coalesce(status,'') NOT ILIKE 'closed%%' AND matter_code NOT LIKE 'AUTO-%%'""")
    low = text.lower()
    hits = []
    for r in cur.fetchall():
        if any(re.search(rf"(?<![\d-]){re.escape(k)}(?![\d-])" if k[0].isdigit()          # numbers: CV6839 ok
                         else rf"(?<![\w-]){re.escape(k)}(?![\w-])", low) for k in _matter_keys(r)):
            hits.append(r)
    return hits


def _case_answer(cur, m, r):
    lang, _ = _voice(m)
    stage = (r["current_stage"] or "").replace("_", " ")
    d = r["next_deadline"]
    if d and d < _today_manila():
        when = (f"{d.strftime('%d %b %Y')} (lumipas na; baka hindi pa updated ang record)" if lang == "tl"
                else f"{d.strftime('%d %b %Y')} (already past; the record may not be updated)")
    else:
        when = d.strftime("%a %d %b %Y") if d else ("wala sa record" if lang == "tl" else "none on record")
    cur.execute("""SELECT count(*) n, min(due_at) FILTER (WHERE due_at >= current_date) nxt FROM office_obligation
                    WHERE matter_code=%s AND state IN ('served_running','replied_not_performed','partial')""",
                (r["matter_code"],))
    ob = cur.fetchone()
    if lang == "tl":
        out = f"{r['title']} ({r['matter_code']}). Stage: {stage or 'wala sa record'}. Susunod ayon sa record: {r['next_event'] or 'wala'}. Date sa record: {when}."
        if ob["n"]:
            out += f" May {ob['n']} office clock na tumatakbo; ang pinakamalapit na reply ay {ob['nxt'].strftime('%d %b') if ob['nxt'] else '?'}."
    else:
        out = f"{r['title']} ({r['matter_code']}). Stage: {stage or 'not on record'}. Next per the record: {r['next_event'] or 'none'}. Date on record: {when}."
        if ob["n"]:
            out += f" {ob['n']} office clock(s) running; the nearest reply is due {ob['nxt'].strftime('%d %b') if ob['nxt'] else '?'}."
    return out


# ── staff desk ─────────────────────────────────────────────────────────────────────────────────────────

VOICE_ASK = ("Hi {name}, it's Leo. I'll send you your LandTek tasks here and take your proof photos. "
             "Before we start: how do you want me to talk to you? English, Tagalog, Taglish or Bikol, "
             "short or detailed? Just tell me in your own words.")
DONE = re.compile(r"\b(done|tapos|nagawa|finished|served|naserve|na-serve|nai-serve|delivered)\s*#?\s*(\d+)?\b", re.I)
SERVE_WORDS = ("served", "naserve", "na-serve", "nai-serve", "delivered")
HOW = re.compile(r"^\s*(how|paano)\s*#?\s*(\d+)\s*\??\s*$", re.I)
LIST = re.compile(r"\b(all|lahat|list)\b", re.I)
WHY = re.compile(r"\b(why|bakit|para saan)\b", re.I)
WHY_SHORT = re.compile(r"^\W*(is it |is this )?(necessary|needed|kailangan ba( (ito|yan|talaga))?)\W*$", re.I)   # "Kailangan ba ng cedula?" is not a why
NUM = re.compile(r"#?\b(\d{1,4})\b")
PASS = re.compile(r"\b(pass|skip|laktaw\w*|mamaya na|later|lipat)\b", re.I)
ORDINALS = {r"first|una|1st|unang": 1, r"second|pangalawa|ikalawa|2nd": 2, r"third|pangatlo|ikatlo|3rd": 3,
            r"fourth|pang-?apat|ikaapat|4th": 4, r"fifth|panlima|ikalima|5th": 5, r"sixth|pang-?anim|6th": 6,
            r"seventh|pampito|7th": 7}
GOTO = re.compile(r"\b(?:task|go to|punta sa)\s*#?(\d{1,4})\b", re.I)


def _handle_staff(cur, m, mid, text):
    text = (text or "").strip()
    st = m["state"] or {}

    if not (m["voice"] or {}).get("raw"):
        if st.get("awaiting_voice") and text and text != "[media]" and not GREETING.match(text):
            cur.execute("UPDATE staff_desk_members SET voice=%s, updated_at=now() WHERE channel=%s AND channel_user_id=%s",
                        (json.dumps({"raw": text, "recorded_at": str(_today_manila())}), m["channel"], m["channel_user_id"]))
            _set_state(cur, m, awaiting_voice=None)
            m["voice"] = {"raw": text}
            _send(m["channel"], m["channel_user_id"], _say(m, "noted") + _next_task_text(cur, m))
            return "voice_recorded"
        if text != "[media]":
            _set_state(cur, m, awaiting_voice=True)
            _send(m["channel"], m["channel_user_id"], VOICE_ASK.format(name=m["name"]))
            return "voice_asked"

    if text == "[media]" or st.get("pending_media") and DIGIT.match(text):
        return _handle_media(cur, m, mid, text)

    pm, gm = PASS.search(text), GOTO.search(text)
    ordinal = next((n for pat, n in ORDINALS.items() if re.search(rf"\b({pat})\b", text, re.I)), None)
    if pm or gm or (ordinal and re.search(r"\b(task|gawain)\b", text, re.I)):
        if pm and st.get("focus"):
            sk = _skipped_today(m) | {st["focus"]}
            _set_state(cur, m, skipped={"on": str(_today_manila()), "ids": sorted(sk)})
        target = None
        if gm:
            target = next(((k, r) for k, r in _candidates(cur, m["assignee_key"]) if r["id"] == int(gm.group(1))), None)
        elif ordinal:
            allitems = _candidates(cur, m["assignee_key"])
            target = allitems[ordinal - 1] if len(allitems) >= ordinal else None
        lead = _say(m, "skipped", i=st["focus"]) if pm and st.get("focus") else ""
        if target:
            if target[0] == "errand":
                _set_state(cur, m, focus=target[1]["id"])
            _send(m["channel"], m["channel_user_id"], lead + _line(*target, m))
        else:
            _send(m["channel"], m["channel_user_id"], lead + _next_task_text(cur, m))
        return "goto" if target else "pass"

    if WHY.search(text) or WHY_SHORT.match(text):
        nm = NUM.search(text)
        eid = int(nm.group(1)) if nm else st.get("focus")
        e = next((x for x in _open_errands(cur, m["assignee_key"], True) if x["id"] == eid), None) if eid else None
        if e:
            _set_state(cur, m, focus=e["id"])
            _send(m["channel"], m["channel_user_id"],
                  _say(m, "why", i=e["id"], w=e["why"]) if e.get("why") else _say(m, "why_none", i=e["id"]))
            return "why"

    hm = HOW.match(text)
    if hm:
        e = next((x for x in _open_errands(cur, m["assignee_key"], True) if x["id"] == int(hm.group(2))), None)
        if not e:
            _send(m["channel"], m["channel_user_id"], _say(m, "not_open"))
            return "how_bad"
        _set_state(cur, m, focus=e["id"])
        _send(m["channel"], m["channel_user_id"],
              f"Task {e['id']}: {e['how'] or e['title']} " + _say(m, "send_back", p=_lc(e['proof_needed']) or 'a short note')
              + " " + _say(m, "reply_done", i=e["id"]))
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
                  _say(m, "send_proof", p=_lc(e['proof_needed']) or 'a photo or short note', i=e["id"]))
            return "errand_done_reported"
        _send(m["channel"], m["channel_user_id"], _say(m, "which_num"))
        return "done_ambiguous"

    if TASKS.search(text):
        _send(m["channel"], m["channel_user_id"], _all_tasks_text(cur, m) if LIST.search(text) else _next_task_text(cur, m))
        return "tasks"

    if st.get("proof_for", "").startswith("errand:") and text and not text.rstrip().endswith("?"):
        # a typed answer IS the proof only for errands that ask for something typeable ("the owner's name",
        # "Allan's confirmation"); a document-proof task waits for the photo, and a question is never proof
        eid = int(st["proof_for"].split(":")[1])
        e = next((x for x in _open_errands(cur, m["assignee_key"]) if x["id"] == eid), None)
        if e and re.search(r"\b(name|confirmation|confirm|note|answer)\b", e.get("proof_needed") or "", re.I):
            return _errand_submitted(cur, m, e, None, text)

    if text and RELAY.search(text):
        return _relay(cur, m, text)

    # Case questions vs task questions (exam, 3 Nov: "FAO deadline", "petition for correction" and "Landbank
    # branch" were sent to the case branch). An EXPLICIT case question (kaso, hearing, court, a docket) goes to
    # the case answer; anything else is tried against her task papers first, and only then a single named matter.
    own = {e["matter_code"] for e in _open_errands(cur, m["assignee_key"], True)}
    hits = [h for h in _find_matters(cur, text) if h["matter_code"] not in own] if text else []

    def _which():
        opts = "; ".join(f"{h['matter_code']} ({h['title'][:40]})" for h in hits[:4]) if hits else \
            "Balane 26-360, guardianship 2680, CV6839, o ARTA 1378"
        lang, _ = _voice(m)
        _send(m["channel"], m["channel_user_id"],
              (f"Aling kaso ang tinutukoy mo? Halimbawa: {opts}." if lang == "tl"
               else f"Which case do you mean? For example: {opts}."))
        return "case_which"

    if text and CASE_EXPLICIT.search(text):
        if len(hits) == 1:
            _send(m["channel"], m["channel_user_id"], _case_answer(cur, m, hits[0]))
            return "case_answered"
        return _which()

    # free questions: first from the knowledge cards + her tasks' own source material (local model, token-checked)
    if text and text != "[media]":
        ans, outcome = _answer_from_materials(cur, m, text)
        if ans:
            _send(m["channel"], m["channel_user_id"], ans)
            return "answered_from_materials"
        if len(hits) == 1:
            _send(m["channel"], m["channel_user_id"], _case_answer(cur, m, hits[0]))
            return "case_answered"
        if len(hits) > 1:
            return _which()
        if outcome in ("not_in_sources", "rejected_unsupported") and own:
            _send(m["channel"], m["channel_user_id"], _say(m, "not_found"))
            return f"materials_{outcome}"

    # questions: answer from the record, scoped to the client of her current task; never free-LLM
    items = _candidates(cur, m["assignee_key"])
    if items and text:
        try:
            import leo_service as ls
            route = ls.try_purpose_route(cur, items[0][1]["client_code"], text,
                                         channel=m["channel"], channel_user_id=m["channel_user_id"])
            closed = (route or {}).get("via") == "stack_closed" or "stack hit" in ((route or {}).get("text") or "").lower()
            if route and route.get("text") and not closed:     # the record's "no hit" line is jargon; use ours
                _send(m["channel"], m["channel_user_id"], route["text"])
                return "answered_from_record"
        except Exception as e:
            print(f"[staff_desk] purpose_route skip: {type(e).__name__}: {e}", flush=True)
    _send(m["channel"], m["channel_user_id"], _say(m, "fallback"))
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
    _send(m["channel"], m["channel_user_id"], _say(m, "saved", i=e["id"]) + _next_task_text(cur, m))
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
        _send(m["channel"], m["channel_user_id"], _say(m, "no_task_file"))
        return "media_no_task"
    if DIGIT.match(text or ""):
        kind, task = _resolve_choice(cur, m, int(DIGIT.match(text).group(1)))
        if not task:
            _send(m["channel"], m["channel_user_id"], _say(m, "not_open"))
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
        _send(m["channel"], m["channel_user_id"], _say(m, "which_photo", nums=nums))
        return "media_choice_asked"

    arts = _artifacts_for(cur, media_mid)
    doc_id = None
    for a in arts:
        doc_id = _land_for_task(cur, a, task) or doc_id
    _set_state(cur, m, pending_media=None)
    if not doc_id:
        _send(m["channel"], m["channel_user_id"], _say(m, "photo_fail"))
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
            _send(m["channel"], m["channel_user_id"], _say(m, "new_task") + _task_line(cur.fetchone()))
        return f"Task {tid} assigned."
    if a["kind"] == "staff_task_done":
        cur.execute("UPDATE staff_task SET state='done', updated_at=now() WHERE id=%s RETURNING assignee, title",
                    (a["ref_id"],))
        r = cur.fetchone()
        m = _member_by_assignee(cur, r["assignee"]) if r else None
        if m:
            _send(m["channel"], m["channel_user_id"], _say(m, "confirmed", i=a["ref_id"]) + _next_task_text(cur, m))
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
            _send(m["channel"], m["channel_user_id"], _say(m, "reopened", i=a["ref_id"]))
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
        if _send(m["channel"], m["channel_user_id"], _say(m, "morning") + _next_task_text(cur, m)):
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


def rebind(cur, assignee, new_uid, channel="messenger"):
    """Move an officer to a new account on the same channel (e.g. Kristyle's new Messenger "Elle Cece",
    2026-11-03). Run only after Jonathan confirms the new account is that person: identity over a channel is
    never assumed. Keeps her tasks, voice and state; marks the new channel_users row as the same approved role."""
    cur.execute("SELECT * FROM staff_desk_members WHERE assignee_key=%s AND channel=%s", (assignee, channel))
    m = cur.fetchone()
    if not m:
        raise SystemExit(f"no {channel} member {assignee}")
    cur.execute("""SELECT cu.* FROM channel_users cu JOIN channels c ON c.id=cu.channel_id
                    WHERE c.name=%s AND cu.channel_user_id=%s""", (channel, str(new_uid)))
    cu = cur.fetchone()
    if not cu:
        raise SystemExit(f"REFUSED: {channel}:{new_uid} has never messaged the page; have them send one message first.")
    old = m["channel_user_id"]
    cur.execute("""UPDATE staff_desk_members SET channel_user_id=%s, updated_at=now()
                    WHERE assignee_key=%s AND channel=%s""", (str(new_uid), assignee, channel))
    cur.execute("""SELECT approved_role, entity_id, onboarding_responses, metadata FROM channel_users cu
                     JOIN channels c ON c.id=cu.channel_id WHERE c.name=%s AND cu.channel_user_id=%s""", (channel, old))
    prev = cur.fetchone() or {}
    pr, pm = prev.get("onboarding_responses") or {}, prev.get("metadata") or {}
    contact = {k: v for k, v in (("email", pr.get("email") or pm.get("email")),
                                 ("phone", pr.get("phone") or pm.get("phone"))) if v}
    # carry the contact details too, or the onboarding flow re-asks a known person for them
    cur.execute("""UPDATE channel_users SET role=coalesce(%s,'filing_assistant'), approved_role=coalesce(%s,'filing_assistant'),
                          authorized=true, authorized_at=now(), authorized_by='jonathan (staff_desk rebind)',
                          onboarding_state='approved', onboarding_completed_at=now(), entity_id=coalesce(entity_id,%s),
                          onboarding_responses = onboarding_responses || %s::jsonb,
                          metadata = metadata || %s::jsonb
                    WHERE id=%s""",
                (prev.get("approved_role"), prev.get("approved_role"), prev.get("entity_id"),
                 json.dumps({**contact, "staff_contact_completed_at": str(_today_manila()),
                             "staff_contact_reason": f"carried from {channel}:{old}"}),
                 json.dumps({**contact, "same_person_as": f"{channel}:{old}", "rebound_on": str(_today_manila())}), cu["id"]))
    m = _member(cur, channel, new_uid, active_only=False)
    if m["active"] and not (m["voice"] or {}).get("raw"):
        _set_state(cur, m, awaiting_voice=True)
        _send(channel, str(new_uid), VOICE_ASK.format(name=m["name"]))
    return {"assignee": assignee, "old": old, "new": str(new_uid), "display_name": cu["display_name"]}


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
    ap.add_argument("cmd", nargs="?", choices=["propose-task", "readiness", "activate", "rebind"])
    ap.add_argument("--psid", help="rebind: the new account id on the channel")
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
        elif a.cmd == "rebind":
            print(json.dumps(rebind(cur, a.assignee, a.psid), indent=2))
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
