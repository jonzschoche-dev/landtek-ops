#!/usr/bin/env python3
"""Deploy 119 — ARTA case roster + chart from gmail_messages."""
import psycopg2, psycopg2.extras, re
DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

SQL = r"""
CREATE TABLE IF NOT EXISTS arta_cases (
  id              serial PRIMARY KEY,
  ctn_no          text UNIQUE NOT NULL,
  case_file       text,
  matter_code     text,
  status          text DEFAULT 'active',   -- 'active','resolved','withdrawn','referred','dismissed'
  filed_date      date,
  last_activity   date,
  respondents     text[],
  subject_summary text,
  email_count     integer DEFAULT 0,
  attachment_count integer DEFAULT 0,
  next_deadline   date,
  next_action     text,
  notes           text,
  created_at      timestamptz DEFAULT now(),
  updated_at      timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_arta_status ON arta_cases(status);
"""

def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(SQL)

    # Find all distinct CTN numbers across emails + docs
    cur.execute("""
        SELECT body_plain || ' ' || COALESCE(subject,'') AS text,
               received_at::date AS d, has_attachments
          FROM gmail_messages
         WHERE body_plain ~ 'CTN\s*SL' OR subject ~ 'CTN\s*SL'
    """)
    rows = cur.fetchall()

    by_ctn = {}
    for r in rows:
        for m in re.finditer(r"(CTN\s*SL[\-\s]*\d{4}[\-\s]*\d{4}[\-\s]*\d{4})", r["text"], re.IGNORECASE):
            ctn = re.sub(r"\s+", " ", m.group(1)).strip().upper()
            ctn = re.sub(r"CTN\s+SL[\-\s]+", "CTN SL-", ctn).replace(" ", "-").replace("CTN-SL-", "CTN SL-")
            # Normalize to "CTN SL-YYYY-MMDD-NNNN"
            ctn = re.sub(r"CTN[\-\s]+SL[\-\s]+", "CTN SL-", ctn)
            d = by_ctn.setdefault(ctn, {"emails": 0, "attachments": 0, "earliest": None, "latest": None})
            d["emails"] += 1
            if r["has_attachments"]:
                d["attachments"] += 1
            if r["d"]:
                if not d["earliest"] or r["d"] < d["earliest"]: d["earliest"] = r["d"]
                if not d["latest"]   or r["d"] > d["latest"]:   d["latest"] = r["d"]

    print(f"  found {len(by_ctn)} distinct ARTA cases in inbox\n")
    for ctn, info in sorted(by_ctn.items()):
        print(f"  {ctn:30s}  {info['emails']:>3} emails  {info['attachments']:>3} w/ attach  "
              f"{info['earliest']} → {info['latest']}")

        # Upsert
        cur.execute("""
            INSERT INTO arta_cases (ctn_no, case_file, status, filed_date, last_activity,
                                     email_count, attachment_count)
            VALUES (%s, 'MWK-001', 'active', %s, %s, %s, %s)
            ON CONFLICT (ctn_no) DO UPDATE SET
              last_activity = EXCLUDED.last_activity,
              email_count = EXCLUDED.email_count,
              attachment_count = EXCLUDED.attachment_count,
              updated_at = now()
        """, (ctn, info["earliest"], info["latest"], info["emails"], info["attachments"]))

    # Also link the existing matter MWK-ARTA-DILG
    cur.execute("""
        UPDATE arta_cases SET matter_code = 'MWK-ARTA-DILG'
         WHERE ctn_no = 'CTN SL-2026-0423-1891'
    """)

    cur.execute("SELECT count(*) AS n, status FROM arta_cases GROUP BY status")
    print(f"\n  arta_cases summary:")
    for r in cur.fetchall():
        print(f"    {r['status']}: {r['n']}")

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
