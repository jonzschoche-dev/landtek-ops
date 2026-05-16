#!/usr/bin/env python3
"""Continuous learning — deploy_095.

Daily check: for each case_file, count documents added since the last
intelligence synthesis. If ≥5 new docs, re-run educate_leo to refresh
the brief + entities.

Ensures Leo's knowledge of each client stays current as new docs arrive.

Idempotent. Runs even if no work to do (just exits silently).
"""
import os
import subprocess
import sys
from datetime import datetime, timezone
import psycopg2
import psycopg2.extras

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")
EDUCATE_PATH = "/root/landtek/educate_leo.py"
MIN_NEW_DOCS = 5  # threshold for re-run


def main():
    conn = psycopg2.connect(**DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT c.case_file, c.name, c.intelligence_updated_at,
               (SELECT count(*) FROM documents d
                 WHERE d.case_file = c.case_file
                   AND length(coalesce(d.extracted_text,'')) > 200
                   AND (c.intelligence_updated_at IS NULL OR d.timestamp > c.intelligence_updated_at))
                 AS new_docs
          FROM clients c
         WHERE c.case_file IS NOT NULL AND c.case_file != ''
         ORDER BY c.case_file;
    """)
    cases = cur.fetchall()
    cur.close(); conn.close()

    triggered = []
    skipped = []
    for c in cases:
        case = c["case_file"]
        new = c["new_docs"] or 0
        last = c["intelligence_updated_at"]
        last_str = last.strftime('%Y-%m-%d') if last else 'never'
        if new >= MIN_NEW_DOCS or last is None:
            print(f"  → {case}: {new} new docs since {last_str} — triggering educate_leo")
            triggered.append(case)
            try:
                subprocess.run(
                    ["python3", EDUCATE_PATH, "--case", case, "--commit-clients-update"],
                    timeout=3600, check=False,
                    stdout=open(f"/var/log/landtek_continuous_{case}.log", "a"),
                    stderr=subprocess.STDOUT,
                )
            except Exception as e:
                print(f"    FAILED: {e}")
        else:
            print(f"  ✓ {case}: {new} new docs since {last_str} — under threshold, skip")
            skipped.append(case)

    print(f"\n  triggered: {len(triggered)} cases ({triggered}), skipped: {len(skipped)}")


if __name__ == "__main__":
    main()
