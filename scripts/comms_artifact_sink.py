#!/usr/bin/env python3
"""comms_artifact_sink.py — the universal, media-type-agnostic comms intake sink.

One sink, N adapters. EVERY inbound artifact from anyone on a matter — document, image, audio
(voice later), video — lands in `documents` under the correct client_code, content-hash deduped,
A5 separation-safe, with the right downstream-processing state. Each channel adapter only fetches
the media bytes + hands off here; no per-channel persistence.

Mandate (never varies per channel):
  * content-hash dedup (same bytes -> existing document_id, never a 2nd row)
  * A5 resolve-or-HOLD: client_code required (from channel_users.mapped_client_code); if unresolved,
    quarantine + surface — NEVER guess a client, NEVER drop the artifact.
  * media-type-aware pending state: image/scan -> ocr_pending ; audio/video -> transcribe_pending ;
    born-digital text/PDF-with-text -> none. Downstream processors (reocr_local, Whisper — both
    local/owned, $0) pick up by state. Voice is a future downstream plug-in, not a re-architecture.
  * every artifact => exactly one comms_artifacts ledger row (landed|deduped|held|quarantined) so
    "lossless" is mechanically checkable (truth_tests/test_lossless_comms_intake.py).
  * degrade-don't-crash: any error -> quarantined (visible), never a silent drop.

Reuses blend_emails (B) for hash/dedup/store/text-extract — does NOT fork the proven path.
Email is NOT a client of this sink (imap_ingest.py is already lossless + multi-party).

CLI (for testing / manual land):
  python3 scripts/comms_artifact_sink.py --self-test          # synthetic land+dedup+hold, rolled back
"""
import hashlib
import mimetypes
import os
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, "/root/landtek"); sys.path.insert(0, "/root/landtek/scripts")
import blend_emails as B  # noqa: E402  (STORE, safe_name, extract_text, borne_date, find_existing)

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
STORE = "/root/landtek/corpus_store/comms"


def _media_state(mime, text):
    """(media_type, processing_state) — the downstream-processor router."""
    m = (mime or "").lower()
    if m.startswith("image/"):
        return "image", "ocr_pending"
    if m.startswith("audio/"):
        return "audio", "transcribe_pending"
    if m.startswith("video/"):
        return "video", "transcribe_pending"
    if m.startswith("text/"):
        return "text", "none"
    if m == "application/pdf" or "document" in m or m.endswith(("msword", "officedocument.wordprocessingml.document")):
        # born-digital if we already pulled real text; else it's a scan -> OCR
        return "document", ("none" if (text and text.strip()) else "ocr_pending")
    return "unknown", "none"


def _resolve_client(cur, channel, channel_user_id):
    """A5: the client_code this identity is bound to (channel_users.mapped_client_code). None => HOLD."""
    cur.execute("""SELECT cu.mapped_client_code
                     FROM channel_users cu JOIN channels c ON c.id = cu.channel_id
                    WHERE c.name = %s AND cu.channel_user_id = %s""",
                (channel, str(channel_user_id)))
    r = cur.fetchone()
    return (r["mapped_client_code"] if r else None) or None


def _ledger(cur, **kw):
    cur.execute("""INSERT INTO comms_artifacts
        (channel, channel_user_id, channel_message_id, client_code, media_ref, original_filename,
         mime_type, media_type, content_hash, doc_id, processing_state, status, reason)
        VALUES (%(channel)s,%(uid)s,%(msg_id)s,%(client)s,%(ref)s,%(fn)s,%(mime)s,%(mtype)s,
                %(hash)s,%(doc)s,%(pstate)s,%(status)s,%(reason)s)
        ON CONFLICT (channel_message_id, content_hash)
          WHERE channel_message_id IS NOT NULL AND content_hash IS NOT NULL
        DO NOTHING RETURNING id""", kw)
    row = cur.fetchone()
    return row["id"] if row else None


