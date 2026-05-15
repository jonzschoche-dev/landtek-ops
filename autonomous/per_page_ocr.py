#!/usr/bin/env python3
"""Per-page Gemini OCR fallback for outsized docs that fail full-doc extraction.

Usage: python3 per_page_ocr.py <doc_id>

Splits the source PDF (already on disk under /root/landtek/per_page_work/<doc_id>/)
into per-page PDFs (already done by pdfseparate). For each page, calls Gemini with
the tct_v3_canonical contract scoped to "what is visible on THIS page only".
Stores resulting chunks in extraction_chunks tagged with page_ref='page N' and
field_name suffixed with the page number to avoid UNIQUE collisions.
"""
import os, sys, io, json, time, glob, re, psycopg2
from psycopg2.extras import Json
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

if len(sys.argv) < 2: sys.exit('usage: per_page_ocr.py <doc_id>')
DOC_ID = int(sys.argv[1])
WORK_DIR = f'/root/landtek/per_page_work/{DOC_ID}'
PG = 'postgresql://n8n:n8npassword@172.18.0.3:5432/n8n'
MODEL = 'gemini-2.5-flash'

KEY = os.environ.get('GEMINI_API_KEY_FALLBACK') or os.environ.get('GEMINI_API_KEY')
if not KEY: sys.exit('no GEMINI_API_KEY in env')
genai.configure(api_key=KEY)

PAGE_PROMPT_PREFIX = """You are reading PAGE {page_n} of {total} from a Philippine TCT.
Extract ONLY content VISIBLE on THIS SINGLE PAGE. For any contract field whose
content is on a different page, emit field_status="not_present".
The encumbrance entries (memorandum_of_encumbrances) array should contain ONLY
entries whose entry-marker block appears on this page (PE-XXX header + body).

Otherwise follow the same schema and quoting rules as the full-doc contract below.

---
"""

SAFETY = {HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
          HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
          HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
          HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE}
SYSTEM = "You are a forensic OCR analyst for Philippine land documents."
BASE_PROMPT = open('/root/landtek/heightened_ocr/prompt_tct_v3_canonical.txt').read()
model = genai.GenerativeModel(MODEL, safety_settings=SAFETY, system_instruction=SYSTEM)

pages = sorted(glob.glob(f'{WORK_DIR}/page-*.pdf'),
               key=lambda p: int(re.search(r'page-(\d+)\.pdf', p).group(1)))
if not pages: sys.exit(f'no page-*.pdf files in {WORK_DIR}')
total = len(pages)
print(f'doc {DOC_ID}: {total} pages')

conn = psycopg2.connect(PG); cur = conn.cursor()
cur.execute("""INSERT INTO extraction_runs (doc_id, model, status, extraction_pass)
               VALUES (%s,%s,'running',1) RETURNING id""",
            (DOC_ID, f'{MODEL} / per_page_split({total}p)'))
run_id = cur.fetchone()[0]; conn.commit()

t0 = time.time()
total_chunks = 0
parsed_pages = 0
per_page_payloads = {}

