#!/usr/bin/env python3
"""Consolidate case_work/HARVEST/HARVEST_*.txt into the master record. Deterministic, no AI.
Writes MASTER_HARVEST.md (by matter), CONFLICTS.md and FILES_INDEX.csv in case_work/HARVEST.
Usage: consolidate_harvest.py"""
import re, os, glob, csv, hashlib, datetime
REPO = os.path.expanduser('~/landtek')
H = f'{REPO}/case_work/HARVEST'
SECTIONS = ['DECISIONS MADE', 'FACTS ESTABLISHED', 'FILES CREATED OR EDITED',
            'DATES AND DEADLINES', 'OPEN ITEMS', 'CONFLICTS OR DOUBTS']
SEC_RE = re.compile(r'^\W*(?:\d\.\s*)?(' + '|'.join(SECTIONS) + r')\b', re.I)
TODAY = datetime.date.today()

# First match wins: specific dockets before broad buckets.
MATTERS = [
    ('26-360', r'26-?360|\bBalane\b|reinvindicatoria|reivindicatoria|Barandon|\bdela? ?Fuente\b|\bde la Fuente\b|T-52540|2021002126|2021002127'),
    ('SP 2680', r'\b2680\b|guardianship|\bBotor\b|\bHoppe\b'),
    ('ARTA 1321', r'\b1321\b'),
    ('ARTA 1378', r'\b1378\b'),
    ('ARTA 1212', r'\b1212\b'),
    ('ARTA (other)', r'\bARTA\b|11032'),
    ('OP', r'\bOP\b|Office of the President|050526-MRO'),
    ('LandBank CARP', r'Land ?Bank|\bLBP\b|\bCARP\b|6839|just compensation'),
    ('Lot 2-A', r'Lot\s*2-A(?![-\w])'),
    ('Inocalla / Paracale', r'Inocalla|Paracale|\bPGC\b|\bSMBC\b|NIBDC|\bAllan\b|shaker|mining|\bMPSA\b|\bFTAA\b'),
    ('MWK', r'\bMWK|Mary Worrick|Keesey|T-4497|T-3291\d|Lot 2-X|Mercedes|Ombudsman|\bheirs\b|estate'),
    ('LandTek product', r'\bLeo\b|simulator|\bn8n\b|\bdrip\b|cockpit|harness|pipeline|\.py\b|\.sh\b|deploy|LandTek|\bVPS\b|Telegram|\bhook|database|ingest|\bOCR\b|corpus|Postgres|\bDB\b|Grok|Messenger|agent'),
]
MATTERS = [(m, re.compile(p, re.I)) for m, p in MATTERS]
ORDER = [m for m, _ in MATTERS] + ['Unclassified']

def matter_of(text):
    for m, rx in MATTERS:
        if rx.search(text): return m
    return None

def load_manifest():
    last = {}
    p = f'{H}/_manifest.csv'
    if os.path.exists(p):
        for r in csv.DictReader(open(p)):
            if r.get('last_ts'): last[r['session'][:8]] = r['last_ts'][:10]
    return last

def parse(path, last):
    name = os.path.basename(path)[len('HARVEST_claude_'):-4]
    m = re.match(r'([0-9a-f]{8})_(\d{4}-\d{2}-\d{2})$', name)
    if m: sid, date = m.group(1), last.get(m.group(1), m.group(2))
    else:  # manual harvest, e.g. 26-360-DLF_2026-10
        label, _, d = name.rpartition('_')
        sid, date = 'manual:' + label, datetime.date.fromtimestamp(os.path.getmtime(path)).isoformat()
    head, sec, items = [], None, {s: [] for s in SECTIONS}
    for raw in open(path, errors='replace'):
        ln = raw.rstrip()
        hm = SEC_RE.match(ln)
        if hm:
            sec = hm.group(1).upper(); continue
        if not ln.strip(): continue
        if sec is None: head.append(ln.strip()); continue
        s = ln.strip()
        if re.match(r'^[-*•]\s+', s):
            text = re.sub(r'^[-*•]\s+', '', s)
            if raw[:1] in ' \t' and items[sec]:  # nested bullet: fold into parent
                items[sec][-1] += ' / ' + text
            else: items[sec].append(text)
        elif items[sec] and raw[:1] in ' \t': items[sec][-1] += ' ' + s
        else: items[sec].append(s)
    hdr = ' '.join(head)
    mline = next((h for h in head if h.upper().startswith('MATTERS')), hdr)
    return dict(sid=sid, date=date, head=hdr, session_matter=matter_of(mline) or matter_of(hdr), items=items, path=path)

