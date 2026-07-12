#!/usr/bin/env python3
"""relationship_profile.py — the first living organ (Increment 2). A per-relationship record that GROWS
from every verified exchange and FEEDS the next reply. Deterministic + $0 (heuristic signals; the LLM is
for generation, not extraction). Minimal + alive: the profile is a living summary, signal_log is the
append-only arc. Never overwrites history.

  observe(cur, channel, uid, client, entity_id, msg_id, message, internal) -> profile dict (evolved)
  to_prompt(profile, exchanges) -> a compact directive block for the generation prompt
"""
import json
import re

_FIL = {"po", "kayo", "salamat", "kamusta", "ako", "ninyo", "naman", "yung", "mga", "ang", "sa", "ng",
        "ito", "kung", "hindi", "opo", "sige", "kita", "natin", "tayo", "niya", "kasi"}
_THEMES = {
    "titles": ["tct", "title", "t-", "oct", "lot", "parcel"],
    "deadlines": ["deadline", "due", "hearing", "filing", "pre-trial", "schedule"],
    "counsel": ["atty", "counsel", "lawyer", "barandon", "avas", "law office"],
    "tax": ["rpt", "tax", "assessment", "real property tax", "amilyar"],
    "survey": ["survey", "relocation", "geodetic", "monument", "metes"],
    "arta": ["arta", "docket", "ctn"],
    "deed": ["deed", "sale", "spa", "donation", "conveyance"],
    "estate": ["estate", "heir", "guardianship", "administrator"],
}
_URGENCY = {"urgent", "asap", "now", "immediately", "today", "emergency", "critical", "rush", "please"}
_GRAT = {"salamat", "thank", "thanks", "appreciate", "grateful"}


def extract_signals(message, internal):
    m = (message or "").lower()
    words = set(re.findall(r"[a-z']+", m))
    lang = "taglish" if len(words & _FIL) >= 2 else "english"
    themes = [t for t, kws in _THEMES.items() if any(k in m for k in kws)]
    detail = "terse" if len(m) < 40 else ("detailed" if len(m) > 200 else "medium")
    return {"lang": lang, "themes": themes, "urgency": bool(words & _URGENCY),
            "gratitude": bool(words & _GRAT), "detail": detail,
            "contradictions": (internal or {}).get("contradictions", 0)}


def _merge(profile, sig):
    def bump(key, sub):
        d = profile.setdefault(key, {}); d[sub] = d.get(sub, 0) + 1
    bump("lang", sig["lang"])
    bump("detail", sig["detail"])
    for t in sig["themes"]:
        bump("themes", t)
    if sig["urgency"]:
        profile["urgency_hits"] = profile.get("urgency_hits", 0) + 1
    if sig["gratitude"]:
        profile["gratitude_hits"] = profile.get("gratitude_hits", 0) + 1
    # living summary derivations (the "how to speak to them right now")
    if profile.get("lang"):
        profile["dominant_lang"] = max(profile["lang"], key=profile["lang"].get)
    if profile.get("detail"):
        profile["usual_detail"] = max(profile["detail"], key=profile["detail"].get)
    if profile.get("themes"):
        profile["top_themes"] = [t for t, _ in sorted(profile["themes"].items(), key=lambda x: -x[1])[:3]]
    return profile


def observe(cur, channel, channel_user_id, client_code, entity_id, inbound_msg_id, message, internal):
    """Evolve the living profile for this verified line from one exchange. Idempotent on inbound_msg_id."""
    channel_user_id = str(channel_user_id)
    cur.execute("SELECT profile, signal_log, exchanges, last_inbound_id FROM relationship_profile "
                "WHERE channel=%s AND channel_user_id=%s", (channel, channel_user_id))
    row = cur.fetchone()
    if row and row["last_inbound_id"] == inbound_msg_id:
        p = dict(row["profile"])                            # already counted this message — no double-count,
        p["_exchanges"] = row["exchanges"]                  # but still report the live count to the caller
        return p
    if entity_id is None:
        cur.execute("""SELECT cu.entity_id FROM channel_users cu JOIN channels c ON c.id=cu.channel_id
                        WHERE c.name=%s AND cu.channel_user_id=%s""", (channel, channel_user_id))
        e = cur.fetchone()
        entity_id = e["entity_id"] if e else None
    sig = extract_signals(message, internal)
    profile = dict(row["profile"]) if row else {}
    log = list(row["signal_log"]) if row else []
    _merge(profile, sig)
    log.append({"msg": inbound_msg_id, **sig})
    log = log[-50:]                                        # bound the arc; the summary carries the long history
    exchanges = (row["exchanges"] if row else 0) + 1
    cur.execute("""
        INSERT INTO relationship_profile
          (channel, channel_user_id, client_code, entity_id, profile, signal_log, exchanges, last_inbound_id, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s, now())
        ON CONFLICT (channel, channel_user_id) DO UPDATE SET
          client_code=EXCLUDED.client_code, entity_id=EXCLUDED.entity_id, profile=EXCLUDED.profile,
          signal_log=EXCLUDED.signal_log, exchanges=EXCLUDED.exchanges,
          last_inbound_id=EXCLUDED.last_inbound_id, updated_at=now()
    """, (channel, channel_user_id, client_code, entity_id, json.dumps(profile), json.dumps(log),
          exchanges, inbound_msg_id))
    profile["_exchanges"] = exchanges
    return profile


