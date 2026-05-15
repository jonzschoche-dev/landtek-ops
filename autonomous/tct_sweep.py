#!/usr/bin/env python3
"""tct_sweep.py — accuracy-first single-pass extraction with gemini-2.5-flash only."""
import os, sys, time, io, json, re, psycopg2
from psycopg2.extras import Json
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

DAILY_BUDGET_CENTS = 1000   # $10/day, accuracy-first not speed
COOLDOWN_HOURS_ON_429 = 4
QUALITY_THRESHOLD = 0.8     # accuracy-first; reverted from temporary 0.6 — discriminator showed 0.8 IS reachable (doc 10 hit 1.000)
MODEL = 'gemini-2.5-flash'  # only this model — no downgrade
PG = 'postgresql://n8n:n8npassword@172.18.0.3:5432/n8n'
CRITICAL_FIELDS = ['title_number','registered_owners','previous_title_numbers','area_sqm','lot_block_plan']

KEYS = [(lbl, os.environ.get(lbl)) for lbl in ['GEMINI_API_KEY','GEMINI_API_KEY_FALLBACK']]
KEYS = [k for k in KEYS if k[1]]
if not KEYS: sys.exit(0)

conn = psycopg2.connect(PG); cur = conn.cursor()

def pick_key():
    cur.execute("""SELECT key_label FROM gemini_key_state
                    WHERE (cooldown_until IS NULL OR cooldown_until < NOW())
                    ORDER BY COALESCE(last_429_at, '1970-01-01') ASC LIMIT 1""")
    row = cur.fetchone()
    if not row: return None
    label = row[0]
    for lbl, val in KEYS:
        if lbl == label: return (lbl, val)
    return None

active = pick_key()
if not active:
    print("all keys in cooldown — waiting"); sys.exit(0)
KEY_LABEL, KEY = active
print(f"key: {KEY_LABEL} | model: {MODEL}")
genai.configure(api_key=KEY)

cur.execute("""SELECT COALESCE(SUM(cost_cents),0) FROM extraction_runs
                WHERE completed_at > NOW() - INTERVAL '24 hours' AND status='completed'""")
spent = float(cur.fetchone()[0] or 0)
if spent >= DAILY_BUDGET_CENTS:
    print(f"budget exhausted: ${spent/100:.2f}"); sys.exit(0)

# Pick a doc — prefer ones never tried, then ones with only 1 pass (for cross-validation)
cur.execute("""
    SELECT q.doc_id, d.drive_file_id, d.smart_filename,
           (SELECT COUNT(*) FROM extraction_runs er
              WHERE er.doc_id=q.doc_id AND er.status='completed'
                AND er.model LIKE 'gemini-2.5-flash%') AS pass_count
      FROM heightened_ocr_queue q JOIN documents d ON d.id=q.doc_id
     WHERE q.case_file='MWK-001' AND d.drive_file_id IS NOT NULL
       AND COALESCE(q.fail_count,0) < 3
       AND (q.status='queued' OR
            (q.status='completed'
             AND (SELECT COUNT(*) FROM extraction_runs er
                    WHERE er.doc_id=q.doc_id AND er.status='completed'
                      AND er.model LIKE 'gemini-2.5-flash%') < 2))
     ORDER BY pass_count ASC, q.priority ASC, q.id ASC LIMIT 1
""")
row = cur.fetchone()
if not row:
    print("nothing to extract"); sys.exit(0)
doc_id, drive_id, fname, existing_passes = row
pass_num = (existing_passes or 0) + 1
print(f"doc {doc_id} ({fname}) — pass {pass_num}")

SAFETY = {HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
          HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
          HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
          HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE}
SYSTEM = "You are a forensic OCR analyst for Philippine land documents."
PROMPT = open('/root/landtek/heightened_ocr/prompt_tct_v3_canonical.txt').read()
model = genai.GenerativeModel(MODEL, safety_settings=SAFETY, system_instruction=SYSTEM)

cur.execute("""INSERT INTO extraction_runs (doc_id, model, status, extraction_pass)
                VALUES (%s,%s,'running',%s) RETURNING id""",
            (doc_id, f'{MODEL} / {KEY_LABEL} / pass{pass_num}', pass_num))
run_id = cur.fetchone()[0]; conn.commit()