def norm(t): return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', t.lower())).strip()

def dedupe(entries):
    """entries: list of (text, sid, date). Exact-normalized merge, then near-duplicate merge (word Jaccard >= 0.8)."""
    out = []
    for text, sid, date in sorted(entries, key=lambda e: e[2], reverse=True):
        n = norm(text); w = set(n.split())
        for o in out:
            if o['n'] == n or (len(w) >= 6 and len(w & o['w']) / len(w | o['w']) >= 0.8):
                if sid not in o['sids']: o['sids'].append(sid)
                break
        else: out.append(dict(text=text, n=n, w=w, sids=[sid], date=date))
    return out

MON = {m: i for i, m in enumerate(['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'], 1)}
DATE_RE = re.compile(r'\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?,?\s+(20\d\d)\b'
                     r'|\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s+(20\d\d)\b'
                     r'|\b(20\d\d)-(\d\d)-(\d\d)\b', re.I)
def dates_in(t):
    out = set()
    for g in DATE_RE.finditer(t):
        try:
            if g.group(1): out.add(datetime.date(int(g.group(3)), MON[g.group(2)[:3].lower()], int(g.group(1))))
            elif g.group(4): out.add(datetime.date(int(g.group(6)), MON[g.group(4)[:3].lower()], int(g.group(5))))
            else: out.add(datetime.date(int(g.group(7)), int(g.group(8)), int(g.group(9))))
        except ValueError: pass
    return out
def fmt(d): return f'{d.day} {d.strftime("%b %Y")}'

# Known current truths (Jonathan, 25 Oct 2026 job brief).
P_SET = {datetime.date(2026, 11, 4), datetime.date(2026, 11, 11), datetime.date(2026, 12, 2), datetime.date(2026, 12, 9)}
D_SET = {datetime.date(2027, 1, 13), datetime.date(2027, 2, 3), datetime.date(2027, 2, 10), datetime.date(2027, 3, 3), datetime.date(2027, 3, 10)}
SP2680_RESET = datetime.date(2026, 11, 11)
LBC_1321 = '142061372862'
HEARING = re.compile(r'hearing|setting|trial|testimon|presentation|reset|calendar|schedul', re.I)

def known_truth_checks(all_items):
    """all_items: list of (matter, section, text, sid, date). Returns list of (rule, text, sids)."""
    hits = []
    for matter, sec, t, sid, _ in all_items:
        ds = dates_in(t)
        if re.search(r'26-?360', t) and HEARING.search(t) and not re.search(r'\b2680\b', t):
            asof = dates_in(' '.join(re.findall(r'(?:as of|as at|until|since)\s+([^.;,]{0,25})', t, re.I)))
            bad = sorted(d for d in ds - asof if d >= TODAY and d not in P_SET | D_SET)
            if bad: hits.append(('26-360 setting date not in the known calendar (' + ', '.join(map(fmt, bad)) + ')', t, sid))
            tm = re.findall(r'\b(\d{1,2}:\d\d)\s*([AP]\.?M)', t, re.I)
            if any(d >= TODAY for d in ds) and [x for x in tm if x[0] != '1:30']:
                hits.append(('26-360 setting time other than 1:30 PM', t, sid))
        if re.search(r'\b2680\b', t) and re.search(r'26-?360|11 Nov', t) and re.search(r'clash|conflict|overlap|collid', t, re.I) and not re.search(r'\bno (clash|conflict)|not a clash', t, re.I):
            hits.append(('SP 2680 / 26-360 on 11 Nov flagged as a clash (known truth: NOT a clash)', t, sid))
        if re.search(r'\b2680\b', t) and HEARING.search(t):
            bad = sorted(d for d in ds if d >= TODAY and d != SP2680_RESET)
            if bad: hits.append(('SP 2680 future date other than the 11 Nov 2026 reset (' + ', '.join(map(fmt, bad)) + ')', t, sid))
        if re.search(r'\b1321\b', t):
            if re.search(r'not (yet )?(been )?filed|unfiled|to be filed|not (yet )?(been )?(sent|delivered|served)|awaiting (filing|delivery)', t, re.I):
                hits.append(('ARTA 1321 described as not filed or not delivered (known truth: filed and delivered, LBC ' + LBC_1321 + ')', t, sid))
            for lbc in re.findall(r'\b\d{12}\b', t):
                if lbc != LBC_1321 and re.search(r'LBC', t, re.I):
                    hits.append(('ARTA 1321 LBC number ' + lbc + ' differs from ' + LBC_1321, t, sid))
        if re.search(r'2021002127', t) and re.search(r'Gloria|Balane', t) and not re.search(r'\b126\b|2126|Hoppe|heirs|sibling|not (the )?Balane|misannotat', t, re.I):
            hits.append(("Gloria Balane's title given as ...127 (record: 079-2021002126; ...127 is the heirs' lot)", t, sid))
        if re.search(r'26-?360', t) and re.search(r'\bRTC\b|Regional Trial', t) and not re.search(r'\bSP\b|2156|2680|6839|Daet|Br(anch|\.) ?4[01]|complaint outline|RTC complaint|RTC_COMPLAINT|appeal', t, re.I):
            hits.append(('26-360 called an RTC case (record: Municipal Trial Court of Mercedes, Camarines Norte, per counsel-facing letters in case_work/MWK-001)', t, sid))
    return hits

