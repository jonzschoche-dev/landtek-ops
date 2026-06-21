#!/usr/bin/env python3
"""matter_readiness.py — the TRUTH DATA-LAYER pre-flight for a matter. $0, deterministic.

A memo is only as true as the matter's data layer. The MWK-ARTA-1891 memo was fluently WRONG about the
matter's nature for many iterations because the operative pleading (the complaint) was ingested but
ORPHANED (matter_code NULL) while a conflated peripheral doc was linked — and nothing flagged it. This
tool checks the data layer BEFORE any memo is generated, and emits a concrete fix-list, so the next
matter takes one readiness report + 1-3 targeted fixes instead of dozens of discovery-by-failure prompts.

Checks (all deterministic SQL — no LLM):
  1. OPERATIVE PLEADING — is the complaint/petition that defines the matter present, linked, and source-read?
  2. ORPHANS — docs whose text/filename carry this matter's docket but are NOT linked (like doc 708 was).
  3. CONFLATIONS — linked docs flagged OFF-PROFILE, or that never mention the docket (likely mis-attributed).
  4. UN-INGESTED ATTACHMENTS — gmail attachments referencing this matter not yet turned into documents.
  5. GROUNDING — verified-fact count, and whether the operative doc itself is source-read.
Then a READINESS verdict + the exact fixes to run.

  python3 scripts/matter_readiness.py MWK-ARTA-1891
  python3 scripts/matter_readiness.py --all          # rank every matter by readiness
"""
import os
import re
import sys

import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
OPERATIVE = r"complaint|petition|manifestation|affidavit|motion|comment|position paper|answer"


def _tokens(docket, title):
    """Specific docket tokens to hunt for in the corpus (e.g. SL-2026-0423-1891, 26-360)."""
    s = (docket or "") + " " + (title or "")
    toks = set(re.findall(r"[A-Z]{0,4}-?\d{2,4}(?:-\d{2,4})+", s))
    return sorted((t for t in toks if len(t) >= 6), key=len, reverse=True)


def _linked(cur, mc):
    cur.execute("""SELECT id FROM documents WHERE matter_code=%s
                   UNION SELECT doc_id FROM document_matter_links WHERE matter_code=%s""", (mc, mc))
    return {r[0] for r in cur.fetchall()}


def assess(cur, mc):
    cur.execute("SELECT title, coalesce(docket_number,''), coalesce(forum,court_or_agency,'') FROM matters WHERE matter_code=%s", (mc,))
    row = cur.fetchone()
    if not row:
        return None
    title, docket, forum = row
    toks = _tokens(docket, title)
    linked = _linked(cur, mc)

    # facts per linked doc + total
    cur.execute("""SELECT source_id, count(*) FROM matter_facts WHERE matter_code=%s AND provenance_level='verified'
                   AND source_kind='doc' GROUP BY source_id""", (mc,))
    facts_by_doc = {int(s): n for s, n in cur.fetchall() if s and s.isdigit()}
    cur.execute("SELECT count(*) FROM matter_facts WHERE matter_code=%s AND provenance_level='verified'", (mc,))
    nfacts = cur.fetchone()[0]

    # detail on linked docs
    docs = []
    if linked:
        cur.execute("""SELECT id, coalesce(original_filename,smart_filename,'?'), coalesce(extracted_text,'')
                       FROM documents WHERE id = ANY(%s)""", (list(linked),))
        for did, fn, txt in cur.fetchall():
            is_op = bool(re.search(OPERATIVE, fn, re.I))
            has_tok = any(t.lower() in (txt + " " + fn).lower() for t in toks)
            docs.append({"id": did, "fn": fn, "op": is_op, "tok": has_tok,
                         "facts": facts_by_doc.get(did, 0), "len": len(txt)})

    operative = [d for d in docs if d["op"]]
    op_grounded = [d for d in operative if d["facts"] > 0]

    # orphans: carry the docket but not linked
    orphans = []
    if toks:
        like = " OR ".join(["extracted_text ILIKE %s OR original_filename ILIKE %s OR smart_filename ILIKE %s"] * len(toks))
        params = []
        for t in toks:
            params += [f"%{t}%", f"%{t}%", f"%{t}%"]
        cur.execute(f"""SELECT id, coalesce(original_filename,smart_filename,'?'), coalesce(matter_code,'(none)'),
                        length(coalesce(extracted_text,'')) FROM documents WHERE ({like})
                        AND coalesce(original_filename,smart_filename,'') !~* 'omnibus|bible|digest|dossier|index'
                        ORDER BY id""", params)
        for did, fn, omc, ln in cur.fetchall():
            if did not in linked:
                orphans.append({"id": did, "fn": fn, "mc": omc, "len": ln,
                                "op": bool(re.search(OPERATIVE, fn, re.I))})

    # conflations: linked but the relevance engine flagged OFF-PROFILE (the real signal — "doesn't cite
    # the docket" is too noisy, since evidence docs like deeds/exhibits rarely carry the docket string).
    cur.execute("SELECT doc_id FROM matter_relevance WHERE focal_matter=%s AND tier='OFF-PROFILE'", (mc,))
    offp = {r[0] for r in cur.fetchall()}
    conflations = [d for d in docs if d["id"] in offp and not re.search(r"annex|exhibit", d["fn"], re.I)]

    # un-ingested gmail attachments referencing the matter
    uningested = []
    cur.execute("""SELECT message_id, coalesce(subject,''), attachment_refs FROM gmail_messages
                   WHERE has_attachments AND (matter_codes @> ARRAY[%s]::text[]
                      OR subject ILIKE %s OR body_plain ILIKE %s)""",
                (mc, f"%{toks[0]}%" if toks else "%~none~%", f"%{toks[0]}%" if toks else "%~none~%"))
    cur.execute("SELECT lower(coalesce(original_filename,smart_filename,'')) FROM documents WHERE id = ANY(%s)",
                (list(linked) or [-1],)) if linked else None
    linked_names = {r[0] for r in cur.fetchall()} if linked else set()
    cur.execute("""SELECT message_id, coalesce(subject,''), attachment_refs FROM gmail_messages
                   WHERE has_attachments AND (matter_codes @> ARRAY[%s]::text[]
                      OR subject ILIKE %s)""", (mc, f"%{toks[0]}%" if toks else "%~none~%"))
    import json as _json
    for mid, subj, refs in cur.fetchall():
        for ref in (refs if isinstance(refs, list) else (_json.loads(refs) if refs else [])):
            fn = (ref.get("filename") or "")
            mime = (ref.get("mime") or "")
            if "pdf" in mime.lower() and fn.lower() not in linked_names and re.search(OPERATIVE + r"|annex", fn, re.I):
                uningested.append({"fn": fn, "subj": subj[:50], "size": ref.get("size", 0)})

    return {"mc": mc, "title": title, "docket": docket, "forum": forum, "tokens": toks,
            "linked": len(linked), "nfacts": nfacts, "docs": docs, "operative": operative,
            "op_grounded": op_grounded, "orphans": orphans, "conflations": conflations,
            "uningested": uningested}


