#!/usr/bin/env python3
"""doc_triage.py — surface 1 unclassified document to Telegram for human classification.

Runs every 2 hours during 8am-8pm Manila via systemd timer. Picks the oldest
unclassified doc (no row in document_matter_links), computes a heuristic
suggestion for the right matter, sends to Jonathan via Telegram with:

  - doc#NNN, filename, preview
  - drive link via leo.hayuma.org/files/c/NNN
  - suggested matter (heuristic: entity-overlap with already-classified docs)
  - reply instructions (file NNN to MATTER / skip NNN / unrelated NNN)

Idempotent: each doc gets pushed exactly once per 7 days via doc_triage_pushed
table.

The suggestion algorithm is intentionally cheap and explainable:
  1. Pull top-N entities mentioned in target doc (doc_entities table)
  2. Find which matter has the most OTHER docs sharing those entities
  3. Score = shared entities; ties broken by recency of last doc

Usage:
  python3 doc_triage.py              # send 1 triage candidate
  python3 doc_triage.py --batch 3    # send 3 candidates
  python3 doc_triage.py --dry-run    # print, don't send
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
JONATHAN_CHAT_ID = "6513067717"
MANILA_TZ = timezone(timedelta(hours=8))
DRIVE_PROXY = "https://leo.hayuma.org/files/c/"
DEDUP_INTERVAL_DAYS = 7


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"[{ts}] {msg}", flush=True)


def load_bot_token() -> str | None:
    for key in ("TG_BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "BOT_TOKEN"):
        v = os.environ.get(key)
        if v:
            return v
    env_path = Path("/root/landtek/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            if k in ("TG_BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "BOT_TOKEN"):
                return v.strip().strip("'\"")
    return None


def esc(s: str | None) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send_telegram(token: str, chat_id: str, text: str) -> tuple[bool, str | None]:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=15) as r:
            body = r.read().decode("utf-8")
            j = json.loads(body)
            if j.get("ok"):
                return True, None
            return False, str(j.get("description", "unknown"))[:200]
    except Exception as e:
        return False, str(e)[:200]


def ensure_schema(cur) -> None:
    cur.execute("""
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
    """)


def pick_candidate(cur, exclude: set[int]) -> dict | None:
    """Pick the oldest doc with no matter linkage that wasn't pushed in last 7d."""
    cur.execute("""
        SELECT d.id, d.case_file, d.matter_code, d.smart_filename, d.original_filename,
               d.created_at, d.drive_file_id,
               LEFT(COALESCE(d.extracted_text, ''), 400) AS preview,
               LENGTH(COALESCE(d.extracted_text, '')) AS text_len
          FROM documents d
         WHERE NOT EXISTS (
                 SELECT 1 FROM document_matter_links l WHERE l.doc_id = d.id
               )
           AND NOT EXISTS (
                 SELECT 1 FROM doc_triage_pushed p
                  WHERE p.doc_id = d.id
                    AND p.pushed_at > now() - (INTERVAL '1 day' * %s)
               )
           AND d.id <> ALL(%s)
         ORDER BY d.created_at ASC NULLS LAST, d.id ASC
         LIMIT 1
    """, (DEDUP_INTERVAL_DAYS, list(exclude) or [0]))
    row = cur.fetchone()
    return dict(row) if row else None


def heuristic_suggest(cur, doc_id: int, top_n: int = 3) -> list[dict]:
    """Score matters by entity overlap with already-classified docs."""
    cur.execute("""
        WITH cand_entities AS (
          SELECT DISTINCT entity_id FROM doc_entities WHERE doc_id = %s
        ),
        scores AS (
          SELECT l.matter_code,
                 COUNT(DISTINCT de.entity_id) AS shared_entities,
                 COUNT(DISTINCT de.doc_id)    AS shared_docs,
                 MAX(d.created_at)            AS latest_doc_at
            FROM doc_entities de
            JOIN document_matter_links l ON l.doc_id = de.doc_id
            JOIN documents d ON d.id = de.doc_id
           WHERE de.entity_id IN (SELECT entity_id FROM cand_entities)
             AND de.doc_id <> %s
             AND l.matter_code NOT IN ('MWK-ESTATE')  -- too broad; reserve for explicit
           GROUP BY l.matter_code
        )
        SELECT matter_code, shared_entities, shared_docs, latest_doc_at
          FROM scores
         WHERE shared_entities >= 2  -- need ≥2 shared entities for confidence
         ORDER BY shared_entities DESC, shared_docs DESC, latest_doc_at DESC
         LIMIT %s
    """, (doc_id, doc_id, top_n))
    return [dict(r) for r in cur.fetchall()]


