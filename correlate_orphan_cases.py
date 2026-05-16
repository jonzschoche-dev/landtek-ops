#!/usr/bin/env python3
"""Correlate orphan documents to cases via keyword scoring (deploy_117).

For each document with NULL or empty case_file:
  - Score against each case's keyword set (count × weight)
  - Assign case_file if winning score is dominant (margin >= 2)
  - Else mark as 'unknown' (manual review needed)

Each correlation logs to audit (which keywords matched).
"""
import argparse
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
MIN_MARGIN = 2.0  # winner must beat runner-up by this much
MIN_WINNER_SCORE = 2.0  # winner must hit at least this many points


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Load keywords grouped by case
    cur.execute("SELECT case_file, keyword, weight FROM case_keywords WHERE case_file != 'Owner'")
    keywords_by_case = {}
    for r in cur.fetchall():
        keywords_by_case.setdefault(r["case_file"], []).append(
            (r["keyword"], float(r["weight"]))
        )
    print(f"  loaded keywords for {len(keywords_by_case)} cases")

    # Fetch orphans
    sql = """
        SELECT id, smart_filename, LEFT(extracted_text, 30000) AS text
          FROM documents
         WHERE (case_file IS NULL OR case_file = '' OR case_file = 'unknown' OR case_file = 'Unknown')
           AND extracted_text IS NOT NULL
           AND length(extracted_text) >= 200
         ORDER BY id
    """
    if args.limit:
        sql += f" LIMIT {args.limit}"
    cur.execute(sql)
    orphans = cur.fetchall()
    print(f"  {len(orphans)} orphan candidates")

    stats = {"assigned": 0, "ambiguous": 0, "no_match": 0}
    by_case = {}
    for d in orphans:
        text_lower = (d["text"] or "").lower()
        scores = {}
        hits_by_case = {}
        for case, kws in keywords_by_case.items():
            score = 0.0
            hits = []
            for kw, weight in kws:
                cnt = text_lower.count(kw.lower())
                if cnt > 0:
                    score += cnt * weight
                    hits.append(f"{kw}({cnt})")
            if score > 0:
                scores[case] = score
                hits_by_case[case] = hits

        if not scores:
            stats["no_match"] += 1
            if args.dry_run:
                print(f"  ⊘ #{d['id']} no keyword match")
            continue

        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        winner, w_score = ranked[0]
        runner_score = ranked[1][1] if len(ranked) > 1 else 0

        if w_score < MIN_WINNER_SCORE or (w_score - runner_score) < MIN_MARGIN:
            stats["ambiguous"] += 1
            if args.dry_run:
                print(f"  ? #{d['id']} ambiguous: {ranked}")
            continue

        if args.dry_run:
            print(f"  ✓ #{d['id']} → {winner} (score={w_score:.1f}, hits: {', '.join(hits_by_case[winner][:5])})")
        else:
            cur.execute("""
                UPDATE documents
                   SET case_file = %s,
                       updated_at = now()
                 WHERE id = %s
            """, (winner, d["id"]))
        stats["assigned"] += 1
        by_case[winner] = by_case.get(winner, 0) + 1

    print(f"\n  Summary:")
    print(f"    assigned:  {stats['assigned']}")
    print(f"    ambiguous: {stats['ambiguous']}")
    print(f"    no_match:  {stats['no_match']}")
    if by_case:
        print(f"  By case:")
        for c, n in sorted(by_case.items(), key=lambda x: -x[1]):
            print(f"    {c}: {n}")

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
