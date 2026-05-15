#!/usr/bin/env python3
"""
daily_digest.py — composes 7AM Manila daily status digest and posts to Telegram.
Read-only against the database. No destructive ops.
"""
import os, sys, json, psycopg2, requests
from datetime import datetime, timezone, timedelta

PG = 'postgresql://n8n:n8npassword@172.18.0.3:5432/n8n'

def load_env():
    env = {}
    if os.path.exists('/root/landtek/.env'):
        for line in open('/root/landtek/.env'):
            if '=' in line and not line.startswith('#'):
                k,v = line.strip().split('=',1)
                env[k] = v.strip('"').strip("'")
    return env

env = load_env()
TG_TOKEN = env.get('TELEGRAM_BOT_TOKEN', '')
CHAT_ID = env.get('TELEGRAM_CHAT_ID', '')
if not (TG_TOKEN and CHAT_ID):
    print(f"missing telegram config — TG_TOKEN={bool(TG_TOKEN)} CHAT_ID={CHAT_ID}", file=sys.stderr)
    # Continue and just print digest

conn = psycopg2.connect(PG); cur = conn.cursor()
cur.execute("SELECT NOW()"); now = cur.fetchone()[0]
manila = now + timedelta(hours=8)
lines = [f"🌅 LandTek Digest — {manila.strftime('%a %d %b %Y, %H:%M Manila')}", ""]

# Counts
cur.execute("SELECT (SELECT COUNT(*) FROM documents WHERE case_file='MWK-001'),"
            "(SELECT COUNT(*) FROM extraction_chunks WHERE field_status='extracted'),"
            "(SELECT COUNT(*) FROM instruments_on_title),"
            "(SELECT COUNT(*) FROM fraud_indicators),"
            "(SELECT COUNT(*) FROM gmail_messages),"
            "(SELECT COUNT(*) FROM titles WHERE provenance_level='verified'),"
            "(SELECT COUNT(*) FROM heightened_ocr_queue WHERE status='queued'),"
            "(SELECT COUNT(*) FROM heightened_ocr_queue WHERE status='completed')")
docs, chunks, instr, fraud, gmail, verified, queued, done = cur.fetchone()
lines.append(f"📚 docs: {docs}    🧩 chunks: {chunks}")
lines.append(f"📜 instruments: {instr}    ⚠️ fraud_flags: {fraud}")
lines.append(f"📧 gmail: {gmail}    ✓ verified_titles: {verified}")
lines.append(f"🎯 TCT queue: {queued} queued / {done} done")
lines.append("")

# Yesterday's extractions
cur.execute("SELECT COUNT(*), ROUND(SUM(cost_cents)::numeric,2) FROM extraction_runs"
            " WHERE completed_at > NOW() - INTERVAL '24 hours' AND status='completed'")
r,c = cur.fetchone()
lines.append(f"📊 last 24h: {r} extractions, ~${(c or 0)/100:.2f} spent")

# Errors
cur.execute("SELECT COUNT(*) FROM extraction_runs WHERE status='failed' AND completed_at > NOW() - INTERVAL '24 hours'")
errs = cur.fetchone()[0]
if errs: lines.append(f"⚠️ extraction errors (24h): {errs}")

# Top missing evidence
cur.execute("""SELECT transferee, COUNT(*) FROM evidence_action_list
                WHERE priority>=4 GROUP BY transferee ORDER BY 2 DESC LIMIT 5""")
top = cur.fetchall()
if top:
    lines.append(""); lines.append("🚨 most-incomplete transferees (need CTC/CNR):")
    for t,n in top: lines.append(f"   {t}: {n} docs missing")

# Recent Gmail
cur.execute("""SELECT received_at::date, LEFT(subject,60) FROM gmail_messages
                ORDER BY received_at DESC LIMIT 3""")
g = cur.fetchall()
if g:
    lines.append(""); lines.append("📬 recent case emails:")
    for d,s in g: lines.append(f"   {d}: {s}")

cur.close(); conn.close()

msg = "\n".join(lines)
print(msg)

if TG_TOKEN and CHAT_ID:
    r = requests.post(f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage',
                      json={'chat_id': CHAT_ID, 'text': msg, 'disable_web_page_preview': True})
    print(f"telegram: {r.status_code}", file=sys.stderr)
