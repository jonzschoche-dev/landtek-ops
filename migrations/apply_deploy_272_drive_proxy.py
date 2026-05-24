#!/usr/bin/env python3
"""Deploy 272 - Drive proxy through leo.hayuma.org/files/c/<doc_id>.

User report (May 25): 3 of 5 Drive links not accessible when tapped from
Telegram, despite identical permissions on all 5 (anyone/writer + Jonathan
owner). Cause: Telegram in-app browser handles Drive's preview UI
inconsistently and sometimes loses the Google session.

Structural fix: Stop relying on drive.google.com URLs. Add a leo-tools
endpoint /files/c/<doc_id> that streams the PDF directly from disk OR from
Drive (via the service account that already has read access). Nginx route
already pre-wired; no auth needed.

This deploy:
  1. (already shipped via separate file)  Flask blueprint leo_tools/files_public.py
  2. (this script)
     a. Backfill documents.drive_link to use https://leo.hayuma.org/files/c/<id>
        for every doc that has a drive_file_id OR a file_path
     b. Update leo_tools API query_documents / cross_reference / party so
        the drive_link returned to Leo is the proxy URL (handled by the
        backfill in (a) — the SQL just returns whatever's in drive_link)
     c. Restart leo-tools so the new blueprint loads
     d. Smoke test that the proxy works for doc#481 (one of the broken ones)
     e. Re-sync workflow_history defensively
"""
import json
import subprocess
import sys
import urllib.request

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
PROXY_BASE = "https://leo.hayuma.org/files/c"


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET LOCAL app.actor = 'jonathan_deploy_272'")

    print("Deploy 272 - Drive proxy via leo.hayuma.org/files/c/")
    print("=" * 60)

    # 1. Backfill drive_link
    cur.execute(f"""
        UPDATE documents
           SET drive_link = '{PROXY_BASE}/' || id::text
         WHERE (drive_file_id IS NOT NULL OR file_path IS NOT NULL)
           AND (drive_link IS NULL
                OR drive_link = ''
                OR drive_link NOT LIKE '{PROXY_BASE}/%')
    """)
    print(f"  drive_link backfilled to proxy URL: {cur.rowcount} rows")

    # Inventory by case_file
    cur.execute("""
        SELECT case_file,
               COUNT(*) FILTER (WHERE drive_link LIKE %s) AS proxy_link,
               COUNT(*) FILTER (WHERE drive_link IS NOT NULL AND drive_link NOT LIKE %s) AS other_link,
               COUNT(*) AS total
          FROM documents WHERE case_file IS NOT NULL
         GROUP BY case_file ORDER BY case_file
    """, (PROXY_BASE + "/%", PROXY_BASE + "/%"))
    print("\n  Inventory:")
    for r in cur.fetchall():
        print(f"    {r['case_file']:<14} proxy={r['proxy_link']:>3}  other={r['other_link']:>3}  total={r['total']}")

    conn.commit()
    cur.close()
    conn.close()

    # 2. Restart leo-tools to load the new blueprint
    print("\n  Restarting leo-tools to load files_public blueprint...")
    r = subprocess.run(["systemctl", "restart", "leo-tools"], capture_output=True, text=True)
    print(f"  rc={r.returncode}")
    if r.stderr.strip():
        print(f"    {r.stderr.strip()[:200]}")

    import time as _t
    _t.sleep(3)

    # 3. Test the proxy works for a known doc
    print("\n  Probe proxy for doc#481 (one of the previously-broken ones)...")
    try:
        with urllib.request.urlopen(f"http://localhost:8765/files/c/481/info", timeout=10) as resp:
            data = json.loads(resp.read())
            print(f"  info OK: {data.get('original_filename') or data.get('smart_filename')} "
                  f"drive_file_id={data.get('drive_file_id')[:14] if data.get('drive_file_id') else None}...")
    except Exception as e:
        print(f"  info FAIL: {type(e).__name__}: {e}")
        sys.exit(1)

    try:
        req = urllib.request.Request(f"http://localhost:8765/files/c/481", method="GET")
        with urllib.request.urlopen(req, timeout=30) as resp:
            content_type = resp.headers.get("Content-Type", "")
            body_len = 0
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                body_len += len(chunk)
            print(f"  PROXY OK: status={resp.status} content-type={content_type} bytes={body_len:,}")
    except Exception as e:
        print(f"  PROXY FAIL: {type(e).__name__}: {e}")
        sys.exit(1)

    # 4. Re-sync workflow_history defensively (not strictly needed but cheap)
    r = subprocess.run(["python3", "/root/landtek/scripts/sync_telegram_webhook.py"],
                       capture_output=True, text=True)
    print(f"\n  webhook re-register: {(r.stdout.split(chr(10))[-2] if r.stdout else '').strip()}")

    print("\n  smoke...")
    r = subprocess.run(["python3", "/root/landtek/scripts/post_deploy_smoke.py"],
                       capture_output=True, text=True)
    print("  " + r.stdout.strip().replace("\n", "\n  "))


if __name__ == "__main__":
    main()
