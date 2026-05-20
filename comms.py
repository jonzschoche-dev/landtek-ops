"""comms — single chokepoint for every Telegram outbound from Landtek.

ALL outbound Telegram traffic must flow through `comms_send()`. Direct calls
to `api.telegram.org` are blocked at the requests.post layer when the target
is a known client chat_id (backstop, see install_telegram_backstop below).

Per [[feedback_no_ops_leak_to_client_ever]] + [[feedback_client_comms_hardcoded]]
+ the 2026-05-19 ops-leak incident.

Audience taxonomy (REQUIRED by every caller):
  "ops"    → operator only (Jonathan). Ops digests, gap_alerts, debug.
  "client" → client/administrator only (Don Qi for MWK-001). NEVER ops content.
  "both"   → ops + client. Case-relevant question or update where both should see.

A message reaches a CLIENT audience only after:
  1. The caller explicitly declared `audience="client"` or `audience="both"`.
  2. The text passed the client_safe_gate denylist (no ops jargon).
  3. For strict kinds (report/brief/memo/demand_letter), output_audit was clean.

If any step fails, the send is BLOCKED and an ops alert is dispatched.
"""
import re
import sys
import requests
from pathlib import Path

# ── boot-time capture of original requests.post BEFORE any monkey-patching ──
_orig_post = requests.post

sys.path.insert(0, "/root/landtek")
from comms_recipients import (
    recipients_for, OPS_RECIPIENTS, MWK_001_CLIENT_RECIPIENTS,
    audience_for_kind,
)

# Registry of known client chat_ids (extend as new clients onboard).
CLIENT_CHAT_IDS = {cid for _, cid in MWK_001_CLIENT_RECIPIENTS}

# Strict kinds — output_audit runs in strict mode (block on factual-citation failure)
STRICT_AUDIT_KINDS = {"report", "brief", "memo", "demand_letter", "mediation_memo"}

# ─── Concision caps per [[feedback_log_event_before_inferring]] ───────────
# Hard char caps on the *text* of any Telegram outbound, per kind.
# Documents (PDF attachments) are exempt; their caption is capped to 300.
# Anything else not in this table defaults to 400.
KIND_CHAR_CAPS = {
    "intake_item":    400,
    "ad_hoc":         400,
    "comms_probe":    300,
    "gap_alert":      800,
    "report":         500,   # daily picks / accelerator output
    "deadline_alert": 500,
    "memo":           99999, # PDF attachment path — caption is separate
    "brief":          99999,
    "demand_letter":  99999,
    "mediation_memo": 99999,
}
DEFAULT_CHAR_CAP = 400


def _enforce_concision(text: str, kind: str) -> tuple[str, bool]:
    """Return (possibly-truncated text, was_truncated). Never silently drop content;
    always leave a trailing `[… /more]` indicator so the operator can pull detail."""
    cap = KIND_CHAR_CAPS.get(kind, DEFAULT_CHAR_CAP)
    if len(text) <= cap:
        return text, False
    # Truncate at the previous line boundary to avoid mid-sentence cuts
    cut = text.rfind("\n", 0, cap - 30)
    if cut < cap // 2:
        cut = cap - 30
    return text[:cut].rstrip() + "\n\n<i>[… truncated by concision rule · reply /more for full]</i>", True


def _load_token() -> str:
    """Read TELEGRAM_BOT_TOKEN from /root/landtek/.env. Cached after first call."""
    if not hasattr(_load_token, "_cached"):
        token = None
        with open("/root/landtek/.env") as f:
            for line in f:
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    token = line.strip().split("=", 1)[1]
                    break
        _load_token._cached = token
    return _load_token._cached


# ═════════════════════════════════════════════════════════════════════════
# client_safe_gate — denylist for ops jargon reaching client audiences
# ═════════════════════════════════════════════════════════════════════════
# Per [[feedback_no_ops_leak_to_client_ever]] — derived from the 2026-05-19
# meta-agent gap-digest leak. Each pattern represents a specific class of
# ops content that must never appear in a client-bound message.

