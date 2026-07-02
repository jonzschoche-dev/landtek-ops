#!/usr/bin/env python3
"""Mint a Google Calendar refresh token for the Agenda Engine (one-time).

The Gmail refresh token is scoped gmail.readonly and CANNOT authorize calendar
writes. This mints a token with the calendar.events scope, reusing the existing
OAuth client (gmail_oauth_client.json). Run it once; paste the result into
/root/landtek/.env as CALENDAR_REFRESH_TOKEN.

Usage:
  python3 scripts/mint_calendar_token.py            # local-server flow (opens browser)
  python3 scripts/mint_calendar_token.py --console  # console flow (headless VPS)

After it prints CALENDAR_REFRESH_TOKEN=..., add that line to /root/landtek/.env
(chmod 600) and run:  python3 scripts/calendar_sync.py --apply
"""
import argparse
import json
import sys

OAUTH_CLIENT_PATH = "/root/landtek/gmail_oauth_client.json"
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--console", action="store_true",
                    help="headless flow: prints a URL, you paste back the code")
    ap.add_argument("--client", default=OAUTH_CLIENT_PATH,
                    help="OAuth client json (default: the Gmail one)")
    args = ap.parse_args()

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        sys.exit("pip install google-auth-oauthlib  (missing)")

    with open(args.client) as f:
        conf = json.load(f)

    flow = InstalledAppFlow.from_client_config(conf, scopes=SCOPES)
    if args.console or not _has_display():
        # Manual copy/paste flow — works over SSH with no browser on the host.
        try:
            creds = flow.run_console()
        except AttributeError:
            # newer google-auth-oauthlib dropped run_console(); do it by hand
            flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
            auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
            print("\n1) Open this URL in a browser signed in to the LandTek Google account:\n")
            print("   " + auth_url + "\n")
            code = input("2) Paste the authorization code here: ").strip()
            flow.fetch_token(code=code)
            creds = flow.credentials
    else:
        creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

    if not creds.refresh_token:
        sys.exit("No refresh_token returned. Revoke prior grant / use prompt=consent and retry.")

    print("\n" + "=" * 60)
    print("Add this line to /root/landtek/.env (chmod 600):\n")
    print("CALENDAR_REFRESH_TOKEN=" + creds.refresh_token)
    print("=" * 60)


def _has_display():
    import os
    return bool(os.environ.get("DISPLAY")) or sys.platform == "darwin"


if __name__ == "__main__":
    main()
