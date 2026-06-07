#!/usr/bin/env python3
"""apply_deploy_361_vault_schema.py — master vault foundation.

Jonathan's filing model (2026-06-07):

  Master vault   = physical originals where no digital copy can substitute.
                   Narrow set: TCT originals, notarized SPAs/deeds/affidavits,
                   court returning copies with wet stamp/seal, PSA civil-registry
                   originals, original government IDs, sealed resolutions.
                   Everything else is digital-master by default.

  Per-case folder = working set. Copies of masters that case needs + case-
                   specific work product (drafts, internal memos, briefs).
                   Many-to-many via existing document_matter_links.

  Vault locator  = SECTION-NNN. Kristyle (filing_assistant) assigns the
                   number when she labels the physical folder. System records
                   what she texts back. No auto-numbering; the paper is the
                   source of truth.

This migration:
  1. Creates vault_sections lookup with 12 starter codes.
  2. Adds documents.master_form ('digital' default; 'physical' for vault items).
  3. Adds documents.vault_section + vault_number + vault_location + digital_scan_id.
  4. Adds index on (vault_section, vault_number) for fast lookup.

Idempotent. Safe to re-run. Does NOT classify existing documents — they all stay
master_form='digital' until Kristyle vaults a physical original.
"""
from __future__ import annotations
import os
import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

SECTIONS = [
    ("TCT",  "Title certificates",          "RD originals + certified true copies of Transfer Certificates of Title"),
    ("DEED", "Deeds",                       "Sale, donation, conveyance, partition — notarized originals"),
    ("SPA",  "Special Powers of Attorney",  "Notarized SPA originals (wet ink + raised seal)"),
    ("AFF",  "Notarized affidavits",        "Affidavits of loss, support, undertaking, etc. — notarized originals"),
    ("TAX",  "Tax declarations + receipts", "Real-property tax declarations + tax payment receipts"),
    ("PSA",  "Civil registry — PSA",        "Birth, death, marriage certificates from PSA (with security paper)"),
    ("ID",   "Government IDs",              "Original government-issued IDs"),
    ("CRT",  "Court returning copies",      "Stamped pleadings, orders, resolutions returned from court/agency"),
    ("RES",  "Resolutions + decisions",     "CTC of resolutions/decisions where original certification is required"),
    ("CONT", "Contracts requiring originals", "Leases, mortgages, JVAs, MOA — where original signature carries force"),
    ("CORR", "Legal correspondence",        "Demand letters with registry stamps; physical correspondence with weight"),
    ("MISC", "Unclassified",                "Pending classification — assign a real section when reviewed"),
]


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor()

    print("[deploy_361] creating vault_sections lookup ...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS vault_sections (
            code        text PRIMARY KEY,
            label       text NOT NULL,
            description text,
            active      boolean NOT NULL DEFAULT true,
            created_at  timestamptz NOT NULL DEFAULT now()
        )
    """)

    print("[deploy_361] seeding 12 starter section codes ...")
    for code, label, desc in SECTIONS:
        cur.execute("""
            INSERT INTO vault_sections (code, label, description)
            VALUES (%s, %s, %s)
            ON CONFLICT (code) DO UPDATE
              SET label = EXCLUDED.label,
                  description = EXCLUDED.description
        """, (code, label, desc))

    print("[deploy_361] extending documents with vault columns ...")
    cur.execute("""
        ALTER TABLE documents
            ADD COLUMN IF NOT EXISTS master_form     text NOT NULL DEFAULT 'digital',
            ADD COLUMN IF NOT EXISTS vault_section   text REFERENCES vault_sections(code),
            ADD COLUMN IF NOT EXISTS vault_number    int,
            ADD COLUMN IF NOT EXISTS vault_location  text,
            ADD COLUMN IF NOT EXISTS digital_scan_id int REFERENCES documents(id)
    """)
    cur.execute("""
        ALTER TABLE documents
            DROP CONSTRAINT IF EXISTS documents_master_form_check
    """)
    cur.execute("""
        ALTER TABLE documents
            ADD CONSTRAINT documents_master_form_check
            CHECK (master_form IN ('digital', 'physical'))
    """)
    cur.execute("""
        ALTER TABLE documents
            DROP CONSTRAINT IF EXISTS documents_vault_locator_unique
    """)
    cur.execute("""
        ALTER TABLE documents
            ADD CONSTRAINT documents_vault_locator_unique
            UNIQUE (vault_section, vault_number)
    """)

    print("[deploy_361] indexes ...")
    cur.execute("""
        CREATE INDEX IF NOT EXISTS documents_master_form_idx
            ON documents(master_form) WHERE master_form = 'physical'
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS documents_vault_section_idx
            ON documents(vault_section) WHERE vault_section IS NOT NULL
    """)

    print("[deploy_361] verification ...")
    cur.execute("SELECT COUNT(*) FROM vault_sections WHERE active = true")
    n_sections = cur.fetchone()[0]
    cur.execute("""
        SELECT column_name FROM information_schema.columns
         WHERE table_name = 'documents'
           AND column_name IN ('master_form','vault_section','vault_number',
                               'vault_location','digital_scan_id')
        ORDER BY column_name
    """)
    cols = [r[0] for r in cur.fetchall()]

    print(f"  vault_sections rows: {n_sections}")
    print(f"  new documents cols : {cols}")
    assert n_sections >= 12, "section seed failed"
    assert len(cols) == 5, f"expected 5 new cols, got {cols}"

    cur.close()
    conn.close()
    print("[deploy_361] DONE")


if __name__ == "__main__":
    main()
