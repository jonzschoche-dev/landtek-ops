#!/usr/bin/env python3
"""correspondence_matcher.py — link emails to matters, goals, and duties.

Runs every 15 min (pair with landtek-email-briefer or own timer).
Deterministic — no LLM. For each gmail_message:

  1. Ensure client_code is set
  2. Upsert matter links from matter_codes[]
  3. Link open landtek_obligations (company duties) for this client/matter
  4. Link open client_needs (client outcomes) for this client
  5. Refresh relevance_status

Usage:
  python3 scripts/correspondence_matcher.py           # since last 48h unlinked
  python3 scripts/correspondence_matcher.py --full    # all emails needing work
  python3 scripts/correspondence_matcher.py --gmail-id 61858
"""
from __future__ import annotations
import argparse
import os
import re
import sys

import psycopg2
import psycopg2.extras

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from correspondence_spine import (  # noqa: E402
    archive_gmail_noise,
    compute_relevance_status,
    is_kb_pollution_email,
    resolve_client_code,
)

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
LOG_PATH = "/var/log/landtek/correspondence_matcher.log"


def log(msg: str) -> None:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    line = f"[correspondence_matcher] {msg}"
    print(line)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def upsert_link(cur, gmail_id: int, link_type: str, link_key: str,
                relation: str, rationale: str, confidence: str = "inferred_strong") -> bool:
    cur.execute("""
        INSERT INTO correspondence_links
          (gmail_id, link_type, link_key, relation, rationale, confidence, assessed_by)
        VALUES (%s, %s, %s, %s, %s, %s, 'correspondence_matcher')
        ON CONFLICT (gmail_id, link_type, link_key) DO UPDATE
           SET relation = EXCLUDED.relation,
               rationale = EXCLUDED.rationale,
               confidence = EXCLUDED.confidence
    """, (gmail_id, link_type, link_key, relation, rationale, confidence))
    return True


def _keyword_hit(haystack: str, label: str) -> bool:
    """True if any token (len>=5) from label appears in haystack."""
    if not haystack or not label:
        return False
    h = haystack.lower()
    for tok in re.findall(r"[a-z0-9]{5,}", label.lower()):
        if tok in h:
            return True
    return False


def _raw_category(row: dict) -> str | None:
    raw = row.get("raw_payload") or {}
    return raw.get("category") if isinstance(raw, dict) else None


