#!/usr/bin/env python3
"""verify_loop.py — the standing loop that keeps the VERIFIABLE CORPUS growing. $0, deterministic.

It does three things, every run (rides the daily timer):

  1. SCOUR  — scan every provenance-bearing knowledge table (matter_facts, matter_parties,
              matter_causes; the title graph is already enqueued by 'system') for rows that are NOT
              verified, and enqueue each into the shared `verification_queue` (current->proposed
              provenance, idempotent). This is the backlog of "claims awaiting a source-read."
  2. POINT  — rank the LEGIBLE source documents (email attachments + good-OCR, matter-linked, not yet
              source-read) so the comprehension step (Cowork now; an LLM reader once activated) always
              reads the highest-value un-verified source next. Reading a doc + writing cited facts
              through the provenance gate is what upgrades inferred/operator -> verified.
  3. MEASURE — compute verifiable-corpus coverage (verified rows / total knowledge rows; docs read /
              legible docs) so the number visibly climbs as the corpus is verified.

It never writes a 'verified' row itself (that needs a real read + the gate). It finds, ranks, measures.

  python3 verify_loop.py            # scour + point + measure (writes queue)
  python3 verify_loop.py --report    # measure + point only (no queue writes)
"""
import argparse
import re

import psycopg2
import psycopg2.extras

_OPERATIVE_RE = re.compile(r"complaint|petition|affidavit|manifestation|motion|answer|comment|position paper"
                           r"|ejectment|detainer|forcible entry|accion|recovery of possession", re.I)

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# (table, pk_col, summary_sql, provenance_col, source_doc_col) — the knowledge layer's verifiable rows.
KNOWLEDGE = [
    ("matter_facts",   "id", "left(statement,110)",                                   "provenance_level", "NULLIF(source_id,'')::text"),
    ("matter_parties", "id", "coalesce(party_name,'')||' / '||coalesce(role,'')",      "provenance_level", "source_doc_id::text"),
    ("matter_causes",  "id", "left(cause,110)",                                        "provenance_level", "operative_doc_id::text"),
]


def scour(cur):
    """Enqueue every not-yet-verified knowledge row that isn't already in the queue."""
    added = 0
    for tbl, pk, summ, prov, srcdoc in KNOWLEDGE:
        cur.execute(f"""
            SELECT t.{pk} AS pk, {summ} AS summ, t.{prov} AS prov, {srcdoc} AS srcdoc
            FROM {tbl} t
            WHERE t.{prov} IS DISTINCT FROM 'verified'
              AND NOT EXISTS (SELECT 1 FROM verification_queue q
                              WHERE q.table_name=%s AND q.row_pk=(t.{pk})::text)
        """, (tbl,))
        for r in cur.fetchall():
            sd = r["srcdoc"]
            sd = int(sd) if (sd and str(sd).isdigit()) else None
            cur.execute("""INSERT INTO verification_queue
                (table_name,row_pk,fact_summary,source_doc_id,current_provenance,proposed_provenance,
                 queued_by,queued_at) VALUES (%s,%s,%s,%s,%s,'verified','verify_loop',now())
                ON CONFLICT (table_name,row_pk) DO NOTHING""",
                (tbl, str(r["pk"]), r["summ"], sd, r["prov"]))
            added += cur.rowcount
    return added


def doc_worklist(cur):
    """Legible, matter-linked docs not yet source-read, ranked by value — the next reads."""
    cur.execute("""
        WITH dm AS (   -- a doc belongs to a matter via its matter_code OR a document_matter_links row
            SELECT id AS doc_id, matter_code FROM documents WHERE matter_code IS NOT NULL
            UNION
            SELECT doc_id, matter_code FROM document_matter_links
        ),
             email AS (SELECT DISTINCT document_id FROM gmail_messages WHERE document_id IS NOT NULL),
             valued AS (SELECT DISTINCT unnest(maps_to_matters) mc FROM client_issues WHERE value_amount IS NOT NULL)
        SELECT d.id,
               dm.matter_code,
               (e.document_id IS NOT NULL) AS from_email,
               coalesce(q.score,0)::numeric(5,2) AS ocr,
               length(coalesce(d.extracted_text,'')) AS tlen,
               (m.next_deadline IS NOT NULL) AS has_deadline,
               (v.mc IS NOT NULL) AS has_value,
               left(coalesce(d.original_filename,d.smart_filename,'?'),52) AS fn
        FROM dm
        JOIN documents d ON d.id = dm.doc_id
        LEFT JOIN ocr_quality q ON q.doc_id=d.id
        LEFT JOIN email e ON e.document_id=d.id
        LEFT JOIN matters m ON m.matter_code=dm.matter_code
        LEFT JOIN valued v ON v.mc=dm.matter_code
        WHERE (m.status IS NULL OR m.status NOT IN ('closed','archived'))
          AND length(coalesce(d.extracted_text,'')) >= 1000
          AND coalesce(q.flagged,false)=false
          AND (e.document_id IS NOT NULL OR coalesce(q.score,0) >= 0.40)
          AND NOT EXISTS (SELECT 1 FROM matter_facts f   -- not yet read FOR THIS matter (per-matter)
                          WHERE f.provenance_level='verified' AND f.source_kind='doc'
                            AND f.source_id=d.id::text AND f.matter_code=dm.matter_code)
    """)
    rows = cur.fetchall()
    for r in rows:
        r["p"] = (3 if r["from_email"] else 0) + (3 if r["has_value"] else 0) \
            + (2 if r["has_deadline"] else 0) + float(r["ocr"]) + min(float(r["tlen"]) / 40000.0, 2) \
            + (4 if _OPERATIVE_RE.search(r["fn"] or "") else 0)   # read the operative pleading FIRST
    rows.sort(key=lambda r: -r["p"])
    return rows


def measure(cur):
    tot = ver = 0
    per = []
    for tbl, *_ in KNOWLEDGE:
        cur.execute(f"SELECT count(*), count(*) FILTER (WHERE provenance_level='verified') FROM {tbl}")
        t, v = cur.fetchone()
        tot += t; ver += v; per.append((tbl, v, t))
    cur.execute("SELECT count(*) FROM verification_queue WHERE decision IS NULL")
    pending = cur.fetchone()[0]
    return ver, tot, pending, per


def report(cur, work):
    ver, tot, pending, per = measure(cur)
    pct = round(100 * ver / tot, 1) if tot else 0
    print("=" * 68)
    print("VERIFY LOOP — verifiable-corpus coverage")
    print("=" * 68)
    print(f"knowledge rows verified: {ver}/{tot}  ({pct}%)   ·   queued for verification: {pending}")
    for tbl, v, t in per:
        print(f"   {tbl}: {v}/{t} verified")
    print(f"\nlegible docs awaiting a source-read: {len(work)}")
    print("NEXT TO READ (highest value first):")
    for r in work[:15]:
        tag = "📧" if r["from_email"] else "  "
        flags = ("$" if r["has_value"] else " ") + ("D" if r["has_deadline"] else " ")
        print(f"   doc:{r['id']:>4} [{r['matter_code']}] p={round(r['p'],2):<5} {tag}{flags} {r['fn']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    c = psycopg2.connect(DSN); c.autocommit = True
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if not a.report:
        added = scour(cur)
        print(f"[verify-loop] enqueued {added} new verification candidates")
    work = doc_worklist(cur)
    report(c.cursor(), work)


if __name__ == "__main__":
    main()
