#!/usr/bin/env python3
"""intake_clarity_report.py — measure table intake vs 90% target; list human-oversight queue.

Definitions (honest, not marketing):
  doc_fact_intake     = linked docs with text that produced ≥1 matter_facts / linked text docs
  fact_field_intake   = facts with ≥1 fact_fields row / all matter_facts
  title_core_intake   = title_brief clear|partial / all title_brief  (usable cards, not inventing)

Unclear is SUCCESS when flagged — failure is unclear data presented as complete.

  python3 scripts/intake_clarity_report.py
  python3 scripts/intake_clarity_report.py --log
  python3 scripts/intake_clarity_report.py --queue 30
"""
from __future__ import annotations

import argparse
import os
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
TARGET = 90.0


def pct(num, den):
    return round(100.0 * num / den, 2) if den else 0.0


def bar(p, target=TARGET):
    mark = "✓" if p >= target else "·" if p >= target * 0.75 else "✗"
    return f"{mark} {p:5.1f}%  (target {target:.0f}%)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", action="store_true", help="append to intake_clarity_log")
    ap.add_argument("--queue", type=int, default=20, help="show N titles needing human review")
    a = ap.parse_args()

    c = psycopg2.connect(DSN)
    c.autocommit = True
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        """
        SELECT count(*) total,
               count(*) FILTER (WHERE length(coalesce(extracted_text,'')) > 80) with_text
        FROM documents
        """
    )
    docs = cur.fetchone()

    cur.execute(
        """
        SELECT count(DISTINCT d.id) n FROM documents d
        JOIN document_matter_links l ON l.doc_id = d.id
        WHERE length(coalesce(d.extracted_text,'')) > 80
        """
    )
    linked = int(cur.fetchone()["n"])

    cur.execute(
        """
        SELECT count(DISTINCT d.id) n FROM documents d
        JOIN document_matter_links l ON l.doc_id = d.id
        WHERE length(coalesce(d.extracted_text,'')) > 80
          AND EXISTS (
            SELECT 1 FROM matter_facts mf
            WHERE mf.source_kind = 'doc' AND mf.source_id = d.id::text
          )
        """
    )
    with_facts = int(cur.fetchone()["n"])
    doc_pct = pct(with_facts, linked)

    cur.execute("SELECT count(*) n FROM matter_facts")
    facts_total = int(cur.fetchone()["n"])
    cur.execute("SELECT count(DISTINCT fact_id) n FROM fact_fields")
    facts_fields = int(cur.fetchone()["n"])
    field_pct = pct(facts_fields, facts_total)

    cur.execute(
        """
        SELECT count(*) n,
               count(*) FILTER (WHERE clarity_status = 'clear') clear,
               count(*) FILTER (WHERE clarity_status = 'partial') partial,
               count(*) FILTER (WHERE clarity_status = 'unclear') unclear,
               count(*) FILTER (WHERE needs_human_review) review
        FROM title_brief
        """
    )
    tb = cur.fetchone()
    titles_n = int(tb["n"] or 0)
    title_pct = pct(int(tb["clear"] or 0) + int(tb["partial"] or 0), titles_n)

    cur.execute(
        """
        SELECT count(*) n,
               count(*) FILTER (WHERE needs_human_review) review,
               count(*) FILTER (WHERE n_facts_verified = 0) no_v
        FROM matter_brief
        """
    )
    mb = cur.fetchone()

    print("═══════════════════════════════════════════════════")
    print("  INTAKE / CLARITY METER  (be honest about gaps)")
    print("═══════════════════════════════════════════════════")
    print(f"  Docs total              {docs['total']}")
    print(f"  Docs with text          {docs['with_text']}")
    print(f"  Linked + text           {linked}")
    print(f"  → produced facts        {with_facts}   {bar(doc_pct)}")
    print(f"  Facts total             {facts_total}")
    print(f"  → typed (≥1 field)      {facts_fields}   {bar(field_pct)}")
    print(f"  Title cards             {titles_n}")
    print(f"     clear / partial / unclear   {tb['clear']} / {tb['partial']} / {tb['unclear']}")
    print(f"     need human review    {tb['review']}")
    print(f"  → usable (clear+partial)        {bar(title_pct)}")
    print(f"  Matter briefs           {mb['n']}  (need_review={mb['review']}, zero_verified={mb['no_v']})")
    print("───────────────────────────────────────────────────")
    print("  Rule: unclear data is FLAGGED, never filled with guesses.")
    print("  90% target = robust intake of what exists; remainder = human queue.")
    print("═══════════════════════════════════════════════════")

    if a.queue:
        print(f"\n  HUMAN OVERSIGHT QUEUE (top {a.queue} titles)")
        cur.execute(
            """
            SELECT title_key, clarity_status, clarity_score, missing_fields,
                   oversight_reason, n_source_docs, headline
            FROM title_brief
            WHERE needs_human_review
            ORDER BY clarity_score ASC NULLS FIRST, n_source_docs ASC
            LIMIT %s
            """,
            (a.queue,),
        )
        for r in cur.fetchall():
            miss = ",".join(r["missing_fields"] or [])
            print(
                f"  · {r['title_key']:<22} {r['clarity_status'] or '?':<8} "
                f"score={r['clarity_score'] or 0:.2f} miss=[{miss}] docs={r['n_source_docs']}"
            )

    if a.log:
        cur.execute(
            """
            INSERT INTO intake_clarity_log (
                docs_total, docs_with_text, docs_linked_text, docs_with_facts, doc_fact_intake_pct,
                facts_total, facts_with_fields, fact_field_intake_pct,
                titles_total, titles_clear, titles_partial, titles_unclear, titles_need_review,
                title_core_intake_pct, matters_total, matters_need_review, target_pct, notes
            ) VALUES (
                %s,%s,%s,%s,%s,
                %s,%s,%s,
                %s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s
            )
            """,
            (
                docs["total"], docs["with_text"], linked, with_facts, doc_pct,
                facts_total, facts_fields, field_pct,
                titles_n, tb["clear"], tb["partial"], tb["unclear"], tb["review"],
                title_pct, mb["n"], mb["review"], TARGET,
                "intake_clarity_report",
            ),
        )
        print("\n  [logged → intake_clarity_log]")

    # exit code soft signal for automation
    worst = min(doc_pct, field_pct, title_pct if titles_n else 100)
    sys.exit(0 if worst >= TARGET else 1)


if __name__ == "__main__":
    main()