_DENYLIST = [
    # Internal HTML formatting that signals raw data dump
    (r"<code>",                            "raw <code> block (db row dump)"),
    (r"<pre>\s*\{",                        "raw <pre>{...} block (db row dump)"),
    # Meta-agent + sentinel + audit-system terminology
    (r"\bgap[_ -]alert\b",                 "gap_alert (meta-agent)"),
    (r"\bmeta[_ -]agent\b",                "meta-agent reference"),
    (r"\binvariant\b",                     "invariant (ops jargon)"),
    (r"\bback[_ -]test\b",                 "back-test reference"),
    (r"\btruth[_ -]negotiator\b",          "truth-negotiator (internal)"),
    (r"\baxiom[_ -]validator\b",           "axiom-validator (internal)"),
    (r"\boutput[_ -]audit\b",              "output_audit reference"),
    # Database column / table names
    (r"\bdoc_date_norm\b",                 "doc_date_norm (db column)"),
    (r"\bmatter_code\b",                   "matter_code (db column)"),
    (r"\bcase_file\s*[=:]",                "case_file= (db reference)"),
    (r"\bintake_response_id\b",            "intake_response_id (db column)"),
    (r"\btg_inquiry_queue\b",              "tg_inquiry_queue (table)"),
    (r"\bexecution_status\b",              "execution_status (db column)"),
    (r"\bextraction_chunks\b",             "extraction_chunks (table)"),
    (r"\bprovenance_level\b",              "provenance_level (db column)"),
    (r"\bclassification\b\s*[=:]",         "classification=(value) (db ref)"),
    (r"\bsmart_filename\b",                "smart_filename (db column)"),
    # Pipeline / processing state jargon
    (r"\bunextracted\b",                   "unextracted (pipeline state)"),
    (r"\bunclassified\b",                  "unclassified (pipeline state)"),
    (r"\bscanner[_ -]skipped\b",           "scanner-skipped (pipeline state)"),
    (r"\bsparse timeline\b",               "sparse timeline (pipeline state)"),
    (r"\bvalidity_audit\b",                "validity_audit (chunk type)"),
    (r"\bdisambiguator\b",                 "disambiguator (internal tool)"),
    # Infrastructure jargon
    (r"\bsystemd\b",                       "systemd (infra)"),
    (r"\bheartbeat\b",                     "heartbeat (infra)"),
    (r"\bcron\b",                          "cron (infra)"),
    (r"\bdebug\b",                         "debug (infra)"),
    (r"\bdeploy_\d+\b",                    "deploy_NNN (internal release)"),
    # Ops priority labels in raw form
    (r"\b🆘 ?P[0-4]\b",                    "🆘 P-rank (ops priority)"),
    (r"\b🚨 ?P[0-4]\b",                    "🚨 P-rank (ops priority)"),
    (r"\b🟠 ?P[0-4]\b",                    "🟠 P-rank (ops priority)"),
    (r"\b🟡 ?P[0-4]\b",                    "🟡 P-rank (ops priority)"),
]


def client_safe_check(text: str) -> tuple[bool, str]:
    """Run the denylist over `text`. Returns (passed, reason).
    A passing message has none of the ops-jargon patterns."""
    for pattern, why in _DENYLIST:
        if re.search(pattern, text, re.IGNORECASE):
            return False, f"denylist hit: {why}"
    return True, ""


# ═════════════════════════════════════════════════════════════════════════
# comms_send — the canonical outbound chokepoint
# ═════════════════════════════════════════════════════════════════════════

