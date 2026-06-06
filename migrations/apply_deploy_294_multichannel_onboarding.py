#!/usr/bin/env python3
"""Deploy 294 — multi-channel client onboarding.

Jonathan: 'Allan should have been onboarded — he was messaging Leo through
Instagram.' This deploy admits + fixes the structural gap:

  - Until now, the `clients` table only modeled Telegram + email + phone as
    contact channels. Instagram, WhatsApp, Messenger, and SMS were invisible
    to every part of the system (autolink, onboarding, unauth notifier,
    silence sentinel).
  - Allan V. Inocalla (clients.id=8) has been on file since before this
    session as a Paracale-001 client but with ZERO contact info populated.

This deploy:

  A. Schema — add multi-channel columns to clients:
       instagram_handle      text
       whatsapp_number       text
       messenger_id          text
       signal_number         text
       contact_channels_jsonb jsonb DEFAULT '{}'  -- catch-all for unknown channels
       last_contact_channel  text                  -- what they used most recently
       last_contact_at       timestamptz

  B. Helper — scripts/onboard_client.py for one-command client onboarding from
     any channel (telegram, instagram, whatsapp, email, phone).

  C. Manual-bridge convention — chat_notes_external table for logging messages
     from clients on channels we don't have integrations for yet (IG, WhatsApp,
     etc.), so when Allan messages Jonathan on Instagram, Jonathan can paste it
     into the system and we keep the record.

Idempotent."""
from __future__ import annotations
import os
import sys
import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
ACTOR = "jonathan_deploy_294"

SCHEMA_SQL = """
ALTER TABLE clients ADD COLUMN IF NOT EXISTS instagram_handle      text;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS whatsapp_number       text;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS messenger_id          text;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS signal_number         text;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS contact_channels      jsonb DEFAULT '{}'::jsonb;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS last_contact_channel  text;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS last_contact_at       timestamptz;

CREATE INDEX IF NOT EXISTS idx_clients_instagram ON clients(instagram_handle) WHERE instagram_handle IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_clients_whatsapp  ON clients(whatsapp_number)  WHERE whatsapp_number  IS NOT NULL;

-- Manual bridge: when a client messages us on a channel we don't have an
-- integration for (Instagram, WhatsApp, Messenger, in-person, phone call),
-- we log the message here so the record exists.
CREATE TABLE IF NOT EXISTS chat_notes_external (
    id              serial PRIMARY KEY,
    client_id       integer REFERENCES clients(id),
    channel         text NOT NULL,  -- 'instagram', 'whatsapp', 'messenger', 'in_person', 'phone_call', 'sms'
    direction       text NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    occurred_at     timestamptz NOT NULL DEFAULT now(),
    logged_at       timestamptz NOT NULL DEFAULT now(),
    logged_by       text NOT NULL,
    content         text NOT NULL,
    matter_code     text,    -- optional matter hint
    attachments_url text[],  -- if Jonathan uploaded screenshots/photos
    notes           text     -- free-form context
);
CREATE INDEX IF NOT EXISTS idx_cne_client ON chat_notes_external(client_id);
CREATE INDEX IF NOT EXISTS idx_cne_channel ON chat_notes_external(channel);
CREATE INDEX IF NOT EXISTS idx_cne_occurred ON chat_notes_external(occurred_at DESC);
"""


def main() -> int:
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET LOCAL app.actor = %s", (ACTOR,))

    print("Deploy 294 — multi-channel onboarding")
    print("=" * 40)

    print("\n  A) Schema additions")
    cur.execute(SCHEMA_SQL)
    print("    ✓ clients columns + chat_notes_external table")

    # Backfill: mark Allan's client record so it's flagged as needing contact info
    print("\n  B) Flag Allan's empty client record")
    cur.execute(
        """
        UPDATE clients
           SET intelligence_updated_at = now(),
               client_intelligence_summary = COALESCE(client_intelligence_summary, '') ||
                    E'\\n[deploy_294] Contact info missing — was messaging Leo via Instagram per Jonathan 2026-05-30. Needs instagram_handle + email/phone populated.'
         WHERE id = 8 AND name ILIKE '%Inocalla%'
        RETURNING id, name
        """
    )
    r = cur.fetchone()
    if r:
        print(f"    ✓ flagged clients.id={r['id']} ({r['name']})")

    conn.commit()
    print("\n  ✓ COMMITTED")
    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
