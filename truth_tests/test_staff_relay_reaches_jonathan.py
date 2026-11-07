#!/usr/bin/env python3
"""test_staff_relay_reaches_jonathan.py — a field officer's "notify Jonathan" must reach his Telegram, and she
must never be told it did when it did not. Locks the defect Jonathan found 4 Nov 2026 ("I'm receiving nothing of
her communications to Leo"):

  1. tg_send's one-at-a-time hold read his replies from leo_interactions, which stopped recording them on
     8 Jun 2026 (they land in telegram_inbox). The hold never opened, so every non-override message to him
     was blocked, Kristyle's two relays included.
  2. A staff relay is someone waiting on him: it goes through the hold (override_pacing, Jonathan 4 Nov).
  3. When a relay is held anyway, Kristyle was told "Done, I've told Jonathan". Now she is told the truth.
  4. "Notify him" was not relayed; "Did you notify him?" had no answer.

DB probes run in a rolled-back transaction; Telegram and Messenger sends are stubbed (nothing goes out).
"""
import os
import sys
import types

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from _harness import run, TruthFailure, DSN
import tg_send
import staff_desk as SD

TOLD_HIM = ("told jonathan", "messaged jonathan", "sinabihan ko na", "na-message ko")


def _rb():
    conn = psycopg2.connect(DSN); conn.autocommit = False
    return conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def hold_opens_on_telegram_inbox_reply(cur):
    conn, tc = _rb()
    try:
        tc.execute("""INSERT INTO outbound_messages (sent_at, chat_id, source, content_hash, content_preview, success)
                      VALUES (now() + interval '1 minute', %s, 'manual_ops', 'tt', 'truth test', true)""",
                   (tg_send.JONATHAN_CHAT,))
        if not tg_send._is_jonathan_awaiting_reply(tc):
            raise TruthFailure("hold did not engage after an unanswered message (test setup)")
        tc.execute("""INSERT INTO telegram_inbox (received_at, chat_id, sender_id, text_content, raw_update)
                      VALUES (now() + interval '2 minutes', %s, %s, 'truth test reply', '{}'::jsonb)""",
                   (tg_send.JONATHAN_CHAT, tg_send.JONATHAN_CHAT))
        if tg_send._is_jonathan_awaiting_reply(tc):
            raise TruthFailure("Jonathan replied (telegram_inbox) but the hold stayed shut: every later "
                               "message to him would be blocked")
    finally:
        conn.rollback(); conn.close()


def _run_relay(send_ok):
    calls, replies = [], []
    fake = types.ModuleType("tg_send")
    fake.send = lambda **kw: (calls.append(kw) or (send_ok, "stub"))
    real_tg, real_send, real_dry = sys.modules.get("tg_send"), SD._send, SD.DRY
    sys.modules["tg_send"] = fake
    SD._send = lambda ch, uid, text: replies.append(text) or True
    SD.DRY = False
    conn, tc = _rb()
    try:
        m = {"assignee_key": "truth-test", "name": "Tester", "channel": "messenger",
             "channel_user_id": "truth-test-0", "state": {}, "voice": {"raw": "english"}}
        SD._relay(tc, m, "Notify Jonathan please")
    finally:
        conn.rollback(); conn.close()
        sys.modules["tg_send"] = real_tg
        SD._send, SD.DRY = real_send, real_dry
    return calls, replies


def staff_relay_goes_through_the_hold(cur):
    calls, _ = _run_relay(True)
    if not calls:
        raise TruthFailure("relay never called tg_send")
    if not calls[0].get("override_pacing"):
        raise TruthFailure(f"staff relay is subject to the one-at-a-time hold (it was blocked on 4 Nov): {calls[0]}")


def held_relay_is_not_reported_as_sent(cur):
    _, replies = _run_relay(False)
    text = " ".join(replies).lower()
    if any(w in text for w in TOLD_HIM):
        raise TruthFailure(f"officer told Jonathan was messaged when the send failed: {replies!r}")
    _, replies = _run_relay(True)
    if not any(w in " ".join(replies).lower() for w in TOLD_HIM):
        raise TruthFailure(f"a delivered relay did not say so: {replies!r}")


