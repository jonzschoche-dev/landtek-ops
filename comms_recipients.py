"""comms_recipients — hardcoded source of truth for client Telegram channels.

Per Jonathan's directive 2026-05-19 (after the 2026-05-17 comms blackout that
left Don Qi the MWK-001 administrator with zero responses from Leo for 48h):

    "communications with clients need to be hard coded.
     we die when things like this happen."

This file is the contract. Every outbound sender imports the constant for
the case it's about to message. No DB lookup. No env-file fallback. No
webhook indirection. Adding a new recipient is a code change → reviewed,
committed, visible in git diff, cannot be silently lost.

When a recipient changes, edit THIS FILE and commit. Then the dispatcher,
the gmail watcher, the deadline sentinel, and any future sender all pick
up the change atomically on next start.
"""

# ═════════════════════════════════════════════════════════════════════════
# AUDIENCE TAXONOMY (critical — DO NOT collapse these)
# ═════════════════════════════════════════════════════════════════════════
# Per Jonathan 2026-05-19: "there should never be a message like this sent
# to our client". Internal ops digests (meta-agent gap_alerts, daily
# accelerator picks, debug dumps, data-quality probes) MUST NEVER reach a
# client. Client-facing comms are case-relevant only.
#
# - OPS  = ops-only (operator's eyes; raw, jargon, ugly is fine)
# - CLIENT = client-facing (polished, action-oriented, case-relevant only)
# - BOTH = goes to ops AND client (e.g., a case-related question we want
#          both Jonathan and the administrator to see)
# ═════════════════════════════════════════════════════════════════════════

# Ops operator(s) — receive ALL internal/ops messages.
OPS_RECIPIENTS = [
    ("Jonathan Zschoche", "6513067717"),  # Owner / Operator
]

# Client / administrator audience for MWK-001 — receive ONLY client-facing
# messages explicitly tagged as such. NEVER gets ops digests.
MWK_001_CLIENT_RECIPIENTS = [
    ("Don Qi Style",      "8575986732"),  # Administrator (MWK-001 estate)
]

# Both = ops + client (for case-relevant messages where both should see)
MWK_001_BOTH_RECIPIENTS = OPS_RECIPIENTS + MWK_001_CLIENT_RECIPIENTS

# Backwards-compatible alias — defaults to OPS-ONLY for safety.
# Any caller that imports MWK_001_RECIPIENTS without specifying audience
# is treated as ops-only. Client-facing senders must explicitly opt in
# via recipients_for(case, audience="client") or audience="both".
MWK_001_RECIPIENTS = OPS_RECIPIENTS
SYSTEM_RECIPIENTS = OPS_RECIPIENTS  # all system/ops alarms → ops only


def recipients_for(case_file: str | None, audience: str = "ops") -> list[tuple[str, str]]:
    """Return the hardcoded recipient list for a case_file + audience.

    audience:
      "ops"    → operator only (default, safe — Jonathan)
      "client" → administrator/client only (NO ops content)
      "both"   → ops + client (case-relevant messages for both)

    Unknown / NULL case → OPS_RECIPIENTS so nothing leaks to a client.
    Any unrecognized audience also defaults to "ops".
    """
    audience = (audience or "ops").lower()
    if not case_file:
        return OPS_RECIPIENTS  # safe default
    cf = case_file.strip().upper()
    if cf in ("MWK-001", "MWK001", "MWK_001"):
        if audience == "client":
            return MWK_001_CLIENT_RECIPIENTS
        if audience == "both":
            return MWK_001_BOTH_RECIPIENTS
        return OPS_RECIPIENTS
    # All other cases: ops only until each is explicitly configured.
    return OPS_RECIPIENTS


def all_recipients_uniq() -> list[tuple[str, str]]:
    """Every recipient across every case, deduplicated by chat_id.
    Used by the comms-health probe to ping each unique human exactly once.
    Includes BOTH ops and client recipients (we still want to confirm both
    channels are alive — we just route content carefully)."""
    seen, out = set(), []
    for case_list in (OPS_RECIPIENTS, MWK_001_CLIENT_RECIPIENTS):
        for name, cid in case_list:
            if cid not in seen:
                seen.add(cid)
                out.append((name, cid))
    return out


# ───────────────────────────────────────────────────────────────────────
# Inquiry-kind → audience map.
# Determines who receives each `tg_inquiry_queue.kind`. Default ops-only.
# Update this map when a new kind is introduced.
# ───────────────────────────────────────────────────────────────────────
KIND_AUDIENCE = {
    "gap_alert":   "ops",     # meta-agent internal data-quality digests
    "report":      "ops",     # daily strategic / accelerator picks (operator-facing)
    "intake_item": "both",    # case-intake question for client; ops sees it too
    "comms_probe": "both",    # health-check pings — both
    # absent kinds default to "ops" via recipients_for()
}


def audience_for_kind(kind: str) -> str:
    return KIND_AUDIENCE.get((kind or "").strip(), "ops")
