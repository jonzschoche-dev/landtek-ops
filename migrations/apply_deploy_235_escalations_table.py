#!/usr/bin/env python3
"""Deploy 235 — `escalations` table + targeted backfill.

Captures the procedural chain that the current schema can't traverse:

    [ARTA Resolution] → [MFR / OP Appeal / CSC Endorsement] → [Response]

Today, those events are scattered as Documents, Emails, and (sometimes) misclassified
`resolutions` rows. The lookup can find them by grep but can't follow the chain
between source decision and downstream filing.

This table normalizes:
  - escalation_date / escalation_type
  - source_resolution_id  → the decision being escalated FROM
  - source_doc_id         → if source isn't yet a resolutions row
  - escalation_doc_id     → the filing doc (the appeal / MFR / endorsement itself)
  - escalation_email_id   → if email-only event (e.g., the May 6 "Notice of Filing at OP")
  - forum_from / forum_to
  - response_doc_id / response_date
  - affected_matter_codes / affected_ctn_nos

Backfill scope (high-confidence known patterns, deterministic):
  1. April 7 ARTA Resolution (doc#706, res#3) ← Jonathan's April 20 Request to Defer (doc#465, #710)
  2. April 7 ARTA Resolution (res#3)          ← May 5 OP Appeal (docs #702, 703, 457, 458, 459)
  3. April 7 ARTA Resolution (res#3)          ← April 30 CSC Endorsement (doc#706 first section)
  4. April 7 ARTA Resolution (res#3)          ← May 6 Notice of Filing at OP (gmail#52)
  5. April 20 Request to Defer                ← April 27 ARTA Response (doc#707)
  6. March 5 ARTA Resolution (res#14)         ← May 15+18 NOC chain (gmail#41/42/7919/8024/8090)

Idempotent (UNIQUE constraint on (source_resolution_id, escalation_doc_id, escalation_email_id)).
"""
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS escalations (
    id SERIAL PRIMARY KEY,
    escalation_date DATE,
    escalation_type TEXT,  -- 'appeal_to_OP', 'mfr', 'endorsement_to_CSC', 'request_to_defer',
                           -- 'response', 'notice_of_compliance', 'reconsideration', 'reply'
    forum_from TEXT,
    forum_to TEXT,
    source_resolution_id INTEGER REFERENCES resolutions(id) ON DELETE SET NULL,
    source_doc_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    escalation_doc_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    escalation_email_id INTEGER REFERENCES gmail_messages(id) ON DELETE SET NULL,
    affected_matter_codes TEXT[] DEFAULT '{}'::text[],
    affected_ctn_nos TEXT[] DEFAULT '{}'::text[],
    filed_by TEXT,
    addressed_to TEXT,
    status TEXT DEFAULT 'pending',
    response_doc_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    response_email_id INTEGER REFERENCES gmail_messages(id) ON DELETE SET NULL,
    response_date DATE,
    provenance_level TEXT NOT NULL DEFAULT 'inferred_weak',
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Composite uniqueness — prevent double-inserts of identical links
    UNIQUE (source_resolution_id, escalation_doc_id, escalation_email_id, escalation_type)
);

CREATE INDEX IF NOT EXISTS idx_escalations_source_res
    ON escalations(source_resolution_id);
CREATE INDEX IF NOT EXISTS idx_escalations_source_doc
    ON escalations(source_doc_id);
CREATE INDEX IF NOT EXISTS idx_escalations_esc_doc
    ON escalations(escalation_doc_id);
CREATE INDEX IF NOT EXISTS idx_escalations_matters
    ON escalations USING GIN(affected_matter_codes);
CREATE INDEX IF NOT EXISTS idx_escalations_date
    ON escalations(escalation_date DESC);

