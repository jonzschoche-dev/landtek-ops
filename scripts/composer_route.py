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

# deploy_972's failure shapes, now composer-owned (Grok review item 2). inquiry_stack remains
# the fallback when the composer misses; the dual path is FORBIDDEN once these soak green.
_TITLE_LIST_RE = re.compile(
    r"\b(list( of| all)?( the| our| my)? titles?|titles? (list|inventory)|how many titles|"
    r"listahan|all( the| of)? titles|(active|clouded|cancelled|contested|unverified) titles|"
    r"which titles|titles? do (we|i) (have|own|hold)|where('?s| is) the list)\b", re.I)
_SLICE_RE = re.compile(r"\b(active|clouded|cancelled|contested|unverified|unknown)\b", re.I)
_STATUS_RE = re.compile(
    r"\b(any updates?|status update|latest (news|status|update)|balita|pinakabagong|"
    r"what('?s| is) (new|happening|the status)|update (sa|naman))\b", re.I)
_MATTER_HINT_RE = re.compile(r"\b(MWK|PARACALE|NIBDC|AUTO)-[A-Z0-9-]{2,}\b"
                             r"|\b(guardianship|estate|arta|26-?360|op petition)\b", re.I)


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


_DOCKET_NUM_RE = re.compile(r"\b(\d{2})\s*-\s*(\d{3})\b|(?<!\d)(\d{4,5})(?!\d)")   # "CV6839" counts too
_ASK_WORDS = {"when", "what", "where", "which", "who", "whose", "next", "hearing", "hearings",
              "case", "cases", "deadline", "deadlines", "filing", "schedule", "upcoming", "kailan",
              "please", "tell", "show", "give", "court", "trial", "date", "dates", "matter"}


def _resolve_matters(cur, client_code, msg):
    """Matters the ask NAMES, always scoped to this client (A5): explicit code > docket number >
    party name in the matter title. [] = the ask names no matter (answer client-wide)."""
    base = ("SELECT matter_code FROM matters WHERE client_code = %s AND matter_code NOT LIKE 'AUTO-%%' "
            "AND COALESCE(status,'') NOT IN ('closed','archived') AND ")

    def _q(sql, params):
        try:
            cur.execute(sql, params)
            return [r["matter_code"] if isinstance(r, dict) else r[0] for r in cur.fetchall()]
        except Exception:
            return []

    codes = [m.group(0).upper() for m in
             re.finditer(r"\b(MWK|PARACALE|PAR|NIBDC|LANDTEK)-[A-Z0-9-]{2,}\b", msg, re.I)]
    if codes:
        return _q(base + "upper(matter_code) = ANY(%s)", (client_code, codes))
    nums = []
    for m in _DOCKET_NUM_RE.finditer(msg):
        n = (m.group(1) + m.group(2)) if m.group(1) else m.group(3)
        if n and not (len(n) == 4 and n[:2] in ("19", "20")):     # a year is not a docket
            nums.append(n)
    if nums:
        hits = _q(base + "regexp_replace(matter_code, '\\D', '', 'g') = ANY(%s)", (client_code, nums))
        if hits:
            return hits
    found = []
    for w in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", msg):
        if w[0].isupper() and w.lower() not in _ASK_WORDS:
            for h in _q(base + "title ILIKE %s", (client_code, f"%{w}%")):
                if h not in found:
                    found.append(h)
    if found:
        return found[:3]
    # a lower-case subject word ("status of the guardianship") names a matter only when exactly ONE of this
    # client's matter titles carries it; two or more is ambiguous and names nothing (J3, 4 Nov 2026)
    for w in re.findall(r"[a-z][a-z'-]{5,}", msg.lower()):
        if w in _ASK_WORDS or w in _SUBJECT_STOP:
            continue
        hits = _q(base + "title ~* %s", (client_code, rf"\m{re.escape(w)}\M"))
        if len(hits) == 1 and hits[0] not in found:
            found.append(hits[0])
    return found[:3]


_SUBJECT_STOP = {"status", "update", "updates", "matter", "matters", "latest", "what's", "happening", "please",
                 "anything", "something", "record", "records", "about", "there", "where", "balita", "kumusta",
                 "kamusta", "nasaan", "naman", "should", "would", "could", "today", "tomorrow", "against"}

