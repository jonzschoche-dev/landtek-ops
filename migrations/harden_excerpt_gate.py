#!/usr/bin/env python3
"""harden_excerpt_gate.py — make the provenance gate verify the EXCERPT, not just that one exists.

The deploy_504 gate checks a verified row cites a resolving doc + has a non-empty excerpt. That is
enough when a human writes the row (self-policing). It is NOT enough for an autonomous LLM reader,
which is exactly where a fabricated quote could slip through. This adds the missing check:

  a verified row's excerpt must be a VERBATIM substring of its cited document's extracted_text.

`excerpt_grounded(excerpt, doc_id)` normalizes both sides (strip quotes/brackets, collapse whitespace,
lowercase) and — because our excerpts join non-contiguous spans with '...' — requires EACH
ellipsis-separated segment (>= 12 chars) to appear in the document. Short fragments are ignored.

  python3 migrations/harden_excerpt_gate.py            # AUDIT: would existing verified rows pass?
  python3 migrations/harden_excerpt_gate.py --apply     # install the function + harden the 3 triggers
"""
import argparse
import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

FUNC = r"""
CREATE OR REPLACE FUNCTION _prov_norm(t text) RETURNS text AS $$
  -- lowercase, then collapse every non-alphanumeric run (punctuation, quotes, brackets, OCR noise,
  -- whitespace) to a single space. Robust to OCR punctuation mangling; still strong — a 12+ char
  -- alphanumeric span cannot be coincidentally fabricated to match a real document.
  SELECT btrim(regexp_replace(lower(coalesce(t,'')), '[^a-z0-9]+', ' ', 'g'))
$$ LANGUAGE sql IMMUTABLE;

-- grounded := at least one contiguous WIN-char verbatim run of the normalized excerpt appears in the
-- normalized document. A real quote always has a long clean run (even if one word is OCR-garbled or
-- the excerpt splices spans with '...'); a fabricated quote has no such run. Strong AND OCR-robust.
CREATE OR REPLACE FUNCTION excerpt_grounded(p_excerpt text, p_doc_id text) RETURNS boolean AS $$
DECLARE doc_norm text; exc_norm text; L int; i int; WIN int := 35;
BEGIN
  SELECT _prov_norm(extracted_text) INTO doc_norm FROM documents WHERE id::text = p_doc_id;
  IF doc_norm IS NULL OR doc_norm = '' THEN RETURN false; END IF;
  exc_norm := _prov_norm(p_excerpt);
  L := length(exc_norm);
  IF L = 0 THEN RETURN false; END IF;
  IF L <= WIN THEN RETURN position(exc_norm in doc_norm) > 0; END IF;
  i := 1;
  WHILE i <= L - WIN + 1 LOOP
    IF position(substr(exc_norm, i, WIN) in doc_norm) > 0 THEN RETURN true; END IF;
    i := i + 5;
  END LOOP;
  RETURN false;
END;
$$ LANGUAGE plpgsql STABLE;
"""

