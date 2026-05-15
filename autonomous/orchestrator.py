#!/usr/bin/env python3
"""
orchestrator.py — runs the deterministic phases of the 48-hr plan.
No LLM judgment. Just the work that can be scripted.
"""
import os, sys, json, re, psycopg2, subprocess
from datetime import datetime, timezone
from psycopg2.extras import Json

PG = 'postgresql://n8n:n8npassword@172.18.0.3:5432/n8n'
PENDING = '/root/landtek/notifications/pending.txt'
BLOCKED = '/root/landtek/notifications/blocked.txt'
LOG_PREFIX = f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}]"

def log(msg, also_pending=False):
    line = f"{LOG_PREFIX} {msg}"
    print(line, flush=True)
    if also_pending:
        with open(PENDING, 'a') as f: f.write(line + '\n')

def block(reason):
    with open(BLOCKED, 'a') as f: f.write(f"{LOG_PREFIX} HALT: {reason}\n")
    log(f"BLOCKED: {reason}", also_pending=True)
    sys.exit(1)

# Hard stop: spend cap
try:
    conn = psycopg2.connect(PG, connect_timeout=5)
except Exception as e:
    log(f"PG unreachable: {e}")
    sys.exit(1)
cur = conn.cursor()
cur.execute("""SELECT COALESCE(SUM(cost_cents),0) FROM extraction_runs
                WHERE completed_at > NOW() - INTERVAL '24 hours' AND status='completed'""")
spent = float(cur.fetchone()[0] or 0)
if spent > 1000:  # $10/day
    block(f"spend cap exceeded: ${spent/100:.2f}/day")

log(f"orchestrator cycle starting — spend last 24h: ${spent/100:.4f}")

# --- PHASE A: re-queue failed extractions younger than 1 hour ---
MAX_FAILURES = 3
cur.execute("""SELECT DISTINCT doc_id FROM extraction_runs
                WHERE status='failed' AND completed_at > NOW() - INTERVAL '1 hour'
                  AND NOT EXISTS (SELECT 1 FROM extraction_runs er2
                                    WHERE er2.doc_id=extraction_runs.doc_id
                                      AND er2.status='completed')
                  AND (SELECT COUNT(*) FROM extraction_runs er3
                         WHERE er3.doc_id=extraction_runs.doc_id
                           AND er3.status='failed') < %s
                ORDER BY doc_id LIMIT 10""", (MAX_FAILURES,))
to_retry = [r[0] for r in cur.fetchall()]
if to_retry:
    cur.execute("""UPDATE heightened_ocr_queue SET status='queued'
                    WHERE doc_id = ANY(%s) AND status != 'completed'""", (to_retry,))
    conn.commit()
    log(f"PHASE A re-queued {len(to_retry)} failed extractions for retry: {to_retry}", also_pending=True)
else:
    log("PHASE A no failures to retry")

# --- PHASE B: source-quote verifier ---
# For each completed extraction not yet validated, check if quote appears in extracted_text
cur.execute("""SELECT ec.id, ec.doc_id, ec.tct_number, ec.field_name, ec.quote_text, d.extracted_text
                 FROM extraction_chunks ec
                 JOIN documents d ON d.id = ec.doc_id
                WHERE ec.field_status='extracted'
                  AND ec.provenance_level='inferred_strong'
                  AND ec.quote_text IS NOT NULL
                  AND length(ec.quote_text) > 10
                  AND ec.created_at > NOW() - INTERVAL '24 hours'
                ORDER BY ec.id DESC LIMIT 100""")
candidates = cur.fetchall()

def normalize(s):
    if not s: return ''
    return re.sub(r'\s+', ' ', s.lower()).strip()

promoted = 0
for chunk_id, doc_id, tct, field, quote, text in candidates:
    nq = normalize(quote)[:80]  # first 80 chars
    nt = normalize(text or '')
    if len(nq) >= 15 and nq in nt:
        cur.execute("""UPDATE extraction_chunks SET provenance_level='verified',
                          verified_by='source_quote_match', verified_at=NOW()
                        WHERE id=%s""", (chunk_id,))
        promoted += 1
    # Also tolerant match: first 5 distinctive words
    elif len(nq) >= 15:
        first_words = ' '.join(nq.split()[:5])
        if first_words and first_words in nt:
            cur.execute("""UPDATE extraction_chunks SET provenance_level='verified',
                              verified_by='partial_quote_match', verified_at=NOW()
                            WHERE id=%s""", (chunk_id,))
            promoted += 1
conn.commit()
log(f"PHASE B verifier: scanned {len(candidates)} chunks, promoted {promoted}",
    also_pending=(promoted > 0))


# --- PHASE B-prime: consensus-to-tables promotion ---
# Pick up any field_consensus rows promoted since last run and propagate them
# into titles / chain_of_title / title_chain / extraction_chunks. Mirrors the
# logic in deploy_136 backfill. Idempotent via ON CONFLICT.
cur.execute("""
  WITH promoted_recent AS (
    SELECT id FROM field_consensus
     WHERE promoted_to_verified=true
       AND COALESCE(decided_at, NOW()) > NOW() - INTERVAL '2 hours'
  ),
  upd_chunks AS (
    INSERT INTO extraction_chunks
      (doc_id, tct_number, chunk_type, field_name, field_status,
       quote_text, structured_value, provenance_level, verified_by, verified_at)
    SELECT fc.doc_id, fc.tct_number, 'cross_validated_field', fc.field_name,
           'extracted',
           COALESCE(fc.pass2_quote, fc.pass1_quote, ''),
           jsonb_build_object('pass1_value', fc.pass1_value,
                              'pass2_value', fc.pass2_value,
                              'agreement',   fc.agreement,
                              'consensus_id', fc.id),
           'verified', 'cross_validated', fc.decided_at
      FROM field_consensus fc
     WHERE fc.id IN (SELECT id FROM promoted_recent)
    ON CONFLICT (doc_id, chunk_type, field_name) DO UPDATE
      SET provenance_level='verified', verified_by='cross_validated',
          verified_at=EXCLUDED.verified_at,
          quote_text=EXCLUDED.quote_text, structured_value=EXCLUDED.structured_value
    RETURNING 1
  )
  SELECT COUNT(*) FROM upd_chunks;
""")
n = cur.fetchone()[0] or 0
log(f"PHASE B-prime: promoted {n} new field_consensus rows into extraction_chunks", also_pending=(n>0))
conn.commit()

# --- PHASE C: current state snapshot ---
cur.execute("""SELECT
  (SELECT COUNT(*) FROM heightened_ocr_queue WHERE status='queued' AND case_file='MWK-001'),
  (SELECT COUNT(*) FROM extraction_runs WHERE status='completed'),
  (SELECT COUNT(*) FROM extraction_chunks WHERE provenance_level='verified'),
  (SELECT COUNT(*) FROM extraction_chunks),
  (SELECT to_char(MAX(completed_at), 'HH24:MI:SS')
     FROM extraction_runs WHERE status='completed')""")
queued, done_runs, ver_chunks, total_chunks, last_done = cur.fetchone()
log(f"STATE: queued={queued}  completed={done_runs}  verified={ver_chunks}/{total_chunks}  last_done={last_done}",
    also_pending=True)

cur.close(); conn.close()
log("orchestrator cycle complete")