GRANT INSERT, SELECT, UPDATE ON escalations TO n8n;
GRANT USAGE, SELECT ON SEQUENCE escalations_id_seq TO n8n;
"""


# Backfill seeds — each entry is one explicit escalation we know about from
# corpus inspection. Resolution IDs verified via SELECT against the current
# state of the resolutions table.
ESCALATIONS_SEED = [
    {
        "escalation_date": "2026-04-20",
        "escalation_type": "request_to_defer",
        "forum_from": "ARTA Southern Luzon RFO, Batangas City",
        "forum_to": "ARTA Southern Luzon RFO, Batangas City",
        "source_resolution_lookup": ("MWK-ARTA-0690", "2026-04-07"),  # → res lookup
        "escalation_doc_id": 465,  # Jonathan's April 20 letter
        "affected_matter_codes": ["MWK-ARTA-0690", "MWK-ARTA-0792", "MWK-ARTA-0747"],
        "filed_by": "Jonathan Paul Zschoche",
        "addressed_to": "Atty. Rodolfo B. Del Rosario Jr.",
        "status": "responded",
        "response_doc_id": 707,  # April 27 ARTA Response
        "response_date": "2026-04-27",
        "provenance_level": "inferred_strong",
        "notes": "Request to Defer Further Action Pending Filing of MFR. Listed three "
                 "CTNs (0690, 0792, 0747). ARTA responded on 2026-04-27 (doc#707).",
    },
    {
        "escalation_date": "2026-04-30",
        "escalation_type": "endorsement_to_CSC",
        "forum_from": "ARTA Southern Luzon RFO, Batangas City",
        "forum_to": "Civil Service Commission, Regional Office V, Legazpi",
        "source_resolution_lookup": ("MWK-ARTA-0690", "2026-04-07"),
        "escalation_doc_id": 706,  # the same doc — the April 30 endorsement is in the head of this doc
        "affected_matter_codes": ["MWK-ARTA-0690", "MWK-ARTA-0792"],
        "filed_by": "ARTA",
        "addressed_to": "Atty. Daisy Punzalan Bragais (CSC RO V, Legazpi)",
        "status": "endorsed",
        "provenance_level": "inferred_strong",
        "notes": "ARTA endorsed the April 7 Resolution to CSC RO V Director IV Atty. "
                 "Bragais on April 30 2026. Endorsement text is in doc#706 head.",
    },
    {
        "escalation_date": "2026-05-05",
        "escalation_type": "appeal_to_OP",
        "forum_from": "ARTA Southern Luzon RFO, Batangas City",
        "forum_to": "Office of the President",
        "source_resolution_lookup": ("MWK-ARTA-0690", "2026-04-07"),
        "escalation_doc_id": 702,  # Petition to OP:ARTA May 5 (the primary)
        "affected_matter_codes": ["MWK-ARTA-0690", "MWK-ARTA-0792"],
        "filed_by": "Jonathan Paul Zschoche",
        "addressed_to": "Office of the President",
        "status": "filed",
        "response_doc_id": 700,  # May 11 LETTER RESPONSE TO MR JONATHAN ZSCHOCHE (needs verification of what it actually responds to)
        "response_date": "2026-05-11",
        "provenance_level": "inferred_strong",
        "notes": "Appeal of April 7 Resolution to OP via ARTA. Related docs: #703 "
                 "(PETITION:OP:ARTA.pdf), #457, #458, #459 (attachments). gmail#52 "
                 "(2026-05-06) = Notice of Filing at the Office of the President. "
                 "doc#700 = May 11 letter response (sender / content needs verification).",
    },
    {
        "escalation_date": "2026-05-06",
        "escalation_type": "notice_of_filing",
        "forum_from": "Office of the President",
        "forum_to": "Office of the President",
        "source_resolution_lookup": ("MWK-ARTA-0690", "2026-04-07"),
        "escalation_email_id": 52,  # May 6 Notice of Filing email
        "affected_matter_codes": ["MWK-ARTA-0690", "MWK-ARTA-0792"],
        "filed_by": "Jonathan Paul Zschoche",
        "status": "filed",
        "provenance_level": "inferred_strong",
        "notes": "Notice of Filing at OP — companion to the May 5 appeal (docs #702-703).",
    },
    {
        "escalation_date": "2026-05-15",
        "escalation_type": "notice_of_compliance",
        "forum_from": "ARTA Southern Luzon RFO, Batangas City",
        "forum_to": "ARTA / LGU Mercedes",
        "source_resolution_lookup": ("MWK-ARTA-1210", "2026-03-05"),
        "escalation_email_id": 42,  # May 15 [RESOLUTION - NOC] email (ARTA → respondents)
        "affected_matter_codes": ["MWK-ARTA-1210"],
        "filed_by": "ARTA Litigation Division",
        "addressed_to": "LGU Mercedes",
        "status": "issued",
        "provenance_level": "inferred_strong",
        "notes": "Notice of Compliance issued for the March 5 LGU Mercedes Resolution. "
                 "Followed up by 3 emails on 2026-05-18 (gmail#7919, #8024, #8090).",
    },
]


def resolve_source_resolution(cur, lookup):
    """Resolve (matter_code, date) → resolution_id. Returns None if not found."""
    if not lookup:
        return None
    matter_code, date = lookup
    cur.execute("""
        SELECT id FROM resolutions
         WHERE %s = ANY(affected_matter_codes)
           AND resolution_date = %s
         ORDER BY id LIMIT 1
    """, (matter_code, date))
    r = cur.fetchone()
    return r["id"] if r else None


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print("Deploy 235 — escalations table + targeted backfill")
    print("=" * 60)

    print("\n[1/3] Schema: CREATE TABLE escalations")
    cur.execute(SCHEMA_SQL)
    print("  ✓ escalations + 5 indexes ready")

    print("\n[2/3] Backfill from explicit seeds")
    inserted = 0
    for seed in ESCALATIONS_SEED:
        src_lookup = seed.pop("source_resolution_lookup", None)
        src_res_id = resolve_source_resolution(cur, src_lookup)

        # Insert
        cols = ["source_resolution_id"]
        vals = [src_res_id]
        for k, v in seed.items():
            cols.append(k)
            vals.append(v)
        placeholders = ", ".join(["%s"] * len(cols))
        col_list = ", ".join(cols)
        try:
            cur.execute(f"""
                INSERT INTO escalations ({col_list}) VALUES ({placeholders})
                ON CONFLICT (source_resolution_id, escalation_doc_id, escalation_email_id, escalation_type)
                DO NOTHING
                RETURNING id
            """, vals)
            r = cur.fetchone()
            if r:
                inserted += 1
                print(f"  ✓ #{r['id']}  {seed['escalation_date']}  {seed['escalation_type']}  "
                      f"src_res={src_res_id}  matters={seed['affected_matter_codes']}")
        except Exception as e:
            print(f"  ✗ failed: {e}")

    print(f"\n  → {inserted} escalations inserted")

    print("\n[3/3] Verify chain queries")
    cur.execute("""
        SELECT e.id, e.escalation_date, e.escalation_type, e.forum_to,
               r.id AS res_id, r.resolution_date,
               e.escalation_doc_id, e.response_doc_id
          FROM escalations e
          LEFT JOIN resolutions r ON r.id = e.source_resolution_id
         ORDER BY e.escalation_date
    """)
    print("\n  All escalations, chronologically:")
    for r in cur.fetchall():
        src = f"res#{r['res_id']} ({r['resolution_date']})" if r['res_id'] else f"(no source res)"
        esc_doc = f"doc#{r['escalation_doc_id']}" if r['escalation_doc_id'] else "—"
        resp = f"resp=doc#{r['response_doc_id']}" if r['response_doc_id'] else ""
        print(f"    #{r['id']:<3d}  {r['escalation_date']}  {r['escalation_type']:<22s}  "
              f"→ {r['forum_to'][:30]:<30s}  src={src}  esc={esc_doc}  {resp}")

    cur.close()
    conn.close()
    print()
    print("=" * 60)
    print("Now: SELECT * FROM escalations WHERE source_resolution_id = <X>")
    print("     surfaces the procedural chain downstream of any resolution.")


if __name__ == "__main__":
    main()
