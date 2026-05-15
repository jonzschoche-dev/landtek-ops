#!/usr/bin/env python3
import os, sys, requests, json
from pathlib import Path
sys.path.insert(0, '/root/landtek')
from leo_rich_metadata_ingestion import ingest_document

GEMINI_KEY = os.environ['GEMINI_API_KEY']
QDRANT_URL = 'https://6ac62f30-e965-4b10-84f2-ce95caa09a4d.australia-southeast1-0.gcp.cloud.qdrant.io'
QDRANT_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIiwic3ViamVjdCI6ImFwaS1rZXk6N2Y3ZTQwMmEtZDczYy00ODZiLTgwODgtYzgwZmQ0YjI5YTg2In0.gqi506r3NMyVGcpFczFAltFcfbkMKEcINsNj-Fl_geg'
COLLECTION = 'landtek_documents'

def embed(text):
    r = requests.post(
        f'https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={GEMINI_KEY}',
        json={'model':'models/gemini-embedding-001','content':{'parts':[{'text':text[:8000]}]},'outputDimensionality':768},
        timeout=30)
    r.raise_for_status()
    return r.json()['embedding']['values']

def upsert(point_id, vector, payload):
    import hashlib
    int_id = int(hashlib.md5(point_id.encode()).hexdigest()[:8], 16)
    requests.put(f'{QDRANT_URL}/collections/{COLLECTION}/points',
        headers={'api-key':QDRANT_KEY,'Content-Type':'application/json'},
        json={'points':[{'id':int_id,'vector':vector,'payload':payload}]},
        timeout=30).raise_for_status()

def process(pdf_path, case_id=None):
    print(f'\nProcessing: {pdf_path}')
    payloads = ingest_document(pdf_path, case_id)
    for p in payloads:
        text = p['payload'].get('text','')
        if not text: continue
        vec = embed(text)
        upsert(p['id'], vec, p['payload'])
        print(f"  ✓ {p['payload'].get('chunk_section','?')} → Qdrant")
    print(f'  Done: {len(payloads)} chunks')

if __name__ == '__main__':
    import time
    inbox = Path('/root/landtek/inbox')
    pdfs = list(inbox.glob('*.pdf')) + list(inbox.glob('*.PDF'))
    print(f'Found {len(pdfs)} PDFs')
    for pdf in pdfs:
        try: process(str(pdf))
        except Exception as e: print(f'  FAILED: {e}')
        time.sleep(1)

    # Verify
    r = requests.get(f'{QDRANT_URL}/collections/{COLLECTION}',
        headers={'api-key':QDRANT_KEY})
    print(f'\nQdrant points: {r.json()["result"]["points_count"]}')
