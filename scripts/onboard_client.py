#!/usr/bin/env python3
"""onboard_client.py — one-command client onboarding, channel-agnostic.

Updates an existing client record OR creates one. Captures any combination
of telegram, instagram, whatsapp, messenger, email, phone, signal.

Usage:
  # Update existing Allan with Instagram handle
  onboard_client.py 8 --instagram @allan_inocalla

  # Add multiple channels at once
  onboard_client.py 8 --instagram @allan_inocalla --whatsapp +639171234567 --email allan@example.com

  # Create new client from scratch
  onboard_client.py --new --name "Jane Doe" --case-file MWK-001 --telegram 1234567 --email jane@example.com

After update, optionally logs an audit chat_note + prints next-action."""
from __future__ import annotations
import argparse
import os
import sys
import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

# Channel name → clients column
CHANNEL_COLS = {
    "telegram":  "telegram_id",
    "telegram_username": "telegram_username",
    "instagram": "instagram_handle",
    "whatsapp":  "whatsapp_number",
    "messenger": "messenger_id",
    "signal":    "signal_number",
    "email":     "email",
    "phone":     "phone",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("client_id", nargs="?", type=int, help="existing clients.id to update")
    ap.add_argument("--new", action="store_true", help="create a new client instead")
    ap.add_argument("--name", help="client name (for --new)")
    ap.add_argument("--case-file", dest="case_file", help="case_file (for --new)")
    ap.add_argument("--client-code", dest="client_code", help="client_code (defaults to case_file)")
    ap.add_argument("--role", help="role (e.g., 'client', 'filing_assistant')")
    for ch in CHANNEL_COLS:
        ap.add_argument(f"--{ch.replace('_', '-')}", dest=ch, help=f"set {ch}")
    ap.add_argument("--last-contact-via", help="channel name they used most recently (records last_contact_channel + last_contact_at)")
    args = ap.parse_args()

    if not args.new and args.client_id is None:
        ap.print_help()
        return 1

    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET LOCAL app.actor = 'onboard_client.py'")

    if args.new:
        if not args.name or not args.case_file:
            print("--new requires --name and --case-file")
            return 1
        cur.execute(
            """
            INSERT INTO clients (name, case_file, client_code, role, source, status)
            VALUES (%s, %s, %s, %s, 'manual_onboard', 'Active')
            RETURNING id
            """,
            (args.name, args.case_file, args.client_code or args.case_file, args.role or "client"),
        )
        args.client_id = cur.fetchone()["id"]
        print(f"created client #{args.client_id}: {args.name}")

    # Build dynamic UPDATE
    updates = []
    params = []
    for ch, col in CHANNEL_COLS.items():
        val = getattr(args, ch, None)
        if val is not None:
            updates.append(f"{col} = %s")
            params.append(val)
    if args.role:
        updates.append("role = %s")
        params.append(args.role)
    if args.last_contact_via:
        updates.append("last_contact_channel = %s")
        params.append(args.last_contact_via)
        updates.append("last_contact_at = now()")

    if not updates:
        print("no channel updates specified")
        return 0

    params.append(args.client_id)
    cur.execute(
        f"UPDATE clients SET {', '.join(updates)} WHERE id = %s "
        f"RETURNING id, name, case_file, telegram_id, instagram_handle, whatsapp_number, email, phone, last_contact_channel",
        params,
    )
    r = cur.fetchone()
    if not r:
        print(f"client #{args.client_id} not found")
        return 1
    conn.commit()

    print(f"✓ updated client #{r['id']} ({r['name']}, {r['case_file']})")
    for k in ("telegram_id", "instagram_handle", "whatsapp_number", "email", "phone", "last_contact_channel"):
        if r[k]:
            print(f"    {k:>20}: {r[k]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
