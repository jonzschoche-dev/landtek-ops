#!/usr/bin/env python3
"""Deploy 232 — refine resolutions.disposition extraction.

Deploy 229 left disposition over-fit: 23 of 29 rows say 'granted' because the
regex hits anywhere in the text. Many candidates are Petitions whose PRAYER
quotes 'GRANTED' as the requested relief — not the adjudicator's disposition.

Refined approach (deterministic, in-place UPDATE):
  1. Look for 'DISPOSITIVE PORTION' or 'WHEREFORE, premises considered' marker.
  2. Search the window AFTER the marker for disposition keywords.
  3. If no marker found AND the doc is classified as 'Motion' or 'Reply',
     mark disposition='not_resolution' (so the row stays in the table but
     is accurately flagged).
  4. If marker found but no keyword in the window: disposition='unknown'.
  5. If neither marker nor classification suggests a real Resolution:
     disposition='unknown'.

Idempotent: re-runs reclassify based on current extraction logic.
"""
import re
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


MARKER_RES = [
    re.compile(r"\bDISPOSITIVE\s+PORTION\b", re.IGNORECASE),
    re.compile(r"\bWHEREFORE,?\s+premises\s+considered\b", re.IGNORECASE),
    re.compile(r"\bWHEREFORE\b", re.IGNORECASE),
    re.compile(r"\bSO\s+ORDERED\b", re.IGNORECASE),
]

DISP_KEYWORDS = [
    (re.compile(r"\bPARTIAL(LY)?\s+GRANTED\b", re.IGNORECASE), "partial_granted"),
    (re.compile(r"\bGRANTED\b", re.IGNORECASE), "granted"),
    (re.compile(r"\bDENIED\b", re.IGNORECASE), "denied"),
    (re.compile(r"\bDISMISSED\b", re.IGNORECASE), "dismissed"),
    (re.compile(r"\bREMANDED\b", re.IGNORECASE), "remanded"),
    (re.compile(r"\bNOTICE\s+OF\s+COMPLIANCE\b", re.IGNORECASE), "compliance_notice"),
    (re.compile(r"\bAFFIRMED\b", re.IGNORECASE), "affirmed"),
    (re.compile(r"\bSET\s+ASIDE\b", re.IGNORECASE), "set_aside"),
    (re.compile(r"\bREVERSED\b", re.IGNORECASE), "reversed"),
]


def refine_disposition(text, classification):
    """Returns (disposition_label, refinement_notes)."""
    if not text or len(text) < 100:
        return ("unknown", "text too short")

    marker_pos = None
    marker_name = None
    for pat in MARKER_RES:
        m = pat.search(text)
        if m:
            marker_pos = m.end()
            marker_name = pat.pattern
            break

    if marker_pos is None:
        if classification in ("Motion", "Reply", "Complaint", "Letter", "Notice",
                              "Affidavit", "Judicial Affidavit", "Memorandum"):
            return ("not_resolution",
                    f"no dispositive marker; classification={classification} suggests filing not resolution")
        return ("unknown", "no DISPOSITIVE/WHEREFORE/SO ORDERED marker found")

    window = text[marker_pos:marker_pos + 2000]
    for pat, label in DISP_KEYWORDS:
        if pat.search(window):
            return (label, f"matched in window after '{marker_name}'")

    return ("unknown", f"marker '{marker_name}' found but no disposition keyword in window")


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print("Deploy 232 — refine resolutions.disposition extraction")
    print("=" * 60)

    cur.execute("""
        SELECT r.id, r.disposition AS old_disp, r.source_doc_id,
               d.classification, d.extracted_text
          FROM resolutions r
          LEFT JOIN documents d ON d.id = r.source_doc_id
         ORDER BY r.id
    """)
    rows = cur.fetchall()
    print(f"\nReviewing {len(rows)} resolution rows…")

    transitions = {}
    for r in rows:
        new_disp, note = refine_disposition(r["extracted_text"], r["classification"])
        if new_disp != r["old_disp"]:
            cur.execute("""
                UPDATE resolutions
                   SET disposition = %s,
                       notes = COALESCE(notes, '') || %s,
                       updated_at = NOW()
                 WHERE id = %s
            """, (new_disp,
                  f" | deploy_232 refined: {r['old_disp']} → {new_disp} ({note})",
                  r["id"]))
            key = f"{r['old_disp']} → {new_disp}"
            transitions[key] = transitions.get(key, 0) + 1

    print(f"\nDisposition transitions:")
    for k, v in sorted(transitions.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")

    print()
    cur.execute("""
        SELECT disposition, COUNT(*) AS n FROM resolutions
         GROUP BY disposition ORDER BY n DESC
    """)
    print("Final resolutions.disposition distribution:")
    for r in cur.fetchall():
        print(f"  {r['disposition']:<22s} {r['n']}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