try:
    for idx, page_path in enumerate(pages):
        page_n = int(re.search(r'page-(\d+)\.pdf', page_path).group(1))
        if idx > 0:
            # Pace BEFORE each call (not after) — free tier ~20 req/min, leave headroom
            time.sleep(8)
        print(f'  page {page_n}/{total}: uploading…')
        gf = genai.upload_file(page_path,
              display_name=f'doc{DOC_ID}_page{page_n}.pdf',
              mime_type='application/pdf')
        while gf.state.name == 'PROCESSING':
            time.sleep(2); gf = genai.get_file(gf.name)
        prompt = PAGE_PROMPT_PREFIX.format(page_n=page_n, total=total) + BASE_PROMPT
        try:
            resp = model.generate_content([prompt, gf],
                generation_config={'temperature': 0, 'max_output_tokens': 32768})
        except Exception as e:
            print(f'  page {page_n}: API exception — {str(e)[:120]}')
            continue
        text = ''.join(p.text for p in resp.candidates[0].content.parts if hasattr(p, 'text')).strip()
        for fence in ['```json', '```']:
            if text.startswith(fence):
                text = text[len(fence):].lstrip()
                if text.endswith('```'): text = text[:-3].rstrip()
                break
        try:
            result = json.loads(text)
        except Exception as e:
            print(f'  page {page_n}: JSON parse failed — {str(e)[:80]}; saving raw text chunk')
            cur.execute("""INSERT INTO extraction_chunks
                            (doc_id, extraction_run_id, chunk_type, field_name, field_status,
                             quote_text, structured_value, page_ref, provenance_level)
                           VALUES (%s,%s,'per_page_raw',%s,'partial',%s,%s,%s,'inferred_weak')
                           ON CONFLICT (doc_id, chunk_type, field_name) DO UPDATE
                              SET quote_text=EXCLUDED.quote_text,
                                  structured_value=EXCLUDED.structured_value""",
                        (DOC_ID, run_id, f'page_{page_n}_raw',
                         text[:5000], Json({'raw_text': text[:50000]}), f'page {page_n}'))
            conn.commit()
            continue

        per_page_payloads[page_n] = result
        parsed_pages += 1

        # Title header (only emit if this page has it)
        th = result.get('title_header') or {}
        if th and any((isinstance(v, dict) and v.get('field_status') == 'extracted') for v in th.values()):
            ro = result.get('registered_owners') or []
            payload = {
                'title_number': (th.get('title_number') or {}).get('value'),
                'survey_plan_psd': (th.get('survey_plan_psd') or {}).get('value'),
                'registry_of_deeds': (th.get('registry_of_deeds_full') or {}).get('value'),
                'date_of_original_registration': (th.get('date_of_original_registration') or {}).get('value'),
                'owners': ro,
            }
            tct_val = payload['title_number']
            quote = ((th.get('title_number') or {}).get('source_quote') or '')[:1000]
            cur.execute("""INSERT INTO extraction_chunks
                            (doc_id, extraction_run_id, tct_number, chunk_type, field_name,
                             field_status, quote_text, structured_value, page_ref, provenance_level)
                           VALUES (%s,%s,%s,'title_header_and_owners',%s,'extracted',%s,%s,%s,'inferred_strong')
                           ON CONFLICT (doc_id, chunk_type, field_name) DO UPDATE
                              SET quote_text=EXCLUDED.quote_text,
                                  structured_value=EXCLUDED.structured_value,
                                  tct_number=COALESCE(EXCLUDED.tct_number, extraction_chunks.tct_number)""",
                        (DOC_ID, run_id, tct_val,
                         f'header_summary_p{page_n}', quote, Json(payload), f'page {page_n}'))
            total_chunks += 1

        # Per-encumbrance entries
        encs = result.get('memorandum_of_encumbrances') or []
        for e in encs:
            pe = (e.get('pe_number') or '').strip() or f'<no_pe_p{page_n}_{encs.index(e)}>'
            field_name = f'{pe}_p{page_n}' if pe.startswith('<') else pe
            quote = (e.get('source_quote') or '')[:1000]
            tct_val = (th.get('title_number') or {}).get('value')
            cur.execute("""INSERT INTO extraction_chunks
                            (doc_id, extraction_run_id, tct_number, chunk_type, field_name,
                             field_status, quote_text, structured_value, page_ref, provenance_level)
                           VALUES (%s,%s,%s,'per_encumbrance',%s,'extracted',%s,%s,%s,'inferred_strong')
                           ON CONFLICT (doc_id, chunk_type, field_name) DO UPDATE
                              SET quote_text=EXCLUDED.quote_text,
                                  structured_value=EXCLUDED.structured_value,
                                  page_ref=EXCLUDED.page_ref""",
                        (DOC_ID, run_id, tct_val, field_name, quote, Json(e), f'page {page_n}'))
            total_chunks += 1

        # Technical description fragment (if visible on this page)
        td = result.get('technical_description') or {}
        ft = (td.get('full_text') or {})
        if isinstance(ft, dict) and ft.get('field_status') == 'extracted' and ft.get('value'):
            cur.execute("""INSERT INTO extraction_chunks
                            (doc_id, extraction_run_id, chunk_type, field_name,
                             field_status, quote_text, structured_value, page_ref, provenance_level)
                           VALUES (%s,%s,'technical_description',%s,'extracted',%s,%s,%s,'inferred_strong')
                           ON CONFLICT (doc_id, chunk_type, field_name) DO UPDATE
                              SET quote_text=EXCLUDED.quote_text,
                                  structured_value=EXCLUDED.structured_value""",
                        (DOC_ID, run_id, f'tech_desc_p{page_n}',
                         (ft.get('source_quote') or '')[:1000], Json(td), f'page {page_n}'))
            total_chunks += 1

        # Fraud indicators on this page
        for i, fi in enumerate(result.get('fraud_indicators') or []):
            cur.execute("""INSERT INTO fraud_indicators (doc_id, indicator_type, severity, description, source_quote, location_on_doc)
                            VALUES (%s,%s,%s,%s,%s,%s)
                            ON CONFLICT DO NOTHING""",
                        (DOC_ID, fi.get('type','unknown'), fi.get('severity','medium'),
                         fi.get('description'), fi.get('source_quote'), fi.get('location_on_doc') or f'page {page_n}'))

        conn.commit()
        print(f'  page {page_n}: parsed OK ({total_chunks} chunks so far)')

    # Store the union of all pages as one full_text chunk (so downstream queries see one summary)
    union = {f'page_{p}': v for p, v in per_page_payloads.items()}
    cur.execute("""INSERT INTO extraction_chunks
                    (doc_id, extraction_run_id, chunk_type, field_name, field_status,
                     structured_value, provenance_level)
                   VALUES (%s,%s,'per_page_union','full_doc','extracted',%s,'inferred_strong')
                   ON CONFLICT (doc_id, chunk_type, field_name) DO UPDATE
                      SET structured_value=EXCLUDED.structured_value""",
                (DOC_ID, run_id, Json(union)))

    cur.execute("""UPDATE extraction_runs SET status='completed', completed_at=NOW(),
                      latency_ms=%s, cost_cents=%s, raw_json=%s,
                      quality_score=%s, quality_decision='per_page_split'
                    WHERE id=%s""",
                (int((time.time() - t0) * 1000), 0.5 * total, Json(union),
                 round(parsed_pages / total, 3), run_id))
    cur.execute("""UPDATE heightened_ocr_queue SET status='completed', completed_at=NOW(),
                      last_error='per_page_split: ' || %s::text || ' chunks from ' || %s::text || '/' || %s::text || ' pages'
                    WHERE doc_id=%s""",
                (total_chunks, parsed_pages, total, DOC_ID))
    conn.commit()
    print(f'\nDONE doc {DOC_ID}: {parsed_pages}/{total} pages parsed, {total_chunks} chunks, '
          f'{int((time.time()-t0))}s')
except Exception as e:
    cur.execute("UPDATE extraction_runs SET status='failed', error=%s, completed_at=NOW() WHERE id=%s",
                (str(e)[:500], run_id))
    conn.commit()
    print(f'ABORTED: {str(e)[:200]}')
finally:
    cur.close(); conn.close()
