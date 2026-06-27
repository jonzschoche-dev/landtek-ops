#!/usr/bin/env python3
"""daily_digest.py — 7 AM Manila trigger for the consolidated daily digest.

deploy_614 — the two daily status digests were merged into one. This is now a THIN 7 AM sender that
renders + posts the same rich digest as build_digest.py (deadlines · corpus stats · client activity ·
uploads · open inquiries · action items · today's calendar · per-case status · system health). All the
section logic lives in build_digest.py — the single source of truth — which also still serves the
`/digest` slash command via /api/digest. build_digest's separate 9 AM systemd timer (landtek-digest.timer)
is retired; this 7 AM cron is the canonical daily push. Read-only against the DB.
"""
import os
import sys

# build_digest.py lives at the repo root, one level up from autonomous/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_digest


def main():
    msgs = build_digest.render_digest_messages()
    print(f"daily_digest: rendered {len(msgs)} message(s)")
    for m in msgs:
        ok = build_digest.tg_send(m)
        print(f"  sent {'✓' if ok else '✗'} ({len(m)} chars)", file=sys.stderr)


if __name__ == "__main__":
    main()
