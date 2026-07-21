#!/usr/bin/env python3
"""classify_client.py — deterministic CLIENT classification for unfiled docs (the durable filing layer).

The scanner backlog piled up unfiled because the deterministic filer only matched DOCKETS and TITLE NUMBERS —
it never used the distinctive CLIENT principals ("Mary Worrick Keesey", "Inocalla", "Northern Island Builders")
that identify which client a document belongs to. This closes that gap: it scans each unfiled document's text +
filename for the client-identifying terms in `case_keywords` and assigns `case_file` when exactly ONE client
matches. Zero or MULTIPLE client matches → routed to PENDING_TRIAGE (flagged for a human), NEVER guessed.

Why the multi-match→flag rule is A5-safe: the families share parties (Inocallas were affiants on Patricia
Keesey's birth record — [[feedback-client-separation-place-keyword-leak]]). A doc carrying BOTH an MWK term
AND a Paracale term is exactly the ambiguous case that must not be auto-filed — so two client hits = flag, not
a coin-flip. A doc with only one client's distinctive terms is unambiguous → filed.

Separation of layers: this sets CLIENT (case_file) only. `reenrich.py` still owns MATTER (matter_code) via
docket-exact match. Client and matter are independent — a doc can be client-filed with matter still refining.

Idempotent · deterministic · $0 (no LLM). Records evidence in analyst_memo.client_classification.

USAGE:
  python3 scripts/classify_client.py [--dry-run] [--limit N] [--doc-id N ...]
  python3 scripts/classify_client.py --file <doc_id> <case_file> [matter_code]   # operator one-click file
"""
import argparse, json, re, sys
import psycopg2, psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
MIN_TEXT = 40
TEXT_CAP = 200_000
CLASSIFIER_VERSION = 1
# buckets that are destinations, never classification TARGETS
NON_CLIENT = {"PENDING_TRIAGE", "Archive", "Owner"}


def load_keywords(cur):
    """case_keywords → {case_file: [(kw_lower, kw_original), ...]} for real client targets only."""
    cur.execute("SELECT case_file, keyword FROM case_keywords WHERE keyword IS NOT NULL")
    kw = {}
    for r in cur.fetchall():
        cf = r["case_file"]
        if cf in NON_CLIENT:
            continue
        kw.setdefault(cf, []).append((r["keyword"].lower().strip(), r["keyword"]))
    return kw


def classify_text(kw, text):
    """Return {case_file: [matched_keywords]} for every client with a distinctive hit."""
    t = re.sub(r"\s+", " ", (text or "")[:TEXT_CAP]).lower()
    hits = {}
    for cf, terms in kw.items():
        m = [orig for low, orig in terms if len(low) >= 3 and low in t]
        if m:
            hits[cf] = sorted(set(m))
    return hits


def _record(cur, doc_id, assigned, hits, reason, dry):
    payload = {"version": CLASSIFIER_VERSION, "assigned": assigned, "reason": reason,
               "matched": hits}
    if dry:
        return
    if assigned:
        cur.execute("""UPDATE documents
                          SET case_file = %s,
                              analyst_memo = coalesce(analyst_memo,'{}'::jsonb)
                                             || jsonb_build_object('client_classification', %s::jsonb)
                        WHERE id = %s AND case_file IS NULL""",
                    (assigned, json.dumps(payload), doc_id))
    else:  # flag → PENDING_TRIAGE (only from NULL; don't re-stamp an already-triaged row)
        cur.execute("""UPDATE documents
                          SET case_file = 'PENDING_TRIAGE',
                              analyst_memo = coalesce(analyst_memo,'{}'::jsonb)
                                             || jsonb_build_object('client_classification', %s::jsonb)
                        WHERE id = %s AND case_file IS NULL""",
                    (json.dumps(payload), doc_id))


def run(cur, dry, limit, doc_ids):
    kw = load_keywords(cur)
    where = ["case_file IS NULL", "length(coalesce(extracted_text,'')) >= %s"]
    params = [MIN_TEXT]
    if doc_ids:
        where.append("id = ANY(%s)"); params.append(doc_ids)
    params.append(limit)
    cur.execute(f"""SELECT id, original_filename, extracted_text
                      FROM documents WHERE {' AND '.join(where)}
                     ORDER BY id LIMIT %s""", params)
    docs = cur.fetchall()
    mode = "DRY-RUN" if dry else "LIVE"
    print(f"  [classify-client {mode}] {len(docs)} unfiled doc(s) with text\n")
    filed = flagged_none = flagged_multi = 0
    for d in docs:
        blob = (d["original_filename"] or "") + " \n " + (d["extracted_text"] or "")
        hits = classify_text(kw, blob)
        clients = list(hits)
        if len(clients) == 1:
            cf = clients[0]
            _record(cur, d["id"], cf, hits, "single_client", dry)
            filed += 1
            print(f"    doc {d['id']:<5} → {cf:<13} via {hits[cf][:4]}")
        elif not clients:
            _record(cur, d["id"], None, hits, "no_client_signal", dry)
            flagged_none += 1
            print(f"    doc {d['id']:<5} ⚑ PENDING_TRIAGE (no client signal)")
        else:
            _record(cur, d["id"], None, hits, "multi_client:" + ",".join(sorted(clients)), dry)
            flagged_multi += 1
            print(f"    doc {d['id']:<5} ⚑ PENDING_TRIAGE (AMBIGUOUS: {', '.join(sorted(clients))} — A5, never guessed)")
    print(f"\n  Summary [{mode}]: filed {filed} · flagged-no-signal {flagged_none} · flagged-ambiguous {flagged_multi}")
    if dry:
        print("  DRY-RUN — nothing written.")


def file_one(cur, doc_id, case_file, matter):
    cur.execute("""UPDATE documents SET case_file=%s, matter_code=coalesce(%s, matter_code),
                          analyst_memo = coalesce(analyst_memo,'{}'::jsonb)
                                         || jsonb_build_object('client_classification',
                                              jsonb_build_object('assigned',%s,'reason','operator_filed'))
                    WHERE id=%s""", (case_file, matter, case_file, doc_id))
    print(f"  ✓ doc {doc_id} filed → {case_file}" + (f" / {matter}" if matter else "") + f" ({cur.rowcount} row)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--doc-id", type=int, action="append", default=None)
    ap.add_argument("--file", nargs="+", metavar=("DOC_ID CASE_FILE", "MATTER"),
                    help="operator one-click: --file <doc_id> <case_file> [matter_code]")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if args.file:
        if len(args.file) < 2:
            print("usage: --file <doc_id> <case_file> [matter_code]"); sys.exit(1)
        file_one(cur, int(args.file[0]), args.file[1], args.file[2] if len(args.file) > 2 else None)
    else:
        run(cur, args.dry_run, args.limit, args.doc_id)
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
