#!/usr/bin/env python3
"""data_audit.py — audit the TRUTH DATA LAYER itself (not the output). $0, deterministic, read-only.

The memos kept being wrong because the DATA was wrong: operative pleadings orphaned, links over-broad
(images + stray letters), conflations. Fixing the renderer can't fix bad inputs. This classifies EVERY
doc↔matter link as KEEP or DROP (with a reason), flags ungrounded operative pleadings + orphan
operatives, and prints a remediation plan split into:
  • AUTO   — INSERT-only (link true orphans, queue source-reads) — allowed, applied with --apply
  • NEEDS-AUTH — DELETE/UPDATE (unlink noise/conflations) — classifier-gated; emitted as SQL for the
    operator to approve, never run autonomously.

  python3 scripts/data_audit.py                 # corpus summary (every MWK matter)
  python3 scripts/data_audit.py MWK-ARTA-1319   # per-matter detail incl. the drop list
  python3 scripts/data_audit.py --plan          # the full remediation plan (auto + needs-auth SQL)
"""
import os
import re
import sys

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from matter_readiness import _tokens

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
IMG = re.compile(r"\.(png|jpe?g|gif|bmp|tiff?|webp)$", re.I)
OPERATIVE = r"complaint|petition|manifestation|affidavit|motion|comment|position paper|answer"


def _toks(docket, title, mc):
    t = list(_tokens(docket, title))
    m = re.search(r"-(\d{3,5})$", mc)
    if m:
        t.append(m.group(1))
    return t or ["~nomatch~"]


def audit(cur, mc):
    cur.execute("SELECT title, coalesce(docket_number,''), coalesce(forum,court_or_agency,'') FROM matters WHERE matter_code=%s", (mc,))
    row = cur.fetchone()
    if not row:
        return None
    title, docket, forum = row
    toks = _toks(docket, title, mc)
    cur.execute("""SELECT d.id, coalesce(d.original_filename,d.smart_filename,'?') fn, coalesce(d.matter_code,'') dmc,
       (SELECT count(*) FROM matter_facts mf WHERE mf.provenance_level='verified' AND mf.source_kind='doc'
          AND mf.source_id=d.id::text AND mf.matter_code=%s) nf,
       (SELECT bool_or((coalesce(d.extracted_text,'')||' '||coalesce(d.original_filename,'')||' '||
          coalesce(d.smart_filename,'')) ILIKE '%%'||t||'%%') FROM unnest(%s::text[]) t) hits
       FROM documents d WHERE d.matter_code=%s OR d.id IN (SELECT doc_id FROM document_matter_links WHERE matter_code=%s)""",
                (mc, toks, mc, mc))
    keep, drop, ops = [], [], []
    for did, fn, dmc, nf, hits in cur.fetchall():
        if re.search(OPERATIVE, fn or "", re.I):
            ops.append((did, fn, nf or 0))
        if (nf or 0) > 0 or hits:
            keep.append((did, fn, nf or 0))
        else:
            reason = "image" if IMG.search(fn or "") else (f"foreign→{dmc}" if dmc and dmc != mc else "no-signal")
            drop.append((did, fn, reason))
    op_grounded = [o for o in ops if o[2] > 0]
    # orphan operatives: carry this docket, operative-type filename, not yet linked
    linked = {k[0] for k in keep} | {d[0] for d in drop}
    like = " OR ".join(["(coalesce(extracted_text,'')||' '||coalesce(original_filename,'')||' '||coalesce(smart_filename,'')) ILIKE %s"] * len(toks))
    cur.execute(f"""SELECT id, coalesce(original_filename,smart_filename,'?') FROM documents WHERE ({like})
       AND coalesce(original_filename,smart_filename,'') !~* 'omnibus|bible|digest|dossier|index'""",
                [f"%{t}%" for t in toks])
    orphans = [(i, fn) for i, fn in cur.fetchall() if i not in linked and re.search(OPERATIVE, fn or "", re.I)]
    return {"mc": mc, "title": title, "toks": toks, "keep": keep, "drop": drop,
            "ops": ops, "op_grounded": op_grounded, "orphans": orphans}


def _matters(cur):
    cur.execute("SELECT matter_code FROM matters WHERE matter_code LIKE 'MWK-%' ORDER BY matter_code")
    return [r[0] for r in cur.fetchall()]