try:
    t0 = time.time()
    creds = service_account.Credentials.from_service_account_file(
        '/root/landtek/google-creds.json',
        scopes=['https://www.googleapis.com/auth/drive.readonly'])
    drive = build('drive','v3', credentials=creds)
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, drive.files().get_media(fileId=drive_id))
    done = False
    while not done: _, done = dl.next_chunk()
    buf.seek(0)
    gf = genai.upload_file(io.BytesIO(buf.read()), display_name=fname, mime_type='application/pdf')
    while gf.state.name == 'PROCESSING':
        time.sleep(2); gf = genai.get_file(gf.name)
    resp = model.generate_content([PROMPT, gf],
        generation_config={'temperature':0,'max_output_tokens':65536})
    text = ''.join(p.text for p in resp.candidates[0].content.parts if hasattr(p,'text'))
    text = text.strip()
    for fence in ['```json','```']:
        if text.startswith(fence):
            text = text[len(fence):].lstrip()
            if text.endswith('```'): text = text[:-3].rstrip()
            break
    result = json.loads(text)

    # Quality score on the 9 EXPECTED fields, using actual tct_v3_canonical paths.
    def _status_ok(obj):
        return (isinstance(obj, dict)
                and obj.get('field_status') == 'extracted'
                and obj.get('source_quote'))
    def _array_ok(arr):
        return isinstance(arr, list) and len(arr) > 0

    th = result.get('title_header') or {}
    td = result.get('technical_description') or {}
    hist = result.get('title_history') or {}

    EXPECTED_CHECKS = [
        ('title_number',                  _status_ok(th.get('title_number'))),
        ('registered_owners',             _array_ok(result.get('registered_owners'))),
        ('previous_title_numbers',        _array_ok(hist.get('previous_title_numbers'))),
        ('date_of_original_registration', _status_ok(th.get('date_of_original_registration'))),
        ('registry_of_deeds_full',        _status_ok(th.get('registry_of_deeds_full'))),
        ('area_sqm',                      _status_ok(td.get('area_sqm'))),
        ('location',                      bool((td.get('location') or {}).get('municipality')
                                              or (td.get('location') or {}).get('province'))),
        ('lot_block_plan',                _status_ok(td.get('lot_block_plan'))),
        ('survey_plan_psd',               _status_ok(th.get('survey_plan_psd'))),
    ]
    extracted_ok = sum(1 for _, ok in EXPECTED_CHECKS if ok)
    q_score = round(extracted_ok / len(EXPECTED_CHECKS), 3)
    q_decision = 'accept' if q_score >= QUALITY_THRESHOLD else 're_extract'

    tct_val = (th.get('title_number') or {}).get('value')
    cur.execute("""UPDATE extraction_runs SET completed_at=NOW(), status='completed',
                      latency_ms=%s, cost_cents=0.5, raw_json=%s,
                      quality_score=%s, quality_decision=%s
                    WHERE id=%s""",
                (int((time.time()-t0)*1000), Json(result), q_score, q_decision, run_id))
    cur.execute("UPDATE gemini_key_state SET last_success_at=NOW() WHERE key_label=%s", (KEY_LABEL,))
    print(f"  ✓ pass {pass_num}: quality={q_score} → {q_decision}")

    # If accept AND pass 1, leave queue 'queued' so pass 2 happens
    # If accept AND pass 2, mark queue completed + run cross-validation
    # If re_extract, leave queue 'queued' for another try
    if q_decision == 'accept':
        if pass_num == 1:
            cur.execute("UPDATE heightened_ocr_queue SET status='queued' WHERE doc_id=%s", (doc_id,))
            print(f"  → kept queued for cross-validation pass 2")
        elif pass_num >= 2:
            # Cross-validate critical fields against pass 1
            cur.execute("""SELECT raw_json FROM extraction_runs
                            WHERE doc_id=%s AND status='completed' AND quality_decision='accept'
                            ORDER BY id LIMIT 2""", (doc_id,))
            rows = cur.fetchall()
            if len(rows) >= 2:
                p1, p2 = (rows[0][0] if isinstance(rows[0][0],dict) else json.loads(rows[0][0])), \
                          (rows[1][0] if isinstance(rows[1][0],dict) else json.loads(rows[1][0]))
                def get_field(d, f):
                    """Resolve CRITICAL_FIELD to (value, source_quote) using actual contract paths."""
                    th = d.get('title_header') or {}
                    td = d.get('technical_description') or {}
                    hist = d.get('title_history') or {}
                    if f == 'title_number':
                        v = th.get('title_number') or {}
                        return (v.get('value'), v.get('source_quote'))
                    if f == 'registered_owners':
                        ros = d.get('registered_owners') or []
                        names = sorted({(o.get('full_legal_name') or '').strip()
                                        for o in ros if o.get('full_legal_name')})
                        return (' | '.join(names) if names else None, None)
                    if f == 'previous_title_numbers':
                        arr = (hist.get('previous_title_numbers') or [])
                        return (' | '.join(sorted(set(arr))) if arr else None,
                                (hist.get('source_quote') if isinstance(hist, dict) else None))
                    if f == 'area_sqm':
                        v = td.get('area_sqm') or {}
                        return (str(v.get('value')) if v.get('value') is not None else None,
                                v.get('source_quote'))
                    if f == 'lot_block_plan':
                        v = td.get('lot_block_plan') or {}
                        return (v.get('value'), v.get('source_quote'))
                    return (None, None)
                def normalize(s):
                    if not s: return ''
                    return re.sub(r'\s+',' ',str(s).lower().strip())[:200]

                agreed = 0
                for f in CRITICAL_FIELDS:
                    v1, q1 = get_field(p1, f)
                    v2, q2 = get_field(p2, f)
                    if normalize(v1) == normalize(v2):
                        agreement = 'identical'
                        promoted = True
                    elif v1 and v2 and (normalize(v1) in normalize(v2) or normalize(v2) in normalize(v1)):
                        agreement = 'normalized_match'
                        promoted = True
                    else:
                        agreement = 'disagreement'
                        promoted = False
                    cur.execute("""INSERT INTO field_consensus
                        (doc_id, tct_number, field_name, pass1_value, pass1_quote, pass2_value, pass2_quote,
                         agreement, promoted_to_verified, decided_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                       ON CONFLICT (doc_id, field_name) DO UPDATE SET
                         pass1_value=EXCLUDED.pass1_value, pass2_value=EXCLUDED.pass2_value,
                         agreement=EXCLUDED.agreement, promoted_to_verified=EXCLUDED.promoted_to_verified,
                         decided_at=NOW()""",
                       (doc_id, tct_val, f, v1, q1, v2, q2, agreement, promoted))
                    if promoted:
                        # promote the relevant extraction_chunks
                        cur.execute("""UPDATE extraction_chunks
                                          SET provenance_level='verified',
                                              verified_by='cross_validated', verified_at=NOW()
                                        WHERE doc_id=%s AND field_name=%s""", (doc_id, f))
                        agreed += 1
                cur.execute("""UPDATE extraction_runs SET cross_validated=TRUE WHERE id=%s""", (run_id,))
                cur.execute("UPDATE heightened_ocr_queue SET status='completed', completed_at=NOW() WHERE doc_id=%s",
                            (doc_id,))
                print(f"  ✓ cross-validation: {agreed}/{len(CRITICAL_FIELDS)} critical fields agreed → verified")
            else:
                cur.execute("UPDATE heightened_ocr_queue SET status='completed', completed_at=NOW() WHERE doc_id=%s",
                            (doc_id,))
    else:
        cur.execute("""UPDATE heightened_ocr_queue SET status='queued', last_error=%s WHERE doc_id=%s""",
                    (f'quality {q_score} below {QUALITY_THRESHOLD}', doc_id))
    conn.commit()