EVENT = re.compile(r'\b(pre-?trial|filed|received|executed|notari[sz]ed|issued|annotated|revo(?:ked|cation)|deed of sale|SPA|order|resolution|adverse claim|died|death)\b', re.I)
KEYTOK = re.compile(r'\b(?:T-\d{3,6}|\d{2}-\d{3,4}|079-\d{10}|Entry \d{6,}|SP \d{3,4}|CV ?\d{3,5}|ARTA \d{3,4}|doc \d{2,5}|Exh\. ?[A-Z]{1,2}(?:-\d)?)\b', re.I)

def cross_session_conflicts(all_items):
    """Same (matter, identifier set, event word) stated with disjoint date sets in different sessions."""
    groups = {}
    for matter, sec, t, sid, date in all_items:
        if sec not in ('FACTS ESTABLISHED', 'DATES AND DEADLINES', 'DECISIONS MADE'): continue
        ds = {d for d in dates_in(t) if d.year >= 1900}
        ev = {e.lower().replace('-', '') for e in EVENT.findall(t)}
        ids = {k.upper().replace(' ', '') for k in KEYTOK.findall(t)}
        if len(ds) != 1 or len(ev) != 1 or not ids: continue  # only unambiguous one-date, one-event statements
        key = (matter, tuple(sorted(ids)), ev.pop())
        groups.setdefault(key, []).append((next(iter(ds)), t, sid))
    out = []
    for key, rows in groups.items():
        byd = {}
        for d, t, sid in rows: byd.setdefault(d, []).append((t, sid))
        if len(byd) > 1 and len({sid for _, _, sid in rows}) > 1:
            out.append((key, byd))
    return out

def court_variance(all_items):
    rtc = [(t, s) for m, _, t, s, _ in all_items if re.search(r'26-?360', t) and re.search(r'\bRTC\b|Regional Trial', t)]
    mtc = [(t, s) for m, _, t, s, _ in all_items if re.search(r'26-?360', t) and re.search(r'\bMTC\b|Municipal Trial', t)]
    return rtc, mtc

PATH_RE = re.compile(r'(?<![\w./-])((?:/Users/[^\s,;:()`\'"]+)|(?:[\w.-]+/)+[\w.@-]+\.[A-Za-z0-9]{1,6}|[\w.@-]+\.(?:py|sh|md|sql|txt|pdf|csv|json|geojson|qgz|html|plist|service|timer|docx|xlsx|kml|gpx|yaml|yml))(?![\w/])')

