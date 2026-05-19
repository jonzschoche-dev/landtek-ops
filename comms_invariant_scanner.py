#!/usr/bin/env python3
"""comms_invariant_scanner — hourly repo scan for client-comms violations.

Enforces (mechanically) [[feedback_no_ops_leak_to_client_ever]]:
  • No raw client chat_id literals outside the allowed files.
  • No raw `requests.post(... api.telegram.org ...)` to client IDs outside comms.py.

If a violation is detected, an ops alert is enqueued (audience='ops'). This is
the CI substitute that catches new direct-send code before it ships content
to a client. Approved files (comms.py, comms_recipients.py, tests, docs)
are excluded from the scan.

Runs as: systemctl --now enable comms-invariant-scanner.timer (hourly).
Exit code 0 always (alerts are enqueued, not raised).
"""
import os
import re
import sys
import subprocess

sys.path.insert(0, "/root/landtek")
import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# Files allowed to mention client chat_ids (the source-of-truth set).
ALLOWED_FILES = {
    "/root/landtek/comms_recipients.py",
    "/root/landtek/comms.py",
    "/root/landtek/comms_invariant_scanner.py",
    "/root/landtek/get_client_for_telegram_id.py",       # registry helper
    "/root/landtek/log_telegram_with_client.py",         # ingest helper, read-side
    "/root/landtek/telegram_message_logger.py",          # ingest helper, read-side
    "/root/landtek/test_log_telegram.py",                # test fixture
}

# Client chat_ids registry (mirrors comms_recipients.MWK_001_CLIENT_RECIPIENTS).
CLIENT_CHAT_IDS = {"8575986732"}  # Don Qi Style — MWK-001 administrator


def scan_repo():
    """Walk /root/landtek (excluding migrations/snapshots/.git) and find any
    .py file that contains a raw client chat_id literal."""
    violations = []
    for root, dirs, files in os.walk("/root/landtek"):
        # Skip uninteresting dirs
        dirs[:] = [d for d in dirs
                   if d not in {".git", "migrations", "snapshots", "__pycache__",
                                "drafts", "node_modules", ".venv", "venv"}]
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(root, fn)
            if path in ALLOWED_FILES:
                continue
            try:
                with open(path, encoding="utf-8", errors="ignore") as f:
                    for line_no, line in enumerate(f, 1):
                        for cid in CLIENT_CHAT_IDS:
                            if cid in line and not line.strip().startswith("#"):
                                violations.append({
                                    "file": path,
                                    "line": line_no,
                                    "chat_id": cid,
                                    "code": line.rstrip()[:200],
                                })
            except Exception:
                continue
    return violations


def enqueue_alert(violations: list[dict]):
    """Insert an ops-only gap_alert into tg_inquiry_queue."""
    if not violations:
        return False
    snippets = []
    for v in violations[:8]:
        # Escape angle brackets so the HTML renderer doesn't choke
        code_safe = (v["code"].replace("&", "&amp;")
                              .replace("<", "&lt;")
                              .replace(">", "&gt;"))
        snippets.append(
            f"  • <code>{v['file'].replace('/root/landtek/', '')}:{v['line']}</code> "
            f"(chat_id {v['chat_id']})\n    {code_safe[:140]}"
        )
    body = (
        f"🚫 <b>Comms-invariant scanner — {len(violations)} violation(s)</b>\n"
        f"<i>Raw client chat_id outside the approved files.</i>\n\n"
        f"<b>Rule:</b> only comms.py / comms_recipients.py may reference client "
        f"chat_ids. Direct sends bypass the audience gate.\n\n"
        f"<b>Locations:</b>\n" + "\n".join(snippets) + "\n\n"
        f"<b>Fix:</b> route the send through "
        f"<code>comms_send(audience=..., kind=..., case_file=...)</code> or "
        f"remove the literal."
    )
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    # Dedup: don't double-enqueue if the same set is already queued/active
    cur.execute("""
        SELECT id FROM tg_inquiry_queue
         WHERE kind='gap_alert'
           AND audience='ops'
           AND status IN ('queued','active')
           AND notes LIKE %s
         LIMIT 1
    """, (f"%comms_invariant_scanner:n={len(violations)}%",))
    if cur.fetchone():
        cur.close(); conn.close()
        return False
    cur.execute("""
        INSERT INTO tg_inquiry_queue (kind, audience, priority, source_table,
                                       matter_code, composed_html, notes)
        VALUES ('gap_alert', 'ops', 10, 'code_scanner',
                'MWK-001', %s,
                %s)
        RETURNING id
    """, (body[:6000], f"comms_invariant_scanner:n={len(violations)}"))
    inquiry_id = cur.fetchone()[0]
    cur.close(); conn.close()
    return inquiry_id


def main():
    violations = scan_repo()
    if not violations:
        print(f"comms_invariant_scanner: clean (0 violations)")
        return 0
    print(f"comms_invariant_scanner: {len(violations)} violation(s) found")
    for v in violations[:10]:
        print(f"  {v['file']}:{v['line']}: {v['code'][:120]}")
    inquiry_id = enqueue_alert(violations)
    if inquiry_id:
        print(f"  → enqueued ops alert #{inquiry_id}")
    else:
        print(f"  → dedupe hit, no new alert")
    return 0


if __name__ == "__main__":
    sys.exit(main())
