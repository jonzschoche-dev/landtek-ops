#!/usr/bin/env python3
"""Stage the SP 2680 (guardianship, RTC Br. 41 Daet) backfill. Read-only on sources; writes only
ops/SP2680_BACKFILL_MANIFEST.csv and an OCR cache in ops/sp2680_ocr_cache/<sha256>.txt.
Rules only (regex/keywords); tesseract for OCR. No DB writes. Loading is a separate reviewed step
"""
import csv, os, re, subprocess, sys, datetime
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ocr_once import sha256, extract_text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.expanduser('~')
CACHE = os.path.join(ROOT, 'ops', 'sp2680_ocr_cache')
OUT = os.path.join(ROOT, 'ops', 'SP2680_BACKFILL_MANIFEST.csv')
CUTOFF = datetime.datetime(2026, 7, 15).timestamp()
IMG = ('.jpg', '.jpeg', '.png', '.heic')
DOC = ('.pdf', '.md', '.txt', '.docx') + IMG
IMAGE_DIRS = [os.path.join(HOME, p) for p in ('Documents/ViberDownloads', 'Downloads', 'Desktop', 'Pictures',
              'Library/CloudStorage/GoogleDrive-jonathan@hayuma.org/My Drive/LANDTEK ')]

CASE_TERMS = {'2680': r'(?<!\d)2680(?!\d)', 'guardianship': r'guardianship', 'spec_proc': r'spec(?:ial)?\.?\s*proc',
              'branch41': r'branch\s*(?:no\.?\s*)?41|br\.\s*41'}
PERSON_TERMS = {'hoppe': r'hoppe', 'gerry': r'\bgerry\b'}
KIND_RULES = [('receipt', r'official\s+receipt|o\.\s?r\.\s*no|\breceipt\b'),
              ('order', r'\bO\s?R\s?D\s?E\s?R\b|so\s+ordered'),
              ('notice', r'\bnotice\b|notice\s+of\s+hearing|subpoena'),
              ('pleading', r'\bmotion\b|\bpetition\b|\bmanifestation\b|\bcomment\b|\bopposition\b|\bcompliance\b'),
              ('letter_received', r'\bdear\b|\brespectfully\s+yours\b|\bsincerely\b|\bhonorable\b.*\bjudge\b|\bletter\b')]
OR_RE = re.compile(r'(?:O\.?\s?R\.?|official\s+receipt)\s*(?:no\.?|number|#)\s*[:.]?\s*([A-Z]?\d[\d\- ]{3,12}\d)', re.I)
AMT_RE = re.compile(r'(?:P|PHP|Php|₱)\s?(\d{1,3}(?:,\d{3})+(?:\.\d{2})?|\d+\.\d{2})')
MONTHS = 'jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec'
DATE_RES = [re.compile(r'(\d{4})-(\d{2})-(\d{2})'),
            re.compile(rf'\b({MONTHS})[a-z]*\.?\s+(\d{{1,2}}),?\s+(20\d\d)', re.I),
            re.compile(rf'\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?({MONTHS})[a-z]*,?\s+(20\d\d)', re.I)]

def date_guess(t):
    for i, r in enumerate(DATE_RES):
        m = r.search(t)
        if not m: continue
        try:
            if i == 0: return datetime.date(int(m[1]), int(m[2]), int(m[3])).isoformat()
            if i == 1: mo, d, y = m[1], m[2], m[3]
            else: d, mo, y = m[1], m[2], m[3]
            return datetime.date(int(y), MONTHS.split('|').index(mo[:3].lower()) + 1, int(d)).isoformat()
        except ValueError: pass
    return ''

def text_for(path):
    if path.lower().endswith('.docx'):
        try: return subprocess.run(['textutil', '-convert', 'txt', '-stdout', path], capture_output=True, text=True, timeout=60).stdout, '', None
        except Exception: return '', '', None
    h = sha256(path); c = os.path.join(CACHE, h + '.txt')
    if os.path.exists(c): return open(c, errors='replace').read(), h, 'cache'
    t, _ = extract_text(path)
    with open(c, 'w') as f: f.write(t)
    return t, h, 'new'

def candidates():
    seen = set()
    for dp, dn, fn in os.walk(os.path.join(ROOT, 'case_work')):
        for f in fn:
            if f.lower().endswith(DOC): yield os.path.join(dp, f), 'case_work'
    for d in IMAGE_DIRS:
        for dp, dn, fn in os.walk(d):
            for f in fn:
                p = os.path.join(dp, f)
                if f.lower().endswith(IMG) and os.path.getmtime(p) > CUTOFF and p not in seen:
                    seen.add(p); yield p, 'post15jul_image'

def analyse(item):
    path, src = item
    try: text, h, _ = text_for(path)
    except Exception as e: return None
    if not h: h = sha256(path)
    hay = os.path.basename(path) + '\n' + text
    case_hits = [k for k, r in CASE_TERMS.items() if re.search(r, hay, re.I)]
    person = [k for k, r in PERSON_TERMS.items() if re.search(r, hay, re.I)]
    kind = next((k for k, r in KIND_RULES if re.search(r, text[:4000], re.I)), 'filing')
    or_no = amt = ''
    if kind == 'receipt':
        m = OR_RE.search(text); or_no = re.sub(r'\s', '', m[1]) if m else ''
        a = AMT_RE.findall(text); amt = a[0].replace(',', '') if a else ''
    return dict(path=path, source=src, sha256=h, kind_guess=kind, doc_date_guess=date_guess(text[:3000]),
                hoppe_hit=int(bool(person)), case_match=int(bool(case_hits)), or_no=or_no, amount=amt,
                matched_terms=';'.join(case_hits + person), text_chars=len(text.strip()),
                first_line=' '.join(text.split())[:140])

def main():
    os.makedirs(CACHE, exist_ok=True)
    items = list(candidates()); print(f'scanning {len(items)} files', file=sys.stderr)
    with ThreadPoolExecutor(6) as ex: rows = [r for r in ex.map(analyse, items) if r]
    keep = [r for r in rows if r['matched_terms'] or (r['source'] == 'post15jul_image' and r['kind_guess'] == 'receipt')]
    with open(OUT, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(keep[0].keys()) if keep else ['path']); w.writeheader(); w.writerows(keep)
    print(f'scanned={len(rows)} manifest_rows={len(keep)} -> {OUT}', file=sys.stderr)

if __name__ == '__main__':
    main()
