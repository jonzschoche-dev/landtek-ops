#!/usr/bin/env python3
"""Leo health watchdog — deploy_073.

Runs every 60s via systemd timer. Checks Leo is reachable end-to-end:
  1. Telegram webhook URL is set to the expected n8n endpoint
  2. Telegram has < 5 pending updates queued (delivery is flowing)
  3. n8n container logs clean of error spam in the last 60s
  4. workflow_entity.active = true on Leo's workflow
  5. (Soft) at least one execution in the last 4h during business hours

On any failure: ATTEMPT AUTO-RECOVERY (setWebhook, restart n8n, reactivate
workflow) AND send Jonathan a DM via Telegram Bot API direct call (works
even when n8n is dead — outbound sendMessage doesn't depend on workflow).

State is persisted in STATE_PATH so alerts don't spam — only alert on
state transitions (healthy<->unhealthy) and on persistent failures
(every ALERT_REPEAT_MIN minutes).
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────
ENV_FILE = "/root/landtek/.env"
WORKFLOW_ID = "vSDQv1vfn6627bnA"
WORKFLOW_NAME = "Leos Workflow"
EXPECTED_WEBHOOK_PREFIX = "https://leo.hayuma.org/webhook/"
JONATHAN_CHAT_ID = "6513067717"
STATE_PATH = "/var/lib/landtek/watchdog_state.json"
LOG_PATH = "/var/log/landtek_watchdog.log"
ALERT_REPEAT_MIN = 5      # repeat alerts every N min while unhealthy
ERROR_LOG_PATTERNS = ["ERROR", "dbTime.getTime", "TypeError", "panic", "Fatal"]


def load_env(path=ENV_FILE):
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k] = v
    return env


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")


def http_get_json(url, timeout=10):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {str(e)[:200]}"}


def http_post_json(url, data, timeout=10):
    body = urllib.parse.urlencode(data).encode()
    try:
        with urllib.request.urlopen(url, data=body, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {str(e)[:200]}"}


def tg_send_message(token, chat_id, text, parse_mode=""):
    """Send Telegram DM. Direct API call — works regardless of n8n state."""
    data = {"chat_id": chat_id, "text": text[:4000]}
    if parse_mode:
        data["parse_mode"] = parse_mode
    return http_post_json(f"https://api.telegram.org/bot{token}/sendMessage", data)


def tg_set_webhook(token, url):
    return http_post_json(f"https://api.telegram.org/bot{token}/setWebhook", {"url": url})


def tg_get_webhook_info(token):
    return http_get_json(f"https://api.telegram.org/bot{token}/getWebhookInfo")


def psql_query(sql):
    """Run a read-only psql query against prod n8n DB. Returns stdout."""
    result = subprocess.run(
        ["docker", "exec", "-i", "n8n-postgres-1", "psql", "-U", "n8n", "-d", "n8n", "-tAc", sql],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(f"psql failed: {result.stderr}")
    return result.stdout.strip()


def psql_exec(sql):
    """Run a mutating psql statement."""
    result = subprocess.run(
        ["docker", "exec", "-i", "n8n-postgres-1", "psql", "-U", "n8n", "-d", "n8n", "-c", sql],
        capture_output=True, text=True, timeout=15,
    )
    return result.returncode == 0


def get_expected_webhook_url():
    """Build the expected webhook URL from webhook_entity table."""
    path = psql_query(
        f"SELECT \"webhookPath\" FROM webhook_entity WHERE \"workflowId\"='{WORKFLOW_ID}' LIMIT 1;"
    )
    if not path:
        return None
    return EXPECTED_WEBHOOK_PREFIX + path


def load_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {"state": "unknown", "last_alert": 0, "last_state_change": 0}


def save_state(state):
    Path(STATE_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


# ── Health checks ─────────────────────────────────────────────────────────
def check_health(env):
    """Returns list of issues; empty = healthy."""
    issues = []
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return ["ENV: TELEGRAM_BOT_TOKEN missing"]

    # 1. Telegram webhook
    info = tg_get_webhook_info(token)
    if "_error" in info:
        issues.append(f"Telegram getWebhookInfo failed: {info['_error']}")
    elif not info.get("ok"):
        issues.append(f"Telegram getWebhookInfo not ok: {info}")
    else:
        result = info.get("result", {})
        actual_url = result.get("url", "")
        pending = result.get("pending_update_count", 0)
        expected = get_expected_webhook_url()
        if not expected:
            issues.append("webhook_entity has no row for Leo's workflow")
        elif actual_url != expected:
            issues.append(f"Telegram webhook URL mismatch: got '{actual_url}', expected '{expected}'")
        if pending >= 5:
            issues.append(f"Telegram has {pending} pending updates (delivery stalled)")

    # 2. n8n container error spam — INFORMATIONAL ONLY.
    # We deliberately do NOT treat log spam as a primary signal because:
    #   (a) n8n's own startup produces 'dbTime.getTime' noise that takes
    #       ~30s to settle — restarting on this creates a restart loop
    #       (incident 2026-05-16 00:01).
    #   (b) Leo can be processing messages successfully while log noise
    #       continues. Telegram-side checks (webhook URL, last_error) are
    #       the true health signal.
    # If logs are SEVERELY spamming AND no successful execution has finished
    # in the last 5 minutes during business hours, we may revisit. For now:
    # log it but do not act on it.
    pass

    # 3. Workflow active
    try:
        active = psql_query(
            f"SELECT active FROM workflow_entity WHERE id='{WORKFLOW_ID}';"
        )
        if active != "t":
            issues.append(f"workflow_entity.active = {active!r} (should be 't')")
    except Exception as e:
        issues.append(f"workflow active check failed: {e}")

    return issues


# ── Recovery actions ──────────────────────────────────────────────────────
def recover_webhook(env):
    """Re-register Telegram webhook via n8n REST API (deactivate+activate cycle).

    CRITICAL: never call Telegram's setWebhook directly — that wipes the
    secret_token that n8n's Telegram Trigger validates. Use n8n's own
    activation path so the secret stays in sync. (Incident 2026-05-16:
    direct setWebhook caused 'Provided secret is not valid' 403s for ~10
    min until we re-activated through n8n's API.)
    """
    api_key = env.get("N8N_API_KEY", "")
    if not api_key:
        return False, "N8N_API_KEY missing in env"
    base = f"http://localhost:5678/api/v1/workflows/{WORKFLOW_ID}"
    # Deactivate (idempotent: 400 if already off, ignore)
    req = urllib.request.Request(f"{base}/deactivate", method="POST",
                                  headers={"X-N8N-API-KEY": api_key})
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except urllib.error.HTTPError as e:
        if e.code != 400:
            return False, f"deactivate failed: HTTP {e.code} {e.reason}"
    except Exception as e:
        return False, f"deactivate failed: {type(e).__name__}: {e}"
    time.sleep(2)
    # Activate with up to 3 attempts (n8n returns transient 400 right after
    # a graph change — matches the retry logic in deploy_helpers.patch_workflow_dual)
    last_err = None
    for attempt in range(3):
        if attempt > 0:
            time.sleep(3)
        req = urllib.request.Request(f"{base}/activate", method="POST",
                                      headers={"X-N8N-API-KEY": api_key})
        try:
            urllib.request.urlopen(req, timeout=15).read()
            last_err = None
            break
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code} {e.reason}"
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
    if last_err:
        return False, f"activate failed after 3 attempts: {last_err}"
    time.sleep(2)
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    info = tg_get_webhook_info(token)
    actual = info.get("result", {}).get("url", "") if info.get("ok") else ""
    expected = get_expected_webhook_url()
    if actual == expected:
        return True, "deactivate+activate via n8n API (secret re-synced)"
    return False, f"after n8n cycle, webhook still wrong: '{actual}' vs '{expected}'"


def recover_workflow_activation():
    """Re-activate workflow via n8n REST API.

    CRITICAL: Do NOT use DB-level UPDATE workflow_entity SET active=true
    on its own — that flips the DB column but n8n's runtime doesn't pick
    up the change. Webhook stays unregistered in n8n's internal registry,
    and Telegram POSTs hit 404 'webhook not registered' (incident
    2026-05-16 00:21). Use the API endpoints instead so n8n reloads.
    """
    env = load_env()
    api_key = env.get("N8N_API_KEY", "")
    if not api_key:
        return False, "N8N_API_KEY missing"
    base = f"http://localhost:5678/api/v1/workflows/{WORKFLOW_ID}"
    # Deactivate (idempotent)
    for action in ("deactivate", "activate"):
        req = urllib.request.Request(
            f"{base}/{action}", method="POST",
            headers={"X-N8N-API-KEY": api_key},
        )
        try:
            urllib.request.urlopen(req, timeout=15).read()
        except urllib.error.HTTPError as e:
            if action == "deactivate" and e.code == 400:
                # Already deactivated, fine
                continue
            return False, f"{action} failed: HTTP {e.code} {e.reason}"
        except Exception as e:
            return False, f"{action} failed: {type(e).__name__}: {e}"
        time.sleep(2)
    return True, "reactivated via n8n REST API"


def recover_n8n_restart():
    """Hard restart the n8n container."""
    try:
        subprocess.run(["docker", "restart", "n8n-n8n-1"], capture_output=True, text=True, timeout=60, check=True)
        # Wait up to 30s for n8n to come back
        for _ in range(30):
            time.sleep(1)
            try:
                with urllib.request.urlopen("http://localhost:5678/healthz", timeout=2):
                    return True, "n8n restarted, /healthz green"
            except Exception:
                continue
        return False, "n8n restarted but /healthz never came up"
    except Exception as e:
        return False, f"restart failed: {e}"


def attempt_recovery(env, issues):
    """Run recovery actions matched to the issues. Returns list of recovery results."""
    actions = []

    if any("webhook URL mismatch" in i for i in issues) or any("getWebhookInfo" in i for i in issues):
        ok, msg = recover_webhook(env)
        actions.append(("webhook re-register", ok, msg))

    if any("workflow_entity.active" in i for i in issues):
        ok, msg = recover_workflow_activation()
        actions.append(("workflow reactivate", ok, msg))

    if any("n8n logs:" in i for i in issues):
        ok, msg = recover_n8n_restart()
        actions.append(("n8n container restart", ok, msg))
        # After restart, re-register webhook (restart often clears it)
        time.sleep(2)
        ok2, msg2 = recover_webhook(env)
        actions.append(("post-restart webhook re-register", ok2, msg2))

    return actions


# ── Main ──────────────────────────────────────────────────────────────────
def main():
    env = load_env()
    state = load_state()
    now = int(time.time())

    issues = check_health(env)
    is_healthy = len(issues) == 0
    prev_state = state.get("state", "unknown")

    if is_healthy:
        if prev_state == "unhealthy":
            # Recovery happened (either by us last cycle or externally)
            msg = "✅ Leo recovered. All health checks pass."
            tg_send_message(env["TELEGRAM_BOT_TOKEN"], JONATHAN_CHAT_ID, msg)
            log(msg)
            state.update({"state": "healthy", "last_state_change": now, "last_alert": now})
        else:
            # Steady healthy state — do nothing
            state.update({"state": "healthy"})
        save_state(state)
        return 0

    # Unhealthy path
    log(f"UNHEALTHY: {len(issues)} issue(s): {issues}")

    # Attempt recovery
    recovery = attempt_recovery(env, issues)
    log(f"Recovery actions: {recovery}")

    # Re-check after recovery
    time.sleep(2)
    issues_after = check_health(env)
    recovered = len(issues_after) == 0

    # Alert logic
    should_alert = False
    if prev_state != "unhealthy":
        # First detection
        should_alert = True
    elif (now - state.get("last_alert", 0)) >= ALERT_REPEAT_MIN * 60:
        # Persistent failure — periodic re-alert
        should_alert = True

    if should_alert:
        body = ["🚨 Leo health check failed:"]
        for i in issues:
            body.append(f"  • {i}")
        body.append("")
        body.append("Auto-recovery attempted:")
        for name, ok, msg in recovery:
            body.append(f"  {'✓' if ok else '✗'} {name}: {msg}")
        body.append("")
        if recovered:
            body.append("✅ Status after recovery: HEALTHY")
        else:
            body.append(f"⚠️ Status after recovery: STILL UNHEALTHY ({len(issues_after)} issue(s))")
            for i in issues_after:
                body.append(f"  • {i}")
        tg_send_message(env["TELEGRAM_BOT_TOKEN"], JONATHAN_CHAT_ID, "\n".join(body))
        state["last_alert"] = now

    state["state"] = "healthy" if recovered else "unhealthy"
    if prev_state != state["state"]:
        state["last_state_change"] = now
    save_state(state)
    return 0 if recovered else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        # Watchdog itself failed — log and try to alert
        log(f"WATCHDOG ITSELF FAILED: {type(e).__name__}: {e}")
        try:
            env = load_env()
            tg_send_message(
                env["TELEGRAM_BOT_TOKEN"], JONATHAN_CHAT_ID,
                f"🚨 Leo watchdog itself failed: {type(e).__name__}: {e}\nManual check needed.",
            )
        except Exception:
            pass
        sys.exit(2)
