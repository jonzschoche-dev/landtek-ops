#!/usr/bin/env python3
"""ingest_strategy_docs.py — put the drip strategy INTO the corpus so every desk and bot can steer by it.

Internal doctrine only: rows are doc_role='background', exhibit_tier='not_for_trial', classification='internal_strategy',
ingest_source='strategy_desk'. They never become exhibits and never render outward (the drip lint's internal_goal_leak
rules + the not_for_trial tier keep them out of bundles and letters). Idempotent: re-running UPDATEs the same row
(matched on file_path) with the current text, so the corpus always holds the latest strategy.

  python3 scripts/ingest_strategy_docs.py            # dry run (rolled back)
  python3 scripts/ingest_strategy_docs.py --apply
"""
import argparse
import hashlib
import os
from datetime import date

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (repo path, case_file, matter_code, title) — client-scoped (A5): MWK docs only under MWK-001
DOCS = [
    ("case_work/MWK-001/DRIP_CHARTER.md", "MWK-001", "MWK-001",
     "MWK DRIP CHARTER (ADOPTED 20 Oct 2026): governs every drip; outranks guide/spec/templates (internal)"),
    ("case_work/MWK-001/BRIEF_MWK-001_2026-10-20.md", "MWK-001", "MWK-001",
     "MWK-001 matter brief 20 Oct 2026 (Charter step 2): standing by goal, suggested drips, decisions (internal)"),
    ("case_work/MWK-001/DRIP_STEERING_GUIDE_MWK.md", "MWK-001", "MWK-001",
     "MWK DRIP STEERING GUIDE: how every communication to an office is steered (internal)"),
    ("agent_specs/005_drip.md", "MWK-001", "MWK-001",
     "Drip algorithm v2: intake, cross-checks, ladder, pick, sleep doctrine, review queue (internal spec)"),
    ("docs/RELATIONSHIP_EQUILIBRIUM.md", "MWK-001", "MWK-001",
     "Reasoning/relationship equilibrium incl. §7 strategic layer, patient-record doctrine, financial-legal angle (internal)"),
    ("case_work/MWK-001/CV6839_WRIT_COLLECTION_PATH.md", "MWK-001", "MWK-CV6839",
     "CV 6839 writ/collection path: per-heir route, Rule 39 window, authority pathways (internal strategy)"),
    ("case_work/MWK-001/GAME_THEORY_LIABILITY_2026-09.md", "MWK-001", "MWK-001",
     "Game theory of the supervision/liability fight: payoffs, deflection, claims (internal strategy)"),
    ("case_work/MWK-001/SMALL_PLAYERS_TARGET_SHEET_2026-10.md", "MWK-001", "MWK-001",
     "Small players target sheet: appointive officials, forum, sequencing (internal strategy)"),
    ("case_work/MATTER_GOALS_PROPOSED_2026-10-20.md", "MWK-001", "MWK-001",
     "Matter goals PROPOSED 20 Oct 2026 (not yet set by Jonathan; internal)"),
    ("case_work/MATTER_REFERENCE_2026-10-20.md", "MWK-001", "MWK-001",
     "Matter and track reference: 68 tracks, pressure per official, dereliction meter (internal)"),
    ("case_work/MWK-001/DRIP_RESULTS_AND_NEXT_MOVES_2026-10-21.md", "MWK-001", "MWK-001",
     "MWK-001 drip results sought & next moves, 20-21 Oct 2026 (internal tracker)"),
    ("case_work/MWK-001/BARANGAY_RECEPTION_LOG_2026-10.md", "MWK-001", "MWK-001",
     "Barangay reception log 21 Oct 2026: III/V received, San Roque/Uno refused; Mayor rumour [O] (internal)"),
    ("case_work/MWK-001/BALIZA_CLAIM_LOG.md", "MWK-001", "MWK-001",
     "Miguel Baliza claim log: 1 Oct 2025 letter unanswered, Torralba JA Q21 link, final notice (internal)"),
    ("case_work/CV26360_COMPLETE/CASE_FILE/PARTIES/TORRALBA_SB_CONDUCT_LOG.md", "MWK-001", "MWK-CV26360",
     "Councilor Torralba SB conduct log: non-recusal [O], minutes refused, livestream erased; subpoena route (internal)"),
    ("case_work/MWK-001/DILG_COMMS_REVIEW_PROVINCIAL_REGIONV_2026-10-21.md", "MWK-001", "MWK-001",
     "DILG communications review, Provincial + Region V, 21 Oct 2026 (internal)"),
    ("case_work/MWK-001/RIDER_ROUNDS_DOWNSTREAM_2026-10-21.md", "MWK-001", "MWK-001",
     "Rider rounds 21 Oct 2026: downstream effects assessment (internal)"),
    ("case_work/DRIP_BOARDS/DRIP_BOARD_MWK-001.md", "MWK-001", "MWK-001",
     "DRIP BOARD MWK-001 (nightly): every ladder's status, proof of receipt, clock and due date (internal)"),
    ("case_work/DRIP_BOARDS/DRIP_BOARD_Paracale-001.md", "Paracale-001", "Paracale-001",
     "DRIP BOARD Paracale-001 (nightly): ladder status, proof of receipt, clocks (internal)"),
]