TRIGGERS = r"""
CREATE OR REPLACE FUNCTION enforce_provenance_facts() RETURNS trigger AS $f$
BEGIN
  IF NEW.provenance_level = 'verified' THEN
    IF NEW.source_kind IS DISTINCT FROM 'doc' OR NEW.source_id IS NULL
       OR NOT EXISTS (SELECT 1 FROM documents d WHERE d.id::text = NEW.source_id)
       OR coalesce(NEW.excerpt,'') = ''
       OR NOT excerpt_grounded(NEW.excerpt, NEW.source_id) THEN
      RAISE EXCEPTION 'PROVENANCE GATE (matter_facts): verified requires source_kind=doc + resolving source_id + an excerpt that is a VERBATIM substring of the cited document. Use operator/inferred otherwise.';
    END IF;
  END IF; RETURN NEW;
END; $f$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION enforce_provenance_parties() RETURNS trigger AS $f$
BEGIN
  IF NEW.provenance_level = 'verified' THEN
    IF NEW.source_doc_id IS NULL OR NOT EXISTS (SELECT 1 FROM documents d WHERE d.id = NEW.source_doc_id)
       OR coalesce(NEW.source_excerpt,'') = ''
       OR NOT excerpt_grounded(NEW.source_excerpt, NEW.source_doc_id::text) THEN
      RAISE EXCEPTION 'PROVENANCE GATE (matter_parties): verified requires source_doc_id (resolving) + a source_excerpt that is a verbatim substring of the cited document.';
    END IF;
  END IF; RETURN NEW;
END; $f$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION enforce_provenance_causes() RETURNS trigger AS $f$
BEGIN
  IF NEW.provenance_level = 'verified' THEN
    IF NEW.operative_doc_id IS NULL OR NOT EXISTS (SELECT 1 FROM documents d WHERE d.id = NEW.operative_doc_id)
       OR coalesce(NEW.source_excerpt,'') = ''
       OR NOT excerpt_grounded(NEW.source_excerpt, NEW.operative_doc_id::text) THEN
      RAISE EXCEPTION 'PROVENANCE GATE (matter_causes): verified requires operative_doc_id (resolving) + a source_excerpt that is a verbatim substring of the cited document.';
    END IF;
  END IF; RETURN NEW;
END; $f$ LANGUAGE plpgsql;
"""

AUDIT = [
    ("matter_facts",   "excerpt",        "source_id"),
    ("matter_parties", "source_excerpt", "source_doc_id::text"),
    ("matter_causes",  "source_excerpt", "operative_doc_id::text"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    c = psycopg2.connect(DSN); c.autocommit = True
    cur = c.cursor()
    cur.execute(FUNC)  # create the checker (safe; no trigger change yet)
    print("[harden] excerpt_grounded() created.\n[harden] AUDIT of existing verified rows:")
    all_ok = True
    for tbl, exc, doc in AUDIT:
        cur.execute(f"SELECT id, {doc} AS d, {exc} AS e FROM {tbl} WHERE provenance_level='verified'")
        rows = cur.fetchall()
        bad = []
        for rid, d, e in rows:
            cur.execute("SELECT excerpt_grounded(%s,%s)", (e, str(d) if d is not None else None))
            if not cur.fetchone()[0]:
                bad.append((rid, str(e)[:70]))
        print(f"   {tbl}: {len(rows)-len(bad)}/{len(rows)} grounded" + (" ✓" if not bad else f"  ✗ {len(bad)} FAIL"))
        for rid, e in bad[:12]:
            print(f"       id={rid}: {e}…")
        all_ok = all_ok and not bad
    if not a.apply:
        print("\n[audit-only] re-run with --apply to harden the triggers" +
              ("" if all_ok else " — FIX failing rows first (or they'll block future re-writes)"))
        return
    # Re-tier any verified row whose excerpt is NOT verbatim-grounded: it was claimed 'verified' but
    # the quote is not in the cited doc -> downgrade to inferred_strong (honest; content kept as a
    # lead, and verify_loop will re-enqueue it for a proper source-read). 'verified' now means verified.
    print()
    for tbl, exc, doc in AUDIT:
        cur.execute(f"UPDATE {tbl} SET provenance_level='inferred_strong' "
                    f"WHERE provenance_level='verified' AND NOT excerpt_grounded({exc}, {doc})")
        if cur.rowcount:
            print(f"[harden] re-tiered {cur.rowcount} non-grounded {tbl}: verified -> inferred_strong")
    cur.execute(TRIGGERS)
    print("[harden] ✓ triggers hardened — verified writes now require a verbatim-substring excerpt.")
    for tbl, *_ in AUDIT:
        cur.execute(f"SELECT count(*) FROM {tbl} WHERE provenance_level='verified'")
        print(f"   {tbl}: {cur.fetchone()[0]} verified (all now verbatim-grounded)")


if __name__ == "__main__":
    main()
