#!/usr/bin/env python3
"""Re-authorize the jonzschoche@gmail.com mailbox (the "backup" account) — run on the MAC.

Why: gmail_watcher --account backup reads GMAIL_REFRESH_TOKEN_BACKUP from /root/landtek/.env. When that
token dies (invalid_grant — Google expires refresh tokens after 7 days while the OAuth app is in
"Testing" status), the jonzschoche mirror silently stops. First seen 2026-09-22; ARTA mail missed.

What it does:
  1. pulls the OAuth client from the VPS (gmail_oauth_client.json);
  2. opens your browser for consent, pre-selecting jonzschoche@gmail.com;
     scopes: gmail.readonly + gmail.send + gmail.compose (compose = Claude can stage DRAFTS; it never sends);
  3. checks the token really belongs to jonzschoche@gmail.com (refuses otherwise);
  4. writes GMAIL_REFRESH_TOKEN_BACKUP into /root/landtek/.env on the VPS (timestamped .bak first);
  5. runs one read-only test pull.

  python3 scripts/mint_gmail_backup_token.py

Permanent fix (Jonathan, Google Cloud console): OAuth consent screen → Publishing status → "In production".
While it stays in "Testing", this token will die again in 7 days.
"""
import json
import os
import subprocess
import sys
import tempfile

ACCOUNT = "jonzschoche@gmail.com"
ENV_KEY = "GMAIL_REFRESH_TOKEN_BACKUP"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly",
          "https://www.googleapis.com/auth/gmail.send",
          "https://www.googleapis.com/auth/gmail.compose"]


def main():
    import urllib.request
    from google_auth_oauthlib.flow import InstalledAppFlow

    tmp = tempfile.mkdtemp()
    client = os.path.join(tmp, "client.json")
    subprocess.run(["scp", "-q", "landtek:/root/landtek/gmail_oauth_client.json", client], check=True)
    flow = InstalledAppFlow.from_client_secrets_file(client, scopes=SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline", login_hint=ACCOUNT,
                                  authorization_prompt_message=f"\nOpening browser — choose {ACCOUNT} and allow.\n")
    os.remove(client)
    if not creds.refresh_token:
        sys.exit("No refresh token returned — remove the app at myaccount.google.com/permissions and retry.")
    req = urllib.request.Request("https://gmail.googleapis.com/gmail/v1/users/me/profile",
                                 headers={"Authorization": "Bearer " + creds.token})
    who = json.loads(urllib.request.urlopen(req, timeout=30).read()).get("emailAddress", "")
    if who.lower() != ACCOUNT:
        sys.exit(f"REFUSED: you consented as {who}, not {ACCOUNT}. Nothing written. Run again and pick {ACCOUNT}.")
    print(f"Consent OK for {who}; scopes: {' '.join(s.rsplit('/', 1)[-1] for s in creds.scopes or SCOPES)}")

    # write to the VPS .env — backup first, re-read at write time (VPS live-file race rule)
    remote = r'''
import os, sys, time, shutil
p = "/root/landtek/.env"; key = sys.argv[1]; tok = sys.stdin.read().strip()
shutil.copy2(p, p + ".bak-" + time.strftime("%Y%m%d-%H%M%S"))
lines = open(p).read().splitlines(); out = []; done = False
for l in lines:
    if l.startswith(key + "="):
        out.append(key + "=" + tok); done = True
    else:
        out.append(l)
if not done:
    out.append(key + "=" + tok)
open(p, "w").write("\n".join(out) + "\n"); os.chmod(p, 0o600)
print("VPS .env updated:", key, "(backup kept)")
'''
    subprocess.run(["ssh", "landtek", "python3", "-c", remote, ENV_KEY], input=creds.refresh_token, text=True, check=True)
    subprocess.run(["ssh", "landtek",
                    "cd /root/landtek && set -a && . ./.env && set +a && "
                    "timeout 120 python3 gmail_watcher.py --account backup --query 'newer_than:2d' --max 3 --dry-run 2>&1 | tail -4"],
                   check=False)
    print("\nDone. The 3-hourly sweep (landtek-gmail-backup-sweep.timer) will resume on its next tick.")


if __name__ == "__main__":
    main()