def main():
    c = psycopg2.connect(DSN); c.autocommit = True; cur = c.cursor()
    arg = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else None
    plan = "--plan" in sys.argv

    if arg:
        a = audit(cur, arg)
        if not a:
            print("no such matter"); return
        print("=" * 74)
        print(f"DATA-LAYER AUDIT — {a['mc']}  ({a['title'][:48]})   tokens={a['toks']}")
        print("=" * 74)
        print(f"  operative pleadings linked: {len(a['ops'])} ({len(a['op_grounded'])} source-read)")
        print(f"  KEEP (relevant): {len(a['keep'])}   DROP (not relevant): {len(a['drop'])}   orphan operatives: {len(a['orphans'])}")
        if a["drop"]:
            print("\n  -- DROP candidates (linked but no facts + no docket match) --")
            for did, fn, reason in a["drop"]:
                print(f"     doc:{did:>5}  [{reason:14}] {fn[:50]}")
        if a["orphans"]:
            print("\n  -- ORPHAN operatives (carry docket, operative-type, NOT linked) --")
            for did, fn in a["orphans"]:
                print(f"     doc:{did:>5}  {fn[:56]}")
        ung = [o for o in a["ops"] if o[2] == 0]
        if not a["op_grounded"] and ung:
            print("\n  -- UNGROUNDED operative (needs source-read) --")
            for did, fn, _ in ung[:6]:
                print(f"     doc:{did:>5}  {fn[:56]}")
        return

    # corpus summary — break "drop" into TRUE NOISE (image/foreign) vs UNREAD evidence (no-signal)
    rows = []
    T = {"keep": 0, "img": 0, "frn": 0, "nos": 0, "orph": 0}
    for mc in _matters(cur):
        a = audit(cur, mc)
        if not a:
            continue
        img = sum(1 for _, _, r in a["drop"] if r == "image")
        frn = sum(1 for _, _, r in a["drop"] if r.startswith("foreign"))
        nos = sum(1 for _, _, r in a["drop"] if r == "no-signal")
        rows.append((a["mc"], len(a["keep"]), img, frn, nos, len(a["orphans"]), "Y" if a["op_grounded"] else "n"))
        T["keep"] += len(a["keep"]); T["img"] += img; T["frn"] += frn; T["nos"] += nos; T["orph"] += len(a["orphans"])
    print("=" * 78)
    print("TRUTH DATA-LAYER AUDIT — corpus")
    print("  KEEP=relevant (facts or docket) · IMG=image noise · FRGN=tagged to another matter · "
          "NOSIG=no relevance signal (likely un-source-read evidence) · ORPH=orphan operative")
    print("=" * 78)
    print(f"{'MATTER':22} {'KEEP':>5} {'IMG':>4} {'FRGN':>5} {'NOSIG':>6} {'ORPH':>5} {'OPg':>4}")
    for mc, k, img, frn, nos, o, g in sorted(rows, key=lambda r: -(r[2] + r[3] + r[4])):
        print(f"{mc:22} {k:>5} {img:>4} {frn:>5} {nos:>6} {o:>5} {g:>4}")
    print(f"\n  TRUE NOISE (unlink — needs operator auth): {T['img']} images + {T['frn']} foreign-matter = {T['img']+T['frn']}")
    print(f"  UN-SOURCE-READ evidence (NOSIG {T['nos']}): NOT noise — source-read via verify_worker to validate→KEEP")
    print(f"  ORPHAN operatives to link+read (AUTO, INSERT-only): {T['orph']}")
    print(f"  Verified-relevant links today: {T['keep']}")
    if plan:
        print("\n" + "=" * 74 + "\nREMEDIATION PLAN\n" + "=" * 74)
        for mc in _matters(cur):
            a = audit(cur, mc)
            if not a or (not a["drop"] and not a["orphans"]):
                continue
            print(f"\n# {mc}")
            for did, fn in a["orphans"]:
                print(f"AUTO  link+read  doc:{did}  ({fn[:44]})")
            for did, fn, reason in a["drop"]:
                print(f"AUTH  unlink     doc:{did}  [{reason}]  ({fn[:40]})")


if __name__ == "__main__":
    main()
