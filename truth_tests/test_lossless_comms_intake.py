#!/usr/bin/env python3
"""test_lossless_comms_intake.py — the lossless comms-intake invariant (COMM-AGENT-MAX T3).

Every inbound chat/SMS message that CARRIES MEDIA must have a comms_artifacts ledger row
(landed | deduped | held | quarantined) — every one of which is a *visible, accounted-for*
outcome. A media-bearing message with NO ledger row is a SILENT DROP — the exact failure the
universal sink (comms_artifact_sink.py) closes. Held (A5-unresolved) and quarantined
(fetch/error) are NOT drops — they are visible and reviewable.

Email is excluded on purpose: imap_ingest.py already lands email attachments losslessly and
multi-party; it is the reference, not a client of the chat sink.

Client-isolated + count-independent: the check is a pure existence guard over ALL inbound
media messages, independent of how many exist (0 today — Telegram/Messenger/Viber have received
no media yet; this guards the FORWARD path). Negative-tested below to prove it bites.
"""
import os
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run, TruthFailure, DSN

# Media-bearing detector, per each platform's payload law. Email excluded (imap_ingest owns it).
_MEDIA_PREDICATE = """
  ( (c.name='messenger' AND jsonb_typeof(cm.metadata->'message'->'attachments')='array'
                       AND jsonb_array_length(cm.metadata->'message'->'attachments') > 0)
 OR (c.name='whatsapp'  AND (cm.metadata ? 'image' OR cm.metadata ? 'audio' OR cm.metadata ? 'document'
                             OR cm.metadata ? 'video' OR cm.metadata->>'type' IN ('image','audio','document','video')))
 OR (c.name='telegram'  AND (cm.metadata ? 'photo' OR cm.metadata ? 'document' OR cm.metadata ? 'voice'
                             OR cm.metadata ? 'video' OR cm.metadata ? 'audio'))
 OR (c.name='sms'       AND (cm.metadata ? 'MediaUrl0' OR (cm.metadata->>'NumMedia') NOT IN ('0','',NULL))) )
"""

_UNACCOUNTED_SQL = f"""
SELECT cm.id, c.name AS channel
  FROM channel_messages cm
  JOIN channels c ON c.id = cm.channel_id
  LEFT JOIN comms_artifacts ca ON ca.channel_message_id = cm.id
 WHERE cm.direction = 'inbound'
   AND c.name IN ('messenger','whatsapp','telegram','viber','sms')
   AND {_MEDIA_PREDICATE}
   AND ca.id IS NULL
"""


def ledger_present(cur):
    cur.execute("SELECT to_regclass('public.comms_artifacts') AS t")
    if not cur.fetchone()["t"]:
        raise TruthFailure("comms_artifacts ledger missing — the lossless-intake surface must exist "
                           "(comms_artifact_sink.py / deploy comms_artifacts_ledger).")


def no_media_message_dropped(cur):
    cur.execute(_UNACCOUNTED_SQL)
    rows = cur.fetchall()
    if rows:
        detail = ", ".join(f"msg#{r['id']}({r['channel']})" for r in rows[:10])
        raise TruthFailure(
            f"{len(rows)} inbound media message(s) have NO comms_artifacts row — silent drop(s): {detail}. "
            "Every media message must land, dedup, hold (A5), or quarantine — never vanish. "
            "Wire the channel's adapter to _ingest_channel_media → comms_artifact_sink.")


def detector_bites_negative(cur):
    """Prove the guard bites: inject a synthetic media message with NO ledger row on an isolated
    connection, confirm the detector flags it, then roll back (prod untouched)."""
    conn = psycopg2.connect(DSN); conn.autocommit = False
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        c.execute("""INSERT INTO channel_messages (channel_id, channel_user_id, direction, text_content,
                        sent_at, status, metadata)
                     VALUES ((SELECT id FROM channels WHERE name='messenger'), 'NEGTEST', 'inbound',
                        '[media]', now(), 'received',
                        '{"message":{"attachments":[{"type":"image","payload":{"url":"http://x/y.jpg"}}]}}'::jsonb)
                     RETURNING id""")
        synth_id = c.fetchone()["id"]
        c.execute(_UNACCOUNTED_SQL)
        hits = {r["id"] for r in c.fetchall()}
        if synth_id not in hits:
            raise TruthFailure("negative test FAILED: a media message with no ledger row was NOT flagged — "
                               "the lossless detector does not bite; it would let real drops pass.")
    finally:
        conn.rollback(); c.close(); conn.close()


TESTS = [
    ("lossless_comms.ledger_present", ledger_present),
    ("lossless_comms.no_media_message_dropped", no_media_message_dropped),
    ("lossless_comms.detector_bites_negative", detector_bites_negative),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
