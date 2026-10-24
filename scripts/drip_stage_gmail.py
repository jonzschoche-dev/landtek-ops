#!/usr/bin/env python3
"""drip_stage_gmail.py — put a drip letter into Jonathan's Gmail DRAFTS. Never sends: drafts.create only, with the
gmail.compose scope; there is no send call anywhere in this module.

Used by the Drip UI's Go (Jonathan, 23 Oct 2026: "Go makes a Gmail draft"). Default account: jonzschoche@gmail.com,
the origin of the MWK threads (Charter channel rule); the draft is a new message — when the letter must sit in an
existing thread, pass thread_id (and in_reply_to, the Message-ID header of the message answered) and the draft is
staged as a reply in that thread (Charter channel rule: always the same thread).

  stage_draft(to, subject, body, cc=None, attachments=(), account="backup", thread_id=None, in_reply_to=None) -> draft id
"""
import base64
import json
import mimetypes
import os
import sys
from email.message import EmailMessage

sys.path.insert(0, "/root/landtek")
FROM = {"backup": "Jonathan Zschoche <jonzschoche@gmail.com>", "primary": "Jonathan Zschoche <jonathan@hayuma.org>"}
SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]


def _service(account):
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from gmail_watcher import load_env_credentials
    env = load_env_credentials()
    key = "GMAIL_REFRESH_TOKEN_BACKUP" if account == "backup" else "GMAIL_REFRESH_TOKEN"
    with open("/root/landtek/gmail_oauth_client.json") as f:
        web = (lambda o: o.get("web") or o.get("installed"))(json.load(f))
    creds = Credentials(None, refresh_token=env[key], token_uri=web["token_uri"], client_id=web["client_id"],
                        client_secret=web["client_secret"], scopes=SCOPES)
    creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def stage_draft(to, subject, body, cc=None, attachments=(), account="backup", thread_id=None, in_reply_to=None):
    msg = EmailMessage()
    msg["From"] = FROM[account]
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(body)
    for path in attachments or ():
        if path and os.path.isfile(path):
            ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
            main, sub = ctype.split("/", 1)
            with open(path, "rb") as f:
                msg.add_attachment(f.read(), maintype=main, subtype=sub, filename=os.path.basename(path))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    message = {"raw": raw}
    if thread_id:
        message["threadId"] = thread_id
    d = _service(account).users().drafts().create(userId="me", body={"message": message}).execute()
    return d["id"]


def delete_draft(draft_id, account="backup"):
    """Only for removing a TEST draft this module created."""
    _service(account).users().drafts().delete(userId="me", id=draft_id).execute()