def anticipate(cur, client_code, profile):
    """0-2 time-sensitive items THIS relationship genuinely cares about — from surfaced_deadlines +
    matter_plays, gated by the profile's OBSERVED themes (relationship-specific, not a global rule).
    Empty is valid and common (no data / no recurring theme yet). Deterministic + $0."""
    themes = set(profile.get("top_themes", []) if profile else [])
    if not themes or not client_code:
        return []
    fam = client_code.split("-")[0]
    items = []
    # a soon, time-sensitive item — surfaced only when the record shows time-sensitive concerns
    if themes & {"deadlines", "titles", "tax", "arta", "survey", "estate", "deed"}:
        cur.execute("""SELECT label, days_out FROM surfaced_deadlines
                        WHERE matter_code LIKE %s AND days_out IS NOT NULL AND days_out >= 0
                        ORDER BY days_out ASC LIMIT 1""", (fam + "%",))
        d = cur.fetchone()
        if d and d["days_out"] is not None and d["days_out"] <= 45:
            items.append({"kind": "deadline", "text": f"{d['label']} — due in {d['days_out']} day(s)"})
    # the relationship's top open action (their own matter; generation decides whether it fits)
    cur.execute("""SELECT title, suggested_action FROM matter_plays
                    WHERE matter_code LIKE %s AND score IS NOT NULL
                    ORDER BY score DESC LIMIT 1""", (fam + "%",))
    p = cur.fetchone()
    if p:
        act = (p["suggested_action"] or p["title"] or "").strip()
        if act:
            items.append({"kind": "action", "text": act[:120]})
    return items[:2]


def tending_block(items):
    """The optional 'tend the relationship' directive — the profile + anticipation are inputs, not commands."""
    if not items:
        return ""
    lines = "; ".join(f"{i['kind']}: {i['text']}" for i in items)
    return ("RELATIONSHIP TENDING (OPTIONAL — the record shows recurring concerns; if and only if it flows "
            "naturally and warmly, you MAY gently surface the single most relevant of these in their learned "
            "tone. Never force it, never list mechanically, never surface if it doesn't fit the moment): " + lines)


def record_anticipation(cur, channel, channel_user_id, inbound_msg_id, items):
    """Append what was surfaced back into the arc (append-only) so the profile can later learn if it landed."""
    if not items:
        return
    try:
        cur.execute("""UPDATE relationship_profile
                          SET signal_log = signal_log || %s::jsonb
                        WHERE channel=%s AND channel_user_id=%s""",
                    (json.dumps([{"msg": inbound_msg_id, "anticipated": items}]), channel, str(channel_user_id)))
    except Exception:
        pass


def to_prompt(profile):
    """Compact directive block — 'how this person wants to be spoken to', for the generation prompt."""
    if not profile:
        return ""
    n = profile.get("_exchanges") or profile.get("exchanges") or 0
    lang = profile.get("dominant_lang", "either")
    detail = profile.get("usual_detail", "medium")
    themes = ", ".join(profile.get("top_themes", [])) or "no recurring theme yet"
    grat = profile.get("gratitude_hits", 0); urg = profile.get("urgency_hits", 0)
    tone = "warm/appreciative" if grat > urg else ("time-pressured" if urg else "neutral")
    return (f"RELATIONSHIP RECORD ({n} prior exchanges — speak the way this record shows they respond best, "
            f"and anticipate their likely next need): preferred language={lang}; usual detail={detail}; "
            f"recurring concerns={themes}; observed tone={tone}.")
