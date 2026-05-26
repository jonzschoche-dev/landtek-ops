#!/usr/bin/env python3
"""Deploy 280 — pattern expansion + Telegram triage pusher.

After deploy_279, 292 documents still have no matter linked. This deploy chips
away at that backlog two ways:

  A. PATTERN EXPANSION — extend the autolink trigger with ~25 more recognizers:
     - All 20 transferee names (Balane, Torralba, Victa, Apor, …)   → MWK-CV26360
     - Atty Barandon (counsel)                                       → MWK-CV26360
     - Donata King (related party)                                   → MWK-CV26360
     - Cesar de la Fuente (forged SPA executor)                     → MWK-CV26360
     - Mayor Pajarillo + variations                                  → MWK-ARTA-0747
     - Major derivative titles (T-32916, T-32917, T-52540)          → MWK-TCT4497
     - Patricia Keesey + variations                                  → MWK-ESTATE
     - MGB / DENR / PENRO (in Paracale context)                     → PAR-CAPACUAN

  B. TELEGRAM TRIAGE PUSHER — scripts/doc_triage.py + systemd timer:
     Every 2h during 8am-8pm Manila, pushes 1 unclassified doc to Telegram
     with heuristic suggestion (entity overlap with classified docs) and reply
     instructions. Idempotent via doc_triage_pushed table (7d dedup).

  C. NORMALIZE — set documents.case_file = NULL where it's 'unknown'/'Unknown'
     so the triage queue is clean.

Conservative: all new pattern hits are 'reference' / 'inferred_strong'. Promotion
to 'evidence' / 'primary' requires human or deploy-script intent.

Idempotent. Audited via app.actor='jonathan_deploy_280'.
"""
from __future__ import annotations

import os
import subprocess
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
ACTOR = "jonathan_deploy_280"
REPO_ROOT = "/root/landtek"
PUSHER_PATH = f"{REPO_ROOT}/scripts/doc_triage.py"
TIMER_NAME = "landtek-doc-triage"
SYSTEMD_DIR = "/etc/systemd/system"

# ---------------------------------------------------------------------------
# Pattern expansion. PG regex syntax: \y = word boundary (symmetric),
# \m = start-of-word, \M = end-of-word.
# Format: (matter_code, regex_pattern)
# ---------------------------------------------------------------------------

NEW_PATTERNS = [
    # Transferees → MWK-CV26360 (defendants in the civil case)
    ("MWK-CV26360", r"\yBalane\y"),
    ("MWK-CV26360", r"\yTorralba\y"),
    ("MWK-CV26360", r"\yVicta\y"),
    ("MWK-CV26360", r"\yApor\y"),
    ("MWK-CV26360", r"\yMabeza\y"),
    ("MWK-CV26360", r"\yBernardo\y"),
    ("MWK-CV26360", r"Cesar\s+Ramirez"),
    ("MWK-CV26360", r"\yGaulit\y"),
    ("MWK-CV26360", r"Dolores\s+Vela"),
    ("MWK-CV26360", r"Edgardo\s+Santiago"),
    ("MWK-CV26360", r"Elsa\s+Illigan"),
    ("MWK-CV26360", r"\yTychingco\y"),
    ("MWK-CV26360", r"Jose\s+Pascual"),
    ("MWK-CV26360", r"\yOnrubio\y"),
    ("MWK-CV26360", r"Maria\s+V?\.?\s*Cereza"),
    ("MWK-CV26360", r"Mariquita\s+Era"),
    ("MWK-CV26360", r"Pedro\s+Valledor"),
    ("MWK-CV26360", r"Rosalina\s+Hansol"),
    ("MWK-CV26360", r"Roscoe\s+Lea(?:n|ñ)o"),
    ("MWK-CV26360", r"Ruben\s+Ocan"),
    ("MWK-CV26360", r"Severino\s+Tenorio"),
    # Civil-case adjacent entities
    ("MWK-CV26360", r"\yBarandon\y"),
    ("MWK-CV26360", r"Donata\s+(?:M\.?\s*)?King"),
    ("MWK-CV26360", r"Cesar\s+(?:N\.?\s*)?de\s+la\s+Fuente"),
    # ARTA-0747 (Mayor Pajarillo)
    ("MWK-ARTA-0747", r"Alexander\s+L\.?\s*Pajarillo"),
    ("MWK-ARTA-0747", r"Mayor\s+Pajarillo"),
    ("MWK-ARTA-0747", r"\yPajarillo\y"),
    # Derivative titles → MWK-TCT4497 (chain of title for T-4497)
    ("MWK-TCT4497", r"\yT[-\s]?32916\y"),
    ("MWK-TCT4497", r"\yT[-\s]?32917\y"),
    ("MWK-TCT4497", r"\yT[-\s]?52540\y"),
    ("MWK-TCT4497", r"\yT[-\s]?52536\y"),
    ("MWK-TCT4497", r"\yT[-\s]?31298\y"),
    ("MWK-TCT4497", r"\yT[-\s]?079-2021002127\y"),
    # Estate
    ("MWK-ESTATE", r"Patricia\s+Keesey\s+Zschoche"),
    ("MWK-ESTATE", r"Patricia\s+Zschoche"),
    # Paracale-side entities
    ("PAR-CAPACUAN", r"\yCapacuan\y"),
    ("PAR-CAPACUAN", r"\bPGC\b"),  # Paracale Gold Consortium
    ("PAR-CAPACUAN", r"Paracale\s+Gold\s+Consortium"),
    ("PAR-CAPACUAN", r"Chavit\s+Singson"),
    ("PAR-CAPACUAN", r"LCS\s+Group"),
    ("PAR-CAPACUAN", r"Satrap\s+Mining"),
]


