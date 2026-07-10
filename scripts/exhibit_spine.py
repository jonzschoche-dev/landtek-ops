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
import argparse, json, re, sys
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


# ─────────────────────────────────────────────────────────────────────────────────────────────
# SUGGESTIONS v2 (deploy_826) — operator-gated proposals from the significance engine's
# composition signals. A filing-main candidate = a doc whose TEXT cites an exhibit-label series
# (flags.cites_exhibit_series + references_exhibits, deploy_812). Its cited labels are reconciled
# against labeled sibling docs from the SAME email thread (v_thread_continuity) + same case_file.
# Output = rows in exhibit_spine_proposals, NEVER direct case_thread_documents writes; --apply <id>
# inserts through the ENFORCED V9 (A54) gate. Labels cited-but-absent are GAPS = missing-evidence
# leads (a finding, not a defect). Bodies flagged cover_message join as proposed role='cover'.
# ─────────────────────────────────────────────────────────────────────────────────────────────

WORD_DRAFT_RE = re.compile(r"\bdraft\b", re.IGNORECASE)   # received-not-draft: word-level for main candidates


def suggest(cur, dry, limit):
    cur.execute("""
        SELECT d.id, d.case_file, d.matter_code, d.original_filename AS fn,
               length(coalesce(d.extracted_text,'')) AS text_len,
               d.analyst_memo->'ingest_signals'->'references_exhibits' AS refs
          FROM documents d
         WHERE d.analyst_memo->'ingest_signals'->'flags' ? 'cites_exhibit_series'
           AND coalesce(d.ingest_source,'') <> 'gmail_body'
           AND NOT EXISTS (SELECT 1 FROM case_thread_documents c
                            WHERE c.doc_id = d.id AND c.role = 'filing_main')
           AND NOT EXISTS (SELECT 1 FROM exhibit_spine_proposals p
                            WHERE p.main_doc_id = d.id AND p.status IN ('pending','applied'))
         ORDER BY d.id LIMIT %s""", (limit,))
    cands = cur.fetchall()
    mode = "DRY-RUN" if dry else "LIVE"
    made = skipped_draft = skipped_label = skipped_noctx = 0
    gap_index = {}   # label -> [citing main ids]
    print(f"  [suggest {mode}] {len(cands)} filing-main candidate(s)\n")

    for m in cands:
        stem = _stem(m["fn"] or "")
        if not stem:
            continue                                        # nameless doc can't title a filing proposal
        if WORD_DRAFT_RE.search(m["fn"] or ""):
            skipped_draft += 1; continue                    # drafts never become proposed filings
        if LABEL_RE.match(stem):
            skipped_label += 1; continue                    # an exhibit citing its sub-parts is not a main
        refs = [str(r).upper() for r in (m["refs"] or [])]
        if not refs:
            continue
        # Pool 1 — same gmail thread (v_thread_continuity), same case_file
        cur.execute("""
            SELECT DISTINCT v.sibling_doc_id AS doc_id, v.sibling_role AS role, d2.original_filename AS fn,
                   coalesce((d2.analyst_memo->'ingest_signals'->'flags' ? 'cover_message'), false) AS is_cover
              FROM v_thread_continuity v JOIN documents d2 ON d2.id = v.sibling_doc_id
             WHERE v.doc_id = %s AND v.sibling_doc_id <> %s AND d2.case_file = %s""",
            (m["id"], m["id"], m["case_file"]))
        sibs = cur.fetchall()
        # Pool 2 — same MATTER (docket-exact-derived matter_code equality; deterministic, client-safe):
        # exhibits often travel in a different email than the filing that cites them.
        if m["matter_code"]:
            cur.execute("""
                SELECT d2.id AS doc_id, 'attachment' AS role, d2.original_filename AS fn, false AS is_cover
                  FROM documents d2
                 WHERE d2.matter_code = %s AND d2.case_file = %s AND d2.id <> %s
                   AND d2.original_filename ~* '^\\s*(exhibit|annex)\\s'""",
                (m["matter_code"], m["case_file"], m["id"]))
            sibs += cur.fetchall()
        if not sibs:
            skipped_noctx += 1; continue                    # no groundable context to match against

        matched, covers, seen = [], [], set()
        for s in sibs:
            if DRAFT_RE.search(s["fn"] or ""):
                continue
            lm = LABEL_RE.match(_stem(s["fn"] or ""))
            if s["role"] == "attachment" and lm and lm.group(2).upper() in refs and s["doc_id"] not in seen:
                matched.append((lm.group(2).upper(), s["doc_id"], s["fn"])); seen.add(s["doc_id"])
            elif s["role"] == "body" and s["is_cover"] and s["doc_id"] not in seen:
                covers.append((s["doc_id"], s["fn"])); seen.add(s["doc_id"])
        gaps = sorted(set(refs) - {l for l, _, _ in matched}, key=_label_sort)
        # BUNDLE HINT: a long main whose cited labels are unmatched likely BINDS its annexes internally →
        # the right home is document_parts (page ranges), and its "gaps" are NOT missing evidence.
        bundle_hint = bool(gaps) and (m["text_len"] or 0) > 30_000
        if not bundle_hint:                                 # bundle-internal labels are not missing evidence
            for g in gaps:
                gap_index.setdefault(g, []).append(m["id"])

        members = [{"doc_id": m["id"], "role": "filing_main", "label": None, "order_seq": 0,
                    "fn": (m["fn"] or "")[:80]}]
        for i, (lab, did, fn) in enumerate(sorted(matched, key=lambda x: _label_sort(x[0])), start=1):
            members.append({"doc_id": did, "role": "exhibit", "label": lab, "order_seq": i, "fn": fn[:80]})
        for j, (did, fn) in enumerate(covers, start=len(members)):
            members.append({"doc_id": did, "role": "cover", "label": None, "order_seq": j, "fn": fn[:80]})

        basis = (f"doc {m['id']} text cites {len(refs)} exhibit label(s); matched {len(matched)} "
                 f"(email-thread siblings + same-matter '{m['matter_code'] or '-'}' labeled docs); "
                 f"{len(covers)} cover message(s); {len(gaps)} cited-but-absent"
                 + (" [BUNDLE HINT: long doc, unmatched labels likely bound INSIDE it → document_parts, "
                    "not missing evidence]" if bundle_hint else " (missing-evidence leads)"))
        tname = f"Filing: {stem[:80]}"
        print(f"  ◆ #{m['id']:<5} {tname[:64]}")
        print(f"      matched {len(matched)}/{len(refs)} labels · {len(covers)} cover(s)"
              + (" · BUNDLE?" if bundle_hint else "")
              + (f" · GAPS: {','.join(gaps[:12])}{'…' if len(gaps) > 12 else ''}" if gaps else ""))
        if not dry:
            cur.execute("""INSERT INTO exhibit_spine_proposals
                             (main_doc_id, case_file, thread_name, proposed_members, gaps, basis)
                           VALUES (%s, %s, %s, %s, %s, %s)
                           ON CONFLICT (main_doc_id) DO NOTHING""",
                        (m["id"], m["case_file"], tname, json.dumps(members),
                         json.dumps(gaps), basis))
            made += cur.rowcount

    print(f"\n  Summary [{mode}]: proposals {'previewed' if dry else 'created'}: "
          f"{made if not dry else len(cands) - skipped_draft - skipped_label - skipped_noctx}")
    print(f"    skipped: {skipped_draft} draft-named · {skipped_label} label-docs · {skipped_noctx} no email context")
    if gap_index:
        top = sorted(gap_index.items(), key=lambda kv: -len(kv[1]))[:10]
        print("    top missing-exhibit leads (label ← citing filings):")
        for lab, mains in top:
            print(f"      {lab:<7} cited by doc(s) {', '.join(map(str, mains[:6]))}")


