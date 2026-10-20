#!/usr/bin/env python3
"""drip_desk.py — the drip's single input/output: the "DRIP DESK" Google Doc in LANDTEK/Drip (Jonathan, 20 Oct 2026).

Jonathan types ONE command under INPUT:; this job (cron, every 2 min, on the VPS) reads it, runs it against the live
review queue, and rewrites the doc with the result under OUTPUT: and the input line cleared. Deterministic, no LLM.
Never sends, never stages an e-mail draft (staging is a separate step on the Mac, from the 'drip_stage_draft' work order).

Commands (case-insensitive):
  next                      → the ONE next draft waiting for comment (full text)
  status                    → the queue board
  comment <ID> <words…>     → logged on that draft; it comes back revised
  make the draft <ID>       → Jonathan's go: marked ready_for_draft (+ staging work order)

  python3 scripts/drip_desk.py            # one pass (what cron runs)
  python3 scripts/drip_desk.py --dry      # read + parse only, print what it would do
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

from google.oauth2 import service_account
from googleapiclient.discovery import build

DOC_ID = os.environ.get("DRIP_DESK_DOC", "15wjEcIeKaBrIWsLDFIceAEd4B4ViiUwTTV47w1JvV5k")
CREDS = "/root/landtek/google-creds.json"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE = [sys.executable, os.path.join(REPO, "scripts", "drip_draft_queue.py")]
HEADER = ("DRIP DESK  (type ONE command on the line under INPUT, then wait ~2 minutes)\n\n"
          "Commands:  next  |  status  |  comment 11 your words here  |  make the draft 11\n\n")


def services():
    cr = service_account.Credentials.from_service_account_file(
        CREDS, scopes=["https://www.googleapis.com/auth/drive"])
    return build("drive", "v3", credentials=cr, cache_discovery=False), None


def read_text(drive):
    data = drive.files().export(fileId=DOC_ID, mimeType="text/plain").execute()
    return data.decode("utf-8-sig") if isinstance(data, bytes) else data


def parse(text):
    m = re.search(r"INPUT:\s*(.*?)\s*OUTPUT:", text, re.S | re.I)
    if not m:
        return None
    lines = [l.strip() for l in m.group(1).splitlines() if l.strip()]
    return lines[0] if lines else None


def run(cmd):
    c = cmd.strip()
    low = c.lower()
    stamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%d %b %Y %H:%M PHT")
    if low == "next":
        args = ["--fill", "--next"]
    elif low == "status":
        args = ["--status"]
    elif m := re.match(r"(?i)comment\s+#?(\d+)\s+(.+)", c, re.S):
        args = ["--comment", m.group(1), m.group(2).strip()]
    elif m := re.match(r"(?i)make\s+the\s+draft\s+#?(\d+)", c):
        args = ["--ready", m.group(1), f"Jonathan via DRIP DESK {stamp}: 'make the draft {m.group(1)}'"]
    else:
        return stamp, f"Not understood: “{c}”.\nUse: next | status | comment 11 your words | make the draft 11"
    p = subprocess.run(QUEUE + args, capture_output=True, text=True, cwd=REPO, timeout=240)
    out = (p.stdout or "").strip()
    if p.returncode != 0:
        out += "\n\n[error] " + (p.stderr or "").strip()[-600:]
    if args[0] == "--comment":
        out = f"Comment logged on draft #{args[1]}. It comes back revised; meanwhile type 'next' for the next one.\n\n" + out
    if args[0] == "--ready":
        out = (f"Draft #{args[1]} marked READY on your word. It will be staged as an unsent draft in its thread's "
               "account (or as a print set for paper). Nothing is sent.\n\n" + out)
    return stamp, out


def write(drive, body):
    """Replace the doc's content via the Drive API (text/plain upload is converted into the Google Doc).
    The Docs API is disabled in the service account's project, so no Docs API calls are used."""
    from googleapiclient.http import MediaInMemoryUpload
    drive.files().update(fileId=DOC_ID, media_body=MediaInMemoryUpload(body.encode("utf-8"), mimetype="text/plain"),
                         supportsAllDrives=True).execute()


def log_event(cmd, stamp):
    try:
        import psycopg2
        c = psycopg2.connect(os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"))
        cur = c.cursor()
        cur.execute("INSERT INTO drip_event (kind, detail) VALUES ('desk_command', %s)",
                    (json.dumps({"command": cmd, "at": stamp, "doc": DOC_ID}),))
        c.commit()
    except Exception as e:  # degrade, don't crash
        print("event log failed:", e, file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    drive, _ = services()
    text = read_text(drive)
    cmd = parse(text)
    if not cmd:
        return 0
    if a.dry:
        print("would run:", cmd)
        return 0
    stamp, out = run(cmd)
    write(drive, HEADER + "INPUT:\n\n\n" + f"OUTPUT:  (for “{cmd}”, {stamp})\n\n" + out + "\n")
    log_event(cmd, stamp)
    print(f"{stamp} ran: {cmd}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