def upsert(cur, path, cf, mc, title, text):
    """Insert/update one internal strategy row by file_path (idempotent). Returns (id, action)."""
    h = hashlib.sha256(text.encode()).hexdigest()
    cur.execute("SELECT id, sha256 FROM documents WHERE file_path=%s AND ingest_source='strategy_desk'", (path,))
    row = cur.fetchone()
    if row and row["sha256"] == h:
        return row["id"], "unchanged"
    vals = dict(case_file=cf, matter_code=mc, file_name=os.path.basename(path), file_path=path,
                document_title=title, extracted_text=text, text_length=len(text), sha256=h, content_hash=h,
                document_date=date.today(), ingest_source="strategy_desk", ingest_status="ingested",
                status="ingested", classification="internal_strategy", doc_role="background",
                exhibit_tier="not_for_trial", processing_mode="lean", master_form="digital",
                analyst_memo=psycopg2.extras.Json({"note": "INTERNAL STRATEGY: steer communications by it; never an exhibit, never quoted outward."}))
    if row:
        sets = ", ".join(f"{k}=%({k})s" for k in vals)
        cur.execute(f"UPDATE documents SET {sets}, updated_at=now(), chunk_count=NULL WHERE id=%(id)s", {**vals, "id": row["id"]})
        return row["id"], "updated"
    cols = ", ".join(vals)
    cur.execute(f"INSERT INTO documents ({cols}) VALUES ({', '.join('%(' + k + ')s' for k in vals)}) RETURNING id", vals)
    return cur.fetchone()["id"], "inserted"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", help="ingest just this one DOCS path (the nightly drip uses it for the board)")
    a = ap.parse_args()
    c = psycopg2.connect(DSN)
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    for path, cf, mc, title in DOCS:
        if a.only and path != a.only:
            continue
        full = os.path.join(REPO, path)
        if not os.path.isfile(full):
            print("MISSING", path)
            continue
        text = open(full, encoding="utf-8").read()
        h = hashlib.sha256(text.encode()).hexdigest()
        cur.execute("SELECT id, sha256 FROM documents WHERE file_path=%s AND ingest_source='strategy_desk'", (path,))
        row = cur.fetchone()
        if row and row["sha256"] == h:
            print(f"unchanged  #{row['id']}  {path}")
            continue
        vals = dict(case_file=cf, matter_code=mc, file_name=os.path.basename(path), file_path=path,
                    document_title=title, extracted_text=text, text_length=len(text), sha256=h, content_hash=h,
                    document_date=date.today(), ingest_source="strategy_desk", ingest_status="ingested",
                    status="ingested", classification="internal_strategy", doc_role="background",
                    exhibit_tier="not_for_trial", processing_mode="lean", master_form="digital",
                    analyst_memo=psycopg2.extras.Json({"note": "INTERNAL STRATEGY: steer communications by it; never an exhibit, never quoted outward."}))
        if row:
            sets = ", ".join(f"{k}=%({k})s" for k in vals)
            cur.execute(f"UPDATE documents SET {sets}, updated_at=now(), chunk_count=NULL WHERE id=%(id)s",
                        {**vals, "id": row["id"]})
            print(f"updated    #{row['id']}  {path}")
        else:
            cols = ", ".join(vals)
            cur.execute(f"INSERT INTO documents ({cols}) VALUES ({', '.join('%(' + k + ')s' for k in vals)}) RETURNING id", vals)
            print(f"inserted   #{cur.fetchone()['id']}  {path}")
    if a.apply:
        c.commit()
        print("COMMITTED")
    else:
        c.rollback()
        print("dry run — rolled back")


if __name__ == "__main__":
    main()