except Exception as e:
    err_str = str(e).lower()
    is_quota = '429' in err_str or 'quota' in err_str
    is_perm_denied = '403' in err_str or 'permission_denied' in err_str or 'service_disabled' in err_str
    if is_quota or is_perm_denied:
        # API-level fault (key, not doc) — cool the key, do NOT bump doc fail_count
        cool_hours = COOLDOWN_HOURS_ON_429 if is_quota else 24  # 403 needs human intervention
        reason = '429 quota' if is_quota else '403 PERMISSION_DENIED (likely API disabled on key project)'
        cur.execute("""UPDATE gemini_key_state
                        SET last_429_at=NOW(), cooldown_until=NOW() + (%s || ' hours')::interval,
                            notes=%s
                        WHERE key_label=%s""", (cool_hours, reason, KEY_LABEL))
        cur.execute("UPDATE extraction_runs SET status='failed', error=%s, completed_at=NOW() WHERE id=%s",
                    (f'{reason} — key {KEY_LABEL} cooled {cool_hours}h', run_id))
        print(f"  ⏸ {reason} on {KEY_LABEL} — {cool_hours}h cooldown")
    else:
        cur.execute("UPDATE extraction_runs SET status='failed', error=%s, completed_at=NOW() WHERE id=%s",
                    (str(e)[:300], run_id))
        cur.execute("""UPDATE heightened_ocr_queue
                          SET fail_count=COALESCE(fail_count,0)+1, last_error=%s
                        WHERE doc_id=%s""", (str(e)[:300], doc_id))
        cur.execute("""UPDATE heightened_ocr_queue SET status='requires_heightened_ocr'
                        WHERE doc_id=%s AND fail_count >= 3""", (doc_id,))
        print(f"  ✗ FAILED: {str(e)[:150]}")
    conn.commit()
cur.close(); conn.close()
