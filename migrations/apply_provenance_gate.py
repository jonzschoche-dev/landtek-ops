#!/usr/bin/env python3
"""apply_provenance_gate.py — Phase 0 architecture fix: enforce provenance discipline on the
knowledge layer so inference can no longer be written as fact. $0, deterministic.

WHY (operator, 2026-06-20): the knowledge layer had NO write-gate — anything could INSERT a row and
stamp it 'verified'/'operator' with nothing checking it was true. Proven live (an inference about
Engr. Erwin Balane's role was written as a verified fact). The corruption enters on WRITE, so the
discipline must live on write.

THREE TIERS (canonical):
  verified  — document-proven: cites a RESOLVING source document + a quoted excerpt (the span). The
              ONLY tier surfaced as fact (the _safe / Constitution layer).
  operator  — asserted by the operator (Jonathan). Trustworthy AS his statement; tracked separately;
              promotable to verified only by a source-read.
  inferred_strong / inferred_weak — derived (LLM / pattern). NEVER surfaced as fact; always marked.

Enforced by BEFORE INSERT/UPDATE triggers on matter_facts / matter_parties / matter_causes: a row may
not be stored 'verified' without a resolving doc citation + quoted span. Paired with
truth_tests/test_provenance_integrity.py (the standing audit). Idempotent.
"""
import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# Re-tier the mislabelled rows FIRST (downgrades pass the gate; must run before it is installed
# only matters for safety — downgrades to operator/inferred never trip the verified-requirement).
RETIER = [
    ("facts: operator-sourced but mislabelled verified -> operator",
     "UPDATE matter_facts SET provenance_level='operator' "
     "WHERE provenance_level='verified' AND source_kind='operator'"),
    ("facts: verified without a resolving doc citation -> inferred_strong",
     "UPDATE matter_facts SET provenance_level='inferred_strong' WHERE provenance_level='verified' "
     "AND (source_kind IS DISTINCT FROM 'doc' OR source_id IS NULL "
     "OR NOT EXISTS (SELECT 1 FROM documents d WHERE d.id::text = source_id))"),
    ("parties: hand-fed decipher (not source-read) -> operator",
     "UPDATE matter_parties SET provenance_level='operator' WHERE provenance_level='verified'"),
    ("causes: hand-fed decipher (not source-read) -> operator",
     "UPDATE matter_causes SET provenance_level='operator' WHERE provenance_level='verified'"),
]

DDL = r"""
ALTER TABLE matter_parties ADD COLUMN IF NOT EXISTS source_doc_id int;
ALTER TABLE matter_parties ADD COLUMN IF NOT EXISTS source_excerpt text;
ALTER TABLE matter_causes  ADD COLUMN IF NOT EXISTS source_excerpt text;

CREATE OR REPLACE FUNCTION enforce_provenance_facts() RETURNS trigger AS $f$
BEGIN
  IF NEW.provenance_level = 'verified' THEN
    IF NEW.source_kind IS DISTINCT FROM 'doc' OR NEW.source_id IS NULL
       OR NOT EXISTS (SELECT 1 FROM documents d WHERE d.id::text = NEW.source_id)
       OR coalesce(NEW.excerpt,'') = '' THEN
      RAISE EXCEPTION 'PROVENANCE GATE (matter_facts): a verified fact requires source_kind=doc + a '
        'resolving source_id + a non-empty excerpt (the quoted span). Use provenance_level=operator '
        'for an operator assertion, or inferred_strong for a derivation.';
    END IF;
  END IF; RETURN NEW;
END; $f$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION enforce_provenance_parties() RETURNS trigger AS $f$
BEGIN
  IF NEW.provenance_level = 'verified' THEN
    IF NEW.source_doc_id IS NULL OR NOT EXISTS (SELECT 1 FROM documents d WHERE d.id = NEW.source_doc_id)
       OR coalesce(NEW.source_excerpt,'') = '' THEN
      RAISE EXCEPTION 'PROVENANCE GATE (matter_parties): verified requires source_doc_id (resolving) '
        '+ source_excerpt. Use operator/inferred_strong otherwise.';
    END IF;
  END IF; RETURN NEW;
END; $f$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION enforce_provenance_causes() RETURNS trigger AS $f$
BEGIN
  IF NEW.provenance_level = 'verified' THEN
    IF NEW.operative_doc_id IS NULL OR NOT EXISTS (SELECT 1 FROM documents d WHERE d.id = NEW.operative_doc_id)
       OR coalesce(NEW.source_excerpt,'') = '' THEN
      RAISE EXCEPTION 'PROVENANCE GATE (matter_causes): verified requires operative_doc_id (resolving) '
        '+ source_excerpt.';
    END IF;
  END IF; RETURN NEW;
END; $f$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tg_prov_facts   ON matter_facts;
DROP TRIGGER IF EXISTS tg_prov_parties ON matter_parties;
DROP TRIGGER IF EXISTS tg_prov_causes  ON matter_causes;
CREATE TRIGGER tg_prov_facts   BEFORE INSERT OR UPDATE ON matter_facts
  FOR EACH ROW EXECUTE FUNCTION enforce_provenance_facts();
CREATE TRIGGER tg_prov_parties BEFORE INSERT OR UPDATE ON matter_parties
  FOR EACH ROW EXECUTE FUNCTION enforce_provenance_parties();
CREATE TRIGGER tg_prov_causes  BEFORE INSERT OR UPDATE ON matter_causes
  FOR EACH ROW EXECUTE FUNCTION enforce_provenance_causes();
"""


def main():
    c = psycopg2.connect(DSN); c.autocommit = True
    cur = c.cursor()
    print("[provenance-gate] re-tiering mislabelled rows ...")
    for label, sql in RETIER:
        cur.execute(sql)
        print(f"  re-tier [{cur.rowcount}] {label}")
    print("[provenance-gate] installing write-gate (columns + triggers) ...")
    cur.execute(DDL)
    cur.execute("SELECT provenance_level, count(*) FROM matter_facts GROUP BY provenance_level ORDER BY 2 DESC")
    print("  matter_facts tiers now:", dict(cur.fetchall()))
    # smoke-test the gate: an uncited 'verified' write MUST be rejected
    try:
        cur.execute("BEGIN")
        cur.execute("INSERT INTO matter_facts(matter_code,statement,provenance_level,source_kind) "
                    "VALUES ('GATE-TEST','smoke','verified','operator')")
        cur.execute("ROLLBACK")
        print("  ⚠ GATE FAILED — an uncited verified write was ACCEPTED")
    except psycopg2.Error:
        cur.execute("ROLLBACK")
        print("  ✓ gate live: an uncited 'verified' write is rejected as designed")


if __name__ == "__main__":
    main()
