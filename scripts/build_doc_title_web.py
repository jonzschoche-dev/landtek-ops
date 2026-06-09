#!/usr/bin/env python3
"""Phase A of the forensic connectivity web: link every document to the TITLE(s)
it cites. Deterministic + exact — matches only the 62 KNOWN tct_numbers, with
word boundaries (so 'T-4497' never matches inside 'T-44971'). No LLM, no guessing,
no rate-limit. This is the navigable backbone: 'every document that touches T-4497'."""
import re
import psycopg2, psycopg2.extras

conn = psycopg2.connect("postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
conn.autocommit = True
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

cur.execute("""
    CREATE TABLE IF NOT EXISTS document_titles (
        id serial PRIMARY KEY,
        doc_id int NOT NULL,
        tct_number text NOT NULL,
        mentions int DEFAULT 1,
        source text DEFAULT 'text_mining',
        created_at timestamptz DEFAULT now(),
        UNIQUE (doc_id, tct_number)
    )
""")
# rebuild the text-mined links cleanly
cur.execute("DELETE FROM document_titles WHERE source='text_mining'")

cur.execute("SELECT tct_number FROM titles WHERE tct_number IS NOT NULL")
titles = [r["tct_number"] for r in cur.fetchall()]
print(f"matching against {len(titles)} known titles...")

total_links = 0
for t in titles:
    # exact, boundary-guarded: preceded by non-alnum/start, followed by non-digit/end
    pat = r'(^|[^A-Za-z0-9])' + re.escape(t) + r'([^0-9]|$)'
    cur.execute("""
        INSERT INTO document_titles (doc_id, tct_number, mentions, source)
        SELECT id, %s,
               (SELECT count(*) FROM regexp_matches(extracted_text, %s, 'g')),
               'text_mining'
          FROM documents
         WHERE master_form='digital' AND extracted_text ~ %s
        ON CONFLICT (doc_id, tct_number) DO NOTHING
    """, (t, pat, pat))
    total_links += cur.rowcount

print(f"created {total_links} doc->title links")
cur.execute("SELECT count(DISTINCT doc_id) FROM document_titles WHERE source='text_mining'")
print("distinct documents now title-linked:", cur.fetchone()["count"])
print("\n=== top title hubs (docs per title) ===")
cur.execute("""SELECT tct_number, count(*) docs FROM document_titles
               WHERE source='text_mining' GROUP BY tct_number ORDER BY 2 DESC LIMIT 10""")
for r in cur.fetchall():
    print(f"  {r['tct_number']}: {r['docs']} docs")
print("\n=== sample: documents touching T-4497 ===")
cur.execute("""SELECT d.id, LEFT(COALESCE(d.smart_filename,d.original_filename),48) nm
               FROM document_titles dt JOIN documents d ON d.id=dt.doc_id
               WHERE dt.tct_number='T-4497' ORDER BY dt.mentions DESC LIMIT 6""")
for r in cur.fetchall():
    print(f"  doc#{r['id']}: {r['nm']}")
cur.close(); conn.close()
print("done")
