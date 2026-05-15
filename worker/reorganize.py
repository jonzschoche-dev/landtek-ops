"""Periodic reorganization auditor.

Runs weekly (or on-demand). Identifies and proposes (or auto-executes for
high-confidence) improvements to file organization:
  1. Re-classification of low-confidence or stale docs against current case intel
  2. Misfiled subfolder detection (rule-based)
  3. Late-duplicate detection (text_hash collisions)
  4. Version-chain backfill (embedding-similarity draft/executed pairs)
  5. Schema-creep proposals (subfolders that need splitting)
  6. Filename harmonization
  7. Stale Unclassified review

Modes:
  --report-only   (default) generate report + queue pending_questions, no changes
  --apply         execute queued auto-eligible changes, with full audit_log

Auto-execute boundary (see TASK_GUIDE for full table):
  - Reclassify with conf delta > 0.2 AND new conf > 0.9
  - Move from Unclassified to specific case (conf > 0.9)
  - Filename harmonization
  - Entity merges with similarity > 0.95
NEVER auto-executed: cross-case moves, new subfolder creation, low-conf changes
"""
from __future__ import annotations
import sys, json, hashlib, re, argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict, Counter
sys.path.insert(0, str(Path(__file__).parent))

from config import (PG_HOST, PG_PORT, PG_DATABASE, PG_USER, PG_PASSWORD,
                    OPENAI_API_KEY, GEMINI_API_KEY, QDRANT_URL, QDRANT_KEY)
from ingest_v5 import (classify_with_gpt4o, embed_text, determine_subfolder,
                       SUBFOLDER_RULES, CASE_ENTITY_HINTS, consistency_check,
                       enforce_filename, load_folders, get_drive_service)


CONF_AUTO_RECLASSIFY = 0.90
CONF_DELTA_AUTO = 0.20
RECLASSIFY_AGE_DAYS = 30
SCHEMA_CREEP_THRESHOLD = 30   # > N files in one subfolder triggers proposal review
ENTITY_AUTO_MERGE_SIMILARITY = 0.95


def pg_conn():
    import psycopg2
    return psycopg2.connect(host=PG_HOST, port=PG_PORT, dbname=PG_DATABASE,
                            user=PG_USER, password=PG_PASSWORD)


def log(m): print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}", flush=True)


# ============================================================================
# Audit 1: re-classification candidates
# ============================================================================
def audit_reclassification(report, apply_mode, drive_service, folders, known_cases):
    log("Audit 1: re-classification candidates")
    conn = pg_conn(); cur = conn.cursor()
    cutoff = datetime.now(timezone.utc) - timedelta(days=RECLASSIFY_AGE_DAYS)
    cur.execute("""
        SELECT id, case_file, smart_filename, document_title, classification,
               confidence, extracted_text, last_seen_at
        FROM documents
        WHERE (confidence IS NULL OR confidence < 0.85 OR last_seen_at < %s)
          AND extracted_text IS NOT NULL AND length(extracted_text) > 100
        ORDER BY confidence ASC NULLS FIRST
        LIMIT 50
    """, (cutoff,))
    rows = cur.fetchall(); cur.close(); conn.close()
    log(f"  candidates: {len(rows)}")

    proposals, autos = [], []
    for row in rows:
        doc_id, old_case, smart_name, title, doc_type, old_conf, text, last_seen = row
        try:
            cls = classify_with_gpt4o(text, smart_name or title or f"doc_{doc_id}", known_cases)
        except Exception as e:
            log(f"  doc {doc_id}: classify failed: {e}"); continue
        new_case = cls.get("case_file", "Unknown")
        new_conf = float(cls.get("case_file_confidence", 0))
        new_type = cls.get("document_type", "Other")
        old_conf_v = float(old_conf or 0)
        delta = new_conf - old_conf_v
        if new_case == old_case and new_type == doc_type:
            continue
        verdict = "propose"
        if (new_case == old_case and new_type != doc_type
            and new_conf >= 0.85):
            # type change only — safer to auto for filing purposes
            verdict = "auto" if new_conf >= CONF_AUTO_RECLASSIFY else "propose"
        elif (new_case != old_case and new_case in known_cases
              and new_conf >= CONF_AUTO_RECLASSIFY and delta >= CONF_DELTA_AUTO
              and (old_case == "Unknown" or old_case == "Unclassified")):
            verdict = "auto"
        elif new_case != old_case and new_case in known_cases:
            verdict = "propose"     # cross-case moves never auto
        entry = {"doc_id": doc_id, "smart_name": smart_name,
                 "old_case": old_case, "new_case": new_case,
                 "old_type": doc_type, "new_type": new_type,
                 "old_conf": old_conf_v, "new_conf": new_conf,
                 "delta": delta, "reasoning": cls.get("case_file_reasoning"),
                 "verdict": verdict}
        (autos if verdict == "auto" else proposals).append(entry)

    log(f"  → {len(autos)} auto-eligible, {len(proposals)} for review")
    if apply_mode and autos:
        for a in autos:
            apply_reclassification(a, drive_service, folders)
    report["reclassification"] = {"auto": autos, "propose": proposals}


