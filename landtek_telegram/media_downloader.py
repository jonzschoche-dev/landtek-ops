#!/usr/bin/env python3
"""media_downloader.py — pull Telegram photos/documents to local disk.

Runs as a poller (every 5s): scans telegram_inbox for rows where
media_file_id is set but media_path is NULL, calls Telegram's getFile +
fetch the binary, saves to /root/landtek/vault_media/, updates the row.

Files land at /root/landtek/vault_media/inbox_<id>_<file_id_short>.jpg
so they're stable references. Future: tie to vault entries via
documents.digital_scan_id once a vault command lands referencing the file.
"""
from __future__ import annotations
import os
import sys
import time
import json
import hashlib
import urllib.request
import urllib.error

import psycopg2

PG_DSN = os.environ.get("LANDTEK_TG_PG_DSN",
                        "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
MEDIA_DIR = os.environ.get("LANDTEK_VAULT_MEDIA_DIR", "/root/landtek/vault_media")
POLL = float(os.environ.get("LANDTEK_TG_POLL_SECONDS", "5"))


def _bot_token():
    p = "/root/landtek/.env"
    for line in open(p):
        line = line.strip()
        for k in ("TG_BOT_TOKEN=", "TELEGRAM_BOT_TOKEN=", "BOT_TOKEN="):
            if line.startswith(k):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


TOKEN = _bot_token()


def _extract_file_id(raw_update):
    """Pull the largest photo / document file_id from a Telegram update."""
    if isinstance(raw_update, str):
        try:
            raw_update = json.loads(raw_update)
        except Exception:
            return None, None
    msg = (raw_update.get("message")
           or raw_update.get("edited_message")
           or raw_update.get("channel_post")
           or {})
    photos = msg.get("photo") or []
    if photos:
        biggest = max(photos, key=lambda p: p.get("file_size", 0))
        return biggest.get("file_id"), "photo"
    doc = msg.get("document") or {}
    if doc.get("file_id"):
        return doc.get("file_id"), (doc.get("mime_type") or "document")
    voice = msg.get("voice") or {}
    if voice.get("file_id"):
        return voice.get("file_id"), "voice"
    return None, None


def _fetch_telegram_file(file_id):
    """Telegram getFile → file_path → download bytes."""
    if not TOKEN:
        return None, None, "no_token"
    api = f"https://api.telegram.org/bot{TOKEN}/getFile?file_id={file_id}"
    try:
        with urllib.request.urlopen(api, timeout=15) as r:
            payload = json.loads(r.read().decode("utf-8"))
        if not payload.get("ok"):
            return None, None, f"getFile_failed: {payload}"
        file_path = (payload.get("result") or {}).get("file_path")
        if not file_path:
            return None, None, "no_file_path"
        dl = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
        with urllib.request.urlopen(dl, timeout=30) as r:
            data = r.read()
        # Telegram returns the original extension from file_path
        ext = os.path.splitext(file_path)[1] or ".bin"
        return data, ext, None
    except Exception as e:
        return None, None, f"{type(e).__name__}: {str(e)[:200]}"


_MEDIA_COLS = ("media_file_id", "media_type", "media_path", "media_size", "media_error")


def _ensure_columns(cur):
    """Make sure the media columns + pending index exist.

    MUST be called once at startup only, never inside the poll loop. An
    unconditional `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` still requests an
    ACCESS EXCLUSIVE lock on every call; if anything else holds a conflicting
    lock at that moment, the ALTER queues for the exclusive lock and — because
    Postgres lock queues are FIFO — every subsequent INSERT/SELECT queues behind
    it, freezing the whole table. (This, run every 5s, was the amplifier in the
    2026-06-08 Telegram choke.) So: check first, only ALTER when a column is
    actually missing, and bound the wait with lock_timeout so it can never hang.
    """
    cur.execute("""
        SELECT count(*) FROM information_schema.columns
         WHERE table_name = 'telegram_inbox'
           AND column_name = ANY(%s)
    """, (list(_MEDIA_COLS),))
    have = cur.fetchone()[0]
    if have < len(_MEDIA_COLS):
        cur.execute("SET lock_timeout = '3s'")
        try:
            cur.execute("""
                ALTER TABLE telegram_inbox
                    ADD COLUMN IF NOT EXISTS media_file_id text,
                    ADD COLUMN IF NOT EXISTS media_type    text,
                    ADD COLUMN IF NOT EXISTS media_path    text,
                    ADD COLUMN IF NOT EXISTS media_size    int,
                    ADD COLUMN IF NOT EXISTS media_error   text
            """)
        finally:
            cur.execute("RESET lock_timeout")
    cur.execute("""
        CREATE INDEX IF NOT EXISTS telegram_inbox_media_pending_idx
            ON telegram_inbox (id)
            WHERE media_file_id IS NOT NULL AND media_path IS NULL
              AND media_error IS NULL
    """)


def _backfill_media_file_ids(cur):
    """For rows whose raw_update has a photo but media_file_id isn't set yet."""
    cur.execute("""
        SELECT id, raw_update::text
          FROM telegram_inbox
         WHERE media_file_id IS NULL
           AND (raw_update::text LIKE '%"photo"%'
                OR raw_update::text LIKE '%"document"%'
                OR raw_update::text LIKE '%"voice"%')
         ORDER BY id
         LIMIT 50
    """)
    rows = cur.fetchall()
    for row_id, raw in rows:
        fid, kind = _extract_file_id(raw)
        if fid:
            cur.execute("""
                UPDATE telegram_inbox SET media_file_id = %s, media_type = %s
                 WHERE id = %s
            """, (fid, kind, row_id))


def main():
    os.makedirs(MEDIA_DIR, exist_ok=True)
    print(f"[media] dir={MEDIA_DIR} poll={POLL}s")
    # One-time schema ensure at startup — NEVER inside the loop (see
    # _ensure_columns docstring). Guarded + lock_timeout-bounded so it cannot
    # freeze the table even on a cold DB.
    try:
        c0 = psycopg2.connect(PG_DSN); c0.autocommit = True
        _ensure_columns(c0.cursor())
        c0.close()
        print("[media] schema ensured")
    except Exception as e:
        print(f"[media] schema ensure failed (continuing): {e}", file=sys.stderr)
    while True:
        try:
            conn = psycopg2.connect(PG_DSN); conn.autocommit = True
            cur = conn.cursor()
            _backfill_media_file_ids(cur)
            cur.execute("""
                SELECT id, media_file_id, media_type
                  FROM telegram_inbox
                 WHERE media_file_id IS NOT NULL
                   AND media_path IS NULL
                   AND media_error IS NULL
                 ORDER BY id LIMIT 5
            """)
            rows = cur.fetchall()
            for row_id, fid, kind in rows:
                data, ext, err = _fetch_telegram_file(fid)
                if err:
                    cur.execute("UPDATE telegram_inbox SET media_error=%s WHERE id=%s",
                                (err[:200], row_id))
                    print(f"[media] inbox#{row_id} FAIL {err[:100]}")
                    continue
                short = hashlib.sha1(fid.encode()).hexdigest()[:12]
                path = os.path.join(MEDIA_DIR, f"inbox_{row_id}_{short}{ext}")
                with open(path, "wb") as f:
                    f.write(data)
                cur.execute("""
                    UPDATE telegram_inbox
                       SET media_path = %s, media_size = %s
                     WHERE id = %s
                """, (path, len(data), row_id))
                print(f"[media] inbox#{row_id} -> {path} ({len(data)}b)")
            cur.close(); conn.close()
        except Exception as e:
            print(f"[media] loop error: {e}", file=sys.stderr)
        time.sleep(POLL)


if __name__ == "__main__":
    main()
