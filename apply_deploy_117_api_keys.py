#!/usr/bin/env python3
"""Deploy 117 — API keys table for the licensable REST API."""
import psycopg2
DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

SQL = r"""
CREATE TABLE IF NOT EXISTS api_keys (
  id            serial PRIMARY KEY,
  name          text UNIQUE NOT NULL,    -- e.g., 'firm:doe-law-office'
  key_hash      text UNIQUE NOT NULL,    -- sha256 hex of the issued key
  scope         text DEFAULT 'public',   -- 'public' | 'firm' | 'internal'
  rate_limit_per_min integer DEFAULT 30,
  monthly_quota_cents integer,
  active        boolean DEFAULT true,
  created_at    timestamptz DEFAULT now(),
  expires_at    timestamptz,
  notes         text,
  last_used_at  timestamptz,
  usage_count   integer DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(active);

-- pgcrypto for digest() — needed by /api/v1/leo/* auth check
CREATE EXTENSION IF NOT EXISTS pgcrypto;
"""

def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    cur.execute(SQL)
    cur.execute("SELECT count(*) FROM api_keys")
    print(f"  ✓ api_keys table ready ({cur.fetchone()[0]} keys provisioned)")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