# "What Balane matter?", "status of the guardianship", "status of CV6839": one NAMED matter, asked about in
# general. Answered from the matters row, never the inquiry stack (which had returned a title list, then
# nothing; J3, 4 Nov 2026).
_MATTER_ASK_RE = re.compile(r"\b(status|update|updates|balita|kumusta|kamusta|what|ano|how('?s| is)|"
                            r"where are we|nasaan)\b", re.I)


def _plain(code):
    return (code or "").replace("_", " ").strip()


def _matter_status_text(cur, client_code, mc):
    """One matter, plain language: what it is, where it stands, the next date on record (a past date is
    flagged, never presented as upcoming, A57), what comes next. Scoped by client in the query (A5)."""
    from datetime import date
    cur.execute("""SELECT title, status, current_stage, COALESCE(forum, court_or_agency) AS forum,
                          next_deadline, next_event
                     FROM matters WHERE matter_code = %s AND client_code = %s""", (mc, client_code))
    r = cur.fetchone()
    if not r:
        return None
    r = r if isinstance(r, dict) else dict(zip(("title", "status", "current_stage", "forum", "next_deadline",
                                                "next_event"), r))
    parts = [f"{r['title'] or mc}" + (f" ({r['forum']})" if r["forum"] else "")]
    st = ", ".join(x for x in (_plain(r["status"]), _plain(r["current_stage"])) if x)
    if st:
        parts.append(f"Status on record: {st}")
    if r["next_deadline"]:
        d = r["next_deadline"]
        parts.append(f"Next date on record: {d.strftime('%d %b %Y')}"
                     + (" (already past; needs updating)" if d < date.today() else ""))
    else:
        parts.append("No next date is on record")
    try:
        try:
            import client_ontology as _co
        except ImportError:
            from leo_tools import client_ontology as _co
        step = _co.client_next_step(r["current_stage"], r["next_event"], matter_code=mc)
        if step and step != _co._NEXTSTEP_GENERIC:
            parts.append(step)
    except Exception:
        pass
    return ". ".join(p.strip().rstrip(".") for p in parts if p) + "."


def try_composer_route(cur, client_code, message, channel=None, channel_user_id=None):
    """Return {"text","via","purpose"} when the composer owns this ask-shape, else None.

    channel/channel_user_id are accepted for signature parity with the other routes and passed
    only into the audit caller tag — the frame NEVER varies by channel (the A86 done-test).
    """
    msg = (message or "").strip()
    if not client_code or not msg:
        return None

    caller = f"composer_route:{channel or 'unknown'}"

    if _TITLE_LIST_RE.search(msg):
        sl = _SLICE_RE.search(msg)
        env = compose_answer("title_inventory", client_code=client_code, caller=caller,
                             slice=sl.group(1).lower() if sl else None)
        if env["status"] == "hit":
            return {"text": _render(env, max_lines=2), "via": f"composer:title_inventory:{env['status']}",
                    "purpose": "composer_title_inventory"}
        # miss/hold → fall through to the tuned inquiry_stack path (dual path until soak green)

    if _STATUS_RE.search(msg) and not _MATTER_HINT_RE.search(msg) and not _resolve_matters(cur, client_code, msg):
        env = compose_answer("client_status", client_code=client_code, caller=caller)
        if env["status"] in ("hit", "partial"):
            return {"text": _render(env, max_lines=3), "via": f"composer:client_status:{env['status']}",
                    "purpose": "composer_client_status"}

    if _DEADLINE_RE.search(msg):
        # A named matter is answered for THAT matter (2026-10-03): "next hearing in the Balane case"
        # used to return the client-wide list, whose first lines were other matters' stale dates.
        scoped = _resolve_matters(cur, client_code, msg)
        if scoped:
            outs = []
            for mc in scoped:
                env = compose_answer("deadlines", client_code=client_code, caller=caller, matter=mc)
                if env["status"] == "hold":
                    continue
                lines = [ln for ln in ((env.get("frame") or {}).get("lines") or [])
                         if not ln.startswith("[gap]")]
                outs.append(lines[0] if lines else f"{mc}: no forward date is set yet")
            if outs:
                return {"text": _clip(". ".join(o.rstrip(".") for o in outs) + "."),
                        "via": "composer:deadlines:matter", "purpose": "composer_deadlines"}
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

    if _MATTER_ASK_RE.search(msg) and not _TITLE_LIST_RE.search(msg):
        scoped = _resolve_matters(cur, client_code, msg)
        if len(scoped) == 1:
            text = _matter_status_text(cur, client_code, scoped[0])
            if text:
                return {"text": _clip(text), "via": "composer:matter_status", "purpose": "composer_matter_status"}

    return None