def relay_phrasings(cur):
    for q in ("Notify him", "Tell him please", "notify Jonathan"):
        if not SD.RELAY.search(q) or SD.RELAY_STATUS.search(q):
            raise TruthFailure(f"{q!r} should be relayed")
    for q in ("Did you notify him?", "Where did you message him?", "Nasabihan mo na ba siya?"):
        if not SD.RELAY_STATUS.search(q):
            raise TruthFailure(f"{q!r} should get the relay status, not a re-send or a non-answer")
    src = open(SD.__file__).read()
    body = src[src.index("def _handle_staff"):]
    if body.index("RELAY_STATUS.search") > body.index("RELAY.search(text)"):
        raise TruthFailure("RELAY_STATUS must be checked before RELAY (else 'did you notify him' re-sends)")


TESTS = [
    ("staff_relay.hold_opens_on_telegram_inbox_reply", hold_opens_on_telegram_inbox_reply),
    ("staff_relay.goes_through_the_hold", staff_relay_goes_through_the_hold),
    ("staff_relay.held_not_reported_as_sent", held_relay_is_not_reported_as_sent),
    ("staff_relay.phrasings", relay_phrasings),
]

# ── 5 Nov 2026 (Jonathan t325s1572 + t326u): every ask is a tracked work order; real reasons; one retry;
# "I'll ask Jonathan" only after a confirmed send; an unanswered question is never a dead end. ──────────
from datetime import timedelta


class _Stub:
    """tg_send + Messenger stubbed; everything in one rolled-back transaction. Nothing goes out."""
    def __init__(self, results):
        self.results, self.calls, self.replies = list(results), [], []

    def __enter__(self):
        fake = types.ModuleType("tg_send")
        def _send(**kw):
            self.calls.append(kw)
            return self.results.pop(0) if self.results else (True, "stub")
        fake.send = _send
        self.real = (sys.modules.get("tg_send"), SD._send, SD.DRY, SD._member_by_assignee, SD._recheck)
        sys.modules["tg_send"] = fake
        SD._send = lambda ch, uid, text: self.replies.append(text) or True
        SD.DRY = False
        self.m = {"assignee_key": "truth-test", "name": "Tester", "channel": "messenger",
                  "channel_user_id": "truth-test-0", "state": {}, "voice": {"raw": "english"}}
        SD._member_by_assignee = lambda cur, a: self.m if a == "truth-test" else None
        SD._recheck = lambda cur, m, q: None
        self.conn, self.cur = _rb()
        return self

    def __exit__(self, *a):
        self.conn.rollback(); self.conn.close()
        sys.modules["tg_send"], SD._send, SD.DRY, SD._member_by_assignee, SD._recheck = self.real


def _wo(cur, wid):
    cur.execute("SELECT * FROM work_orders WHERE id=%s", (wid,))
    return cur.fetchone()


def relay_overrides_rate_limit_and_opens_decision(cur):
    with _Stub([(True, "ok")]) as S:
        SD._relay(S.cur, S.m, "Notify Jonathan please")
        kw = S.calls[0]
        if not (kw.get("override_pacing") and kw.get("override_rate_limit")):
            raise TruthFailure(f"relay must override pacing AND rate limit: {kw}")
        S.cur.execute("""SELECT w.* FROM work_orders w JOIN staff_question q ON w.target_ref='staff_question:'||q.id
                         WHERE q.assignee='truth-test' ORDER BY w.id DESC LIMIT 1""")
        w = S.cur.fetchone()
        if not w or w["kind"] != "decision" or w["steps"][0].get("owner") != "jonathan":
            raise TruthFailure(f"relay did not open a decision work order owned by Jonathan: {w}")
        if "i'll ask jonathan" not in " ".join(S.replies).lower():
            raise TruthFailure(f"confirmed send should tell her \"I'll ask Jonathan\": {S.replies}")


