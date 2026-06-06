#!/usr/bin/env python3
"""micro_probe_runner.py — Mode 3 of the lean simulator (deploy_337).

Reads probes/lean_probe_library.yaml, fires each probe whose `slice` contains
the requested slice name (default 'daily'), grades replies with hardcoded
substring rules (no LLM grading), records cost via simulator_budget.

Default: runs the 10 'daily' probes once per day at 03:00 UTC (~11am Manila).
Budget cap enforced via simulator_budget.can_afford().

Estimated cost: 10 probes × ~$0.01 = ~$0.10/day on Sonnet.

Usage:
    python3 scripts/micro_probe_runner.py            # daily slice
    python3 scripts/micro_probe_runner.py post_deploy  # post-deploy slice

All gates from the previous simulator are inherited (chat_id rewrite to '0',
Rules S1-S13 enforcement). This script does NOT touch the workflow itself —
just POSTs to the webhook and reads back leo_interactions.
"""
from __future__ import annotations
import json, os, random, sys, time, urllib.request, yaml
from datetime import datetime, timezone

import psycopg2, psycopg2.extras

sys.path.insert(0, "/root/landtek/scripts")
from simulator_budget import ensure_schema, can_afford, record_call, daily_total

# Lazy-load report_publisher (only needed if we push)
def _push(headline, body=None, slug=None):
    try:
        from report_publisher import push_strict
        push_strict(headline=headline, body_md=body, source="watchdog", slug=slug)
    except Exception as e:
        print(f"[push] failed: {e}")

DSN              = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
PROBE_LIB_PATH   = "/root/landtek/probes/lean_probe_library.yaml"
WORKFLOW_ID      = "vSDQv1vfn6627bnA"
WEBHOOK_PATH_ID  = "2fe01d2f-680c-47bd-86c6-7bb24893afb9"
WEBHOOK_NODE_ID  = "fc7b5df9-2d73-48d4-92e8-c5fc21dee837"
WEBHOOK_URL      = f"https://leo.hayuma.org/webhook/{WEBHOOK_PATH_ID}/webhook"
WEBHOOK_SECRET   = f"{WORKFLOW_ID}_{WEBHOOK_NODE_ID}"
POLL_TIMEOUT_S   = 60
POLL_INTERVAL_S  = 2
# Conservative token estimate per probe (Leo's input + output)
EST_INPUT_TOKENS  = 25_000   # systemMessage + context per real-user exec
EST_OUTPUT_TOKENS = 500


def load_library() -> list[dict]:
    with open(PROBE_LIB_PATH) as f:
        data = yaml.safe_load(f)
    return data.get("probes") or []


def grade(reply: str, probe: dict) -> tuple[bool, str]:
    if not reply:
        return (False, "no reply text captured")
    rt = reply.lower()
    for s in (probe.get("expected_all") or []):
        if s.lower() not in rt:
            return (False, f"missing required: {s!r}")
    expected_any = probe.get("expected_any") or []
    if expected_any:
        if not any(s.lower() in rt for s in expected_any):
            return (False, f"none of {expected_any[:3]} present")
    for s in (probe.get("forbidden") or []):
        if s.lower() in rt:
            return (False, f"contained forbidden: {s!r}")
    return (True, "pass")


def post_synthetic(sender_id: str, text: str) -> dict | None:
    chat_id = int(sender_id)
    msg_id = random.randint(1, 1_000_000_000)
    upd_id = random.randint(1, 9_999_999_999)
    update = {
        "update_id": upd_id,
        "message": {
            "message_id": msg_id,
            "from": {"id": chat_id, "is_bot": False,
                     "first_name": f"Sim{sender_id[-3:]}", "language_code": "en"},
            "chat": {"id": chat_id, "first_name": f"Sim{sender_id[-3:]}", "type": "private"},
            "date": int(time.time()),
            "text": text,
        },
    }
    body = json.dumps(update).encode()
    req = urllib.request.Request(
        WEBHOOK_URL, data=body,
        headers={"Content-Type": "application/json",
                 "X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except urllib.error.HTTPError as e:
        if e.code not in (200, 204):
            print(f"  webhook POST failed: HTTP {e.code}")
            return None
    return update


def wait_reply(cur, sender_id: str, since_ts) -> str | None:
    deadline = time.time() + POLL_TIMEOUT_S
    while time.time() < deadline:
        cur.execute("""
            SELECT reply_text FROM leo_interactions
             WHERE sender_id = %s AND timestamp >= %s
             ORDER BY id DESC LIMIT 1
        """, (sender_id, since_ts))
        r = cur.fetchone()
        if r and r["reply_text"]:
            return r["reply_text"]
        time.sleep(POLL_INTERVAL_S)
    return None


def main():
    slice_name = sys.argv[1] if len(sys.argv) > 1 else "daily"
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_schema(cur)

    probes = [p for p in load_library() if slice_name in (p.get("slice") or [])]
    if not probes:
        print(f"[micro_probe] no probes match slice {slice_name!r}")
        return

    print(f"[micro_probe] firing {len(probes)} probes in slice {slice_name!r}")
    results = []
    skipped_budget = 0
    for p in probes:
        ok_budget, projected, cap = can_afford(cur, EST_INPUT_TOKENS, EST_OUTPUT_TOKENS, "claude-sonnet-4-5")
        if not ok_budget:
            print(f"  budget cap hit (${projected:.4f} >= ${cap:.2f}); skipping {p['name']}")
            skipped_budget += 1
            continue

        ts_before = datetime.now(timezone.utc)
        sent = post_synthetic(p["sender_id"], p["prompt"])
        if not sent:
            results.append({"probe": p["name"], "passed": False, "reason": "webhook fail", "harm": p.get("harm_if_broken")})
            continue
        reply = wait_reply(cur, p["sender_id"], ts_before)
        passed, reason = grade(reply or "", p)
        results.append({"probe": p["name"], "passed": passed, "reason": reason,
                        "reply_preview": (reply or "")[:240],
                        "harm": p.get("harm_if_broken")})
        # Record budget regardless of pass/fail (the LLM was called)
        record_call(cur, "claude-sonnet-4-5", EST_INPUT_TOKENS, EST_OUTPUT_TOKENS,
                    source=f"micro_probe.{slice_name}", detail=p["name"])
        print(f"  {('✓' if passed else '✗'):2s} {p['name']:50s}  {reason[:60]}")

    fails = [r for r in results if not r["passed"]]
    today = daily_total(cur)

    # Strict-rails report
    if fails:
        headline = f"🚨 {len(fails)}/{len(results)} probes FAILED (lean sim)"
        body = ["## Lean Simulator — failed probes", "",
                f"Slice: `{slice_name}`  ·  Today's sim spend: ${today:.4f} / $1.00",
                f"Skipped (budget cap): {skipped_budget}",
                ""]
        for r in fails:
            body.append(f"### {r['probe']}")
            body.append(f"- **Harm if broken**: {r.get('harm','?')}")
            body.append(f"- **Failure reason**: `{r['reason']}`")
            body.append(f"- **Leo's reply**: {(r.get('reply_preview') or '(empty)')[:200]}")
            body.append("")
        _push(headline, "\n".join(body), slug=f"sim-fail-{slice_name}-{datetime.now(timezone.utc):%Y%m%d-%H%M}")
    else:
        # All green = silent (no Telegram). Only log.
        print(f"[micro_probe] ALL {len(results)} GREEN. Today's spend: ${today:.4f}")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
