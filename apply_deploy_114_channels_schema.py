#!/usr/bin/env python3
"""Deploy 114 — Multi-channel adapter schema.

Adds:
  channels             — registered I/O channels (telegram, whatsapp, web, email, slack, etc.)
  channel_users        — maps per-channel user IDs to a canonical Landtek identity
  channel_messages     — every inbound/outbound message, normalized
  channel_audit        — auth + delivery audit trail

This enables Leo's brain to be reached from any platform — Telegram is
just channel #1.
"""
import psycopg2
DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

SQL = r"""
CREATE TABLE IF NOT EXISTS channels (
  id              serial PRIMARY KEY,
  name            text UNIQUE NOT NULL,    -- 'telegram', 'whatsapp', 'web', 'email', 'slack', 'sms', 'voice', 'api'
  provider        text,                    -- 'BotAPI', '360dialog', 'twilio', 'gmail', 'meta', etc.
  webhook_url     text,
  auth_secret_ref text,                    -- env var name where token lives (don't store secret)
  active          boolean DEFAULT true,
  default_locale  text DEFAULT 'en',
  rate_limit_per_min integer DEFAULT 60,
  notes           text,
  created_at      timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS channel_users (
  id              serial PRIMARY KEY,
  channel_id      integer REFERENCES channels(id) ON DELETE CASCADE,
  channel_user_id text NOT NULL,           -- e.g., Telegram chat_id, WhatsApp phone, email address
  display_name    text,
  mapped_client_code text,                 -- e.g., 'MWK-001' if this is a client
  mapped_operator text,                    -- e.g., 'jonathan' if this is staff
  role            text DEFAULT 'unknown',  -- 'operator' | 'client' | 'counterparty' | 'unknown'
  authorized      boolean DEFAULT false,
  authorized_at   timestamptz,
  authorized_by   text,
  first_seen_at   timestamptz DEFAULT now(),
  last_seen_at    timestamptz,
  metadata        jsonb DEFAULT '{}'::jsonb,
  UNIQUE(channel_id, channel_user_id)
);
CREATE INDEX IF NOT EXISTS idx_chu_role ON channel_users(role, authorized);

CREATE TABLE IF NOT EXISTS channel_messages (
  id              bigserial PRIMARY KEY,
  channel_id      integer REFERENCES channels(id),
  channel_user_id text,
  direction       text NOT NULL,           -- 'inbound' | 'outbound'
  external_msg_id text,                    -- platform's ID for the message
  text_content    text,
  attachments     jsonb,
  reply_to_id     bigint REFERENCES channel_messages(id) ON DELETE SET NULL,
  sent_at         timestamptz DEFAULT now(),
  delivered_at    timestamptz,
  read_at         timestamptz,
  status          text DEFAULT 'sent',     -- 'sent','delivered','read','failed'
  metadata        jsonb DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_cm_channel_user ON channel_messages(channel_id, channel_user_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_cm_direction ON channel_messages(direction, sent_at DESC);

CREATE TABLE IF NOT EXISTS channel_audit (
  id           serial PRIMARY KEY,
  channel_id   integer REFERENCES channels(id),
  event_type   text NOT NULL,              -- 'auth_attempt','rate_limit','delivery_failure','webhook_received','adapter_error'
  payload      jsonb,
  result       text,
  created_at   timestamptz DEFAULT now()
);

-- Seed Telegram as channel #1
INSERT INTO channels (name, provider, auth_secret_ref, active, notes)
VALUES ('telegram', 'BotAPI', 'TELEGRAM_BOT_TOKEN', true, 'Primary channel — @LeoLandtekBot')
ON CONFLICT (name) DO NOTHING;

-- Seed Jonathan as the operator on Telegram
INSERT INTO channel_users (channel_id, channel_user_id, display_name, mapped_operator, role, authorized, authorized_at, authorized_by)
SELECT id, '6513067717', 'Jonathan Zschoche', 'jonathan', 'operator', true, now(), 'system_seed'
  FROM channels WHERE name='telegram'
ON CONFLICT (channel_id, channel_user_id) DO NOTHING;

-- Stub channels for future adapters
INSERT INTO channels (name, provider, auth_secret_ref, active, notes) VALUES
  ('whatsapp', 'meta_360dialog', 'WHATSAPP_API_TOKEN', false, 'Pending — needs WABA provisioning + Meta verification'),
  ('web',      'leo_web_widget', 'WEB_WIDGET_SECRET',  false, 'Pending — embed on landtek.com'),
  ('email',    'gmail_api',      'GMAIL_REFRESH_TOKEN',false, 'Pending — wire Gmail responses through Leo'),
  ('slack',    'slack_bolt',     'SLACK_BOT_TOKEN',    false, 'Pending — internal team ops'),
  ('sms',      'twilio_sms',     'TWILIO_AUTH_TOKEN',  false, 'Pending — for non-smartphone PH users'),
  ('voice',    'twilio_voice',   'TWILIO_AUTH_TOKEN',  false, 'Pending — phone Leo with STT/TTS'),
  ('api',      'rest_public',    'LEO_API_KEY',        false, 'Pending — licensable product for other firms')
ON CONFLICT (name) DO NOTHING;
"""

def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    print("  → applying channels schema …")
    cur.execute(SQL)
    cur.execute("SELECT id, name, provider, active FROM channels ORDER BY id")
    rows = cur.fetchall()
    print(f"  ✓ channels seeded: {len(rows)}")
    for r in rows:
        print(f"    #{r[0]} {r[1]:10s} provider={r[2] or '—':18s} active={r[3]}")
    cur.execute("SELECT count(*) FROM channel_users")
    print(f"  channel_users: {cur.fetchone()[0]}")
    cur.close(); conn.close()
    print("  ✓ deploy_114 complete")


if __name__ == "__main__":
    main()
