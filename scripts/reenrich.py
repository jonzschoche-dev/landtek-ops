#!/usr/bin/env python3
"""reenrich.py — POST-OCR RE-ENRICHMENT: the corpus-wide significance refresher (deploy_812).

LEGAL_FINDABILITY directive. Once a document has real extracted_text (OCR'd or born-digital), its significance
signals should reflect the TEXT, not just the ingest envelope. This driver REUSES the deploy_809/810/811 engine
(extract_email_attachments.extract_signals — one engine, no duplication) and adds the v3 depth: the text pool +
unknown-reference LEADS (registry-expansion candidates) + exhibit-series citation (bundle detection).

DETECTION — three classes, ONE query; C1/C2 drain once, C3 makes every later run O(changed docs):
  C1 never-enriched with substantive text  (the whole non-email corpus: titles, deeds, court orders)
  C2 signals version < SIGNALS_VERSION     (older engine — e.g. v2 envelope-only, no text pool)
  C3 STALE: signals.text_hash <> md5(extracted_text)  (doc re-OCR'd since last enrichment — the same
     eviction logic as rag_embed_local._restale(); v3 stamps text_hash so this class self-maintains)

PRIORITY: active-litigation / ARTA / title docs first (matter_code active OR case_file MWK + filing-ish type),
then the rest by recency. --limit batches; safe to stop and resume anytime (idempotent by design).

OBSERVABILITY: per-doc DELTA line (what the text pool ADDED vs the previous signals) + run summary
(gained-matters / gained-titles / new leads / bundle flags). --dry-run writes nothing.

INVARIANTS: A5/A54 — same client-scoping + cross-client tripwire as ingest; unknown refs are LEADS, never
verified links; auto-matter stays single-same-client-docket-exact-only.

USAGE: python3 scripts/reenrich.py [--dry-run] [--limit N] [--doc-id N ...] [--case-file CF] [--matter M]
"""
import argparse, hashlib, json, sys, os

sys.path.insert(0, "/root/landtek")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2, psycopg2.extras
from extract_email_attachments import (DSN, SIGNALS_VERSION, load_registries, extract_signals,
                                       extract_text_extras, apply_enrichment, _sig_summary)

MIN_TEXT = 120  # substantive-text floor


def _hits(sig, key):
    """Identity set of a hit list — matter_code/tct/name only, so a pool RENAME (body→text) or metadata
    refresh (a deadline moving) is not mis-reported as a gained signal."""
    return {(h.get("matter_code") or h.get("tct") or h.get("name")) for h in (sig or {}).get(key) or []}


