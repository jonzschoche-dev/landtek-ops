#!/usr/bin/env python3
"""case_dossier.py — lay out each matter's VERIFIED corpus + evidence in one clean, regenerable view.

For every acknowledged matter it renders: identity (court/docket/status/deadline) -> parties -> causes
-> VERIFIED facts (the document-proven corpus, each with its doc citation + quoted excerpt) -> evidence
(the documents on file, classified read / legible-unread / OCR-blocked) -> coverage & gaps (what's
proven, what's operator-asserted-but-unproven, what's queued to read next). It reads the knowledge
layer honestly: only provenance='verified' rows are the corpus; operator/inferred are listed separately
as "asserted / pending verification" so it is always obvious what still needs proving. Regenerable —
re-run as the worker builds the corpus (rides the daily timer).

  python3 scripts/case_dossier.py --all                  # write case_dossiers/<MATTER>.md + INDEX.md
  python3 scripts/case_dossier.py --matter MWK-CV26360    # print one to stdout
"""
import argparse
import os
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "case_dossiers")


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True
    return c


def matters(cur):
    cur.execute("""SELECT matter_code, title, court_or_agency, docket_number, status, current_stage,
                   next_deadline, legal_theory FROM matters ORDER BY matter_code""")
    return cur.fetchall()


def _stats(cur, mc):
    cur.execute("SELECT provenance_level, count(*) n FROM matter_facts WHERE matter_code=%s GROUP BY 1", (mc,))
    p = {r["provenance_level"]: r["n"] for r in cur.fetchall()}
    cur.execute("""SELECT count(*) tot,
        count(*) FILTER (WHERE EXISTS (SELECT 1 FROM matter_facts f WHERE f.provenance_level='verified'
            AND f.source_kind='doc' AND f.source_id=d.id::text)) read,
        count(*) FILTER (WHERE coalesce(q.flagged,false) AND NOT EXISTS (SELECT 1 FROM matter_facts f
            WHERE f.provenance_level='verified' AND f.source_kind='doc' AND f.source_id=d.id::text)) blocked
        FROM documents d LEFT JOIN ocr_quality q ON q.doc_id=d.id WHERE d.matter_code=%s""", (mc,))
    d = cur.fetchone()
    return p, d