def list_pending(cur):
    cur.execute("""SELECT id, main_doc_id, case_file, thread_name,
                          jsonb_array_length(proposed_members) AS members,
                          coalesce(jsonb_array_length(gaps),0) AS gaps, status
                     FROM exhibit_spine_proposals ORDER BY status, id""")
    for r in cur.fetchall():
        print(f"  [{r['status']:<8}] #{r['id']:<4} main={r['main_doc_id']:<5} {r['members']} member(s), "
              f"{r['gaps']} gap(s)  {r['thread_name'][:58]}  [{r['case_file']}]")


def apply_proposal(cur, pid):
    cur.execute("SELECT * FROM exhibit_spine_proposals WHERE id=%s AND status='pending'", (pid,))
    p = cur.fetchone()
    if not p:
        print(f"  no PENDING proposal #{pid}"); return
    cur.execute("SELECT id FROM case_threads WHERE parent_case_file=%s AND thread_name=%s",
                (p["case_file"], p["thread_name"]))
    row = cur.fetchone()
    if row:
        tid = row["id"]
    else:
        cur.execute("""INSERT INTO case_threads (parent_case_file, thread_name, thread_type, status, summary)
                       VALUES (%s, %s, 'filing', 'open', %s) RETURNING id""",
                    (p["case_file"], p["thread_name"],
                     f"Applied from exhibit_spine_proposals #{pid} (operator-approved). {p['basis']}"))
        tid = cur.fetchone()["id"]
    n = 0
    for mem in p["proposed_members"]:      # inserts pass THROUGH the enforced V9 (A54) gate
        cur.execute("""INSERT INTO case_thread_documents
                         (thread_id, doc_id, role, linked_by, exhibit_label, order_seq)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT (thread_id, doc_id, role) DO NOTHING""",
                    (tid, mem["doc_id"], mem["role"], f"exhibit_spine.py --apply {pid}",
                     mem.get("label"), mem.get("order_seq")))
        n += cur.rowcount
    cur.execute("""UPDATE exhibit_spine_proposals
                      SET status='applied', decided_at=now(), applied_thread_id=%s WHERE id=%s""", (tid, pid))
    print(f"  ✓ proposal #{pid} applied → thread {tid} ({n} new row(s)). Gaps remain leads: {p['gaps']}")


def reject_proposal(cur, pid):
    cur.execute("""UPDATE exhibit_spine_proposals SET status='rejected', decided_at=now()
                    WHERE id=%s AND status='pending'""", (pid,))
    print(f"  {'✓ rejected' if cur.rowcount else 'no pending proposal'} #{pid}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--suggest", action="store_true", help="v2: generate operator-gated proposals")
    ap.add_argument("--list", action="store_true", help="v2: list proposals")
    ap.add_argument("--apply", type=int, default=None, metavar="ID", help="v2: apply proposal ID (via V9 gate)")
    ap.add_argument("--reject", type=int, default=None, metavar="ID", help="v2: reject proposal ID")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if args.suggest:
        suggest(cur, args.dry, args.limit); cur.close(); conn.close(); return
    if args.list:
        list_pending(cur); cur.close(); conn.close(); return
    if args.apply is not None:
        apply_proposal(cur, args.apply); cur.close(); conn.close(); return
    if args.reject is not None:
        reject_proposal(cur, args.reject); cur.close(); conn.close(); return

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