def apply_reclassification(a, drive_service, folders):
    """Update documents row + (if drive_service) move file in Drive."""
    conn = pg_conn(); cur = conn.cursor()
    cur.execute("""SELECT case_file, classification, smart_filename FROM documents WHERE id = %s""",
                (a["doc_id"],))
    before = cur.fetchone()
    cur.execute("""UPDATE documents SET case_file = %s, classification = %s,
                    confidence = %s, updated_at = NOW() WHERE id = %s""",
                (a["new_case"], a["new_type"], a["new_conf"], a["doc_id"]))
    cur.execute("""INSERT INTO audit_log
        (actor, actor_type, action, target_type, target_id, before_state, after_state)
        VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)""",
        ("reorganize", "worker", "reclassify_auto", "documents", str(a["doc_id"]),
         json.dumps({"case_file": before[0], "classification": before[1], "smart_filename": before[2]}),
         json.dumps(a, default=str)))
    conn.commit(); cur.close(); conn.close()
    log(f"  ✓ auto-reclassified doc {a['doc_id']}: {a['old_case']}→{a['new_case']} ({a['old_type']}→{a['new_type']})")


# ============================================================================
# Audit 2: misfiled subfolder (drive-side rule mismatch)
# ============================================================================
def audit_misfiled(report, apply_mode, drive_service, folders):
    log("Audit 2: subfolder misfile detection")
    if not drive_service:
        log("  no drive service — skipping"); return
    mismatches = []
    conn = pg_conn(); cur = conn.cursor()
    cur.execute("""SELECT id, case_file, smart_filename, classification
                   FROM documents
                   WHERE case_file IN (SELECT case_file FROM cases) AND classification IS NOT NULL""")
    rows = cur.fetchall(); cur.close(); conn.close()
    for doc_id, case_file, smart_name, doc_type in rows:
        case_map = folders.get(case_file)
        if not case_map: continue
        expected_sub = determine_subfolder(doc_type)
        expected_folder_id = case_map.get(expected_sub) or case_map.get("default")
        # Find file in Drive by name+case
        try:
            resp = drive_service.files().list(
                q=f"name='{(smart_name or '').replace(chr(39),chr(92)+chr(39))}' and trashed=false",
                fields="files(id,name,parents)",
                supportsAllDrives=True, includeItemsFromAllDrives=True,
            ).execute()
        except Exception:
            continue
        for f in resp.get("files", []):
            actual_parent = (f.get("parents") or [None])[0]
            if actual_parent and actual_parent != expected_folder_id:
                mismatches.append({"doc_id": doc_id, "smart_name": smart_name,
                                   "case_file": case_file,
                                   "actual_folder_id": actual_parent,
                                   "expected_folder_id": expected_folder_id,
                                   "expected_sub": expected_sub,
                                   "drive_file_id": f["id"]})
    log(f"  misfiled: {len(mismatches)}")
    report["misfiled"] = mismatches
    # Misfiled corrections: always proposed, never auto (user approves)


# ============================================================================
# Audit 3: late-duplicate detection (text_hash)
# ============================================================================
def audit_duplicates(report):
    log("Audit 3: late-duplicate detection")
    conn = pg_conn(); cur = conn.cursor()
    cur.execute("""SELECT text_hash, COUNT(*), array_agg(id), array_agg(case_file)
                   FROM documents WHERE text_hash IS NOT NULL
                   GROUP BY text_hash HAVING COUNT(*) > 1""")
    dups = []
    for row in cur.fetchall():
        text_hash, count, ids, cases = row
        dups.append({"text_hash": text_hash, "count": count,
                     "doc_ids": ids, "case_files": cases})
    cur.close(); conn.close()
    log(f"  duplicate text_hash groups: {len(dups)}")
    report["text_hash_duplicates"] = dups


# ============================================================================
# Audit 4: version-chain backfill via embedding similarity
# ============================================================================
def audit_version_chains(report, apply_mode):
    log("Audit 4: version-chain backfill (skipped — runs against pgvector when wired)")
    report["version_chains"] = "deferred — wired in v4 pgvector migration"


# ============================================================================
# Audit 5: schema-creep
# ============================================================================
def audit_schema_creep(report):
    log("Audit 5: schema-creep proposals")
    conn = pg_conn(); cur = conn.cursor()
    cur.execute("""SELECT case_file, classification, COUNT(*)
                   FROM documents WHERE case_file IS NOT NULL AND classification IS NOT NULL
                   GROUP BY case_file, classification
                   HAVING COUNT(*) > %s""", (SCHEMA_CREEP_THRESHOLD,))
    proposals = [{"case_file": r[0], "doc_type": r[1], "count": r[2]} for r in cur.fetchall()]
    cur.close(); conn.close()
    log(f"  schema-creep proposals: {len(proposals)}")
    report["schema_creep"] = proposals


