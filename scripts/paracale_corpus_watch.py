#!/usr/bin/env python3
"""
paracale_corpus_watch.py — meticulous change-tracker for the Paracale-001 (Inocalla) corpus.

On each run it snapshots every Paracale-relevant document, diffs against the last
manifest, and for anything NEW or CHANGED it (a) shows it and (b) auto-checks it against
the matter's OPEN-ITEMS watchlist so newly ingested facts get incorporated, not missed.

Usage:
  python3 paracale_corpus_watch.py            # report deltas since last manifest (no write)
  python3 paracale_corpus_watch.py --update   # report, then update the manifest baseline
  python3 paracale_corpus_watch.py --full      # list the entire current inventory
Manifest: case_work/Paracale-001/corpus_manifest.json  (tracked in git so diffs travel Mac<->VPS)
"""
import subprocess, json, re, sys, os

MANIFEST = os.environ.get("PARACALE_MANIFEST",
    "/root/landtek/case_work/Paracale-001/corpus_manifest.json")

# Scope: case_file Paracale-001 + the NULL-case Inocalla docs (early ingests) by content signal.
SCOPE_SQL = """
SELECT json_build_object(
  'id', id,
  'title', COALESCE(document_title, smart_filename, original_filename, ''),
  'hash', COALESCE(text_hash, content_hash, md5(COALESCE(extracted_text,''))),
  'len', COALESCE(LENGTH(extracted_text),0),
  'status', status,
  'ts', to_char(COALESCE(created_at, timestamp), 'YYYY-MM-DD')
)
FROM documents
WHERE case_file = 'Paracale-001'
   OR (case_file IS NULL AND extracted_text ~* '(inocalla|paracale|capacuan|jose panganiban|casper|vicente inocalla|ace inocalla|bombita)')
ORDER BY id;
"""

# OPEN ITEMS — keyword -> which matter question a new doc might resolve.
WATCH = [
 ("Undertaking notarization (§5-G / act 7a-iii)", r'notari|acknowledgment|jurat|before me.*notary'),
 ("DBP full-payment proof (§5-G / act 7a-ii)", r'development bank|\bDBP\b'),
 ("DBP payment/release specifically", r'(certificate of full payment|release of (real estate )?mortgage|fully paid|redemption|cancellation of mortgage)'),
 ("RD title status — DBP lots / old numbers", r'\b(2075[4567]|4781|5941|4251|4695)\b'),
 ("Melvin alive-vs-dead (§3)", r'melv(i|y)n'),
 ("Ereneo Agon branch (§3)", r'ereneo|agon'),
 ("Radj Gymson / Senen rep (§3)", r'radj|gymson'),
 ("Senen heirless proof (CENOMAR/death cert)", r'(cenomar|certificate of no marriage|no record of marriage)'),
 ("PSA death certificate", r'(certificate of death|death certificate|PSA)'),
 ("Barangay conciliation / CFA (ejectment §6)", r'(certification to file action|lupon|katarungan|barangay 759|pambarangay)'),
 ("Estate tax / amnesty (§11)", r'(estate tax|tax amnesty|RA 11213|11956|eCAR|BIR ruling)'),
 ("Partition docket 5625/5626 (§4)", r'(5625|5626|judicial partition|compromise agreement.*1992|certificate of finality)'),
 ("Heir SPA / consent / waiver", r'(special power of attorney|waiver of rights|conforme|extrajudicial settlement|deed of.*adjudication)'),
 ("Ace / Bombita / ejectment fronts (§6)", r'(vicente.*inocalla iii|\bace\b|bombita|ejectment|unlawful detainer|demand to vacate|13-131220|256997)'),
 ("Mineral rights / MPSA / APSA / mining (§6-B)", r'(APSA|EXPA|MPSA|minahang bayan|mineral|NCIP|MGB)'),
 ("Manila building / TCT 44055 (§6 Front 1B)", r'(44055|206789|002-2011002723|del pilar|santa ana|vito cruz)'),
]

def q(sql):
    return subprocess.run(
        ["docker","exec","-i","n8n-postgres-1","psql","-U","n8n","-d","n8n","-t","-A"],
        input=sql, capture_output=True, text=True).stdout

def load_current():
    cur={}
    for line in q(SCOPE_SQL).splitlines():
        line=line.strip()
        if not line: continue
        try:
            d=json.loads(line); cur[str(d["id"])]=d
        except: pass
    return cur

def fetch_text(did):
    r=q("SELECT extracted_text FROM documents WHERE id=%s;"%did)
    return r or ""

def watch_hits(text):
    hits=[]
    for label,pat in WATCH:
        if re.search(pat, text, re.I):
            hits.append(label)
    return hits

def main():
    args=set(sys.argv[1:])
    cur=load_current()
    prev={}
    if os.path.exists(MANIFEST):
        try: prev=json.load(open(MANIFEST)).get("docs",{})
        except: prev={}

    if "--full" in args:
        print("=== PARACALE CORPUS — FULL INVENTORY (%d docs) ==="%len(cur))
        for did,d in sorted(cur.items(), key=lambda x:int(x[0])):
            print("  doc %-5s [%s] len=%-6s %s | %s"%(did,d["ts"],d["len"],d["status"],(d["title"] or "?")[:44]))
        return

    new_ids=[i for i in cur if i not in prev]
    chg_ids=[i for i in cur if i in prev and cur[i]["hash"]!=prev[i]["hash"]]
    gone_ids=[i for i in prev if i not in cur]

    print("=== PARACALE CORPUS WATCH ===")
    print("baseline: %s | current docs: %d | prior: %d"%(
        "none (first run)" if not prev else "loaded", len(cur), len(prev)))
    print("NEW: %d | CHANGED: %d | REMOVED: %d\n"%(len(new_ids),len(chg_ids),len(gone_ids)))

    for tag,ids in (("NEW",new_ids),("CHANGED",chg_ids)):
        for did in sorted(ids,key=int):
            d=cur[did]; text=fetch_text(did)
            hits=watch_hits(text)
            print("--- %s doc %s [%s] %s (len=%s)"%(tag,did,d["ts"],(d["title"] or "?")[:50],d["len"]))
            if hits:
                print("    >>> MAY RESOLVE / TOUCHES:")
                for h in hits: print("        - "+h)
            else:
                print("    (no open-item keyword hit — review manually)")
            snip=re.sub(r'\s+',' ',text[:240])
            print("    head: "+snip)
    if gone_ids:
        print("\nREMOVED ids:", ", ".join(sorted(gone_ids,key=int)))

    if "--update" in args:
        os.makedirs(os.path.dirname(MANIFEST), exist_ok=True)
        json.dump({"docs":cur}, open(MANIFEST,"w"), indent=0)
        print("\n[manifest updated: %d docs baselined]"%len(cur))
    else:
        print("\n(run with --update to baseline these as seen)")

if __name__=="__main__":
    main()
