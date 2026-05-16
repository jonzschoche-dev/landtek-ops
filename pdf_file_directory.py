#!/usr/bin/env python3
"""Master file directory + integrity scorecard (deploy_117-D).

Shows every file the system tracks:
  - Where it lives (DB record / local / Drive)
  - How it's accessed (per role)
  - Integrity status (extracted? hashed? case-correlated?)
  - Per-case breakdown

Output: PDF + summary stats.
"""
import argparse, os, sys
from datetime import datetime, timezone
import psycopg2, psycopg2.extras
from weasyprint import HTML

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
UPLOADS = "/root/landtek/uploads"


def fmt(n):
    try: return f"{int(n):,}"
    except: return str(n)


def fetch(cur, sql, params=()):
    cur.execute(sql, params); return cur.fetchall()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default=None)
    ap.add_argument("--out", default="/root/landtek/reports/file_directory.pdf")
    ap.add_argument("--send-tg", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Integrity scorecard
    cur.execute("""
        SELECT
          count(*) AS total,
          count(drive_file_id) AS has_drive,
          count(content_hash) AS has_hash,
          count(*) FILTER (WHERE extracted_text IS NOT NULL AND length(extracted_text) >= 200) AS has_text,
          count(*) FILTER (WHERE case_file IS NOT NULL AND case_file <> '' AND case_file NOT IN ('unknown','Unknown')) AS has_case,
          count(*) FILTER (WHERE execution_status IS NOT NULL AND execution_status <> 'unknown') AS has_exec_status,
          count(*) FILTER (WHERE classification IS NOT NULL AND classification <> '') AS has_classification
        FROM documents
    """)
    s = cur.fetchone()
    pct = lambda n, t=s["total"]: f"{(n/t*100):.0f}%" if t else "—"

    # Local file count
    local_count = sum(1 for _ in os.walk(UPLOADS) for _ in _ if _ != UPLOADS) if os.path.exists(UPLOADS) else 0
    local_files = 0
    for root, _, files in os.walk(UPLOADS):
        local_files += len(files)

    # Per-case breakdown
    cases = fetch(cur, """
        SELECT case_file,
               count(*) AS total,
               count(drive_file_id) AS has_drive,
               count(*) FILTER (WHERE extracted_text IS NOT NULL AND length(extracted_text) >= 200) AS has_text,
               count(*) FILTER (WHERE execution_status IS NOT NULL AND execution_status <> 'unknown') AS has_exec
          FROM documents
         WHERE case_file IS NOT NULL AND case_file <> ''
         GROUP BY case_file
         ORDER BY count(*) DESC
    """)

    # Classification breakdown
    classifications = fetch(cur, """
        SELECT classification, count(*) AS n
          FROM documents
         WHERE classification IS NOT NULL AND classification <> ''
         GROUP BY classification ORDER BY count(*) DESC LIMIT 25
    """)

    # Execution-status breakdown
    exec_statuses = fetch(cur, """
        SELECT execution_status, count(*) AS n
          FROM documents
         WHERE execution_status IS NOT NULL
         GROUP BY execution_status ORDER BY count(*) DESC
    """)

    # Channel-users (who can access what)
    channel_users = fetch(cur, """
        SELECT cu.display_name, cu.channel_user_id, c.name AS channel,
               cu.role, cu.approved_role, cu.approved_scope_case, cu.onboarding_state
          FROM channel_users cu JOIN channels c ON c.id = cu.channel_id
         ORDER BY cu.role, cu.last_seen_at DESC NULLS LAST
    """)

    # Per-case file listing (limited for body — appendix for full)
    per_case_files = None
    if args.case:
        per_case_files = fetch(cur, """
            SELECT id, smart_filename, classification, execution_status,
                   drive_file_id IS NOT NULL AS on_drive,
                   length(extracted_text) >= 200 AS extracted,
                   text_length, doc_date, created_at
              FROM documents WHERE case_file=%s
             ORDER BY created_at DESC, id DESC LIMIT 100
        """, (args.case,))

    cur.close(); conn.close()

    # Build HTML
    html = f"""<!DOCTYPE html><html><head><style>
    @page {{ size: A4; margin: 18mm 14mm; }}
    body {{ font-family: Helvetica, Arial, sans-serif; font-size: 10pt; color: #1a1a1a; }}
    h1 {{ color: #0a3d62; font-size: 22pt; margin: 0; }}
    h2 {{ color: #0a3d62; font-size: 14pt; border-bottom: 2px solid #0a3d62; padding-bottom: 4px; margin-top: 22px; }}
    h3 {{ color: #2c3e50; font-size: 11pt; margin-top: 14px; }}
    .subtitle {{ color: #7f8c8d; font-size: 10pt; margin-bottom: 16px; }}
    .stat {{ display: inline-block; padding: 8px 12px; background: #f5f8fb; border-left: 3px solid #0a3d62; min-width: 28%; margin: 4px 6px 4px 0; vertical-align: top; }}
    .stat-label {{ color: #586e7a; font-size: 8.5pt; text-transform: uppercase; }}
    .stat-value {{ font-size: 14pt; font-weight: 600; color: #0a3d62; }}
    .stat-sub {{ font-size: 8pt; color: #95a5a6; }}
    table {{ width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 9pt; }}
    th {{ background: #e8eef4; text-align: left; padding: 5px 7px; border-bottom: 1.5px solid #0a3d62; }}
    td {{ padding: 4px 7px; border-bottom: 1px solid #eee; }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .ok {{ color: #27ae60; }}
    .miss {{ color: #c0392b; }}
    .tag {{ display: inline-block; padding: 1px 5px; background: #e8eef4; color: #0a3d62; border-radius: 3px; font-size: 8pt; font-family: monospace; }}
    .pagebreak {{ page-break-before: always; }}
    </style></head><body>
<h1>LandTek Master File Directory</h1>
<div class="subtitle">Generated {now} · {'Case-scoped: ' + args.case if args.case else 'All cases'}</div>

<h2>Integrity scorecard ({fmt(s['total'])} indexed documents)</h2>
<div class="stat"><div class="stat-label">On Google Drive</div>
  <div class="stat-value">{pct(s['has_drive'])}</div>
  <div class="stat-sub">{fmt(s['has_drive'])} have drive_file_id</div></div>
<div class="stat"><div class="stat-label">Hashed (dedup-ready)</div>
  <div class="stat-value">{pct(s['has_hash'])}</div>
  <div class="stat-sub">{fmt(s['has_hash'])} have content_hash</div></div>
<div class="stat"><div class="stat-label">Extracted text</div>
  <div class="stat-value">{pct(s['has_text'])}</div>
  <div class="stat-sub">{fmt(s['has_text'])} have OCR'd text ≥200 chars</div></div>
<br>
<div class="stat"><div class="stat-label">Case-correlated</div>
  <div class="stat-value">{pct(s['has_case'])}</div>
  <div class="stat-sub">{fmt(s['has_case'])} have a case_file</div></div>
<div class="stat"><div class="stat-label">Execution-classified</div>
  <div class="stat-value">{pct(s['has_exec_status'])}</div>
  <div class="stat-sub">{fmt(s['has_exec_status'])} have notarized/filed/draft/etc.</div></div>
<div class="stat"><div class="stat-label">Doc-type classified</div>
  <div class="stat-value">{pct(s['has_classification'])}</div>
  <div class="stat-sub">{fmt(s['has_classification'])} have classification</div></div>

<h2>Storage locations</h2>
<table><tr><th>Location</th><th>What lives there</th><th>Access pattern</th><th>Count</th></tr>
<tr><td><b>Postgres <code class='tag'>documents</code> table</b></td>
    <td>Source-of-truth metadata index — id, drive_file_id, content_hash, extracted_text, case_file, classification, execution_status</td>
    <td>Internal Leo operations + REST API consumers (with API key)</td>
    <td class='num'>{fmt(s['total'])}</td></tr>
<tr><td><b>Local <code class='tag'>/root/landtek/uploads/</code></b></td>
    <td>Files downloaded for OCR / processing</td>
    <td>Internal scripts only — not directly served</td>
    <td class='num'>{fmt(local_files)}</td></tr>
<tr><td><b>Google Drive</b></td>
    <td>Master file store · LANDTEK shared folder<br>(folder ID 1BMnZL7LWoH9tWq0C9RdCTaAQBGhtL8CP)</td>
    <td>Jonathan + service account · clients via shared sub-folder (their case only)</td>
    <td class='num'>{fmt(s['has_drive'])}</td></tr>
<tr><td><b>Qdrant vector index</b></td>
    <td>Semantic embeddings for RAG retrieval (landtek_documents collection)</td>
    <td>Leo's truth_negotiator + chat path</td>
    <td class='num'>≈942 vectors</td></tr>
</table>

<h2>Per-case breakdown</h2>
<table><thead><tr><th>Case</th><th class='num'>Total</th><th class='num'>On Drive</th><th class='num'>Extracted</th><th class='num'>Exec-status</th></tr></thead><tbody>
"""
    for c in cases:
        html += f"<tr><td><b>{c['case_file']}</b></td><td class='num'>{fmt(c['total'])}</td><td class='num'>{fmt(c['has_drive'])}</td><td class='num'>{fmt(c['has_text'])}</td><td class='num'>{fmt(c['has_exec'])}</td></tr>"
    html += "</tbody></table>"

    html += "<h2>Document classification breakdown</h2><table><thead><tr><th>Classification</th><th class='num'>Count</th></tr></thead><tbody>"
    for c in classifications:
        html += f"<tr><td>{c['classification']}</td><td class='num'>{fmt(c['n'])}</td></tr>"
    html += "</tbody></table>"

    html += "<h2>Execution status distribution</h2>"
    html += "<div style='color:#586e7a; font-size:9pt; margin-bottom:6px'><i>Per truth_negotiator discipline: drafts never cited as fact; emails citable for fact-of-communication only; notarized + filed + government-issued have full legal force.</i></div>"
    html += "<table><thead><tr><th>Status</th><th class='num'>Count</th><th>Citation policy</th></tr></thead><tbody>"
    POLICY = {
        "executed_notarized":   "✓ Full legal force [V·N]",
        "executed_filed":       "✓ Full legal force [V·F]",
        "executed_signed_only": "✓ With caveat [V·S]",
        "government_issued":    "✓ Full legal force [V·G]",
        "email_sent":           "○ Communication only [V·E]",
        "email_received":       "○ Communication only [V·R]",
        "draft_unsigned":       "✗ NEVER citable as fact [D]",
        "template":             "✗ Not citable [?]",
        "unknown":              "? Pending classification",
    }
    for r in exec_statuses:
        policy = POLICY.get(r['execution_status'], "?")
        html += f"<tr><td><span class='tag'>{r['execution_status']}</span></td><td class='num'>{fmt(r['n'])}</td><td>{policy}</td></tr>"
    html += "</tbody></table>"

    html += "<h2>Channel users + their access scope</h2>"
    html += "<table><thead><tr><th>Name</th><th>Channel</th><th>Role</th><th>State</th><th>Scope (case)</th></tr></thead><tbody>"
    for u in channel_users:
        html += f"<tr><td>{u['display_name'] or '—'}<br><span class='tag'>{u['channel_user_id']}</span></td><td>{u['channel']}</td><td>{u['approved_role'] or u['role'] or '—'}</td><td>{u['onboarding_state']}</td><td>{u['approved_scope_case'] or '<i>all (operator)</i>' if (u['approved_role'] or '') == 'operator' else (u['approved_scope_case'] or '<i>(not scoped)</i>')}</td></tr>"
    html += "</tbody></table>"

    if per_case_files:
        html += f'<div class="pagebreak"></div><h2>Case <code class="tag">{args.case}</code> — file listing (latest 100)</h2>'
        html += "<table><thead><tr><th>ID</th><th>Filename</th><th>Class</th><th>Exec status</th><th>Drive</th><th>Extracted</th></tr></thead><tbody>"
        for f in per_case_files:
            drive = "✓" if f["on_drive"] else "✗"
            ext = "✓" if f["extracted"] else "✗"
            html += f"<tr><td>#{f['id']}</td><td>{(f['smart_filename'] or '—')[:80]}</td><td>{f['classification'] or '—'}</td><td><span class='tag'>{f['execution_status'] or 'unknown'}</span></td><td>{drive}</td><td>{ext}</td></tr>"
        html += "</tbody></table>"

    html += "</body></html>"

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    HTML(string=html).write_pdf(args.out)
    print(f"  ✓ wrote {args.out} ({os.path.getsize(args.out):,} bytes)")

    if args.send_tg:
        import requests
        env = {}
        with open("/root/landtek/.env") as f:
            for l in f:
                if "=" in l and not l.startswith("#"):
                    k, _, v = l.strip().partition("="); env[k.strip()] = v.strip()
        caption = f"📂 LandTek Master File Directory" + (f" — {args.case}" if args.case else "")
        with open(args.out, "rb") as f:
            r = requests.post(
                f"https://api.telegram.org/bot{env['TELEGRAM_BOT_TOKEN']}/sendDocument",
                data={"chat_id": "6513067717", "caption": caption},
                files={"document": (os.path.basename(args.out), f, "application/pdf")},
                timeout=30,
            )
        print(f"  TG: {r.status_code}")


if __name__ == "__main__":
    main()
