#!/usr/bin/env python3
"""Auto-harvest LandTek Claude Code sessions (read-only on session files).
Usage: harvest_sessions.py [--limit N] [--only SESSIONID8] [--digest-only] [--now]
--now (with --only): harvest even if the session file was just written (SessionEnd hook)."""
import json, re, sys, os, glob, time, csv, subprocess, argparse
HOME = os.path.expanduser('~')
OUT = f'{HOME}/landtek/case_work/HARVEST'
LOG = f'{OUT}/_harvest.log'; MAN = f'{OUT}/_manifest.csv'
DIG = f'{OUT}/_digests'
CLAUDE = f'{HOME}/.local/bin/claude'
CAP = 40000
PROMPT = ("This is a digest of a closed LandTek Claude Code session being harvested into the master record. "
 "Output ONLY these headings in plain text: SESSION (tool, date range, main topic in one line, then a line MATTERS: the case numbers or matters touched); 1. DECISIONS MADE (say if each was carried out, only approved, or interrupted); "
 "2. FACTS ESTABLISHED (each with its source; mark unsourced facts UNVERIFIED); 3. FILES CREATED OR EDITED (path and what it is); "
 "4. DATES AND DEADLINES (with case number); 5. OPEN ITEMS; 6. CONFLICTS OR DOUBTS. Never invent; write UNKNOWN. Under each heading put one item per line, each line starting with a hyphen and a space. No paragraphs. No markdown bold. No em-dashes.")
FACT = re.compile(r'(\b20\d\d-\d\d-\d\d\b|\b\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+20\d\d|'
 r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+20\d\d|\bT-\d{3,6}\b|\bTCT\b|\bLot\s+\d+[-A-Z]*|'
 r'\b(Civil Case|SP|Sp\. Proc\.|Case No\.?)\s*[\w-]*\d|\b\d{2}-\d{3,4}\b)', re.I)
def log(m):
    with open(LOG,'a') as f: f.write(time.strftime('%Y-%m-%d %H:%M:%S ')+m+'\n')
def text_of(c):
    if isinstance(c,str): return c
    return '\n'.join(b.get('text','') for b in c if isinstance(b,dict) and b.get('type')=='text')
def digest(path):
    sid=os.path.basename(path)[:-6]; ts=[]; cwd=None; items=[]; files=set(); facts=[]; seen=set()
    for line in open(path,errors='replace'):
        try: d=json.loads(line)
        except Exception: continue
        if d.get('timestamp'): ts.append(d['timestamp'])
        cwd=cwd or d.get('cwd')
        m=d.get('message')
        if not isinstance(m,dict): continue
        c=m.get('content')
        if d.get('type')=='user':
            t=text_of(c).strip()  # tool_result blocks are dropped
            if t and not t.startswith('<'): items.append('USER: '+t[:3000])
            elif t.startswith('<command-name>'): items.append('USER: '+t[:300])
        elif d.get('type')=='assistant' and isinstance(c,list):
            for b in c:
                if b.get('type')=='tool_use':
                    i=b.get('input') or {}
                    p=i.get('file_path') or i.get('notebook_path')
                    if p and b.get('name') in ('Write','Edit','MultiEdit','NotebookEdit'): files.add(p)
            t=text_of(c).strip()
            if t:
                items.append('ASSISTANT: '+(t if len(t)<=2500 else t[:1800]+' [...] '+t[-600:]))
                for ln in t.splitlines():
                    if FACT.search(ln) and ln.strip() not in seen and len(ln)<400:
                        seen.add(ln.strip()); facts.append(ln.strip())
            # facts from user lines too
        if d.get('type')=='user':
            for ln in text_of(c).splitlines():
                if FACT.search(ln) and ln.strip() not in seen and len(ln)<400 and not ln.startswith('<'):
                    seen.add(ln.strip()); facts.append(ln.strip())
    head=f"SESSION ID: {sid}\nCWD: {cwd}\nFIRST TS: {ts[0] if ts else 'UNKNOWN'}\nLAST TS: {ts[-1] if ts else 'UNKNOWN'}\n"
    fsec='\n== FILES WRITTEN/EDITED ==\n'+'\n'.join(sorted(files))[:5000]
    xsec='\n== FACT LINES (dates, cases, titles, lots) ==\n'+'\n'.join(facts)[:9000]
    budget=CAP-len(head)-len(fsec)-len(xsec)-200
    conv='\n\n'.join(items)
    if len(conv)>budget: conv=conv[:budget*55//100]+'\n\n[... MIDDLE OF SESSION OMITTED ...]\n\n'+conv[-(budget*45//100):]
    return sid, (ts[0] if ts else ''), (ts[-1] if ts else ''), cwd, head+fsec+xsec+'\n== CONVERSATION (start and end) ==\n'+conv
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--limit',type=int); ap.add_argument('--only'); ap.add_argument('--digest-only',action='store_true'); ap.add_argument('--now',action='store_true')
    a=ap.parse_args(); os.makedirs(DIG,exist_ok=True)
    files=[f for f in glob.glob(f'{HOME}/.claude/projects/-Users-jonathanzschoche-landtek*/*.jsonl')]
    files.sort(key=os.path.getmtime)
    now=time.time(); newman=not os.path.exists(MAN)
    mf=open(MAN,'a',newline=''); w=csv.writer(mf)
    if newman: w.writerow(['session','first_ts','last_ts','cwd','bytes','digest_chars','status','output'])
    n=0
    for p in files:
        sid8=os.path.basename(p)[:8]
        if a.only and sid8!=a.only[:8]: continue
        if now-os.path.getmtime(p)<1800 and not (a.now and a.only): log(f'SKIP active {sid8}'); continue
        prev=glob.glob(f'{OUT}/HARVEST_claude_{sid8}_*.txt')
        if prev and min(os.path.getmtime(x) for x in prev)>=os.path.getmtime(p): continue
        stale=prev  # session resumed since last harvest; replaced below on success
        if a.limit and n>=a.limit: break
        n+=1
        try:
            sid,t0,t1,cwd,dg=digest(p)
        except Exception as e:
            log(f'FAIL digest {sid8}: {e}'); w.writerow([sid8,'','','',os.path.getsize(p),0,'digest_error','']); mf.flush(); continue
        open(f'{DIG}/{sid8}.txt','w').write(dg)
        out=f'{OUT}/HARVEST_claude_{sid8}_{(t1 or "unknown")[:10]}.txt'
        if len(dg)<400: status='empty_session'; log(f'SKIP empty {sid8}')
        elif a.digest_only: status='digest_only'
        else:
            log(f'RUN {sid8} digest={len(dg)}')
            try:
                r=subprocess.run([CLAUDE,'-p','--model','haiku','--tools','','--no-session-persistence',PROMPT],
                    input=dg,capture_output=True,text=True,timeout=600,cwd='/tmp')
                if r.returncode==0 and r.stdout.strip():
                    for x in stale:
                        if x!=out: os.remove(x)  # our own older harvest of this session, never a .jsonl
                    open(out,'w').write(r.stdout.replace('\u2014','-').replace('\u2013','-')); status='ok'
                else: status=f'claude_rc{r.returncode}'; log(f'FAIL {sid8}: {(r.stderr or r.stdout)[:500]}')
            except subprocess.TimeoutExpired: status='timeout'; log(f'FAIL timeout {sid8}')
        w.writerow([sid,t0,t1,cwd,os.path.getsize(p),len(dg),status,out if status=='ok' else '']); mf.flush()
        log(f'DONE {sid8} {status}')
    log(f'BATCH END processed={n}')
if __name__=='__main__': main()