def failed_relay_logs_real_reason_and_retries_once(cur):
    reason = "rate_limit: 9/8 in last 3600s for chat 6513067717"
    with _Stub([(False, reason), (True, "ok"), (True, "ok")]) as S:
        SD._relay(S.cur, S.m, "Notify Jonathan please")
        if "i'll ask jonathan" in " ".join(S.replies).lower():
            raise TruthFailure(f"told \"I'll ask Jonathan\" before the send was confirmed: {S.replies}")
        S.cur.execute("SELECT * FROM staff_question WHERE assignee='truth-test' ORDER BY id DESC LIMIT 1")
        q = S.cur.fetchone()
        if reason not in (q["relayed_via"] or "") or q["detail"] != reason:
            raise TruthFailure(f"the real tg_send reason was not logged: {q['relayed_via']!r} / {q['detail']!r}")
        S.cur.execute("SELECT id FROM work_orders WHERE target_ref=%s", (f"staff_question:{q['id']}",))
        wid = S.cur.fetchone()["id"]
        SD.followups(S.cur, now=SD._now() + timedelta(minutes=5), force=True)
        if len(S.calls) != 1:
            raise TruthFailure("retried before 15 minutes")
        SD.followups(S.cur, now=SD._now() + timedelta(minutes=16), force=True)
        if len(S.calls) != 2:
            raise TruthFailure(f"no retry after 15 minutes (calls={len(S.calls)})")
        if not any("now reached jonathan" in r.lower() for r in S.replies):
            raise TruthFailure(f"she was not told once the retry reached him: {S.replies}")
        SD.followups(S.cur, now=SD._now() + timedelta(minutes=40), force=True)
        if len(S.calls) != 2:
            raise TruthFailure("retried more than once")
        if not _wo(S.cur, wid)["steps"][0].get("sent"):
            raise TruthFailure("work order not marked sent after the retry")


def unanswered_question_becomes_tracked_request(cur):
    with _Stub([]) as S:
        wid, sent = SD._open_inquiry(S.cur, S.m, "What kind of service should I choose?")
        w = _wo(S.cur, wid)
        st = w["steps"][0]
        if w["kind"] != "staff_inquiry" or st.get("owner") != "jonathan" or not st.get("next_follow_up_at"):
            raise TruthFailure(f"unanswered question did not open an owned, followed-up request: {w}")
        if w["status"] not in SD.REQ_OPEN:
            raise TruthFailure(f"request not open: {w['status']}")
        if SD._open_inquiry(S.cur, S.m, "What kind of service should I choose?")[0] != wid:
            raise TruthFailure("same question opened a second request (dedup)")
        SD._my_requests(S.cur, S.m)
        if f"#{wid}" not in S.replies[-1]:
            raise TruthFailure(f"'my requests' does not show it: {S.replies[-1]}")
        if SD.close_request(S.cur, wid)["closed"]:
            raise TruthFailure("a request closed without an answer or resolution")
        n0 = len(S.calls)
        SD.followups(S.cur, now=SD._now() + timedelta(hours=25), force=True)
        if len(S.calls) <= n0 or "follow-up 1" not in S.calls[-1]["text"].lower():
            raise TruthFailure("no 24 h follow-up to the owner")
        if not SD.close_request(S.cur, wid, answer="Choose Filing of Verified Petition.", send=True)["closed"]:
            raise TruthFailure("close with an answer failed")
        if _wo(S.cur, wid)["status"] != "done":
            raise TruthFailure("closed request not done")


def backfilled_requests_never_ping(cur):
    with _Stub([]) as S:
        S.cur.execute("""INSERT INTO staff_question (assignee, question, outcome) VALUES ('truth-test','q?','not_in_sources')
                         RETURNING id""")
        sq = S.cur.fetchone()["id"]
        out = SD.open_backfill(S.cur, [sq], ping=False)
        S.cur.execute("UPDATE work_orders SET status='cancelled' WHERE created_by='staff_desk' AND id<>%s",
                      (out[0]["work_order"],))      # isolate (rolled back)
        SD.followups(S.cur, now=SD._now() + timedelta(days=3), force=True)
        if S.calls or S.replies:
            raise TruthFailure(f"a backfilled request pinged someone: {S.calls} {S.replies}")
        if _wo(S.cur, out[0]["work_order"])["status"] not in SD.REQ_OPEN:
            raise TruthFailure("backfilled request not open")


TESTS += [
    ("staff_relay.overrides_rate_limit_opens_decision", relay_overrides_rate_limit_and_opens_decision),
    ("staff_relay.real_reason_and_one_retry", failed_relay_logs_real_reason_and_retries_once),
    ("staff_relay.unanswered_becomes_request", unanswered_question_becomes_tracked_request),
    ("staff_relay.backfill_never_pings", backfilled_requests_never_ping),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
