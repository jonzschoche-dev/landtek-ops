#!/usr/bin/env python3
"""corpus_integrity_audit.py — is the corpus bullet-proof? Measure it.

Read-only audit across every integrity dimension. Prints a scorecard
(PASS / WARN / FAIL) + the specific defect worklist behind each finding.
Designed to run as a one-shot now and later as a standing sentinel.

Dimensions:
  COMPLETE   every doc reachable (file_path on disk OR drive_file_id)
  READ       every doc has extracted_text; no empty/placeholder shells
  UNIQUE     no duplicate rows (same drive_file_id / content_hash)
  SEARCHABLE embedding coverage in Qdrant; no orphan vectors
  HONEST     OCR honesty flags present; provenance tagged
  LINKED     vault<->digital + doc->title + evidence links resolve to real rows
  EVIDENCE   claims have supporting evidence; no naked claims
"""
from __future__ import annotations
import os, sys
import psycopg2, psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def envk(name):
    v = os.environ.get(name)
    if v:
        return v
    try:
        for line in open("/root/landtek/.env"):
            line = line.strip()
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return None


findings = []  # (dimension, status, headline, detail)


def add(dim, status, headline, detail=""):
    findings.append((dim, status, headline, detail))


def one(cur, sql, args=()):
    cur.execute(sql, args)
    r = cur.fetchone()
    return r[0] if r else None


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("ANALYZE documents")  # defeat stale-stats (we got bitten by this)

    total = one(cur, "SELECT count(*) FROM documents WHERE master_form='digital'")
    add("COMPLETE", "INFO", f"{total} digital documents in corpus")

    # ── COMPLETE: reachability ────────────────────────────────────────────────
    cur.execute("""SELECT id, file_path, drive_file_id,
                          COALESCE(NULLIF(smart_filename,''), original_filename)
                     FROM documents WHERE master_form='digital'""")
    rows = cur.fetchall()
    no_locator, broken_path = [], []
    for did, fp, drive, nm in rows:
        has_disk = bool(fp) and os.path.exists(fp)
        if fp and not has_disk and not drive:
            broken_path.append((did, fp))
        if not (has_disk or drive):
            no_locator.append((did, nm))
    if no_locator:
        add("COMPLETE", "FAIL", f"{len(no_locator)} docs are UNREACHABLE (no working file_path, no drive_file_id)",
            "; ".join(f"#{d}:{(n or '')[:30]}" for d, n in no_locator[:8]))
    else:
        add("COMPLETE", "PASS", "every doc has a working locator (disk or Drive)")
    if broken_path:
        add("COMPLETE", "WARN", f"{len(broken_path)} docs have a file_path that no longer exists on disk (no Drive fallback)",
            "; ".join(f"#{d}" for d, _ in broken_path[:10]))

    # ── READ: extracted_text present + not a shell ───────────────────────────
    empty = one(cur, "SELECT count(*) FROM documents WHERE master_form='digital' AND (extracted_text IS NULL OR length(trim(extracted_text))=0)")
    shells = one(cur, """SELECT count(*) FROM documents WHERE master_form='digital'
                          AND length(coalesce(extracted_text,'')) BETWEEN 1 AND 120""")
    add("READ", "FAIL" if empty else "PASS",
        f"{empty} docs have NO extracted_text (AI is blind to them)" if empty else "every doc has extracted_text")
    if shells:
        add("READ", "WARN", f"{shells} docs have <120 chars of text (possible empty shell / failed OCR)")

    # ── UNIQUE: duplicates ────────────────────────────────────────────────────
    dup_drive = one(cur, """SELECT count(*) FROM (
        SELECT drive_file_id FROM documents WHERE drive_file_id IS NOT NULL
        GROUP BY drive_file_id HAVING count(*)>1) x""")
    add("UNIQUE", "WARN" if dup_drive else "PASS",
        f"{dup_drive} drive_file_ids map to MULTIPLE doc rows (duplicate ingests)" if dup_drive
        else "no duplicate Drive ingests")
    has_hash = one(cur, "SELECT count(*) FROM information_schema.columns WHERE table_name='documents' AND column_name='content_hash'")
    if has_hash:
        dup_hash = one(cur, """SELECT count(*) FROM (SELECT content_hash FROM documents
                                WHERE content_hash IS NOT NULL GROUP BY content_hash HAVING count(*)>1) x""")
        if dup_hash:
            add("UNIQUE", "WARN", f"{dup_hash} content_hashes appear in multiple rows (identical-content dupes)")

    # ── SEARCHABLE: embedding coverage ────────────────────────────────────────
    try:
        from qdrant_client import QdrantClient
        qc = QdrantClient(url=envk("QDRANT_URL"), api_key=envk("QDRANT_KEY"), timeout=30)
        cnt = qc.count(collection_name="landtek_documents", exact=True).count
        embedded = set()
        nxt = None
        while True:
            pts, nxt = qc.scroll(collection_name="landtek_documents", limit=512,
                                 offset=nxt, with_payload=["doc_id_postgres"], with_vectors=False)
            for p in pts:
                d = (p.payload or {}).get("doc_id_postgres")
                if d is not None:
                    embedded.add(int(d))
            if nxt is None:
                break
        live = {r[0] for r in rows}  # digital doc ids from earlier fetch
        cur.execute("SELECT id FROM documents")
        all_ids = {r[0] for r in cur.fetchall()}
        orphans = embedded - all_ids
        covered = len(embedded & live)
        pct = round(100 * covered / total, 1) if total else 0
        status = "PASS" if pct >= 95 else ("WARN" if pct >= 60 else "FAIL")
        add("SEARCHABLE", status,
            f"semantic search covers {pct}% of docs ({covered}/{total}); {cnt} vectors, {len(embedded)} distinct docs",
            f"{total - covered} docs have NO embedding -> invisible to meaning-search")
        if orphans:
            add("SEARCHABLE", "WARN", f"{len(orphans)} ORPHAN vectors (doc_id no longer in corpus)",
                "; ".join(f"#{d}" for d in list(orphans)[:10]))
    except Exception as e:
        add("SEARCHABLE", "FAIL", f"could not audit Qdrant: {type(e).__name__}: {e}")

    # ── HONEST: OCR honesty + provenance ──────────────────────────────────────
    has_chunks = one(cur, "SELECT count(*) FROM information_schema.tables WHERE table_name='extraction_chunks'")
    if has_chunks:
        cur.execute("SELECT coalesce(field_status,'(null)'), count(*) FROM extraction_chunks GROUP BY 1 ORDER BY 2 DESC")
        dist = cur.fetchall()
        total_chunks = sum(c for _, c in dist)
        flagged = sum(c for s, c in dist if s in ("illegible", "partial", "requires_heightened_ocr"))
        add("HONEST", "INFO", f"{total_chunks} extraction chunks; field_status: " +
            ", ".join(f"{s}={c}" for s, c in dist[:6]))
        if total_chunks and flagged == 0:
            add("HONEST", "WARN", "ZERO chunks flagged illegible/partial/requires_heightened_ocr — "
                "OCR-honesty contract not yet applied to existing extractions (re-run needed)")
        ver = one(cur, "SELECT count(*) FROM extraction_chunks WHERE provenance_level='verified'")
        add("HONEST", "INFO", f"{ver}/{total_chunks} chunks are provenance=verified ({round(100*ver/total_chunks,1) if total_chunks else 0}%)")

    # ── LINKED: vault + doc->title + evidence resolve ────────────────────────
    bad_vault = one(cur, """SELECT count(*) FROM documents v WHERE v.master_form='physical'
        AND v.digital_scan_id IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM documents d WHERE d.id=v.digital_scan_id)""")
    add("LINKED", "FAIL" if bad_vault else "PASS",
        f"{bad_vault} vault entries point to a NON-EXISTENT digital doc" if bad_vault
        else "all vault->digital links resolve")
    physical = one(cur, "SELECT count(*) FROM documents WHERE master_form='physical' AND vault_section IS NOT NULL")
    unscanned = one(cur, """SELECT count(*) FROM documents WHERE master_form='physical' AND vault_section IS NOT NULL
                             AND digital_scan_id IS NULL""")
    if unscanned:
        add("LINKED", "WARN", f"{unscanned}/{physical} vault entries have NO digital scan linked yet")
    junk_titles = one(cur, """SELECT count(*) FROM document_titles dt
        WHERE NOT EXISTS (SELECT 1 FROM titles t WHERE t.tct_number=dt.tct_number)""")
    add("LINKED", "FAIL" if junk_titles else "PASS",
        f"{junk_titles} doc->title links point to an UNKNOWN title" if junk_titles
        else "all doc->title links resolve to known titles")

    # ── EVIDENCE: claims supported ────────────────────────────────────────────
    naked = one(cur, """SELECT count(*) FROM claims c WHERE c.status='open'
        AND NOT EXISTS (SELECT 1 FROM evidence_trail e WHERE e.claim_id=c.id)""")
    nclaims = one(cur, "SELECT count(*) FROM claims")
    add("EVIDENCE", "WARN" if naked else "PASS",
        f"{naked}/{nclaims} open claims have ZERO confirmed evidence" if naked
        else f"all {nclaims} claims have confirmed evidence")

    # ── scorecard ─────────────────────────────────────────────────────────────
    cur.close(); conn.close()
    order = {"FAIL": 0, "WARN": 1, "PASS": 2, "INFO": 3}
    icon = {"FAIL": "❌", "WARN": "⚠️ ", "PASS": "✅", "INFO": "··"}
    fails = sum(1 for _, s, _, _ in findings if s == "FAIL")
    warns = sum(1 for _, s, _, _ in findings if s == "WARN")
    print("\n" + "=" * 72)
    print(f" CORPUS INTEGRITY AUDIT   —   {fails} FAIL · {warns} WARN")
    print("=" * 72)
    for dim, st, head, det in sorted(findings, key=lambda f: (order[f[1]], f[0])):
        print(f"{icon[st]} [{dim:10}] {head}")
        if det:
            print(f"            └ {det}")
    verdict = "NOT bullet-proof — FAILs must be cleared" if fails else \
              ("hardening needed — clear the WARNs" if warns else "BULLET-PROOF ✅")
    print("=" * 72)
    print(f" VERDICT: {verdict}")
    print("=" * 72)


if __name__ == "__main__":
    main()