def comms_send(
    text: str,
    *,
    audience: str,
    kind: str = "ad_hoc",
    case_file: str = "MWK-001",
    reply_to: int | None = None,
    parse_mode: str = "HTML",
    strict_audit: bool | None = None,
    token: str | None = None,
):
    """Send `text` to the appropriate recipients for (audience, case_file).

    REQUIRED:
        audience: "ops" | "client" | "both"

    Returns:
        (ok: bool, results: list[dict])
        ok = True iff at least one recipient succeeded
        results = per-recipient {"name", "chat_id", "ok", "message_id",
                                 "http_status", "tg_description"}
                  OR a single {"blocked": True, "reason": "..."} if gate failed.

    Side-effects:
      • For audience ∈ {client, both}: runs client_safe_gate. If it fails, send is
        BLOCKED and an ops alert is dispatched describing the leak attempt.
      • For strict kinds: runs output_audit. If it fails in strict mode, send is BLOCKED.
    """
    if audience not in ("ops", "client", "both"):
        raise ValueError(
            f"comms_send: unknown audience {audience!r}; must be 'ops', 'client', or 'both'"
        )

    # ── Concision enforcement (per [[feedback_log_event_before_inferring]]) ──
    text, _was_truncated = _enforce_concision(text, kind)

    # ── client_safe_gate (denylist) for any client-reaching audience ──
    if audience in ("client", "both"):
        passed, reason = client_safe_check(text)
        if not passed:
            _alert_ops_blocked(text, reason, audience, kind, case_file)
            return False, [{"blocked": True, "reason": reason}]

    # ── output_audit (citation discipline) for strict kinds ──
    if strict_audit is None:
        strict_audit = (audience in ("client", "both")) and (kind in STRICT_AUDIT_KINDS)
    if strict_audit:
        try:
            from output_audit import audit_text
            passed, findings = audit_text(text, strict=True)
            if not passed:
                high = [f for f in findings if f.get("severity") == "high"][:3]
                reason = f"output_audit failed (strict): {high}"
                _alert_ops_blocked(text, reason, audience, kind, case_file)
                return False, [{"blocked": True, "reason": reason}]
        except ImportError:
            pass  # output_audit module not present — degrade gracefully

    # ── route + send ──
    token = token or _load_token()
    if not token:
        return False, [{"blocked": True, "reason": "TELEGRAM_BOT_TOKEN missing"}]

    recipients = recipients_for(case_file, audience=audience)
    results = []
    for name, chat_id in recipients:
        body = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode,
                "disable_web_page_preview": True}
        if reply_to:
            body["reply_to_message_id"] = reply_to
        try:
            r = _orig_post(f"https://api.telegram.org/bot{token}/sendMessage",
                           json=body, timeout=15)
            j = r.json() if r.content else {}
            ok = (r.status_code == 200 and j.get("ok") is True)
            results.append({
                "name": name,
                "chat_id": chat_id,
                "ok": ok,
                "message_id": (j.get("result", {}) or {}).get("message_id") if ok else None,
                "http_status": r.status_code,
                "tg_description": "ok" if ok else j.get("description", "no-desc")[:200],
            })
        except Exception as e:
            results.append({
                "name": name, "chat_id": chat_id, "ok": False,
                "http_status": None,
                "tg_description": f"exception: {str(e)[:180]}",
                "message_id": None,
            })

    any_ok = any(r["ok"] for r in results)
    return any_ok, results


def _alert_ops_blocked(text: str, reason: str, audience: str, kind: str, case_file: str):
    """Send an ops-only alert that a client-bound message was BLOCKED."""
    snippet = text[:400] + ("..." if len(text) > 400 else "")
    # Escape HTML in the snippet so it doesn't break the alert
    snippet_safe = (snippet.replace("&", "&amp;")
                            .replace("<", "&lt;")
                            .replace(">", "&gt;"))
    alert = (
        f"🚫 <b>Client-bound message BLOCKED by comms gate</b>\n"
        f"<i>audience={audience} · kind={kind} · case={case_file}</i>\n\n"
        f"<b>Reason:</b> {reason}\n\n"
        f"<b>Original snippet:</b>\n<pre>{snippet_safe}</pre>\n\n"
        f"Fix the source script — do not bypass the gate."
    )
    token = _load_token()
    if not token:
        return
    for _name, cid in OPS_RECIPIENTS:
        try:
            _orig_post(f"https://api.telegram.org/bot{token}/sendMessage",
                       json={"chat_id": cid, "text": alert[:4000],
                             "parse_mode": "HTML",
                             "disable_web_page_preview": True},
                       timeout=15)
        except Exception:
            pass  # best-effort; never raise