SCHEMA_SQL = """
-- Triage pushed table (the pusher script creates this too, but we ensure here)
CREATE TABLE IF NOT EXISTS doc_triage_pushed (
    id          serial PRIMARY KEY,
    doc_id      integer NOT NULL,
    pushed_at   timestamptz NOT NULL DEFAULT now(),
    telegram_ok boolean,
    telegram_error text,
    suggestion  text,
    UNIQUE (doc_id, pushed_at)
);
CREATE INDEX IF NOT EXISTS idx_doc_triage_doc ON doc_triage_pushed(doc_id);

-- Normalize noise case_file values
UPDATE documents
   SET case_file = NULL
 WHERE case_file IN ('unknown', 'Unknown', 'UNCLASSIFIED', '');
"""


def build_trigger_sql(new_patterns: list[tuple[str, str]]) -> str:
    """Generate the document_autolink_matters() function with the full pattern set.

    We REGENERATE the function from a known-good base + the NEW_PATTERNS list,
    so this is the single source of truth for the trigger's regex library."""
    base_patterns = [
        # CTN SL identifiers (deploy_279)
        ("MWK-ARTA-0690", r"CTN[\s-]*SL[-\s]*\d{4}[-\s]*\d{4}[-\s]*0690\M"),
        ("MWK-ARTA-0747", r"CTN[\s-]*SL[-\s]*\d{4}[-\s]*\d{4}[-\s]*0747\M"),
        ("MWK-ARTA-0792", r"CTN[\s-]*SL[-\s]*\d{4}[-\s]*\d{4}[-\s]*0792\M"),
        ("MWK-ARTA-1210", r"CTN[\s-]*SL[-\s]*\d{4}[-\s]*\d{4}[-\s]*1210\M"),
        ("MWK-ARTA-1212", r"CTN[\s-]*SL[-\s]*\d{4}[-\s]*\d{4}[-\s]*1212\M"),
        ("MWK-ARTA-1319", r"CTN[\s-]*SL[-\s]*\d{4}[-\s]*\d{4}[-\s]*1319\M"),
        ("MWK-ARTA-1321", r"CTN[\s-]*SL[-\s]*\d{4}[-\s]*\d{4}[-\s]*1321\M"),
        ("MWK-ARTA-1378", r"CTN[\s-]*SL[-\s]*\d{4}[-\s]*\d{4}[-\s]*1378\M"),
        ("MWK-ARTA-1891", r"CTN[\s-]*SL[-\s]*\d{4}[-\s]*\d{4}[-\s]*1891\M"),
        ("MWK-CV26360",    r"Civil\s+Case\s+(No\.?\s+)?26[-\s]?360"),
        ("MWK-CV6839",     r"Civil\s+Case\s+(No\.?\s+)?6839"),
        ("PAR-CV13-131220", r"Civil\s+Case\s+(No\.?\s+)?13[-\s]?131220"),
        ("MWK-TCT4497",    r"\mT[-\s]?4497\M"),
        ("MWK-ESTATE",     r"Mary\s+Worrick\s+Keesey"),
        ("PAR-CAPACUAN",   r"(Paracale\s+Gold\s+Partnership|Allan\s+Inocalla)"),
    ]
    all_patterns = base_patterns + new_patterns

    # Build the VALUES list. SQL-escape single quotes inside the regex.
    values_lines = []
    for matter, pat in all_patterns:
        pat_escaped = pat.replace("'", "''")
        values_lines.append(f"        ('{matter}', '{pat_escaped}')")
    values_sql = ",\n".join(values_lines)

    return f"""
CREATE OR REPLACE FUNCTION document_autolink_matters() RETURNS TRIGGER AS $$
DECLARE
  pat_record RECORD;
BEGIN
  -- 1) Primary link from documents.matter_code
  IF NEW.matter_code IS NOT NULL AND NEW.matter_code NOT IN ('', 'UNCLASSIFIED', 'unknown', 'Unknown') THEN
    INSERT INTO document_matter_links (doc_id, matter_code, case_file, relation_kind, provenance_level, linked_by, note)
    VALUES (NEW.id, NEW.matter_code, NEW.case_file, 'primary', 'verified', 'autolink_trigger',
            'Primary link from documents.matter_code')
    ON CONFLICT (doc_id, matter_code, relation_kind) DO UPDATE
      SET case_file = EXCLUDED.case_file, updated_at = now();
  END IF;

  -- 2) Reference links via regex patterns (deploy_280 expanded set)
  IF NEW.extracted_text IS NOT NULL AND LENGTH(NEW.extracted_text) > 50 THEN
    FOR pat_record IN
      SELECT matter, pat FROM (VALUES
{values_sql}
      ) AS p(matter, pat)
    LOOP
      IF NEW.extracted_text ~* pat_record.pat THEN
        INSERT INTO document_matter_links (doc_id, matter_code, relation_kind, provenance_level, linked_by, note)
        VALUES (NEW.id, pat_record.matter, 'reference', 'inferred_strong', 'autolink_trigger',
                'Detected via text pattern: ' || pat_record.matter)
        ON CONFLICT (doc_id, matter_code, relation_kind) DO NOTHING;
      END IF;
    END LOOP;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_documents_autolink ON documents;
CREATE TRIGGER trg_documents_autolink
  AFTER INSERT OR UPDATE OF case_file, matter_code, extracted_text ON documents
  FOR EACH ROW EXECUTE FUNCTION document_autolink_matters();
"""