def _delta(old, new):
    """What did the new pass ADD over the previous signals? (matter/title/party gains + new leads/flags)"""
    bits = []
    for key, name in (("matter_hits", "matters"), ("title_hits", "titles"), ("party_hits", "parties")):
        gained = _hits(new, key) - _hits(old, key)
        if gained:
            bits.append(f"+{name}:" + ",".join(sorted(gained)))
    for lead in ("unknown_titles", "unknown_dockets"):
        n_old, n_new = len((old or {}).get(lead) or []), len(new.get(lead) or [])
        if n_new > n_old:
            bits.append(f"+{lead}({n_new})")
    for fl in new.get("flags", {}):
        if fl not in (old or {}).get("flags", {}):
            bits.append(f"+FLAG:{fl}")
    return "; ".join(bits) if bits else ("unchanged" if old else "first-enrich")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--doc-id", type=int, action="append", default=None)
    ap.add_argument("--case-file", default=None)
    ap.add_argument("--matter", default=None)
    ap.add_argument("--quiet", action="store_true", help="only print docs whose signals CHANGED")
    ap.add_argument("--force", action="store_true",
                    help="ignore the staleness gate (use after a REGISTRY-only change: new titles/aliases)")
    args = ap.parse_args()
    dry = args.dry_run

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    regs = load_registries(cur)
    known_tcts = [r["tct_number"] for r in regs["tcts"]]   # regs["tcts"] is (tct, case_file) rows since v4
    known_dockets = [m["docket_number"] for m in regs["matters"] if m["docket_number"]] + \
                    [a for m in regs["matters"] for a in (m.get("docket_aliases") or [])]

    where = ["length(coalesce(d.extracted_text,'')) >= %s"]
    params = [MIN_TEXT]
    if not args.force:
        where.append("""( NOT coalesce(d.analyst_memo ? 'ingest_signals', false)                  -- C1 never
                 OR coalesce((d.analyst_memo->'ingest_signals'->>'version')::int, 0) < %s      -- C2 old engine
                 OR d.analyst_memo->'ingest_signals'->>'text_hash' IS DISTINCT FROM md5(d.extracted_text) )""")
        params.append(SIGNALS_VERSION)
    if args.doc_id:
        where.append("d.id = ANY(%s)"); params.append(args.doc_id)
    if args.case_file:
        where.append("d.case_file = %s"); params.append(args.case_file)
    if args.matter:
        where.append("d.matter_code = %s"); params.append(args.matter)
    params.append(args.limit)

    cur.execute(f"""
        SELECT d.id, d.case_file, d.original_filename, d.extracted_text,
               d.analyst_memo->'ingest_signals' AS old_sig,
               -- envelope pools for email-linked docs (subject/body add context text lacks)
               (SELECT string_agg(DISTINCT g.subject, ' | ')
                  FROM email_documents e JOIN gmail_messages g ON g.message_id = e.message_id
                 WHERE e.doc_id = d.id) AS subjects
          FROM documents d
         WHERE {' AND '.join(where)}
         ORDER BY CASE
             WHEN d.matter_code IN (SELECT matter_code FROM matters WHERE status='active') THEN 0
             WHEN d.case_file = 'MWK-001' AND d.document_type ~* 'order|motion|complaint|answer|affidavit|resolution|title|deed' THEN 1
             WHEN d.case_file = 'MWK-001' THEN 2
             ELSE 3 END,
             d.id DESC
         LIMIT %s""", params)
    docs = cur.fetchall()
    mode = "DRY-RUN" if dry else "LIVE"
    print(f"  [reenrich {mode}] {len(docs)} doc(s) need re-enrichment (engine v{SIGNALS_VERSION})\n")

    changed = unchanged = gained_m = gained_t = leads_t = leads_d = bundles = 0
    for d in docs:
        text = d["extracted_text"] or ""
        sig = extract_signals(regs, d["case_file"],
                              {"filename": d["original_filename"], "subject": d["subjects"], "text": text})
        # carry forward ingest-only flags the text pass can't re-derive (cover_message needs the email context)
        if (d["old_sig"] or {}).get("flags", {}).get("cover_message"):
            sig["flags"]["cover_message"] = True
        sig = extract_text_extras(sig, text, known_tcts, known_dockets)
        sig["text_hash"] = hashlib.md5(text.encode()).hexdigest()

        delta = _delta(d["old_sig"], sig)
        if delta in ("unchanged",):
            unchanged += 1
        else:
            changed += 1
            gained_m += 1 if "+matters" in delta else 0
            gained_t += 1 if "+titles" in delta else 0
        leads_t += 1 if sig.get("unknown_titles") else 0
        leads_d += 1 if sig.get("unknown_dockets") else 0
        bundles += 1 if sig["flags"].get("cites_exhibit_series") else 0
        am = apply_enrichment(cur, d["id"], sig, dry)
        if not args.quiet or delta not in ("unchanged",):
            print(f"    doc {d['id']:<5} {(d['original_filename'] or '')[:40]:<42} {delta}"
                  + (f"  →matter_code={am}" if am else ""))

    print(f"\n  Summary [{mode}] (engine v{SIGNALS_VERSION}):")
    print(f"    processed: {len(docs)}   changed: {changed}   unchanged(stamped current): {unchanged}")
    print(f"    docs gaining matter hits: {gained_m}   gaining title hits: {gained_t}")
    print(f"    unknown-TITLE leads: {leads_t} docs   unknown-DOCKET leads: {leads_d} docs")
    print(f"    exhibit-series citers (bundle candidates): {bundles}")
    if dry:
        print("\n  DRY-RUN — nothing written.")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
