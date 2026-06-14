#!/usr/bin/env python3
"""knowledge_coverage.py — measure awareness so "is the system getting smarter" is a NUMBER.

The failure mode this guards against: spending LLM budget on ephemeral work (chat, QA, indexing)
that never accretes into durable knowledge — so the system stays clueless no matter the spend.
This scores how much of what the system SHOULD know it actually knows (as reconciled, grounded
facts), names the biggest cluelessness gaps, and is re-runnable so every comprehension pass must
visibly move the score. Pure SQL, creditless. The whole point: budget is only worth spending where
it moves this number.

  python3 knowledge_coverage.py              # the awareness scorecard + biggest gaps
"""
import os
import sys

import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True; return c


def _scalar(cur, sql):
    try:
        cur.execute(sql); r = cur.fetchone(); return r[0] if r else 0
    except Exception:
        return 0


def _ratio(n, d):
    return (n / d) if d else 0.0


def run(log=False):
    c = _conn(); cur = c.cursor()
    M = []  # (layer, metric, n, d, weight)

    # DOC layer — can it even read the corpus?
    docs = _scalar(cur, "SELECT count(*) FROM documents WHERE coalesce(file_path,'')<>'' OR drive_file_id IS NOT NULL")
    readable = _scalar(cur, "SELECT count(*) FROM ocr_quality WHERE NOT flagged")
    M.append(("DOC", "documents readable (clean OCR)", readable, docs, 1.0))

    # TITLE layer — does it know each title's real status?
    titles = _scalar(cur, "SELECT count(*) FROM titles WHERE coalesce(tct_number,'')<>''")
    t_status = _scalar(cur, "SELECT count(*) FROM titles WHERE coalesce(status,'unknown')<>'unknown'")
    t_compr = _scalar(cur, "SELECT count(*) FROM property_assets WHERE title_ref IS NOT NULL AND coalesce(note,'') LIKE '%comprehended%'")
    M.append(("TITLE", "titles with a KNOWN status (not 'unknown')", t_status, titles, 2.0))
    M.append(("TITLE", "titles actually COMPREHENDED from their doc", t_compr, titles, 2.0))

    # ASSET layer — does it know what each asset is worth / its real title state?
    assets = _scalar(cur, "SELECT count(*) FROM property_assets")
    a_valued = _scalar(cur, "SELECT count(*) FROM property_assets WHERE est_value IS NOT NULL")
    a_compr = _scalar(cur, "SELECT count(*) FROM property_assets WHERE coalesce(note,'') LIKE '%comprehended%'")
    M.append(("ASSET", "assets with a real valuation (not a guess)", a_valued, assets, 1.5))
    M.append(("ASSET", "assets with a comprehended title status", a_compr, assets, 1.5))

    # MATTER layer — does each matter have reasoned elements + verified claims?
    matters = _scalar(cur, "SELECT count(*) FROM matters WHERE coalesce(status,'') NOT IN ('closed','merged','archived','out_of_scope','pending_triage')")
    m_elem = _scalar(cur, "SELECT count(DISTINCT matter_code) FROM matter_elements")
    M.append(("MATTER", "matters with an evidence matrix", m_elem, matters, 1.0))

    # FACT layer — the heart of awareness: durable, grounded, VERIFIED facts
    facts = _scalar(cur, "SELECT count(*) FROM matter_facts")
    facts_v = _scalar(cur, "SELECT count(*) FROM matter_facts WHERE provenance_level='verified'")
    claims = _scalar(cur, "SELECT count(*) FROM claims")
    M.append(("FACT", "reconciled matter-facts exist at all", min(facts, matters), matters, 3.0))
    M.append(("FACT", "facts that are VERIFIED (not just inferred)", facts_v, max(facts, 1), 2.0))

    print("\n" + "=" * 74)
    print("AWARENESS SCORECARD — what the system should know vs. what it actually knows")
    print("=" * 74)
    layer = None
    weighted_sum = wt = 0.0
    gaps = []
    for lyr, metric, n, d, w in M:
        if lyr != layer:
            layer = lyr; print(f"\n{lyr}")
        r = min(_ratio(n, d), 1.0)
        weighted_sum += r * w; wt += w
        bar = "█" * int(r * 20) + "·" * (20 - int(r * 20))
        print(f"  {bar} {r*100:5.1f}%  {metric}  ({n}/{d})")
        gaps.append((w * (1 - r), f"{metric} — {n}/{d} ({r*100:.0f}%)"))
    score = (weighted_sum / wt * 100) if wt else 0
    print("\n" + "-" * 74)
    print(f"  OVERALL AWARENESS: {score:4.1f}%   (weighted across layers)")
    print("\n  BIGGEST CLUELESSNESS GAPS (where comprehension budget should go first):")
    for _, g in sorted(gaps, reverse=True)[:5]:
        print(f"    • {g}")
    print("\n  → every comprehension pass must move this number. If spend doesn't move it,")
    print("    it's being wasted on ephemera (chat/QA/indexing) — exactly the past failure.")
    if log:
        cur.execute("""CREATE TABLE IF NOT EXISTS awareness_log
            (ts timestamptz DEFAULT now(), score real, n_facts int, titles_comprehended int, assets_valued int)""")
        cur.execute("""INSERT INTO awareness_log (score, n_facts, titles_comprehended, assets_valued)
            VALUES (%s, (SELECT count(*) FROM matter_facts),
                    (SELECT count(*) FROM property_assets WHERE coalesce(note,'') LIKE '%%comprehended%%'),
                    (SELECT count(*) FROM property_assets WHERE est_value IS NOT NULL))""", (round(score, 1),))
        print(f"\n  [logged awareness={score:.1f}% to awareness_log]")
    cur.close(); c.close()


if __name__ == "__main__":
    run(log="--log" in sys.argv)
