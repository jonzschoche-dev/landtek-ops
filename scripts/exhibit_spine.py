#!/usr/bin/env python3
"""exhibit_spine.py — populate the composition layer's exhibit spine from labeled attachment filenames.

Turns the ingest significance engine's `composition_candidate` docs (deploy_809) into REAL composition rows:
a case_thread (thread_type='filing') per filing, with case_thread_documents carrying exhibit_label + order_seq
— the structure case_bundle.py binds and the V9/V10 guards (deploy_808, ENFORCED) protect.

GROUPING (deterministic, filename-grounded — a filing's exhibits are split across sibling emails, so email
grouping alone fragments; the filename itself names its parent filing):
  Pass A — "Exhibit A - Complaint - Civil Case No. 26-360.pdf" → label 'A', parent hint 'Complaint - Civil
           Case No. 26-360' (hint must contain a FILING keyword; else it's the annex's own title, not a parent).
  Pass B — label docs without a parent hint (e.g. 'Annex 1 - Special Power of Attorney.pdf') group with the
           FILING-keyword doc that co-traveled in the same email (the Answer, the Motion, …).
  Unplaceable label docs are LISTED, never guessed into a filing.

RULES:
  • [DRAFT]-named docs are EXCLUDED (received-not-draft doctrine) — a filing binds what was submitted.
  • Idempotent: thread matched by (parent_case_file, thread_name); ctd insert ON CONFLICT DO NOTHING.
  • case_threads.finalized_at is NOT set here — labeling is filename-derived and operator-reviewable first;
    finalizing (which freezes composition under V10) is a human decision.
  • V9 (A54 client-scope) fires on every insert — a cross-client bind would be REJECTED by the DB, by design.

USAGE: python3 scripts/exhibit_spine.py [--dry] [--limit N]
"""
import argparse, re, sys
import psycopg2, psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# Label = letter/number with optional compound suffix ('A-1', '1-A', 'B to B-4'); trailing '- <parent>' optional
# ('ANNEX A-1.jpg' has no parent segment). Matched against the extension-stripped stem.
LABEL_RE = re.compile(r"^\s*(Exhibit|Annex)\s+([A-Z]{1,2}(?:-\d{1,3})?|\d{1,3}(?:-[A-Z])?)"
                      r"(?:\s+to\s+[A-Za-z0-9-]+)?\s*(?:[-–—]\s*(.*))?$", re.IGNORECASE)
FILING_KW = re.compile(r"\b(complaint|answer|motion|manifestation|reply|petition|counter[- ]?affidavit"
                       r"|position paper|comment|opposition|memorandum|request)\b", re.IGNORECASE)
DRAFT_RE = re.compile(r"\[\s*draft\s*\]", re.IGNORECASE)


def _stem(fn):
    return re.sub(r"\.(pdf|docx?|zip|jpe?g|png|xlsx?)$", "", (fn or "").strip(), flags=re.IGNORECASE)


def _normkey(s):
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9 .-]", " ", s or "")).upper().strip(" .-")


