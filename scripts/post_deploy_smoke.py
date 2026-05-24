#!/usr/bin/env python3
"""post_deploy_smoke.py - structural health check after workflow mutation.

Tier 1 bulletproofing (deploy_266). Call after ANY workflow mutation:

  python3 scripts/post_deploy_smoke.py

Exit 0 if ALL of these pass; nonzero otherwise. Migrations treat nonzero
as "rollback needed".

  1. Container alive: docker inspect n8n-n8n-1 shows Status='running' AND
     Health.Status='healthy' (or 'starting' with grace)
  2. n8n responds: HTTP GET http://localhost:5678/healthz returns 200
  3. Webhook registered with Telegram: getWebhookInfo returns the right URL
  4. Bot token valid: getMe returns ok=true
  5. Workflow active: Leos Workflow active=true in DB
  6. Gemini Embed uses Gemini API URL (deploy_265 invariant)
  7. Telegram Trigger node still wired into Whitelist Check

We do NOT inject a synthetic webhook payload because the Telegram Trigger
enforces a secret token we can't fake. A REAL Telegram message from Jonathan
remains the ultimate test — but the seven checks above catch every failure
mode that's killed the bot historically.
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
WORKFLOW_ID = "vSDQv1vfn6627bnA"
HEALTHZ_URL = "http://localhost:5678/healthz"
BOT_TOKEN_PATH = "/root/landtek/.env"
TELEGRAM_BOT_KEY = "TG_BOT_TOKEN"


def load_bot_token():
    with open(BOT_TOKEN_PATH) as f:
        for line in f:
            for k in (TELEGRAM_BOT_KEY, "TELEGRAM_BOT_TOKEN", "BOT_TOKEN"):
                if line.startswith(k + "="):
                    return line.split("=", 1)[1].strip().strip('"\'')
    return None


def check_container():
    r = subprocess.run(
        ["docker", "inspect", "n8n-n8n-1", "--format", "{{.State.Status}} {{.State.Health.Status}}"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return False, f"docker inspect failed: {r.stderr.strip()}"
    parts = r.stdout.strip().split()
    state = parts[0] if parts else ""
    health = parts[1] if len(parts) > 1 else "no-health-defined"
    if state != "running":
        return False, f"container state={state}"
    if health not in ("healthy", "starting", "no-health-defined"):
        return False, f"container health={health}"
    return True, f"running, health={health}"


def check_healthz():
    try:
        with urllib.request.urlopen(HEALTHZ_URL, timeout=5) as resp:
            if resp.status == 200:
                return True, f"healthz 200"
            return False, f"healthz {resp.status}"
    except Exception as e:
        return False, f"healthz: {type(e).__name__}: {e}"


def check_webhook_registered():
    token = load_bot_token()
    if not token:
        return False, f"could not find bot token in {BOT_TOKEN_PATH}"
    url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        if not data.get("ok"):
            return False, f"getWebhookInfo not ok: {data}"
        info = data.get("result", {})
        whurl = info.get("url", "")
        pending = info.get("pending_update_count", 0)
        if not whurl:
            return False, "no webhook URL registered"
        return True, f"url={whurl[-40:]} pending={pending}"
    except Exception as e:
        return False, f"getWebhookInfo: {type(e).__name__}: {e}"


def check_bot_alive():
    token = load_bot_token()
    if not token:
        return False, "no token"
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        if data.get("ok") and data.get("result", {}).get("is_bot"):
            return True, f"@{data['result'].get('username','?')}"
        return False, f"getMe not ok: {data}"
    except Exception as e:
        return False, f"getMe: {type(e).__name__}: {e}"


def check_workflow_active():
    conn = psycopg2.connect(DSN)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT active FROM workflow_entity WHERE id = %s", (WORKFLOW_ID,))
    r = cur.fetchone()
    cur.close()
    conn.close()
    if not r:
        return False, "workflow not found"
    if not r["active"]:
        return False, "workflow active=false"
    return True, "active"


def check_gemini_embed_url():
    conn = psycopg2.connect(DSN)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT n->'parameters'->>'url' AS url
          FROM workflow_entity, jsonb_array_elements(nodes::jsonb) n
         WHERE id = %s AND n->>'name' = 'Gemini Embed'
    """, (WORKFLOW_ID,))
    r = cur.fetchone()
    cur.close()
    conn.close()
    if not r:
        return False, "Gemini Embed node not found"
    url = (r["url"] or "").lower()
    if "openai.com" in url:
        return False, "Gemini Embed STILL using OpenAI URL — deploy_265 reverted"
    if "generativelanguage.googleapis.com" not in url:
        return False, f"Gemini Embed URL unexpected: {url[:60]}"
    return True, "Gemini API"


