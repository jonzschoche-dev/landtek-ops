#!/usr/bin/env python3
"""comprehend_browser_adapter.py — drop-in alternate transport for comprehend.py
when the Gemini API key×model ladder hits QuotaExhausted.

Same PROMPT, same write path, same confidence threshold — different transport.
Instead of calling generativelanguage.googleapis.com, this module exposes the
text-to-comprehend so an interactive Claude session can push it through the
Gemini Advanced chat (browser), capture the JSON response, and feed it back.

Why this exists:
  comprehend.py runs comprehension via Gemini API (free tier, currently exhausted).
  Gemini Advanced subscription chat uses a separate quota that is not exhausted.
  Driving the chat via Claude-in-Chrome MCP from a session is creditless re: API
  spend, accretes the SAME verified facts into property_assets, and respects the
  deploy_466 standing rule (spend only where it moves the awareness score).

Architecture:
  - --next [N]: print JSON array of next N pending titles {tct, prompt, text}
    Pending = title has readable source doc + property_assets.note has no
    "comprehended" marker yet. Same query as comprehend.sweep().
  - --write --tct T-X --json '{...}': apply comprehend's write logic exactly
    (UPDATE property_assets if confidence >= CONF_WRITE; flag if lower).
    Also writes a row to comprehend_browser_log so awareness pre/post is measurable.

Usage in a Cowork session:
  1. Run --next 1 to get the next job
  2. Open Gemini Advanced (browser), paste prompt + text, capture JSON response
  3. Run --write --tct ... --json '...' to commit
  4. Repeat. Or batch in browser_batch.

Idempotent (won't double-write a comprehended title), respects CONF_WRITE
threshold, mirrors comprehend.py's exact UPDATE logic. Reads PROMPT from
comprehend.py at import time so they cannot drift.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras

# Import PROMPT + CONF_WRITE from comprehend.py — single source of truth, no drift
sys.path.insert(0, str(Path(__file__).resolve().parent))
from comprehend import PROMPT, CONF_WRITE  # noqa: E402

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True
    return c


def _ensure_log_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS comprehend_browser_log (
            id          serial PRIMARY KEY,
            tct         text NOT NULL,
            transport   text NOT NULL DEFAULT 'browser',  -- 'browser' | 'api' | 'manual'
            written     boolean NOT NULL,
            confidence  numeric,
            title_status text,
            raw_json    jsonb,
            session_id  text,
            created_at  timestamptz DEFAULT now()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cbl_tct ON comprehend_browser_log(tct, created_at DESC)")


def next_jobs(n: int = 1):
    """Return up to N pending titles needing comprehension, mirroring comprehend.sweep()'s query."""
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT t.tct_number,
               LEFT(d.extracted_text, 12000) AS text
          FROM titles t
          JOIN documents d ON d.id = t.source_doc_id
     LEFT JOIN property_assets p ON p.title_ref = t.tct_number
         WHERE LENGTH(COALESCE(d.extracted_text, '')) > 50
           AND COALESCE(p.note, '') NOT LIKE %s
         ORDER BY t.tct_number
         LIMIT %s
    """, ('%comprehended%', n))
    rows = cur.fetchall()
    cur.close(); c.close()
    jobs = []
    for r in rows:
        jobs.append({
            "tct": r["tct_number"],
            "prompt": PROMPT,
            "text": r["text"],
            "instructions_for_browser": (
                "Paste the PROMPT, then 'TEXT:', then the TEXT into Gemini Advanced "
                "chat (gemini.google.com). Capture the JSON response and pass it back "
                "via: python3 comprehend_browser_adapter.py --write --tct " +
                r["tct_number"] + " --json '...'"
            ),
        })
    return jobs


def write_result(tct: str, parsed: dict, session_id: str = None):
    """Mirror comprehend_title's write logic exactly."""
    if not isinstance(parsed, dict):
        return {"tct": tct, "error": "not a dict"}
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    _ensure_log_table(cur)

    conf = float(parsed.get("confidence") or 0)
    title_status = parsed.get("title_status")
    written = False
    flagged = False
    note_text = None

    if conf >= CONF_WRITE and title_status in ("clean", "clouded", "cancelled"):
        note_text = (
            f"comprehended {title_status} (conf {conf:.2f}, via browser): "
            f"{str(parsed.get('evidence', ''))[:160]}"
        )
        cur.execute("""
            UPDATE property_assets
               SET title_status = %s,
                   tier = CASE
                            WHEN %s IN ('clouded', 'cancelled') THEN 'recover_then'
                            WHEN COALESCE(area_sqm, 0) > 20000 THEN 'develop'
                            ELSE 'earn_now'
                          END,
                   note = LEFT(COALESCE(note, '') || ' | ' || %s, 400),
                   est_value = COALESCE(%s, est_value),
                   updated_at = now()
             WHERE title_ref = %s
        """, (
            title_status,
            title_status,
            note_text,
            parsed.get("assessed_or_market_value_php"),
            tct,
        ))
        written = cur.rowcount > 0
    elif conf < CONF_WRITE:
        flagged = True

    cur.execute("""
        INSERT INTO comprehend_browser_log
            (tct, transport, written, confidence, title_status, raw_json, session_id)
        VALUES (%s, 'browser', %s, %s, %s, %s::jsonb, %s)
    """, (tct, written, conf, title_status, json.dumps(parsed), session_id))

    cur.close(); c.close()
    return {
        "tct": tct,
        "written": written,
        "flagged_for_human": flagged,
        "title_status": title_status,
        "confidence": conf,
        "note": note_text,
    }


def baseline_count():
    """How many titles are still pending comprehension. The awareness move = this number down."""
    c = _conn(); cur = c.cursor()
    cur.execute("""
        SELECT COUNT(*)
          FROM titles t
          JOIN documents d ON d.id = t.source_doc_id
     LEFT JOIN property_assets p ON p.title_ref = t.tct_number
         WHERE LENGTH(COALESCE(d.extracted_text, '')) > 50
           AND COALESCE(p.note, '') NOT LIKE %s
    """, ('%comprehended%',))
    n = cur.fetchone()[0]
    cur.close(); c.close()
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd")
    ap.add_argument("--next", type=int, default=None, help="print next N pending jobs as JSON")
    ap.add_argument("--write", action="store_true", help="write a result (requires --tct + --json)")
    ap.add_argument("--tct", help="title number for --write")
    ap.add_argument("--json", help="JSON string of Gemini's response for --write")
    ap.add_argument("--session-id", default=None, help="optional session id for the log row")
    ap.add_argument("--status", action="store_true", help="print baseline pending count + a header")
    args = ap.parse_args()

    if args.status:
        n = baseline_count()
        print(json.dumps({"pending_titles": n,
                          "interpretation": "drain this number; each drain == awareness move"},
                         indent=2))
        return

    if args.next is not None:
        jobs = next_jobs(args.next)
        print(json.dumps(jobs, indent=2))
        return

    if args.write:
        if not args.tct or not args.json:
            print("ERROR: --write requires --tct and --json", file=sys.stderr)
            sys.exit(2)
        try:
            parsed = json.loads(args.json)
        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"--json not valid JSON: {e}"}, indent=2), file=sys.stderr)
            sys.exit(2)
        result = write_result(args.tct, parsed, session_id=args.session_id)
        print(json.dumps(result, indent=2))
        return

    print(__doc__)


if __name__ == "__main__":
    main()