def verdict(a):
    """Readiness verdict + BLOCKERS (decide readiness) and ADVISORIES (summarized noise)."""
    fixes, advis = [], []
    if not a["operative"]:
        fixes.append("NO operative pleading linked — find/link the complaint/petition that defines this matter.")
    elif not a["op_grounded"]:
        d = a["operative"][0]
        fixes.append(f"Operative pleading doc:{d['id']} ({d['fn'][:40]}) is NOT source-read — read it into verified facts (this is what defines the matter).")
    op_orphans = [o for o in a["orphans"] if o["op"]]
    for o in op_orphans:
        fixes.append(f"OPERATIVE ORPHAN doc:{o['id']} ({o['fn'][:40]}, {o['mc']}) carries this docket but isn't linked — link + source-read it.")
    for u in a["uningested"]:
        fixes.append(f"UN-INGESTED attachment '{u['fn'][:40]}' ({u['size']//1024}KB) — fetch + extract.")
    if a["nfacts"] < 5:
        fixes.append(f"Only {a['nfacts']} verified facts — under-grounded; source-read the operative + key docs.")
    others = [o for o in a["orphans"] if not o["op"]]
    if others:
        advis.append(f"{len(others)} other docs carry this docket but aren't linked — review/link (e.g. " +
                     ", ".join(f"doc:{o['id']}" for o in others[:4]) + ").")
    if a["conflations"]:
        advis.append(f"{len(a['conflations'])} linked docs may be conflations (don't cite docket / OFF-PROFILE) — verify they belong.")
    ready = (bool(a["op_grounded"]) and not op_orphans and a["nfacts"] >= 5 and not a["uningested"])
    return ready, fixes, advis


def show(a):
    ready, fixes, advis = verdict(a)
    print("=" * 74)
    print(f"TRUTH DATA-LAYER READINESS — {a['mc']}")
    print(f"  {a['title'][:64]}")
    print(f"  forum={a['forum'][:40]}  docket={a['docket'][:30]}  tokens={a['tokens']}")
    print("=" * 74)
    print(f"  linked docs: {a['linked']} · verified facts: {a['nfacts']}")
    print(f"  operative pleading: {len(a['operative'])} found, {len(a['op_grounded'])} source-read")
    for d in a["operative"]:
        print(f"      doc:{d['id']:>5}  {d['fn'][:46]:46}  facts={d['facts']}")
    print(f"  orphans (carry docket, not linked): {len(a['orphans'])}")
    for o in a["orphans"][:8]:
        print(f"      doc:{o['id']:>5}  {o['fn'][:42]:42} [{o['mc']}]{' OPERATIVE!' if o['op'] else ''}")
    print(f"  possible conflations: {len(a['conflations'])}")
    for c in a["conflations"][:6]:
        print(f"      doc:{c['id']:>5}  {c['fn'][:46]}")
    print(f"  un-ingested attachments: {len(a['uningested'])}")
    for u in a["uningested"][:6]:
        print(f"      {u['fn'][:46]}  ({u['size']//1024}KB)  on: {u['subj']}")
    print("-" * 74)
    print(f"  VERDICT: {'✓ READY for a truth-memo' if ready else '✗ NOT READY — fix the data layer first'}")
    for i, fx in enumerate(fixes, 1):
        print(f"   FIX {i}. {fx}")
    for ad in advis:
        print(f"   · advisory: {ad}")
    if not fixes:
        print("   (no blocking fixes)")
    return ready


def main():
    c = psycopg2.connect(DSN); c.autocommit = True; cur = c.cursor()
    if "--all" in sys.argv:
        cur.execute("SELECT matter_code FROM matters WHERE matter_code LIKE 'MWK-%' ORDER BY matter_code")
        rows = []
        for (mc,) in cur.fetchall():
            a = assess(cur, mc)
            if a:
                ready, fixes, advis = verdict(a)
                rows.append((ready, len(fixes), mc, a["nfacts"]))
        print(f"{'RDY':>3}  {'BLOCK':>5}  {'FACTS':>5}  MATTER")
        for ready, nf, mc, facts in sorted(rows, key=lambda r: (r[0], -r[1])):
            print(f"{'✓' if ready else '✗':>3}  {nf:>5}  {facts:>5}  {mc}")
        return
    mc = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "MWK-ARTA-1891"
    a = assess(cur, mc)
    if not a:
        print(f"no such matter: {mc}"); return
    show(a)


if __name__ == "__main__":
    main()
