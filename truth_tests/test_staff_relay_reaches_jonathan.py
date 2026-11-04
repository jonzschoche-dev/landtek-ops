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

if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
