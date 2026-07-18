#!/usr/bin/env python3
"""composer_route.py — the Read Composer as a governed spine route (A86 P1; docs/READ_CONSENSUS_DIRECTIVE.md §5).

One brain, one reader: leo_service.try_purpose_route calls try_composer_route for BOTH channels
(telegram + messenger), so a composer-owned ask yields the SAME frame on every channel — the
directive's done-test. Channel only changes transport.

P1 scope — the composer claims the ask-shapes with NO tuned dedicated owner today:
  * deadlines  — "what's due / deadlines / upcoming / kailan" (previously fell to the generic
                 inquiry_stack aggregate; three deadline homes composed to one dated list, A57/A68)
  * facts      — "facts about X / what do we know about X" with an extractable topic
                 (tier-ranked verified-first; inferred only labeled; proposals NEVER asserted)

Deliberately NOT claimed in P1 (tuned owners stay; tracked by the A86 inventory):
  * status_update      — deploy_972's dosed matter_brief path
  * title history/pack — title_fetch's table-backed chain evidence
  * OP/docket/ARTA membership — corpus_answer's dedicated answerers

Live audience today is internal (operator + JJ test surface); frames may carry matter codes.
Client-facing exposure stays behind the A79 clamp + A32 projection (switch held).

Deterministic, creditless, read-only; every answer is a logged composer_audit envelope.
"""
from __future__ import annotations

import re

try:
    from consensus import compose_answer          # VPS runtime (leo_tools on sys.path)
except ImportError:                               # repo-relative fallback
    from leo_tools.consensus import compose_answer

S14_CAP = 280

_DEADLINE_RE = re.compile(
    r"\b(deadlines?|due dates?|what('?s| is)? due|anything due|upcoming|kailan ang|"
    r"(next|when is( the)?|kailan) .*(hearing|filing|deadline)|schedule ahead|calendar)\b",
    re.I)

# topic must be explicitly extractable — a bare "what do we know" stays with the generic stack
_FACTS_RE = re.compile(
    r"(?:verified facts?|facts?)\s+(?:about|on|for|regarding)\s+(?P<topic>.{2,60}?)[?.!]*$"
    r"|what do we know about\s+(?P<topic2>.{2,60}?)[?.!]*$"
    r"|ano ang alam natin (?:sa|tungkol sa)\s+(?P<topic3>.{2,60}?)[?.!]*$",
    re.I)

_TOPIC_STRIP_RE = re.compile(r"^(the|our|my|ang|si|kay)\s+", re.I)


def _clip(text: str, cap: int = S14_CAP) -> str:
    if len(text) <= cap:
        return text
    return text[: cap - 1] + "…"


def _render(env, max_lines: int = 3) -> str:
    """Envelope → one S14-safe emission: headline + top lines, tier-honest, ≤280 by construction."""
    frame = env.get("frame") or {}
    parts = [frame.get("headline") or ""]
    for ln in (frame.get("lines") or [])[:max_lines]:
        if not ln.startswith("[gap]"):
            parts.append(ln)
    if env["status"] in ("partial", "miss") and env.get("gaps"):
        g = env["gaps"][0]
        n = f" x{g['n']}" if g.get("n") else ""
        parts.append(f"(gap: {g['kind']}{n})")
    return _clip(". ".join(p.strip().rstrip(".") for p in parts if p.strip()))


def _extract_topic(message: str):
    m = _FACTS_RE.search((message or "").strip())
    if not m:
        return None
    topic = next((g for g in (m.group("topic"), m.group("topic2"), m.group("topic3")) if g), "")
    topic = _TOPIC_STRIP_RE.sub("", topic.strip()).strip()
    return topic or None


def try_composer_route(cur, client_code, message, channel=None, channel_user_id=None):
    """Return {"text","via","purpose"} when the composer owns this ask-shape, else None.

    channel/channel_user_id are accepted for signature parity with the other routes and passed
    only into the audit caller tag — the frame NEVER varies by channel (the A86 done-test).
    """
    msg = (message or "").strip()
    if not client_code or not msg:
        return None

    caller = f"composer_route:{channel or 'unknown'}"

    if _DEADLINE_RE.search(msg):
        env = compose_answer("deadlines", client_code=client_code, caller=caller)
        if env["status"] == "hold":
            return None                      # scope refusals fall to the stack's own gates
        return {"text": _render(env, max_lines=3), "via": f"composer:deadlines:{env['status']}",
                "purpose": "composer_deadlines"}

    topic = _extract_topic(msg)
    if topic:
        # explicit matter hint in the ask wins; else CLIENT-WIDE (the A5 wall stays in the
        # composer's SQL — never a guessed single matter, the MWK-ESTATE mis-scope lesson)
        mm = re.search(r"\b(MWK|PARACALE|NIBDC|AUTO)-[A-Z0-9-]{2,}\b", msg, re.I)
        env = compose_answer("facts", client_code=client_code, caller=caller,
                             matter=mm.group(0).upper() if mm else None, topic=topic)
        if env["status"] == "hold":
            return None
        if env["status"] == "miss" and not env["claims"]:
            return None                      # nothing composed — let the generic stack try
        return {"text": _render(env, max_lines=2), "via": f"composer:facts:{env['status']}",
                "purpose": "composer_facts"}

    return None