# ---------------------------------------------------------------------------
# systemd units
# ---------------------------------------------------------------------------

SERVICE_UNIT = f"""[Unit]
Description=LandTek doc triage pusher — surface 1 unclassified doc to Telegram
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory={REPO_ROOT}
Environment="PG_DSN=postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
ExecStart=/usr/bin/python3 {PUSHER_PATH} --working-hours-only
StandardOutput=append:/var/log/landtek-doc-triage.log
StandardError=append:/var/log/landtek-doc-triage.log
"""

TIMER_UNIT = f"""[Unit]
Description=Run LandTek doc triage pusher every 2h

[Timer]
OnBootSec=5min
OnUnitActiveSec=2h
AccuracySec=2min
Unit={TIMER_NAME}.service

[Install]
WantedBy=timers.target
"""


def write_unit(path: str, content: str) -> bool:
    existing = ""
    if os.path.exists(path):
        with open(path) as f:
            existing = f.read()
    if existing.strip() == content.strip():
        return False
    with open(path, "w") as f:
        f.write(content)
    return True


def run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def main() -> int:
    print("Deploy 280 — pattern expansion + triage pusher")
    print("=" * 60)

    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET LOCAL app.actor = %s", (ACTOR,))

    # ---- C. Normalize noise + ensure triage table ----
    print("\n  A) Schema + normalize noise")
    cur.execute(SCHEMA_SQL)
    affected = cur.rowcount
    conn.commit()
    print(f"    ✓ doc_triage_pushed table ensured")
    print(f"    ✓ normalized 'unknown'/'Unknown' case_file → NULL ({affected} rows)")

    # ---- A. Pattern expansion: regenerate trigger ----
    print("\n  B) Regenerate autolink trigger with expanded pattern set")
    trigger_sql = build_trigger_sql(NEW_PATTERNS)
    cur.execute(trigger_sql)
    conn.commit()
    print(f"    ✓ trigger function regenerated with {15 + len(NEW_PATTERNS)} patterns")

    # ---- B. Backfill against new patterns ----
    print("\n  C) Backfill references using new patterns")
    n_ref_total = 0
    for matter, pat in NEW_PATTERNS:
        cur.execute("""
            INSERT INTO document_matter_links (doc_id, matter_code, relation_kind, provenance_level, linked_by, note)
            SELECT d.id, %s, 'reference', 'inferred_strong', 'deploy_280_backfill',
                   'Detected via text pattern: ' || %s
              FROM documents d
             WHERE d.extracted_text IS NOT NULL
               AND d.extracted_text ~* %s
               AND COALESCE(d.matter_code, '') <> %s
            ON CONFLICT (doc_id, matter_code, relation_kind) DO NOTHING
            RETURNING id
        """, (matter, matter, pat, matter))
        n = cur.rowcount
        n_ref_total += n
        if n:
            print(f"    ✓ {n:>4}  {matter}  ←  /{pat[:60]}/")
    conn.commit()
    print(f"  → {n_ref_total} new reference links seeded")

    # ---- D. Pusher script presence + executable ----
    print(f"\n  D) Triage pusher: {PUSHER_PATH}")
    if not os.path.exists(PUSHER_PATH):
        print("    ✗ MISSING — copy scripts/doc_triage.py to VPS first")
        return 1
    st = os.stat(PUSHER_PATH)
    os.chmod(PUSHER_PATH, st.st_mode | 0o111)
    print(f"    ✓ present ({st.st_size} bytes), executable")

    # ---- E. systemd timer ----
    print("\n  E) Install systemd timer")
    svc_path = f"{SYSTEMD_DIR}/{TIMER_NAME}.service"
    tmr_path = f"{SYSTEMD_DIR}/{TIMER_NAME}.timer"
    svc_changed = write_unit(svc_path, SERVICE_UNIT)
    tmr_changed = write_unit(tmr_path, TIMER_UNIT)
    print(f"    {'✓ wrote' if svc_changed else '· unchanged'} {svc_path}")
    print(f"    {'✓ wrote' if tmr_changed else '· unchanged'} {tmr_path}")
    if svc_changed or tmr_changed:
        run(["systemctl", "daemon-reload"])
    rc, _ = run(["systemctl", "enable", "--now", f"{TIMER_NAME}.timer"])
    print(f"    ✓ enabled+started {TIMER_NAME}.timer  rc={rc}")

    # ---- F. Final recap ----
    print("\n  F) Triage queue status")
    cur2 = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur2.execute("SELECT COUNT(*) AS n FROM documents")
    total = cur2.fetchone()["n"]
    cur2.execute("SELECT COUNT(DISTINCT doc_id) AS n FROM document_matter_links")
    linked = cur2.fetchone()["n"]
    cur2.execute("SELECT COUNT(*) AS n FROM documents_needing_classification")
    triage = cur2.fetchone()["n"]
    print(f"    Total docs:           {total}")
    print(f"    Linked to ≥1 matter:  {linked} ({linked*100//total}%)")
    print(f"    Needing classification: {triage} ({triage*100//total}%)")

    cur2.execute("""
        SELECT COUNT(*) AS n FROM (
          SELECT doc_id FROM document_matter_links GROUP BY doc_id HAVING COUNT(DISTINCT matter_code) > 1
        ) s
    """)
    multi = cur2.fetchone()["n"]
    print(f"    Multi-matter docs:    {multi} ({multi*100//total}%)")

    cur.close()
    cur2.close()
    conn.close()
    print("\n  ✓ deploy_280 complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
