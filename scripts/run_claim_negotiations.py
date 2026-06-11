#!/usr/bin/env python3
"""Run the truth_negotiator over every case claim and persist the verdict, so the
truth layer (verified / uncertain / refuted + citations) is queryable per claim and
shown on the evidence matrix. This is the case's indisputable-data foundation."""
import json, re, subprocess
import psycopg2, psycopg2.extras

conn = psycopg2.connect("postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
conn.autocommit = True
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

cur.execute("""CREATE TABLE IF NOT EXISTS claim_truth_verdicts (
    claim_id int PRIMARY KEY,
    verdict text, citation_tag text, evidence_count int, negotiation_id int,
    checked_at timestamptz DEFAULT now())""")

cur.execute("SELECT id, short_label, claim_text FROM claims ORDER BY priority DESC NULLS LAST, id")
for r in cur.fetchall():
    try:
        out = subprocess.run(
            ["python3", "truth_negotiator.py", "--claim", r["claim_text"],
             "--case", "MWK-001", "--user", "system"],
            capture_output=True, text=True, timeout=200, cwd="/root/landtek").stdout
        m = re.search(r"\{.*\}", out, re.S)
        j = json.loads(m.group(0)) if m else {}
    except Exception as e:
        print(f"claim {r['id']} [{r['short_label']}]: ERROR {type(e).__name__}")
        continue
    cur.execute("""INSERT INTO claim_truth_verdicts
        (claim_id, verdict, citation_tag, evidence_count, negotiation_id)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (claim_id) DO UPDATE SET verdict=excluded.verdict,
          citation_tag=excluded.citation_tag, evidence_count=excluded.evidence_count,
          negotiation_id=excluded.negotiation_id, checked_at=now()""",
        (r["id"], j.get("verdict"), j.get("citation_tag"),
         j.get("evidence_count"), j.get("id")))
    print(f"claim {r['id']} [{r['short_label']}]: {j.get('verdict')}  {j.get('citation_tag')}  ({j.get('evidence_count')} backers)")
cur.close(); conn.close()
