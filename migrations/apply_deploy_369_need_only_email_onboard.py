#!/usr/bin/env python3
"""deploy_369 — Need-only email onboarding policy.

gmail_watcher default: legal-signal Gmail query + should_onboard_email gate.
Unneeded mail is skipped (not stored). --full-inbox retains legacy mirror mode.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from landtek_core import db


def main():
    with db() as cur:
        cur.execute("""
            INSERT INTO deploy_log (deploy_id, summary) VALUES (
              'deploy_369',
              'Need-only email onboarding: gmail_watcher fetches legal-signal query '
              'only; should_onboard_email gates active KB inserts; unneeded mail '
              'skipped entirely (no gmail_messages, no archive). SENT stream + '
              'active-thread continuation preserved. Use --full-inbox for legacy.'
            )
            ON CONFLICT (deploy_id) DO UPDATE SET summary = EXCLUDED.summary
        """)
        cur.execute("SELECT COUNT(*) AS n FROM gmail_messages")
        active = cur.fetchone()["n"]
    print(f"✓ deploy_369: need-only email policy logged; active_gmail={active}")


if __name__ == "__main__":
    main()