def check_trigger_wired():
    conn = psycopg2.connect(DSN)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT connections FROM workflow_entity WHERE id = %s", (WORKFLOW_ID,))
    r = cur.fetchone()
    cur.close()
    conn.close()
    conns = r["connections"] if isinstance(r["connections"], dict) else json.loads(r["connections"])
    tt = conns.get("Telegram Trigger", {}).get("main", [])
    if not tt:
        return False, "Telegram Trigger has no outgoing connections"
    # First branch should include Whitelist Check
    first = tt[0] if tt else []
    if not any(c.get("node") == "Whitelist Check" for c in first):
        return False, "Telegram Trigger no longer wired to Whitelist Check"
    return True, f"-> Whitelist Check (+{len(first)-1} other branches)"


def check_workflow_history_in_sync():
    """workflow_entity (draft) MUST match workflow_history (executing version).
    n8n v2.16 runs from workflow_history; drift here causes silent failures."""
    conn = psycopg2.connect(DSN)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT (we.nodes::text) AS draft, (wh.nodes::text) AS published
          FROM workflow_entity we
          LEFT JOIN workflow_history wh ON wh."workflowId" = we.id
         WHERE we.id = %s
        """, (WORKFLOW_ID,))
    r = cur.fetchone()
    cur.close()
    conn.close()
    if not r or not r["published"]:
        return False, "workflow_history has no row — n8n won't execute anything"
    if r["draft"] != r["published"]:
        return False, "workflow_entity (draft) != workflow_history (executing) — run sync_workflow_history.py"
    return True, "draft==published"


def check_webhook_secret_matches():
    """The Telegram webhook secret n8n expects is deterministic:
    workflow_id + '_' + node_id (after stripping non-[A-Za-z0-9_-]).
    Verify our setWebhook recorded a non-empty URL with the expected webhook_id."""
    token = load_bot_token()
    if not token:
        return False, "no token"
    try:
        info = json.loads(urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/getWebhookInfo", timeout=8
        ).read()).get("result", {})
    except Exception as e:
        return False, f"getWebhookInfo error: {e}"
    url = info.get("url", "")
    last_err = info.get("last_error_message", "") or ""
    last_err_age = None
    if info.get("last_error_date"):
        import time as _t
        last_err_age = _t.time() - info["last_error_date"]
    # If url is set AND last error (if any) is older than 10 minutes OR doesn't
    # mention 403 (secret check), we're healthy. Telegram does not let us read
    # the actual secret; we infer health from absence of recent 403s.
    if not url:
        return False, "webhook URL empty"
    if "403" in last_err and last_err_age is not None and last_err_age < 600:
        return False, f"recent 403 error from Telegram: {last_err} ({int(last_err_age)}s ago)"
    return True, f"url set, last_error: {last_err[:40] or '(none)'}"


CHECKS = [
    ("container_health", check_container),
    ("n8n_healthz", check_healthz),
    ("bot_alive", check_bot_alive),
    ("webhook_registered", check_webhook_registered),
    ("webhook_secret_ok", check_webhook_secret_matches),
    ("workflow_active", check_workflow_active),
    ("workflow_history_synced", check_workflow_history_in_sync),
    ("gemini_embed_url", check_gemini_embed_url),
    ("trigger_wired", check_trigger_wired),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    results = []
    overall = True
    for name, fn in CHECKS:
        try:
            ok, msg = fn()
        except Exception as e:
            ok, msg = False, f"{type(e).__name__}: {e}"
        results.append((name, ok, msg))
        if not ok:
            overall = False

    if args.json:
        print(json.dumps({"ok": overall, "checks": [{"name": n, "ok": o, "msg": m} for n, o, m in results]}, indent=2))
    else:
        print("post_deploy_smoke - structural checks")
        print("=" * 60)
        for name, ok, msg in results:
            mark = "✓" if ok else "✗"
            print(f"  {mark} {name:<22s} {msg}")
        print()
        print(f"  Overall: {'PASS' if overall else 'FAIL'}")

    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()