def build_message(doc: dict, suggestions: list[dict]) -> str:
    name = doc.get("smart_filename") or doc.get("original_filename") or f"(no filename) doc#{doc['id']}"
    name = name[:120]
    preview = (doc.get("preview") or "").replace("\n", " ").replace("\r", " ")
    preview = " ".join(preview.split())[:300]
    drive_url = f"{DRIVE_PROXY}{doc['id']}"

    lines = [
        f"📁 <b>Triage doc#{doc['id']}</b>",
        "",
        f"📄 <b>{esc(name)}</b>",
        f"🗂 current: case={esc(doc.get('case_file') or '∅')} matter={esc(doc.get('matter_code') or '∅')}",
        f"📅 ingested: {doc['created_at'].astimezone(MANILA_TZ).strftime('%Y-%m-%d') if doc.get('created_at') else '?'}",
        f"📎 <a href=\"{drive_url}\">open in Drive</a>",
    ]

    if preview:
        lines.append("")
        lines.append(f"<i>{esc(preview)}…</i>")

    if suggestions:
        lines.append("")
        lines.append("<b>Suggested matters</b> (by entity overlap):")
        for s in suggestions:
            lines.append(f"  • <code>{esc(s['matter_code'])}</code>  ({s['shared_entities']} shared entities, {s['shared_docs']} docs)")

    lines.append("")
    lines.append("<b>Reply with one of:</b>")
    lines.append(f"  • <code>file {doc['id']} to MWK-CV26360</code>  (or any matter)")
    lines.append(f"  • <code>skip {doc['id']}</code>  (defer 7 days)")
    lines.append(f"  • <code>unrelated {doc['id']}</code>  (mark as not case-relevant)")
    lines.append("")
    lines.append("<i>Leo will UPDATE documents.matter_code which fires the autolink trigger.</i>")

    return "\n".join(lines)


def mark_pushed(cur, doc_id: int, suggestion: str | None, ok: bool, err: str | None) -> None:
    cur.execute("""
        INSERT INTO doc_triage_pushed (doc_id, suggestion, telegram_ok, telegram_error)
        VALUES (%s, %s, %s, %s)
    """, (doc_id, suggestion, ok, err))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=1, help="number of candidates to push this run")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--working-hours-only", action="store_true",
                    help="skip outside 8am-8pm Manila")
    args = ap.parse_args()

    # Working hours guard
    if args.working_hours_only:
        now_manila = datetime.now(MANILA_TZ)
        if now_manila.hour < 8 or now_manila.hour >= 20:
            log(f"outside working hours ({now_manila.strftime('%H:%M')} Manila), skipping")
            return 0

    token = load_bot_token()
    if not token and not args.dry_run:
        log("FATAL: no bot token")
        return 1

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_schema(cur)

    pushed_this_run: set[int] = set()
    for _ in range(args.batch):
        doc = pick_candidate(cur, pushed_this_run)
        if not doc:
            log("no candidates in triage queue")
            break
        pushed_this_run.add(doc["id"])
        suggestions = heuristic_suggest(cur, doc["id"], top_n=3)
        msg = build_message(doc, suggestions)
        suggestion_str = ",".join(s["matter_code"] for s in suggestions) if suggestions else None

        if args.dry_run:
            log(f"[DRY] would push doc#{doc['id']}  suggest={suggestion_str}")
            print("--- message ---")
            print(msg)
            print("--- end ---")
            continue

        ok, err = send_telegram(token, JONATHAN_CHAT_ID, msg)
        mark_pushed(cur, doc["id"], suggestion_str, ok, err)
        log(f"pushed doc#{doc['id']}  ok={ok}  suggest={suggestion_str}  err={err}")

    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