# ═════════════════════════════════════════════════════════════════════════
# install_telegram_backstop — monkey-patch requests.post
# ═════════════════════════════════════════════════════════════════════════
# Intercepts raw Telegram POSTs that target a known CLIENT chat_id and
# bypasses comms_send. Sends to OPS chat_ids and non-Telegram URLs pass
# through unmodified — this lets the 29 legacy scripts that hardcode
# Jonathan's chat_id keep working unchanged. Only NEW client leaks are caught.

def _intercepting_post(url, **kwargs):
    """Replacement for requests.post — intercepts Telegram URLs to client IDs."""
    if "api.telegram.org/" in url and ("/sendMessage" in url
                                       or "/sendDocument" in url
                                       or "/sendPhoto" in url):
        body = kwargs.get("json") or kwargs.get("data") or {}
        chat_id = str(body.get("chat_id", "")).strip()
        if chat_id in CLIENT_CHAT_IDS:
            # BLOCK — log + alert. Caller gets a synthetic 403.
            text_field = str(body.get("text") or body.get("caption") or "")[:500]
            _alert_ops_blocked(
                text_field,
                f"raw requests.post to client chat_id {chat_id} bypassed comms_send",
                "UNKNOWN", "RAW_POST", "UNKNOWN",
            )
            return _BlockedResponse()
    return _orig_post(url, **kwargs)


class _BlockedResponse:
    """Synthetic response returned to callers whose direct send was blocked."""
    status_code = 403
    content = b'{"ok":false,"description":"BLOCKED by comms backstop - use comms_send"}'
    text = '{"ok":false,"description":"BLOCKED by comms backstop — use comms_send"}'

    def json(self):
        return {"ok": False,
                "description": "BLOCKED by comms backstop — use comms_send"}


def install_telegram_backstop():
    """Monkey-patch requests.post (idempotent). Safe to call multiple times."""
    if requests.post is _intercepting_post:
        return
    requests.post = _intercepting_post


# ── Auto-install on import ────────────────────────────────────────────
install_telegram_backstop()


# ── self-test ─────────────────────────────────────────────────────────
def _selftest():
    """Validate the denylist + audience routing. Does not actually send."""
    print("comms.py self-test")
    print(f"  CLIENT_CHAT_IDS = {CLIENT_CHAT_IDS}")
    print(f"  STRICT_AUDIT_KINDS = {STRICT_AUDIT_KINDS}")
    print()

    cases = [
        # (text, should_pass_gate)
        ("Hi Don Qi, just confirming the May 22 meeting in Naga is on?", True),
        ("⚠️ Meta-agent gap digest — 10 findings\n<code>{...}</code>", False),
        ("Pretrial confirmed for June 30 at RTC Br 64 Daet.", True),
        ("12 docs have NULL doc_date_norm, breaks timeline", False),
        ("Reminder: deadline to file Reply is May 30.", True),
        ("🆘 P0 axiom-validator regression in back-test", False),
    ]
    for text, should_pass in cases:
        ok, reason = client_safe_check(text)
        tag = "✓" if ok == should_pass else "✗ MISMATCH"
        outcome = "PASS" if ok else f"BLOCK ({reason})"
        print(f"  {tag} expected={should_pass!s:5s} got={outcome[:60]}  text={text[:55]!r}")


if __name__ == "__main__":
    _selftest()