def match_one(cur, row: dict) -> dict:
    """Link a single gmail row. Returns stats dict."""
    stats = {"matters": 0, "obligations": 0, "needs": 0, "archived_noise": 0}
    gid = row["id"]
    subject = row.get("subject") or ""
    body = (row.get("body_plain") or "")[:8000]
    if is_kb_pollution_email(
        from_addr=row.get("from_addr"),
        subject=subject,
        body_plain=body,
        relevance_status=row.get("relevance_status"),
        matter_codes=list(row.get("matter_codes") or []),
        raw_category=_raw_category(row),
    ):
        archive_gmail_noise(
            cur, row,
            reason="correspondence_matcher_noise",
            archived_by="correspondence_matcher",
        )
        stats["archived_noise"] = 1
        return stats
    haystack = f"{subject} {body}"
    matter_codes = list(row.get("matter_codes") or [])
    case_file = row.get("case_file")

    client_code = resolve_client_code(
        cur,
        case_file=case_file,
        matter_codes=matter_codes,
        existing=row.get("client_code"),
    )
    if client_code and client_code != row.get("client_code"):
        cur.execute(
            "UPDATE gmail_messages SET client_code = %s WHERE id = %s",
            (client_code, gid),
        )

    for mc in matter_codes:
        cur.execute("SELECT 1 FROM matters WHERE matter_code = %s", (mc,))
        if cur.fetchone():
            upsert_link(
                cur, gid, "matter", mc, "unclear",
                f"Email tagged to matter {mc} (matter_codes[])",
            )
            stats["matters"] += 1

    if not client_code:
        cur.execute(
            "UPDATE gmail_messages SET relevance_status = 'unlinked' WHERE id = %s",
            (gid,),
        )
        return stats

    # Company obligations (landtek duties)
    cur.execute("""
        SELECT id, short_label, description, matter_code, obligation_kind
          FROM landtek_obligations
         WHERE client_code = %s
           AND status IN ('open','in_progress','blocked')
    """, (client_code,))
    for ob in cur.fetchall():
        link = False
        relation = "unclear"
        rationale = f"Open obligation: {ob['short_label']}"
        if ob["matter_code"] and ob["matter_code"] in matter_codes:
            link = True
            relation = "advances"
            rationale = f"Matter {ob['matter_code']} matches obligation {ob['short_label']}"
        elif not ob["matter_code"]:
            link = True
            relation = "unclear"
        elif _keyword_hit(haystack, ob["short_label"] or ""):
            link = True
            relation = "advances"
            rationale = f"Subject/body matches obligation keywords: {ob['short_label']}"
        if link:
            upsert_link(
                cur, gid, "company_obligation", str(ob["id"]),
                relation, rationale,
            )
            stats["obligations"] += 1

    # Client outcomes (client_needs)
    cur.execute("""
        SELECT id, short_label, description, need_kind
          FROM client_needs
         WHERE client_code = %s
           AND status IN ('open','escalated')
    """, (client_code,))
    for need in cur.fetchall():
        relation = "unclear"
        rationale = f"Client has open need: {need['short_label']}"
        if _keyword_hit(haystack, need["short_label"] or ""):
            relation = "advances"
            rationale = f"Email may address client need: {need['short_label']}"
        upsert_link(
            cur, gid, "client_goal", f"need_{need['id']}",
            relation, rationale,
        )
        stats["needs"] += 1

    cur.execute(
        "SELECT COUNT(*) AS n FROM correspondence_links "
        "WHERE gmail_id = %s AND link_type IN ('client_goal','company_obligation')",
        (gid,),
    )
    has_goals = (cur.fetchone()["n"] or 0) > 0
    cur.execute("SELECT assessment_id FROM gmail_messages WHERE id = %s", (gid,))
    has_assessment = cur.fetchone()["assessment_id"] is not None

    status = compute_relevance_status(
        client_code=client_code,
        matter_codes=matter_codes,
        has_goal_links=has_goals,
        has_assessment=has_assessment,
    )
    cur.execute(
        "UPDATE gmail_messages SET relevance_status = %s WHERE id = %s",
        (status, gid),
    )
    return stats


def fetch_batch(cur, *, full: bool, gmail_id: int | None, hours: int) -> list:
    if gmail_id:
        cur.execute("SELECT * FROM gmail_messages WHERE id = %s", (gmail_id,))
        return cur.fetchall()
    if full:
        cur.execute("""
            SELECT * FROM gmail_messages
             WHERE relevance_status NOT IN ('assessed')
                OR client_code IS NULL
                OR cardinality(COALESCE(matter_codes, '{}'::text[])) = 0
             ORDER BY COALESCE(received_at, sent_at) DESC NULLS LAST
             LIMIT 2000
        """)
        return cur.fetchall()
    cur.execute(f"""
        SELECT * FROM gmail_messages
         WHERE COALESCE(received_at, sent_at, ingested_at) > now() - interval '{hours} hours'
            OR relevance_status IN ('unlinked','client_only','matter_linked')
         ORDER BY COALESCE(received_at, sent_at) DESC NULLS LAST
         LIMIT 500
    """)
    return cur.fetchall()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="process all emails needing linkage")
    ap.add_argument("--gmail-id", type=int, help="single email by id")
    ap.add_argument("--hours", type=int, default=48, help="lookback window (default 48h)")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    rows = fetch_batch(cur, full=args.full, gmail_id=args.gmail_id, hours=args.hours)
    totals = {"emails": 0, "matters": 0, "obligations": 0, "needs": 0, "archived_noise": 0}

    for row in rows:
        s = match_one(cur, row)
        totals["emails"] += 1
        totals["matters"] += s["matters"]
        totals["obligations"] += s["obligations"]
        totals["needs"] += s["needs"]
        totals["archived_noise"] += s.get("archived_noise", 0)

    log(
        f"processed={totals['emails']} matter_links={totals['matters']} "
        f"obligation_links={totals['obligations']} need_links={totals['needs']} "
        f"archived_noise={totals['archived_noise']}"
    )
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()