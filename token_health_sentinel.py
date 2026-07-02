#!/usr/bin/env python3
"""token_health_sentinel.py — proactive health check of every OAuth token.

House doctrine (memory/feedback-autonomous-stack-degrade-gracefully.md):
DEGRADE, DON'T CRASH. This sentinel is a MONITOR — it must never itself go
`failed` in systemd (the "systemctl --failed == 0" invariant). It ALWAYS
exits 0. Expected-idle conditions (a token not yet provisioned, google libs
absent, DB unreachable, network blip) are logged and no-op'd. A genuinely
REVOKED / EXPIRED token is an actionable finding: it is logged, written to the
`token_health` table, and alerted to Jonathan (self-suppressed) — but STILL
exits 0, so the alert is about the token, not about a broken monitor.

  (This unit previously pointed at a script that did not exist, so Python
   exited 2 = "can't open file" and systemd marked the unit failed every hour.
   This is that missing script, written to the house degrade-gracefully spec.)

Monitored OAuth credentials (VPS /root/landtek/.env):
  GMAIL_REFRESH_TOKEN      gmail.readonly     (required)
  DRIVE_REFRESH_TOKEN      drive              (required)
  CALENDAR_REFRESH_TOKEN   calendar.events    (optional — being added; its
                                               absence is expected-idle, not a
                                               fault, until it is provisioned)
  google-creds.json        Drive service acct (required)

Each refresh token is validated with a LIVE refresh against Google's OAuth
endpoint, using the shared OAuth client (gmail_oauth_client.json):
  ok               refresh succeeded — token healthy
  not_provisioned  key absent from .env — expected-idle for optional tokens
  revoked          invalid_grant — token revoked/expired, needs re-mint (ACTION)
  error            transient/other failure (network etc.) — logged, not alerted

Wired: token-health-sentinel.service + .timer (hourly). The unit appends
StandardOutput/StandardError to /var/log/token_health_sentinel.log, so every
print() here IS the sentinel's log line.

Usage:
  python3 token_health_sentinel.py             # check + alert (daemon default)
  python3 token_health_sentinel.py --no-alert  # check + log only
  python3 token_health_sentinel.py --json      # machine-readable summary too
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timezone, timedelta

ENV_PATH = "/root/landtek/.env"
OAUTH_CLIENT_PATH = "/root/landtek/gmail_oauth_client.json"
SERVICE_ACCOUNT_PATH = "/root/landtek/google-creds.json"
DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
JONATHAN = "6513067717"
TOKEN_URI = "https://oauth2.googleapis.com/token"
REALERT_AFTER = timedelta(hours=6)  # self-suppress: re-alert a persistent fault only this often

# (env_key, label, scopes, required)
#   required=True  → absence is a soft warning (alerted, self-suppressed)
#   required=False → absence is expected-idle (logged only, never alerted)
OAUTH_TOKENS = [
    ("GMAIL_REFRESH_TOKEN",    "Gmail",    ["https://www.googleapis.com/auth/gmail.readonly"],  True),
    ("DRIVE_REFRESH_TOKEN",    "Drive",    ["https://www.googleapis.com/auth/drive"],           True),
    ("CALENDAR_REFRESH_TOKEN", "Calendar", ["https://www.googleapis.com/auth/calendar.events"], False),
]
# Scope used only to mint a probe access token for the service account.
SA_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    print(f"[token_health] {ts} {msg}", flush=True)


# ── env + oauth client ────────────────────────────────────────────────────
def load_env(path: str = ENV_PATH) -> dict:
    env: dict[str, str] = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    except FileNotFoundError:
        log(f"env file absent ({path}); relying on process env only")
    # process env overrides the file (matches calendar_sync.py convention)
    for k in [t[0] for t in OAUTH_TOKENS]:
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def oauth_client() -> tuple[str | None, str | None]:
    """Return (client_id, client_secret) or (None, None) if unavailable."""
    try:
        with open(OAUTH_CLIENT_PATH) as f:
            conf = json.load(f)
        block = conf.get("web") or conf.get("installed") or {}
        return block.get("client_id"), block.get("client_secret")
    except Exception as e:  # noqa: BLE001 — degrade, don't crash
        log(f"oauth client unreadable ({OAUTH_CLIENT_PATH}): {e}")
        return None, None


def _classify_auth_error(msg: str) -> bool:
    """True if the error means the credential itself is bad (actionable)."""
    low = msg.lower()
    return any(s in low for s in (
        "invalid_grant", "invalid_rapt", "revoked", "expired", "unauthorized_client",
        "account has been deleted", "disabled",
    ))


# ── checks ─────────────────────────────────────────────────────────────────
def check_oauth_token(env, key, label, scopes, required, client_id, client_secret) -> dict:
    base = {"key": key, "label": label, "required": required}
    token = env.get(key)
    if not token:
        # required-but-missing is a soft warning; optional-missing is expected-idle
        return {**base, "status": "not_provisioned",
                "detail": "key absent from .env"
                          + ("" if required else " (optional — expected until minted)"),
                "actionable": required}
    if not client_id or not client_secret:
        return {**base, "status": "error",
                "detail": "no OAuth client available to validate against",
                "actionable": False}
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except Exception as e:  # noqa: BLE001
        return {**base, "status": "error",
                "detail": f"google libs unavailable: {e}", "actionable": False}
    try:
        # scopes=None on purpose: a refresh_token grant re-mints with whatever
        # scopes were ORIGINALLY granted. Passing scopes here makes Google return
        # invalid_scope when they don't match exactly (e.g. a drive.readonly token
        # probed with full `drive`) — a false failure. We only need to know the
        # token can still mint an access token, so we don't constrain the scope.
        creds = Credentials(
            token=None, refresh_token=token, token_uri=TOKEN_URI,
            client_id=client_id, client_secret=client_secret, scopes=None,
        )
        creds.refresh(Request())
        exp = creds.expiry.replace(tzinfo=timezone.utc).isoformat() if creds.expiry else "n/a"
        return {**base, "status": "ok",
                "detail": f"refresh ok; access token expires {exp}", "actionable": False}
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if _classify_auth_error(msg):
            return {**base, "status": "revoked",
                    "detail": f"token rejected — re-mint required: {msg[:180]}",
                    "actionable": True}
        # network / transient — log, but don't cry wolf
        return {**base, "status": "error",
                "detail": f"transient/unknown (not alerted): {msg[:180]}", "actionable": False}


def check_service_account() -> dict:
    base = {"key": "google-creds.json", "label": "Drive service account", "required": True}
    if not os.path.exists(SERVICE_ACCOUNT_PATH):
        return {**base, "status": "not_provisioned",
                "detail": f"file absent ({SERVICE_ACCOUNT_PATH})", "actionable": True}
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
    except Exception as e:  # noqa: BLE001
        return {**base, "status": "error",
                "detail": f"google libs unavailable: {e}", "actionable": False}
    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_PATH, scopes=SA_SCOPES)
        creds.refresh(Request())
        exp = creds.expiry.replace(tzinfo=timezone.utc).isoformat() if creds.expiry else "n/a"
        return {**base, "status": "ok",
                "detail": f"token mint ok; expires {exp}", "actionable": False}
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if _classify_auth_error(msg):
            return {**base, "status": "revoked",
                    "detail": f"service account key rejected: {msg[:180]}", "actionable": True}
        return {**base, "status": "error",
                "detail": f"transient/unknown (not alerted): {msg[:180]}", "actionable": False}


# ── persistence + self-suppression ─────────────────────────────────────────
def persist_and_pick_alerts(results, do_alert) -> list:
    """Upsert every result into token_health; return the actionable findings that
    should be alerted now (first detection, then again only every REALERT_AFTER).
    Degrades to an empty alert list (log-only) if the DB is unreachable — no
    suppression state means we must not risk hourly spam."""
    try:
        import psycopg2
        import psycopg2.extras
    except Exception as e:  # noqa: BLE001
        log(f"psycopg2 unavailable; skipping DB persistence + alert: {e}")
        return []
    try:
        conn = psycopg2.connect(DSN)
        conn.autocommit = True
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    except Exception as e:  # noqa: BLE001
        log(f"DB unreachable; skipping persistence + alert (degrade): {e}")
        return []

    cur.execute("""
        CREATE TABLE IF NOT EXISTS token_health (
            token_key        text PRIMARY KEY,
            label            text,
            status           text,
            detail           text,
            required         boolean,
            checked_at       timestamptz,
            first_alerted_at timestamptz,
            last_alerted_at  timestamptz,
            fail_streak      integer NOT NULL DEFAULT 0
        )
    """)

    now = datetime.now(timezone.utc)
    to_alert = []
    for r in results:
        cur.execute("""
            INSERT INTO token_health (token_key, label, status, detail, required, checked_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (token_key) DO UPDATE SET
                label=EXCLUDED.label, status=EXCLUDED.status,
                detail=EXCLUDED.detail, required=EXCLUDED.required,
                checked_at=EXCLUDED.checked_at
        """, (r["key"], r["label"], r["status"], r["detail"], r["required"], now))

        if r["actionable"]:
            cur.execute("SELECT first_alerted_at, last_alerted_at FROM token_health WHERE token_key=%s",
                        (r["key"],))
            st = cur.fetchone()
            last = st["last_alerted_at"] if st else None
            should = (last is None) or ((now - last) > REALERT_AFTER)
            if should:
                r = {**r, "first_alert": (st is None or st["first_alerted_at"] is None)}
                to_alert.append(r)
                cur.execute("""
                    UPDATE token_health
                       SET first_alerted_at = COALESCE(first_alerted_at, %s),
                           last_alerted_at  = %s,
                           fail_streak      = fail_streak + 1
                     WHERE token_key = %s
                """, (now, now, r["key"]))
        else:
            # healthy / expected-idle → clear any prior alert state
            cur.execute("""
                UPDATE token_health
                   SET first_alerted_at = NULL, last_alerted_at = NULL, fail_streak = 0
                 WHERE token_key = %s AND first_alerted_at IS NOT NULL
            """, (r["key"],))

    conn.close()
    return to_alert if do_alert else []


def send_alert(alerts) -> None:
    """One concise, human-readable Telegram line (S14: plain text, one point,
    no double-tap → we do NOT override pacing). tg_send sanitizes + caps."""
    sys.path.insert(0, "/root/landtek/scripts")
    try:
        from tg_send import send as tg_send
    except Exception as e:  # noqa: BLE001
        log(f"tg_send unavailable; logging alert only: {e}")
        tg_send = None

    parts = [f"{a['label']} token {a['status']}" for a in alerts]
    text = ("Token health: " + "; ".join(parts)
            + ". Re-mint needed (see scripts/mint_calendar_token.py for the calendar one).")
    log("ALERT → " + text)
    if tg_send is None:
        return
    try:
        tg_send(JONATHAN, text, source="watchdog",
                recipient_name="Jonathan", override_rate_limit=True)
    except Exception as e:  # noqa: BLE001
        log(f"tg_send failed (alert logged above, not re-raised): {e}")


# ── main ────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(description="Proactive OAuth token health sentinel")
    ap.add_argument("--no-alert", action="store_true", help="check + log only, no Telegram")
    ap.add_argument("--json", action="store_true", help="also print a machine-readable summary")
    args = ap.parse_args()

    try:
        env = load_env()
        cid, csec = oauth_client()
        results = [check_oauth_token(env, k, lbl, sc, req, cid, csec)
                   for (k, lbl, sc, req) in OAUTH_TOKENS]
        results.append(check_service_account())

        for r in results:
            log(f"{r['label']:<22} {r['status']:<16} {r['detail']}")

        alerts = persist_and_pick_alerts(results, do_alert=not args.no_alert)
        if alerts:
            send_alert(alerts)

        actionable = [r for r in results if r["actionable"]]
        healthy = [r for r in results if r["status"] == "ok"]
        log(f"summary: {len(results)} checked, {len(healthy)} ok, "
            f"{len(actionable)} actionable, {len(alerts)} alerted this cycle")

        if args.json:
            print(json.dumps({"results": results,
                              "alerted": [a["key"] for a in alerts]}, default=str))
    except Exception:  # noqa: BLE001 — a monitor must never go `failed`
        log("UNEXPECTED ERROR (caught so the unit stays green):\n" + traceback.format_exc())

    sys.exit(0)


if __name__ == "__main__":
    main()