def build_files_index(sessions):
    rows = {}
    def add(p, sid, src):
        p = p.rstrip('.').rstrip(')')
        r = rows.setdefault(p, dict(sids=[], src=set()))
        if sid not in r['sids']: r['sids'].append(sid)
        r['src'].add(src)
    for s in sessions:
        for t in s['items']['FILES CREATED OR EDITED']:
            for p in PATH_RE.findall(t): add(p, s['sid'], 'harvest_text')
        dg = f'{H}/_digests/{s["sid"]}.txt'
        if os.path.exists(dg):  # ground truth: Write/Edit tool calls recorded in the transcript
            txt = open(dg, errors='replace').read()
            m = re.search(r'== FILES WRITTEN/EDITED ==\n(.*?)\n== ', txt, re.S)
            if m:
                for p in m.group(1).splitlines():
                    if p.strip(): add(p.strip(), s['sid'], 'tool_call')
    base = {}
    MEM = os.path.expanduser('~/.claude/projects/-Users-jonathanzschoche-landtek/memory')
    for root, dirs, files in [w for top in (REPO, MEM) for w in os.walk(top)]:  # no symlink follow: drive_local stays out
        dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '__pycache__', '.venv')]
        for f in files: base.setdefault(f, []).append(os.path.join(root, f))
    out = []
    for p, r in sorted(rows.items()):
        if p.startswith('/'): cands = [p]
        elif os.path.exists(os.path.join(REPO, p)): cands = [os.path.join(REPO, p)]
        else: cands = [c for c in base.get(os.path.basename(p), []) if c.endswith('/' + p)]  # path given relative to a subfolder
        resolved = cands[0] if len(cands) == 1 else ''
        exists = 'yes' if resolved and os.path.isfile(resolved) else ('dir' if resolved and os.path.isdir(resolved) else ('ambiguous' if len(cands) > 1 else 'no'))
        sha = size = ''
        if exists == 'yes':
            h = hashlib.sha256()
            with open(resolved, 'rb') as f:
                for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
            sha, size = h.hexdigest(), os.path.getsize(resolved)
        out.append([p, resolved, exists, sha, size, '+'.join(sorted(r['src'])), ' '.join(r['sids'])])
    with open(f'{H}/FILES_INDEX.csv', 'w', newline='') as f:
        w = csv.writer(f); w.writerow(['path_as_stated', 'resolved_path', 'exists', 'sha256', 'bytes', 'source', 'sessions'])
        w.writerows(out)
    return out