def land_artifact(channel, channel_user_id, channel_message_id, filename, data, mime=None,
                  media_ref=None, conn=None):
    """Land ONE artifact. Self-contained (opens its own autocommit conn unless one is passed).
    Returns {status, doc_id, client_code, processing_state, reason}. Never raises to the caller."""
    own = conn is None
    if own:
        conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    fn = filename or "artifact"
    mime = mime or mimetypes.guess_type(fn)[0] or "application/octet-stream"
    try:
        client = _resolve_client(cur, channel, channel_user_id)
        if not client:
            # A5: resolve-or-HOLD. Visible, never dropped, never guessed.
            _ledger(cur, channel=channel, uid=str(channel_user_id), msg_id=channel_message_id,
                    client=None, ref=media_ref, fn=fn, mime=mime, mtype=None, hash=None, doc=None,
                    pstate=None, status="held", reason="unresolved_client (A5): identity not bound to a client_code")
            return {"status": "held", "doc_id": None, "client_code": None,
                    "reason": "unresolved_client"}

        raw = data if isinstance(data, (bytes, bytearray)) else (data or "").encode("utf-8", "ignore")
        chash = hashlib.sha256(raw).hexdigest()
        existing, _how = B.find_existing(cur, chash)
        if existing:
            cur.execute("""INSERT INTO document_matter_links (doc_id, matter_code) VALUES (%s,%s)
                           ON CONFLICT DO NOTHING""", (existing, client))
            _ledger(cur, channel=channel, uid=str(channel_user_id), msg_id=channel_message_id,
                    client=client, ref=media_ref, fn=fn, mime=mime, mtype=None, hash=chash,
                    doc=existing, pstate=None, status="deduped", reason="content_hash match")
            return {"status": "deduped", "doc_id": existing, "client_code": client}

        os.makedirs(STORE, exist_ok=True)
        path = os.path.join(STORE, f"{channel}_{B.safe_name(str(channel_message_id or chash[:12]))}__{B.safe_name(fn)}")
        with open(path, "wb") as fh:
            fh.write(raw)
        text = None
        try:
            text = B.extract_text(raw, mime, path)  # born-digital text if any; images return empty
        except Exception:
            text = None
        media_type, pstate = _media_state(mime, text)
        emeta = {"source": f"comms_{channel}", "channel": channel,
                 "channel_user_id": str(channel_user_id), "channel_message_id": channel_message_id,
                 "media_ref": media_ref, "processing_state": pstate}
        cur.execute("""INSERT INTO documents
            (master_form, ingest_source, original_filename, smart_filename, mime_type, file_path,
             content_hash, case_file, classification, extracted_text, processing_mode, execution_metadata)
            VALUES ('digital',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (f"comms_{channel}", fn, fn, mime, path, chash, client, "correspondence_artifact",
             (text or None), pstate, psycopg2.extras.Json(emeta)))
        did = cur.fetchone()["id"]
        cur.execute("""INSERT INTO document_matter_links (doc_id, matter_code) VALUES (%s,%s)
                       ON CONFLICT DO NOTHING""", (did, client))
        _ledger(cur, channel=channel, uid=str(channel_user_id), msg_id=channel_message_id,
                client=client, ref=media_ref, fn=fn, mime=mime, mtype=media_type, hash=chash,
                doc=did, pstate=pstate, status="landed", reason=None)
        return {"status": "landed", "doc_id": did, "client_code": client, "processing_state": pstate}
    except Exception as e:
        # degrade-don't-crash: quarantine (visible), never a silent drop
        try:
            _ledger(cur, channel=channel, uid=str(channel_user_id), msg_id=channel_message_id,
                    client=None, ref=media_ref, fn=fn, mime=mime, mtype=None, hash=None, doc=None,
                    pstate=None, status="quarantined", reason=f"{type(e).__name__}: {str(e)[:200]}")
        except Exception:
            pass
        return {"status": "quarantined", "doc_id": None, "reason": str(e)[:200]}
    finally:
        cur.close()
        if own:
            conn.close()


def self_test():
    """Synthetic land + dedup + hold, inside a rolled-back transaction (prod untouched)."""
    conn = psycopg2.connect(DSN); conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT channel_user_id FROM channel_users cu JOIN channels c ON c.id=cu.channel_id "
                "WHERE c.name='messenger' AND cu.mapped_client_code IS NOT NULL LIMIT 1")
    bound = cur.fetchone()
    payload = b"%PDF-1.4 synthetic self-test artifact " + os.urandom(8)
    print("[self-test] bound identity:", bound and bound["channel_user_id"])
    if bound:
        r1 = land_artifact("messenger", bound["channel_user_id"], None, "selftest.pdf", payload,
                           mime="application/pdf", media_ref="selftest", conn=conn)
        r2 = land_artifact("messenger", bound["channel_user_id"], None, "selftest.pdf", payload,
                           mime="application/pdf", media_ref="selftest", conn=conn)  # dedup
        print("[self-test] first  land :", r1)
        print("[self-test] second land :", r2, "(expect deduped -> same doc_id)")
        img = land_artifact("messenger", bound["channel_user_id"], None, "scan.jpg", os.urandom(64),
                            mime="image/jpeg", conn=conn)
        print("[self-test] image land  :", img, "(expect processing_state=ocr_pending)")
    hold = land_artifact("messenger", "UNBOUND_STRANGER_999", None, "x.pdf", os.urandom(32),
                         mime="application/pdf", conn=conn)
    print("[self-test] unbound     :", hold, "(expect status=held, no doc)")
    conn.rollback()
    cur.close(); conn.close()
    print("[self-test] rolled back — prod untouched.")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        print(__doc__)