def _label_sort(label):
    """Natural exhibit order: numeric series (1, 1-A, 2 …) before letter series (A, A-1, B …),
    compound suffixes ordered within their parent label."""
    m = re.match(r"^(\d+)(?:-([A-Z]))?$", label)
    if m:
        return (0, int(m.group(1)), m.group(2) or "")
    m = re.match(r"^([A-Z]+)(?:-(\d+))?$", label)
    if m:
        return (1, m.group(1), int(m.group(2) or 0))
    return (2, label, 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--limit", type=int, default=500)
    args = ap.parse_args()

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # All email-linked docs (labels + potential mains travel by email), with their email ids.
    cur.execute("""
        SELECT d.id, d.case_file, d.original_filename AS fn,
               array_agg(DISTINCT g.id) AS email_ids
          FROM documents d
          JOIN email_documents e ON e.doc_id = d.id
          JOIN gmail_messages g  ON g.message_id = e.message_id
         WHERE d.original_filename IS NOT NULL
         GROUP BY d.id ORDER BY d.id LIMIT %s""", (args.limit,))
    docs = cur.fetchall()
    by_email = {}
    for d in docs:
        for eid in d["email_ids"]:
            by_email.setdefault(eid, []).append(d)

    filings = {}      # key -> {"case_file","title","main":doc|None,"exhibits":[(label, doc)]}
    unplaced = []

    for d in docs:
        m = LABEL_RE.match(_stem(d["fn"]))
        if not m or DRAFT_RE.search(d["fn"]):
            continue
        label, rest = m.group(2).upper(), (m.group(3) or "").strip()
        key = title = main = None
        if rest and FILING_KW.search(rest):             # Pass A: the filename names its parent filing
            key, title = (d["case_file"], _normkey(rest)), rest
        else:                                           # Pass B: co-traveling filing doc in the same email
            for eid in d["email_ids"]:
                for sib in by_email.get(eid, []):
                    if sib["id"] == d["id"] or DRAFT_RE.search(sib["fn"]) or LABEL_RE.match(_stem(sib["fn"])):
                        continue
                    if FILING_KW.search(sib["fn"]):
                        key, title, main = (sib["case_file"], _normkey(_stem(sib["fn"]))), _stem(sib["fn"]), sib
                        break
                if key:
                    break
        if not key:
            unplaced.append(d)
            continue
        f = filings.setdefault(key, {"case_file": key[0], "title": title, "main": None, "exhibits": []})
        if main and not f["main"]:
            f["main"] = main
        f["exhibits"].append((label, d))

    # Resolve Pass-A mains: a non-label, non-draft doc whose stem is a prefix of the filing key (COMPLAINT.pdf).
    for key, f in filings.items():
        if f["main"]:
            continue
        for d in docs:
            if LABEL_RE.match(_stem(d["fn"])) or DRAFT_RE.search(d["fn"]) or d["case_file"] != f["case_file"]:
                continue
            stem = _normkey(_stem(d["fn"]))
            if stem and (key[1].startswith(stem) or stem.startswith(key[1])) and len(stem) >= 6:
                f["main"] = d
                break

    mode = "DRY-RUN" if args.dry else "LIVE"
    print(f"  [exhibit-spine {mode}] {len(filings)} filing(s) from {sum(len(f['exhibits']) for f in filings.values())} labeled docs\n")

    made_threads = made_rows = 0
    for key, f in sorted(filings.items()):
        thread_name = f"Filing: {f['title'][:80]}"
        print(f"  ◆ {thread_name}  [{f['case_file']}]")
        exhibits = sorted(set((l, d["id"], d["fn"]) for l, d in f["exhibits"]), key=lambda x: _label_sort(x[0]))
        if f["main"]:
            print(f"      main    doc {f['main']['id']:<5} {f['main']['fn'][:56]}")
        for i, (label, did, fn) in enumerate(exhibits, start=1):
            print(f"      {label:<7} doc {did:<5} {fn[:56]}")
        if args.dry:
            continue
        cur.execute("SELECT id FROM case_threads WHERE parent_case_file=%s AND thread_name=%s",
                    (f["case_file"], thread_name))
        row = cur.fetchone()
        if row:
            tid = row["id"]
        else:
            cur.execute("""INSERT INTO case_threads (parent_case_file, thread_name, thread_type, status, summary)
                           VALUES (%s, %s, 'filing', 'open',
                                   'Exhibit spine auto-built from labeled attachment filenames (exhibit_spine.py); operator-reviewable; NOT finalized.')
                           RETURNING id""", (f["case_file"], thread_name))
            tid = cur.fetchone()["id"]; made_threads += 1
        if f["main"]:
            cur.execute("""INSERT INTO case_thread_documents (thread_id, doc_id, role, linked_by, order_seq)
                           VALUES (%s, %s, 'filing_main', 'exhibit_spine.py', 0)
                           ON CONFLICT (thread_id, doc_id, role) DO NOTHING""", (tid, f["main"]["id"]))
            made_rows += cur.rowcount
        for i, (label, did, fn) in enumerate(exhibits, start=1):
            cur.execute("""INSERT INTO case_thread_documents (thread_id, doc_id, role, linked_by, exhibit_label, order_seq)
                           VALUES (%s, %s, 'exhibit', 'exhibit_spine.py', %s, %s)
                           ON CONFLICT (thread_id, doc_id, role) DO NOTHING""", (tid, did, label, i))
            made_rows += cur.rowcount

    if unplaced:
        print(f"\n  ⚠ {len(unplaced)} labeled doc(s) UNPLACED (no parent filing resolvable — listed, never guessed):")
        for d in unplaced[:12]:
            print(f"      doc {d['id']:<5} {d['fn'][:60]}")
    if not args.dry:
        print(f"\n  Created: {made_threads} filing thread(s), {made_rows} new exhibit row(s).")
    else:
        print("\n  DRY-RUN — nothing written.")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
