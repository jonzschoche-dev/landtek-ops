#!/usr/bin/env python3
"""Deploy 296 — email sender disposition + digest filter.

Symptom (Jonathan's 6/4 6:12am digest):
  📬 Inbox digest — Thu Jun 4
  Last 24h: 32 ingested (0 linked, 32 unlinked)
  Unlinked (32) — may need manual review
    • Price decrease to $250K on 1501 W La Pasadita St
        from Redfin <listings@redfin.com>
    • New in Tucson at $345K
        from Redfin <listings@redfin.com>
    ...

The categorizer mis-tagged 11 Redfin listings as 'legal_correspondence' (word
overlap on 'court', 'price', etc.). Even when it didn't, the digest treats any
unlinked email as 'may need manual review' regardless of obvious noise.

Fix: explicit sender disposition table. Sender domain is far more reliable than
keyword matching. Three dispositions:

  - 'show'           : surface normally
  - 'archive'        : never show in digest; just count
  - 'critical_only'  : only surface if the sender is actively in a case
                       AND the subject hits a critical-push pattern

Layers:
  A. Schema: email_sender_disposition (sender_address, sender_domain, disposition)
  B. Seed with the noise senders visible in tonight's digest + common ones
  C. Patch email_briefer.py:
       - Filter unlinked query: exclude disposition='archive'
       - Show suppressed count at digest bottom
  D. CLI helper: scripts/archive_email_sender.py for one-command future additions

Retroactive: mark the 32 tonight as auto-classified noise where applicable."""
from __future__ import annotations
import os
import sys
import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
ACTOR = "jonathan_deploy_296"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS email_sender_disposition (
    id              serial PRIMARY KEY,
    sender_address  text,
    sender_domain   text,
    disposition     text NOT NULL CHECK (disposition IN ('show','archive','critical_only')),
    reason          text,
    added_by        text NOT NULL,
    added_at        timestamptz NOT NULL DEFAULT now(),
    -- exactly one of sender_address or sender_domain must be set
    CHECK ((sender_address IS NULL) <> (sender_domain IS NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS uniq_esd_address ON email_sender_disposition(sender_address) WHERE sender_address IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uniq_esd_domain ON email_sender_disposition(sender_domain) WHERE sender_domain IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_esd_disposition ON email_sender_disposition(disposition);
"""

# Initial blocklist — clear noise senders observed in tonight's digest + obvious ones
SEED = [
    # Real estate (Tucson AZ subscription noise)
    (None, "redfin.com", "archive", "Real estate listings"),
    (None, "e.mail.realtor.com", "archive", "Realtor.com listings"),
    (None, "mail.realtor.com", "archive", "Realtor.com listings"),
    # Travel
    (None, "msg.kayak.com", "archive", "Travel marketing"),
    # Personal finance / shopping
    (None, "mail.nerdwallet.com", "archive", "Personal finance newsletter"),
    (None, "info.acretrader.com", "archive", "Land investment marketing"),
    (None, "info@acretrader.com", "archive", "Land investment marketing"),
    # Auto parts / random commerce
    (None, "pelicanparts.com", "archive", "Auto parts marketing"),
    (None, "supergut.com", "archive", "Health/wellness marketing"),
    # Backup / SaaS marketing
    (None, "mail.notion.so", "archive", "Notion marketing"),
    (None, "backblaze.com", "archive", "Backblaze marketing"),
    (None, "info@backblaze.com", "archive", "Backblaze marketing"),
    # Quora / Hiive / general newsletters
    (None, "quora.com", "archive", "Newsletter digest"),
    (None, "mail.hiive.com", "archive", "Investment marketing"),
    # Health newsletter (tonight's digest had this one)
    ("yourhealth@drmichaelwhelan.com", None, "archive", "Health newsletter"),
    # Generic noreply / postmaster shouldn't be surfaced as needing review
    (None, "termius.com", "archive", "Termius account email"),
    # ---- WHITELIST entries (disposition='show') for legal correspondents ----
    (None, "arta.gov.ph", "show", "ARTA Litigation Division"),
    (None, "judiciary.gov.ph", "show", "Courts"),
    (None, "denr.gov.ph", "show", "DENR"),
    (None, "csc.gov.ph", "show", "Civil Service Commission"),
    (None, "dilg.gov.ph", "show", "DILG"),
    (None, "mgb.gov.ph", "show", "Mines and Geosciences Bureau"),
    # Allan/Joy and other clients — show whenever they message
    # (handled via authorized_users / clients lookup separately)
]


def main() -> int:
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET LOCAL app.actor = %s", (ACTOR,))

    print("Deploy 296 — email sender disposition + digest filter")
    print("=" * 56)

    print("\n  A) Schema")
    cur.execute(SCHEMA_SQL)
    print("    ✓ email_sender_disposition table + indexes")

    print("\n  B) Seed dispositions")
    inserted = 0
    skipped = 0
    for addr, domain, disp, reason in SEED:
        try:
            cur.execute(
                """
                INSERT INTO email_sender_disposition (sender_address, sender_domain, disposition, reason, added_by)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (addr, domain, disp, reason, "deploy_296_seed"),
            )
            inserted += 1
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            cur.execute("SET LOCAL app.actor = %s", (ACTOR,))
            skipped += 1
    print(f"    ✓ inserted: {inserted}  skipped (already present): {skipped}")

    # Recap
    cur.execute("SELECT disposition, COUNT(*) FROM email_sender_disposition GROUP BY 1 ORDER BY 1")
    for r in cur.fetchall():
        print(f"      {r['disposition']:>14}: {r['count']}")

    conn.commit()
    print("\n  ✓ COMMITTED")
    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