# ============================================================================
# Audit 6: filename harmonization
# ============================================================================
_FILE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_[\w\-\.]+\.pdf$", re.IGNORECASE)
def audit_filenames(report, apply_mode):
    log("Audit 6: filename harmonization")
    conn = pg_conn(); cur = conn.cursor()
    cur.execute("""SELECT id, smart_filename, original_filename, document_title,
                          classification, case_file
                   FROM documents WHERE smart_filename IS NOT NULL""")
    bad = []
    for row in cur.fetchall():
        doc_id, smart, orig, title, dtype, case = row
        if smart and not _FILE_RE.match(smart):
            bad.append({"doc_id": doc_id, "current": smart, "case_file": case})
    cur.close(); conn.close()
    log(f"  malformed smart_filenames: {len(bad)}")
    report["filename_issues"] = bad


# ============================================================================
# Audit 7: stale unclassified
# ============================================================================
def audit_stale_unclassified(report):
    log("Audit 7: stale Unclassified review")
    conn = pg_conn(); cur = conn.cursor()
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    cur.execute("""SELECT id, smart_filename, classification, last_seen_at, confidence
                   FROM documents WHERE case_file = 'Unclassified' AND last_seen_at < %s
                   ORDER BY last_seen_at""", (cutoff,))
    stale = [{"doc_id": r[0], "smart_name": r[1], "doc_type": r[2],
              "last_seen_at": str(r[3]), "confidence": float(r[4] or 0)} for r in cur.fetchall()]
    cur.close(); conn.close()
    log(f"  stale unclassified: {len(stale)}")
    report["stale_unclassified"] = stale


# ============================================================================
# Pending-questions queue + reporting
# ============================================================================
def queue_proposals(report):
    conn = pg_conn(); cur = conn.cursor()
    queued = 0
    for p in report.get("reclassification", {}).get("propose", []):
        cur.execute("""INSERT INTO pending_questions
            (case_file, source_doc_id, question, priority, context)
            VALUES (%s, %s, %s, %s, %s)""",
            (p.get("new_case") if p.get("new_case") in ("Paracale-001","MWK-001") else "Unknown",
             p["doc_id"],
             f"Reclassify doc {p['doc_id']} ({p['smart_name']}) from {p['old_case']}/{p['old_type']} "
             f"to {p['new_case']}/{p['new_type']}? Conf {p['old_conf']:.2f} → {p['new_conf']:.2f}. "
             f"Reason: {p.get('reasoning','')[:200]}",
             "normal", "reorganize_proposal"))
        queued += 1
    for m in report.get("misfiled", []):
        cur.execute("""INSERT INTO pending_questions
            (case_file, source_doc_id, question, priority, context)
            VALUES (%s, %s, %s, %s, %s)""",
            (m["case_file"], m["doc_id"],
             f"Doc {m['doc_id']} ({m['smart_name']}) is in folder {m['actual_folder_id']} "
             f"but rule says it belongs in {m['expected_sub']} ({m['expected_folder_id']}). Move?",
             "normal", "subfolder_misfile"))
        queued += 1
    for s in report.get("schema_creep", []):
        cur.execute("""INSERT INTO pending_questions
            (case_file, source_doc_id, question, priority, context)
            VALUES (%s, NULL, %s, %s, %s)""",
            (s["case_file"],
             f"{s['count']} documents of type '{s['doc_type']}' in {s['case_file']} — "
             f"create dedicated sub-subfolder?",
             "low", "schema_creep"))
        queued += 1
    conn.commit(); cur.close(); conn.close()
    return queued


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="execute auto-eligible changes (default: report-only)")
    args = parser.parse_args()
    apply_mode = args.apply
    log(f"Reorganize run — mode={'APPLY' if apply_mode else 'REPORT-ONLY'}")

    folders = load_folders()
    known_cases = [k for k in folders.keys() if k not in ("inbox", "unclassified")]

    try:
        drive_service = get_drive_service()
    except Exception as e:
        log(f"Drive auth failed: {e}"); drive_service = None

    report = {"timestamp": datetime.now().isoformat(),
              "mode": "apply" if apply_mode else "report-only"}
    audit_reclassification(report, apply_mode, drive_service, folders, known_cases)
    audit_misfiled(report, apply_mode, drive_service, folders)
    audit_duplicates(report)
    audit_version_chains(report, apply_mode)
    audit_schema_creep(report)
    audit_filenames(report, apply_mode)
    audit_stale_unclassified(report)

    queued = queue_proposals(report) if not apply_mode else 0

    out = Path(f"/root/landtek/reorganize_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    out.write_text(json.dumps(report, indent=2, default=str))
    print("\n" + "="*72 + "\nREORGANIZE REPORT\n" + "="*72)
    rec = report.get("reclassification", {})
    print(f"Reclassify auto:    {len(rec.get('auto', []))}")
    print(f"Reclassify propose: {len(rec.get('propose', []))}")
    print(f"Misfiled subfolders: {len(report.get('misfiled', []))}")
    print(f"Text-hash duplicate groups: {len(report.get('text_hash_duplicates', []))}")
    print(f"Schema-creep proposals: {len(report.get('schema_creep', []))}")
    print(f"Malformed filenames: {len(report.get('filename_issues', []))}")
    print(f"Stale unclassified (>7d): {len(report.get('stale_unclassified', []))}")
    print(f"Queued for review: {queued}")
    print(f"Full report: {out}")


if __name__ == "__main__":
    main()
