#!/usr/bin/env python3
"""Deploy 115 — Title ↔ ARP ↔ Matter linkage schema.

Adds:
  titles.lifecycle_status     — active | cancelled | superseded | contested | lost | void
  title_tax_links             — many-to-many: titles ↔ ARPs (one TCT may have multiple ARPs over time)
  title_matter_links          — titles → matters relationship (subject/evidence/forthcoming/affected)
  view asset_full_record      — unified TCT + ARP + lifecycle + matter view

Idempotent.
"""
import psycopg2
DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

SQL = r"""
ALTER TABLE titles
  ADD COLUMN IF NOT EXISTS lifecycle_status text DEFAULT 'unknown',
  ADD COLUMN IF NOT EXISTS lifecycle_updated_at timestamptz DEFAULT now(),
  ADD COLUMN IF NOT EXISTS lifecycle_notes text;

CREATE TABLE IF NOT EXISTS title_tax_links (
  id               serial PRIMARY KEY,
  title_no         text NOT NULL,        -- e.g., 'T-32917'
  arp_no           text NOT NULL,        -- e.g., 'GR-2014-HH-07-001-00229'
  pin              text,                 -- Property Index Number
  link_source      text,                 -- 'tax_doc_extraction' | 'manual' | 'classifier'
  source_doc_id    integer REFERENCES documents(id) ON DELETE SET NULL,
  confidence       real DEFAULT 0.5,
  effective_from   date,
  effective_to     date,
  notes            text,
  created_at       timestamptz DEFAULT now(),
  UNIQUE(title_no, arp_no)
);
CREATE INDEX IF NOT EXISTS idx_ttl_title ON title_tax_links(title_no);
CREATE INDEX IF NOT EXISTS idx_ttl_arp   ON title_tax_links(arp_no);

CREATE TABLE IF NOT EXISTS title_matter_links (
  id              serial PRIMARY KEY,
  title_no        text NOT NULL,
  matter_code     text NOT NULL REFERENCES matters(matter_code),
  relationship    text NOT NULL,         -- 'subject' | 'evidence' | 'forthcoming_subject' | 'indirectly_affected'
  notes           text,
  created_at      timestamptz DEFAULT now(),
  UNIQUE(title_no, matter_code, relationship)
);
CREATE INDEX IF NOT EXISTS idx_tml_title ON title_matter_links(title_no);
CREATE INDEX IF NOT EXISTS idx_tml_matter ON title_matter_links(matter_code);

-- Unified view: TCT + lifecycle + ARP linkage + tax-doc valuation + matter linkage
CREATE OR REPLACE VIEW asset_full_record AS
WITH title_valuation AS (
  SELECT DISTINCT ON (av.asset_title)
         av.asset_title, av.market_price_value, av.assessed_value, av.area_sqm,
         av.tax_dec_no, av.current_use, av.snapshot_date, av.source_docs
    FROM asset_valuations av
   ORDER BY av.asset_title, av.snapshot_date DESC
),
arp_valuation AS (
  -- Aggregate market value per TCT through tax-link
  SELECT ttl.title_no AS asset_title,
         sum(av.market_price_value) AS linked_market_value,
         sum(av.assessed_value) AS linked_assessed_value,
         sum(av.area_sqm) AS linked_area_sqm,
         count(*) AS linked_arps
    FROM title_tax_links ttl
    JOIN asset_valuations av ON av.asset_title = ttl.arp_no
   GROUP BY ttl.title_no
),
matter_links AS (
  SELECT title_no,
         string_agg(matter_code || ':' || relationship, ', ' ORDER BY relationship) AS matters
    FROM title_matter_links GROUP BY title_no
)
SELECT
  COALESCE(t.tct_number, tv.asset_title) AS title_or_id,
  t.lifecycle_status,
  t.lifecycle_notes,
  -- value: prefer aggregated ARP-linked value over single record
  COALESCE(av.linked_market_value, tv.market_price_value) AS market_value,
  COALESCE(av.linked_assessed_value, tv.assessed_value) AS assessed_value,
  COALESCE(av.linked_area_sqm, tv.area_sqm) AS area_sqm,
  tv.tax_dec_no,
  tv.current_use,
  av.linked_arps,
  ml.matters,
  tv.snapshot_date
FROM titles t
FULL OUTER JOIN title_valuation tv ON tv.asset_title = t.tct_number
LEFT JOIN arp_valuation av ON av.asset_title = t.tct_number
LEFT JOIN matter_links ml ON ml.title_no = t.tct_number;
"""


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    print("  → applying title linkage schema …")
    cur.execute(SQL)
    cur.execute("SELECT 1 FROM information_schema.tables WHERE table_name='title_tax_links'")
    print(f"    {'✓' if cur.fetchone() else '✗'} title_tax_links")
    cur.execute("SELECT 1 FROM information_schema.tables WHERE table_name='title_matter_links'")
    print(f"    {'✓' if cur.fetchone() else '✗'} title_matter_links")
    cur.execute("SELECT 1 FROM information_schema.views WHERE table_name='asset_full_record'")
    print(f"    {'✓' if cur.fetchone() else '✗'} view asset_full_record")
    cur.execute("SELECT 1 FROM information_schema.columns WHERE table_name='titles' AND column_name='lifecycle_status'")
    print(f"    {'✓' if cur.fetchone() else '✗'} titles.lifecycle_status")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
