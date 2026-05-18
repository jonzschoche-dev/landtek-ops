#!/usr/bin/env python3
"""landtek_daemon — autonomous ingestion + reasoning orchestrator.

Per Jonathan 2026-05-18: transition from one-shot scripts to a hands-free
loop that processes new evidence as it lands.

Pipeline per newly-detected document:
  Step A — text already extracted? skip OCR. else: Gemini OCR pass.
  Step B — lineage extract (Sonnet 4.6 tool-call → llm_extracted_lineage)
  Step C — graph extract  (Sonnet 4.6 tool-call → knowledge_graph_triples)
  Step D — deterministic anomaly scan (no LLM) against hard axioms
  Step E — append findings to /root/landtek/system_state.json

HONEST SCOPE NOTES:
  - Deterministic anomaly detector (no LLM judgment in the loop) — checks
    against ~5 hard axioms. Can't hallucinate findings.
  - No 'geospatial boundary intersection' — we have no polygon data in DB.
  - File watcher is poll-based (not inotify) — simpler, more robust on long
    runs, polls every 30s.
  - Does NOT auto-enable as a systemd service. User must explicitly enable.

Modes:
  python3 landtek_daemon.py --once               # one polling pass + exit
  python3 landtek_daemon.py --process-doc <id>   # run pipeline on existing doc
  python3 landtek_daemon.py                       # daemon loop (poll every 30s)
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone, date
from pathlib import Path
sys.path.insert(0, "/root/landtek")
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
WATCH_DIRS = [
    "/root/landtek/case_files/MWK-001",
    "/root/landtek/uploads",
]
STATE_FILE = Path("/root/landtek/system_state.json")
POLL_INTERVAL = 30  # seconds

# ── Hard axioms — deterministic checks only, no LLM judgment ─────────────
FOUNDATIONAL_TRUNK = ["OCT T-106", "T-111", "T-4493", "T-4497"]
CESAR_DEATH_DATE = date(2017, 6, 21)
SPA_REVOKED_DATE = date(2005, 8, 15)
NAMED_TRANSFEREES = {
    "alberto victa", "ananias apor", "arnel mabeza", "aurora bernardo",
    "cesar ramirez", "delfin gaulit", "dolores vela", "edgardo santiago",
    "elsa illigan", "erlinda tychingco", "jose pascual jr", "librada b onrubio",
    "librada onrubio", "maria v cereza", "maria cereza", "mariquita era",
    "pedro valledor", "rosalina hansol", "roscoe leano", "ruben ocan",
    "severino tenorio jr", "severino tenorio", "gloria balane",
}
PHANTOM_TITLE_PATTERNS = [
    r'^T-(19|20)\d{2}$',           # year format
    r'^T-\d{3}-\d{1,4}(-\d+)?$',   # tax PIN format
]


import hashlib

def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def infer_case_file(path):
    """Infer case_file from path. /case_files/MWK-001/* → MWK-001 etc.
    Defaults to MWK-001 for /uploads/ since that's the active case."""
    s = str(path)
    for cf in ("MWK-001", "Paracale-001", "Owner"):
        if f"/{cf}/" in s or f"/{cf}." in s:
            return cf
    return "MWK-001"


def extract_text_fast(path):
    """Try pdftotext first (free, fast). Returns text or empty string."""
    if str(path).lower().endswith(".pdf"):
        try:
            r = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                                capture_output=True, text=True, timeout=60)
            return r.stdout if r.returncode == 0 else ""
        except Exception:
            return ""
    return ""


def ingest_file(path):
    """Auto-ingest sidecar — insert a new file into documents, return doc_id.
    Steps:
      1. SHA256 content hash
      2. Dedup-check against documents.content_hash → returns None on dup
         (the existing doc is already in the corpus and presumed processed;
          re-running pipeline on every dup detected on each poll is wasteful)
      3. Insert row (case_file, file_path, original_filename, content_hash, etc.)
      4. Attempt fast text extraction (pdftotext); leave for Gemini OCR if empty
    Returns: doc_id for NEW docs only. Returns None for duplicates (caller
    should skip pipeline run on dups).
    """
    conn, cur = db()
    try:
        content_hash = sha256_of(path)
        # Dedup check — content_hash already in DB means this file was previously ingested
        cur.execute("SELECT id, case_file FROM documents WHERE content_hash = %s LIMIT 1", (content_hash,))
        existing = cur.fetchone()
        if existing:
            log(f"  Ingest: dup detected (matches doc#{existing['id']}, case={existing['case_file']}) — skipping pipeline")
            return None  # caller skips process_doc

        case_file = infer_case_file(path)
        original_filename = path.name
        text = extract_text_fast(path)
        text_len = len(text or "")

        cur.execute("""
            INSERT INTO documents
              (case_file, original_filename, smart_filename, file_path, file_name,
               content_hash, extracted_text, classification, execution_status,
               status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, NULL, 'ingested_by_daemon',
                    NOW(), NOW())
            RETURNING id
        """, (case_file, original_filename, original_filename, str(path),
              path.stem, content_hash, text or None))
        doc_id = cur.fetchone()["id"]
        log(f"  Ingest: inserted as doc#{doc_id} (case={case_file}, text={text_len} chars{', OCR pending' if text_len < 100 else ''})")
        return doc_id
    except Exception as e:
        log(f"  ✗ Ingest failed for {path}: {str(e)[:200]}")
        return None
    finally:
        conn.close()


def db():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    return conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


# ── State management ─────────────────────────────────────────────────────
def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {
        "last_run": None,
        "docs_processed": 0,
        "anomalies": [],
        "axioms": {
            "foundational_trunk": FOUNDATIONAL_TRUNK,
            "cesar_death_date": CESAR_DEATH_DATE.isoformat(),
            "spa_revoked_date": SPA_REVOKED_DATE.isoformat(),
            "named_transferees_count": len(NAMED_TRANSFEREES),
        },
    }


def save_state(state):
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


# ── File watcher ─────────────────────────────────────────────────────────
def find_new_files(cur, since_timestamp=None):
    """Return list of PDF/image files in WATCH_DIRS not yet in documents table.
    Checks by (file_path, original_filename, smart_filename) — all three because
    different ingest paths populate different fields. Files whose content_hash
    matches an existing doc will still be caught by ingest_file's dedup check,
    so this layer just optimizes by skipping obviously-known files."""
    cur.execute("""
        SELECT file_path, original_filename, smart_filename FROM documents
         WHERE case_file IN ('MWK-001', 'Paracale-001', 'Owner', 'Unknown')
    """)
    rows = cur.fetchall()
    known_paths = {r["file_path"] for r in rows if r["file_path"]}
    known_names = set()
    for r in rows:
        if r["smart_filename"]: known_names.add(r["smart_filename"])
        if r["original_filename"]: known_names.add(r["original_filename"])

    new_files = []
    for d in WATCH_DIRS:
        p = Path(d)
        if not p.exists():
            continue
        for f in p.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix.lower() not in (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".heic"):
                continue
            if str(f) in known_paths:
                continue
            if f.name in known_names:
                continue
            new_files.append(f)
    return new_files


# ── Pipeline steps ───────────────────────────────────────────────────────
def step_a_ocr(doc_id):
    """Skip if extracted_text already present (≥200 chars matches what Steps
    B+C require as the eligibility threshold)."""
    conn, cur = db()
    cur.execute("SELECT length(coalesce(extracted_text,'')) AS tlen FROM documents WHERE id=%s", (doc_id,))
    r = cur.fetchone()
    conn.close()
    if r and r["tlen"] >= 200:
        log(f"  Step A: ocr SKIPPED (text already present, {r['tlen']} chars)")
        return True
    log(f"  Step A: text missing/short ({r['tlen'] if r else 0} chars) — Gemini OCR would run here (not yet wired)")
    return False


def step_b_lineage(doc_id):
    """Run llm_title_extractor on this specific doc."""
    log(f"  Step B: running lineage extractor on doc#{doc_id}...")
    result = subprocess.run(
        ["python3", "/root/landtek/llm_title_extractor.py", "--doc", str(doc_id)],
        capture_output=True, text=True, timeout=120,
    )
    last_line = (result.stdout.strip().split("\n") or [""])[-1] if result.stdout else "(no output)"
    log(f"           {last_line}")
    return result.returncode == 0


def step_c_graph(doc_id):
    """Run build_truth_graph on this specific doc."""
    log(f"  Step C: running graph extractor on doc#{doc_id}...")
    result = subprocess.run(
        ["python3", "/root/landtek/build_truth_graph.py", "--doc", str(doc_id)],
        capture_output=True, text=True, timeout=120,
    )
    last_line = (result.stdout.strip().split("\n") or [""])[-1] if result.stdout else "(no output)"
    log(f"           {last_line}")
    return result.returncode == 0


def step_d_anomalies(doc_id):
    """Deterministic anomaly detection against hard axioms. Returns list of dicts."""
    import re
    conn, cur = db()
    anomalies = []

    # Pull the triples just extracted from this doc
    cur.execute("""
        SELECT subject_entity, relationship_type, object_entity, attributes_json, source_excerpt
          FROM knowledge_graph_triples
         WHERE source_doc_id = %s AND relationship_type <> '_NONE_'
    """, (doc_id,))
    triples = cur.fetchall()
    log(f"  Step D: scanning {len(triples)} triples for anomalies...")

    # Pull doc metadata
    cur.execute("SELECT smart_filename, doc_date_norm FROM documents WHERE id=%s", (doc_id,))
    doc_meta = cur.fetchone() or {}
    doc_date = doc_meta.get("doc_date_norm")

    for t in triples:
        subj = (t["subject_entity"] or "").strip()
        pred = (t["relationship_type"] or "").strip()
        obj = (t["object_entity"] or "").strip()
        subj_l = subj.lower()
        obj_l = obj.lower()
        attrs = t["attributes_json"] or {}

        # AXIOM CHECK 1: phantom titles in any title slot
        for slot, val in [("subject", subj), ("object", obj)]:
            for pat in PHANTOM_TITLE_PATTERNS:
                if re.match(pat, val):
                    anomalies.append({
                        "type": "phantom_title_in_triple",
                        "severity": "high",
                        "doc_id": doc_id,
                        "detail": f"Triple slot '{slot}'={val!r} matches phantom pattern; should NOT be treated as a real title",
                        "triple": f"{subj} —[{pred}]→ {obj}",
                    })

        # AXIOM CHECK 2: Cesar dela Fuente as actor after death (2017-06-21)
        cesar_actor = ("cesar" in subj_l and ("dela fuente" in subj_l or "delafuente" in subj_l))
        action_date = None
        if attrs.get("transaction_date"):
            try: action_date = date.fromisoformat(attrs["transaction_date"])
            except Exception: pass
        if not action_date and doc_date:
            try: action_date = doc_date if isinstance(doc_date, date) else date.fromisoformat(str(doc_date))
            except Exception: pass
        if cesar_actor and pred in ("SOLD_TO", "SOLD_PORTION_TO", "DONATED_TO", "AUTHORIZED_BY") and action_date and action_date > CESAR_DEATH_DATE:
            anomalies.append({
                "type": "post_mortem_action_by_cesar",
                "severity": "critical",
                "doc_id": doc_id,
                "detail": f"Triple implies Cesar dela Fuente acted on {action_date} — IMPOSSIBLE (died 2017-06-21)",
                "triple": f"{subj} —[{pred}]→ {obj}",
            })

        # AXIOM CHECK 3: Cesar conveyance after SPA revocation (2005-08-15)
        if cesar_actor and pred in ("SOLD_TO", "SOLD_PORTION_TO") and action_date and action_date > SPA_REVOKED_DATE:
            anomalies.append({
                "type": "post_revocation_conveyance_by_cesar",
                "severity": "high",
                "doc_id": doc_id,
                "detail": f"Cesar dela Fuente conveyance on {action_date} — POST-REVOCATION (SPA revoked 2005-08-15). Void per case theory.",
                "triple": f"{subj} —[{pred}]→ {obj}",
            })

        # AXIOM CHECK 4: new transferee not in 20-named list (informational, not adverse)
        if pred in ("SOLD_TO", "SOLD_PORTION_TO", "DONATED_TO"):
            obj_normalized = re.sub(r'[^\w\s]', '', obj_l).strip()
            obj_clean = re.sub(r'\s+', ' ', obj_normalized)
            if obj_clean and not any(known in obj_clean or obj_clean in known
                                       for known in NAMED_TRANSFEREES):
                # Skip institutional/corporate buyers from this check
                if "police" not in obj_l and "bank" not in obj_l and "office" not in obj_l \
                   and "municipality" not in obj_l and "company" not in obj_l:
                    anomalies.append({
                        "type": "transferee_outside_named_list",
                        "severity": "info",
                        "doc_id": doc_id,
                        "detail": f"Transferee {obj!r} not in the 20-named-transferees list — may require human classification",
                        "triple": f"{subj} —[{pred}]→ {obj}",
                    })

        # AXIOM CHECK 5: foundational trunk integrity
        if pred == "IS_DERIVATIVE_OF":
            # If a title claims to derive from something that's NOT in the trunk and NOT
            # a documented chain title, that's a flag (just informational)
            if obj == "OCT T-106" and subj not in ("T-111", "T-4497", "T-23796", "T-46038", "T-51641"):
                anomalies.append({
                    "type": "novel_oct_derivative",
                    "severity": "info",
                    "doc_id": doc_id,
                    "detail": f"Triple asserts {subj} derives from OCT T-106 — verify against trunk (T-111→T-4493→T-4497)",
                    "triple": f"{subj} —[{pred}]→ {obj}",
                })

    conn.close()
    log(f"          {len(anomalies)} anomaly(ies) flagged")
    return anomalies


def process_doc(doc_id):
    """Full per-doc pipeline. Returns dict with results.
    If Step A returns False (text missing, OCR would be needed but isn't
    wired yet), Steps B+C are skipped to avoid wasted Sonnet calls."""
    log(f"━━━ Processing doc#{doc_id} ━━━")
    result = {
        "doc_id": doc_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "steps": {},
    }
    step_a = step_a_ocr(doc_id)
    result["steps"]["a_ocr"] = step_a
    if not step_a:
        log(f"  Skipping B+C+D for doc#{doc_id} — text missing, OCR not yet wired in daemon")
        result["steps"]["b_lineage"] = "skipped_no_text"
        result["steps"]["c_graph"] = "skipped_no_text"
        result["steps"]["d_anomalies"] = "skipped_no_text"
        result["anomalies_flagged"] = 0
        result["anomalies"] = []
        result["completed_at"] = datetime.now(timezone.utc).isoformat()
        return result
    result["steps"]["b_lineage"] = step_b_lineage(doc_id)
    result["steps"]["c_graph"] = step_c_graph(doc_id)
    anomalies = step_d_anomalies(doc_id)
    result["anomalies_flagged"] = len(anomalies)
    result["anomalies"] = anomalies
    result["completed_at"] = datetime.now(timezone.utc).isoformat()
    return result


def update_state(per_doc_result):
    state = load_state()
    state["docs_processed"] += 1
    state["anomalies"].extend(per_doc_result.get("anomalies", []))
    # Keep only most recent 200 anomalies
    state["anomalies"] = state["anomalies"][-200:]
    state["last_doc"] = per_doc_result
    save_state(state)
    log(f"  Step E: state updated → {STATE_FILE}")


# ── Entry ────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="One poll pass then exit")
    ap.add_argument("--process-doc", type=int, help="Run pipeline on a specific existing doc")
    args = ap.parse_args()

    if args.process_doc:
        log(f"Single-doc mode: doc#{args.process_doc}")
        result = process_doc(args.process_doc)
        update_state(result)
        log("Done.")
        return

    log(f"landtek_daemon starting. watching: {WATCH_DIRS}")
    conn, cur = db()
    while True:
        new_files = find_new_files(cur)
        if new_files:
            log(f"New files detected: {len(new_files)}")
            for f in new_files:
                log(f"  → {f}")
                doc_id = ingest_file(f)
                if doc_id:
                    result = process_doc(doc_id)
                    update_state(result)
        else:
            log(f"No new files. Sleeping {POLL_INTERVAL}s...")
        if args.once:
            break
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