def main():
    last = load_manifest()
    files = sorted(glob.glob(f'{H}/HARVEST_*.txt'))
    sessions = [parse(p, last) for p in files]
    all_items = []
    for s in sessions:
        for sec in SECTIONS:
            for t in s['items'][sec]:
                if re.fullmatch(r'(none|unknown|n/?a)\.?(\s.*)?', t.strip(), re.I) and len(t) < 60: continue
                m = matter_of(t) or s['session_matter'] or 'Unclassified'
                all_items.append((m, sec, t, s['sid'], s['date']))
    stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    tag = lambda e: '[' + ', '.join(e['sids'][:6]) + (f' +{len(e["sids"]) - 6}' if len(e['sids']) > 6 else '') + ']'

    # MASTER_HARVEST.md
    L = [f'# MASTER HARVEST', '',
         f'Generated {stamp} by scripts/consolidate_harvest.py from {len(sessions)} harvest files. Deterministic; no AI in this step.',
         'Each item is an AI summary of a session transcript, tagged with its session id (newest first). It is a pointer into the record, not the record: verify against the cited source before relying on it. Items marked UNVERIFIED in a session stay UNVERIFIED here.', '']
    opens = dedupe([(t, sid, d) for m, sec, t, sid, d in all_items if sec == 'OPEN ITEMS'])
    mfor = {}
    for m, sec, t, sid, d in all_items:
        if sec == 'OPEN ITEMS': mfor.setdefault(norm(t), m)
    L += ['## Recent open items (all matters, newest session first)', '']
    for e in opens[:40]: L.append(f'- ({mfor.get(e["n"], "?")}, {e["date"]}) {e["text"]} {tag(e)}')
    L += ['', '## Sessions harvested', '']
    for s in sorted(sessions, key=lambda s: s['date'], reverse=True):
        L.append(f'- {s["sid"]} ({s["date"]}): {s["head"][:180]}')
    L.append('')
    for m in ORDER:
        mi = [x for x in all_items if x[0] == m]
        if not mi: continue
        L += [f'## {m}', '']
        for sec in SECTIONS:
            if sec == 'CONFLICTS OR DOUBTS': continue  # those go to CONFLICTS.md
            es = dedupe([(t, sid, d) for _, s2, t, sid, d in mi if s2 == sec])
            if not es: continue
            L += [f'### {sec.title()}', '']
            L += [f'- {e["text"]} {tag(e)}' for e in es]
            L.append('')
    open(f'{H}/MASTER_HARVEST.md', 'w').write('\n'.join(L).replace('—', '-'))

    # FILES_INDEX.csv
    fx = build_files_index(sessions)

    # CONFLICTS.md
    C = ['# CONFLICTS', '', f'Generated {stamp} by scripts/consolidate_harvest.py. Deterministic pattern checks; every row is a candidate for Jonathan to rule on, not a finding.', '',
         'Known current truths used (Jonathan, 25 Oct 2026): 26-360 plaintiff settings 4 Nov, 11 Nov, 2 Dec, 9 Dec 2026; defendant settings 13 Jan, 3 Feb, 10 Feb, 3 Mar, 10 Mar 2027; all 1:30 PM. SP 2680 reset to 11 Nov 2026 morning (time unconfirmed), NOT a clash with 26-360. ARTA 1321 filed and delivered under LBC 142061372862. From the record: Gloria Balane holds TCT 079-2021002126.', '']
    C += ['## A. Session statements that contradict a known current truth', '']
    kt = known_truth_checks(all_items)
    grouped = {}
    for rule, t, sid in kt: grouped.setdefault(rule, []).append((t, sid))
    if not grouped: C += ['- None found.', '']
    for rule in sorted(grouped):
        C.append(f'### {rule}'); C.append('')
        for e in dedupe([(t, sid, '') for t, sid in grouped[rule]]): C.append(f'- {e["text"]} {tag(e)}')
        C.append('')
    C += ['## B. Same event, different dates across sessions', '',
          'Grouped by matter, identifiers (title, case, entry, doc, exhibit) and event word. Only one-date, one-event statements are compared.', '']
    cs = cross_session_conflicts(all_items)
    if not cs: C += ['- None found.', '']
    for (m, ids, ev), byd in sorted(cs):
        C.append(f'### {m}: {", ".join(ids)} / {ev}')
        for d in sorted(byd):
            sids = sorted({s for _, s in byd[d]})
            C.append(f'- {fmt(d)}: "{byd[d][0][0][:220]}" [{", ".join(sids)}]')
        C.append('')
    rtc, mtc = court_variance(all_items)
    C += ['## C. Court named for 26-360', '']
    if rtc and mtc:
        C.append(f'- Sessions call 26-360 an RTC case in {len(rtc)} items [{", ".join(sorted({s for _, s in rtc}))}] and an MTC case in {len(mtc)} items [{", ".join(sorted({s for _, s in mtc}))}]. Check the caption.')
    else: C.append('- No variance found.')
    C += ['', '## D. Files sessions say they created that are not on disk now', '']
    miss = [r for r in fx if r[2] == 'no']
    gone_ok = lambda p: '/.claude/worktrees/' in p or p.startswith(('/tmp', '/private/')) or 'scratchpad' in p
    strong = [r for r in miss if 'tool_call' in r[5] and not gone_ok(r[0]) and (r[0].startswith(REPO) or not r[0].startswith('/'))]
    C.append(f'- {len(miss)} paths in FILES_INDEX.csv have exists=no. Most are scratch scripts, worktree or /tmp paths, or names cut short in the summaries. The ones below were written by a Write/Edit tool call into the repo and are not there now (moved, renamed, deleted, or written in another checkout):')
    C += [f'  - {r[0]} [{r[6]}]' for r in strong] or ['  - None.']
    C += ['', '## E. Conflicts and doubts raised inside the sessions themselves', '']
    for m in ORDER:
        es = dedupe([(t, sid, d) for m2, sec, t, sid, d in all_items if m2 == m and sec == 'CONFLICTS OR DOUBTS'])
        if not es: continue
        C += [f'### {m}', ''] + [f'- {e["text"]} {tag(e)}' for e in es] + ['']
    open(f'{H}/CONFLICTS.md', 'w').write('\n'.join(C).replace('—', '-'))
    print(f'sessions={len(sessions)} items={len(all_items)} open_items={len(opens)} known_truth_hits={len(kt)} cross_session={len(cs)} files={len(fx)} missing={len(miss)}')

if __name__ == '__main__': main()
