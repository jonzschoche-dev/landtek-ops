#!/usr/bin/env python3
"""forensic_new_doc_trigger — flag newly ingested high-impact documents for
forensic review. Runs every 30 min.

A "high-impact" doc is one whose classification or filename suggests it could
shift the case theory: SPA, Revocation, Deed of Sale/Donation, Death Certificate,
Court Order, Petition, Judicial Affidavit.

When detected, queue ONE ops inquiry per (matter, day): "New high-impact evidence
detected — run /forensic <matter>?"

Tracks last-seen doc id in a small marker file so it only acts on truly new docs.
"""
import os, re, sys
from pathlib import Path
sys.path.insert(0, "/root/landtek")
import psycopg2, psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
MARKER = Path("/var/lib/landtek/forensic_trigger_marker")
MARKER.parent.mkdir(parents=True, exist_ok=True)

HIGH_IMPACT_CLASSIFICATIONS = {
    "Special Power of Attorney", "Revocation", "Deed", "Deed of Donation",
    "Pleading - Complaint (Draft)", "Petition", "Judicial Affidavit",
    "Order", "Resolution", "Decision", "Title (TCT/OCT)",
}
HIGH_IMPACT_NAME_PATTERNS = [
    r"death\s*cert", r"revocation", r"\bSPA\b", r"\bspecial\s+power\b",
    r"deed\s+of\s+(absolute\s+)?sale", r"deed\s+of\s+donation",
    r"petition\s+for\s+guardian", r"affidavit\s+of\s+confirmation",
]

def detect_new_high_impact(cur, last_id):
    cur.execute("""
        SELECT id, doc_date_norm, classification, matter_code, case_file,
               COALESCE(smart_filename, document_title, original_filename) AS name
          FROM documents
         WHERE id > %s
           AND case_file IS NOT NULL
         ORDER BY id LIMIT 50
    """, (last_id,))
    candidates = []
    for r in cur.fetchall():
        name = (r["name"] or "").lower()
        if r["classification"] in HIGH_IMPACT_CLASSIFICATIONS:
            candidates.append(r)
            continue
        if any(re.search(p, name, re.IGNORECASE) for p in HIGH_IMPACT_NAME_PATTERNS):
            candidates.append(r)
    return candidates

def queue_forensic_suggestion(cur, doc, matter_code):
    """Queue one ops inquiry suggesting a forensic run on the matter."""
    body = (
        f"🔬 <b>New high-impact evidence — forensic review suggested</b>\n"
        f"<i>matter={matter_code}</i>\n\n"
        f"<b>Doc #{doc['id']}</b> classified as <b>{doc['classification'] or '(unknown)'}</b>\n"
        f"File: <code>{(doc['name'] or '(unnamed)')[:80]}</code>\n"
        f"Date: {doc['doc_date_norm'] or '(undated)'}\n\n"
        f"This document may shift the case theory.\n"
        f"Reply <code>/forensic {matter_code}</code> to run a full Opus 4.7 forensic analysis (~$0.50-3.00).\n"
        f"Reply <code>/skip</code> to dismiss."
    )
    cur.execute("""
        SELECT id FROM tg_inquiry_queue
         WHERE status IN ('queued','active')
           AND matter_code = %s
           AND notes LIKE %s
         LIMIT 1
    """, (matter_code, f"forensic_new_doc_trigger:doc={doc['id']}%"))
    if cur.fetchone():
        return None  # dedupe
    cur.execute("""
        INSERT INTO tg_inquiry_queue
          (kind, audience, priority, source_table, source_id, matter_code,
           composed_html, notes)
        VALUES ('gap_alert','ops', 20, 'forensic_new_doc_trigger', %s, %s,
                %s, %s)
        RETURNING id
    """, (doc["id"], matter_code, body[:6000],
          f"forensic_new_doc_trigger:doc={doc['id']}:matter={matter_code}"))
    return cur.fetchone()["id"]

def main():
    last_id = int(MARKER.read_text().strip()) if MARKER.exists() else 0
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cands = detect_new_high_impact(cur, last_id)
    if not cands:
        # Update marker to latest doc id so we don't keep scanning
        cur.execute("SELECT COALESCE(MAX(id),0) AS m FROM documents")
        new_max = cur.fetchone()["m"]
        MARKER.write_text(str(new_max))
        print(f"forensic_new_doc_trigger: no new high-impact docs (marker now at {new_max})")
        return 0

    print(f"forensic_new_doc_trigger: {len(cands)} new high-impact doc(s)")
    queued = 0
    for d in cands:
        matter = d["matter_code"] or ("MWK-CV26360" if d["case_file"] == "MWK-001" else None)
        if not matter:
            continue
        iid = queue_forensic_suggestion(cur, d, matter)
        if iid:
            queued += 1
            print(f"  ✓ doc#{d['id']} ({d['classification']}) → inquiry #{iid} matter={matter}")

    # Update marker to highest doc id seen
    new_max = max(d["id"] for d in cands)
    MARKER.write_text(str(new_max))
    print(f"\nmarker updated to {new_max} · queued {queued} forensic suggestion(s)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
