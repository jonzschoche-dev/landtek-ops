-- deploy_979_client_money_chat.sql — Client app Money + Chat substrate
-- Billing config/invoices are thin; property ledger reuses transactions.
-- Chat is its own table (NOT channel_messages) so client_app inbound does not
-- fire notify_leo_inbound / dual-brain auto-replies (A85). Ops replies here.

CREATE TABLE IF NOT EXISTS client_billing (
  client_code       text PRIMARY KEY REFERENCES clients(client_code),
  plan_label        text,                          -- e.g. 'Monthly retainer'
  monthly_amount    numeric(14,2),
  currency          text NOT NULL DEFAULT 'PHP',
  status            text NOT NULL DEFAULT 'not_set', -- not_set|active|paused|past_due
  next_bill_date    date,
  notes             text,
  updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS client_invoices (
  id                bigserial PRIMARY KEY,
  client_code       text NOT NULL REFERENCES clients(client_code),
  invoice_no        text NOT NULL,
  issue_date        date NOT NULL DEFAULT CURRENT_DATE,
  due_date          date,
  amount            numeric(14,2) NOT NULL,
  currency          text NOT NULL DEFAULT 'PHP',
  status            text NOT NULL DEFAULT 'draft',  -- draft|sent|paid|void|overdue
  description       text,
  pdf_doc_id        integer REFERENCES documents(id) ON DELETE SET NULL,
  paid_at           date,
  created_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (client_code, invoice_no)
);

CREATE INDEX IF NOT EXISTS idx_client_invoices_client
  ON client_invoices (client_code, status, due_date);

CREATE TABLE IF NOT EXISTS client_app_messages (
  id                bigserial PRIMARY KEY,
  client_code       text NOT NULL REFERENCES clients(client_code),
  direction         text NOT NULL CHECK (direction IN ('inbound', 'outbound')),
  author            text NOT NULL DEFAULT 'client',  -- client|ops|system
  body              text NOT NULL,
  status            text NOT NULL DEFAULT 'sent',
  created_at        timestamptz NOT NULL DEFAULT now(),
  read_at           timestamptz
);

CREATE INDEX IF NOT EXISTS idx_client_app_messages_thread
  ON client_app_messages (client_code, created_at DESC);

-- MWK: billing not configured yet (honest empty) — no seed amount.
INSERT INTO client_billing (client_code, plan_label, status, notes)
VALUES ('MWK-001', 'LandTek portfolio retainer', 'not_set',
        'Set monthly_amount when first invoice ships')
ON CONFLICT (client_code) DO NOTHING;

INSERT INTO client_billing (client_code, plan_label, status, notes)
VALUES ('Paracale-001', 'LandTek portfolio retainer', 'not_set',
        'Set monthly_amount when first invoice ships')
ON CONFLICT (client_code) DO NOTHING;

-- Welcome line once (idempotent via fixed system fingerprint in body prefix)
INSERT INTO client_app_messages (client_code, direction, author, body, status)
SELECT c.client_code, 'outbound', 'system',
       'Welcome to LandTek. Message us here about titles, tax, map, or billing — your team will reply.',
       'sent'
  FROM clients c
 WHERE c.client_code IN ('MWK-001', 'Paracale-001')
   AND NOT EXISTS (
         SELECT 1 FROM client_app_messages m
          WHERE m.client_code = c.client_code AND m.author = 'system'
            AND m.body LIKE 'Welcome to LandTek.%'
       );