def dossier(cur, m):
    mc = m["matter_code"]
    L = [f"# {mc} — {m['title'] or '(untitled)'}", ""]
    meta = []
    if m["court_or_agency"]: meta.append(f"**Forum:** {m['court_or_agency']}")
    if m["docket_number"]: meta.append(f"**Docket:** {m['docket_number']}")
    if m["status"]: meta.append(f"**Status:** {m['status']}" + (f" / {m['current_stage']}" if m["current_stage"] else ""))
    if m["next_deadline"]: meta.append(f"**Next deadline:** {m['next_deadline']}")
    if meta: L += ["  ·  ".join(meta), ""]

    cur.execute("""SELECT side, party_name, role, source_doc_id FROM matter_parties
                   WHERE matter_code=%s AND provenance_level='verified' ORDER BY side DESC, id""", (mc,))
    parties = cur.fetchall()
    if parties:
        L += ["## Parties (verified)", ""]
        for p in parties:
            L.append(f"- **{p['side']}** — {p['party_name']}: {p['role']}  `doc:{p['source_doc_id']}`")
        L.append("")

    cur.execute("""SELECT cause, against_parties, basis, operative_doc_id FROM matter_causes
                   WHERE matter_code=%s AND provenance_level='verified' ORDER BY id""", (mc,))
    causes = cur.fetchall()
    if causes:
        L += ["## Causes of action (verified)", ""]
        for c in causes:
            L.append(f"- **{c['cause']}** — vs {c['against_parties']}. {c['basis']}  `doc:{c['operative_doc_id']}`")
        L.append("")

    cur.execute("""SELECT statement, excerpt, source_id, created_by FROM matter_facts
                   WHERE matter_code=%s AND provenance_level='verified'
                   ORDER BY (source_id ~ '^[0-9]+$') DESC, source_id::text, id""", (mc,))
    facts = cur.fetchall()
    L += [f"## Verified facts — the document-proven corpus ({len(facts)})", ""]
    for f in facts:
        src = f"doc:{f['source_id']}" if f["source_id"] else "—"
        L.append(f"- {f['statement']}  `{src}`")
        if f["excerpt"]:
            L.append(f"  > \"{f['excerpt'][:300]}\"")
    if not facts:
        L.append("_(none yet — see Coverage & gaps below for what's queued)_")
    L.append("")

    cur.execute("""SELECT d.id, coalesce(d.original_filename, d.smart_filename, '?') fn,
        length(coalesce(d.extracted_text,'')) tlen, coalesce(q.flagged,false) flagged, coalesce(q.score,0) score,
        (SELECT count(*) FROM matter_facts f WHERE f.provenance_level='verified' AND f.source_kind='doc'
            AND f.source_id=d.id::text) nfacts
        FROM documents d LEFT JOIN ocr_quality q ON q.doc_id=d.id
        WHERE d.matter_code=%s ORDER BY nfacts DESC, tlen DESC""", (mc,))
    docs = cur.fetchall()
    if docs:
        L += [f"## Evidence on file ({len(docs)} documents)", ""]
        for d in docs:
            if d["nfacts"]:
                tag = f"✅ read ({d['nfacts']} facts)"
            elif d["flagged"] or (d["tlen"] < 1000):
                tag = "⛔ OCR-blocked / too short"
            elif d["score"] >= 0.40 or d["tlen"] >= 1000:
                tag = "📄 legible — unread"
            else:
                tag = "· unscored"
            L.append(f"- `doc:{d['id']}` {d['fn'][:64]} — {tag}")
        L.append("")

    p, ds = _stats(cur, mc)
    L += ["## Coverage & gaps", ""]
    L.append(f"- Verified facts: **{p.get('verified',0)}**  ·  operator-asserted (pending source): "
             f"**{p.get('operator',0)}**  ·  inferred (not surfaced as fact): {p.get('inferred_strong',0)+p.get('inferred_weak',0)}")
    L.append(f"- Documents: {ds['tot']} on file — {ds['read']} read, {ds['blocked']} OCR-blocked, "
             f"{ds['tot']-ds['read']-ds['blocked']} other")
    cur.execute("""SELECT statement FROM matter_facts WHERE matter_code=%s AND provenance_level='operator' ORDER BY id LIMIT 6""", (mc,))
    ops = cur.fetchall()
    if ops:
        L.append("- **Operator-asserted, needs a source-read to verify:**")
        for o in ops:
            L.append(f"    - {o['statement'][:150]}")
    L.append("")
    return "\n".join(L), p, ds


def index_row(mc, title, p, ds):
    return (f"| [{mc}]({mc}.md) | {(title or '')[:38]} | {p.get('verified',0)} | "
            f"{p.get('operator',0)} | {ds['read']}/{ds['tot']} | {ds['blocked']} |")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--matter")
    a = ap.parse_args()
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if a.matter:
        cur.execute("SELECT matter_code,title,court_or_agency,docket_number,status,current_stage,next_deadline,legal_theory FROM matters WHERE matter_code=%s", (a.matter,))
        m = cur.fetchone()
        if not m:
            print("no such matter"); return
        body, _, _ = dossier(cur, m)
        print(body); return
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for m in matters(cur):
        p, ds = _stats(cur, m["matter_code"])
        if (p.get("verified", 0) + ds["tot"]) == 0:
            continue  # skip empty stubs
        body, p, ds = dossier(cur, m)
        with open(os.path.join(OUT, f"{m['matter_code']}.md"), "w") as fh:
            fh.write(body)
        rows.append((p.get("verified", 0), index_row(m["matter_code"], m["title"], p, ds)))
    rows.sort(key=lambda r: -r[0])
    idx = ["# LandTek case dossiers — corpus & evidence index", "",
           "Regenerate: `python3 scripts/case_dossier.py --all`. Verified = document-proven (cited + "
           "quoted). Operator = asserted by Jonathan, pending a source-read. The verify_worker grows "
           "these automatically.", "",
           "| Matter | Title | Verified | Operator | Docs read | OCR-blocked |",
           "|---|---|---|---|---|---|"] + [r[1] for r in rows]
    with open(os.path.join(OUT, "INDEX.md"), "w") as fh:
        fh.write("\n".join(idx) + "\n")
    print(f"[dossier] wrote {len(rows)} matter dossiers + INDEX.md to {OUT}")


if __name__ == "__main__":
    main()
