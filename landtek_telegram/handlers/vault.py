#!/usr/bin/env python3
"""landtek_telegram/handlers/vault.py — deterministic vault command handler.

Parses Kristyle/Jonathan's natural-language messages into vault tool calls.
No LLM in the hot path. Uses regex + matter-code lexicon + section-code
lexicon. Falls back to a clarifying question when ambiguous.

Calls the vault HTTP endpoints exposed by leo_tools (already running at
:8765). Replies via tg_send.py with override_rate_limit=True (these are
operational confirmations, not unprompted bombardment).

Returns a dict: {"handler": "vault", "outcome": "...", "reply_sent": bool}.
"""
from __future__ import annotations
import os
import re
import sys
import urllib.parse
import urllib.request
import json

sys.path.insert(0, "/root/landtek/scripts")
try:
    from tg_send import send as tg_send
except Exception:
    tg_send = None

LEO_TOOLS_BASE = os.environ.get("LANDTEK_LEO_TOOLS_BASE",
                                "http://127.0.0.1:8765")

VAULT_SECTIONS = {"TCT", "DEED", "SPA", "AFF", "TAX", "PSA", "ID",
                  "CRT", "RES", "CONT", "CORR", "MISC"}

# Matter shortcuts — what Kristyle says → canonical matter_code
MATTER_LEXICON = {
    r"\b4497\b":                 "MWK-TCT4497",
    r"\bTCT[\s\-]?4497\b":       "MWK-TCT4497",
    r"\bT[\s\-]?4497\b":         "MWK-TCT4497",
    r"\b26[\s\-]?360\b":         "MWK-CV26360",
    r"\bCV[\s\-]?26[\s\-]?360\b":"MWK-CV26360",
    r"\bbalane\b":               "MWK-CV26360",
    r"\bcivil case\b":           "MWK-CV26360",
    r"\bOP[\s\-]?petition\b":    "MWK-OP-PETITION",
    r"\bOP case\b":              "MWK-OP-PETITION",
    r"\bestate\b":               "MWK-ESTATE",
    r"\bguardianship\b":         "MWK-GUARDIANSHIP",
    r"\bARTA[\s\-]?1210\b":      "MWK-ARTA-1210",
    r"\b1210\b":                 "MWK-ARTA-1210",
    r"\bARTA[\s\-]?0747\b":      "MWK-ARTA-0747",
    r"\b747\b":                  "MWK-ARTA-0747",
    r"\bARTA[\s\-]?1212\b":      "MWK-ARTA-1212",
    r"\b1212\b":                 "MWK-ARTA-1212",
    r"\bARTA[\s\-]?1378\b":      "MWK-ARTA-1378",
    r"\bARTA[\s\-]?1319\b":      "MWK-ARTA-1319",
    r"\bARTA[\s\-]?1321\b":      "MWK-ARTA-1321",
    r"\bARTA[\s\-]?1891\b":      "MWK-ARTA-1891",
    r"\bARTA[\s\-]?0690\b":      "MWK-ARTA-0690",
    r"\bARTA[\s\-]?0792\b":      "MWK-ARTA-0792",
    r"\b6839\b":                 "MWK-CV6839",
    r"\bCV[\s\-]?6839\b":        "MWK-CV6839",
    r"\bagrarian\b":             "MWK-CV6839",
    r"\bCRIM[\s\-]?9221\b":      "MWK-PARALLEL-CRIM9221",
    r"\b9221\b":                 "MWK-PARALLEL-CRIM9221",
    r"\bCV[\s\-]?6922\b":        "MWK-PARALLEL-CV6922",
    r"\b6922\b":                 "MWK-PARALLEL-CV6922",
    r"\bDILG\b":                 "MWK-ARTA-DILG",
    r"\bcapacuan\b":             "PAR-CAPACUAN",
    r"\bvito[\s\-]?cruz\b":      "PAR-VITO-CRUZ",
    r"\bgolden[\s\-]?sand\b":    "PAR-GOLDEN-SAND",
    r"\bTCT[\s\-]?1616\b":       "PAR-TCT1616",
}

# Explicit syntax patterns (highest priority)
SECT_NUM_RE = re.compile(r"\b(TCT|DEED|SPA|AFF|TAX|PSA|ID|CRT|RES|CONT|CORR|MISC)[\s\-]?0*(\d{1,4})\b",
                         re.IGNORECASE)
EXPLICIT_MATTER_RE = re.compile(r"matter[\s:=]+([A-Z]{2,5}[\-_][A-Z0-9\-]+)", re.IGNORECASE)


def _http_get(path, **params):
    qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    url = f"{LEO_TOOLS_BASE}{path}" + (f"?{qs}" if qs else "")
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": f"http_get_failed: {e}"}


def _http_post(path, body):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{LEO_TOOLS_BASE}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"ok": False, "error": f"http_error_{e.code}"}
    except Exception as e:
        return {"ok": False, "error": f"http_post_failed: {e}"}


def _match_matter(text):
    """Best-effort matter_code extraction from natural text."""
    em = EXPLICIT_MATTER_RE.search(text)
    if em:
        return em.group(1).upper()
    for pattern, code in MATTER_LEXICON.items():
        if re.search(pattern, text, re.IGNORECASE):
            return code
    return None


def _reply(chat_id, text, recipient_name=None, override_pacing=True):
    if tg_send is None:
        print(f"[vault] tg_send unavailable; would reply to {chat_id}: {text[:120]}")
        return False
    try:
        ok, _info = tg_send(chat_id=str(chat_id), text=text, source="vault_handler",
                            recipient_name=recipient_name,
                            override_pacing=override_pacing,
                            override_rate_limit=True,
                            human_readable=False)
        return ok
    except Exception as e:
        print(f"[vault] tg_send raised: {e}", file=sys.stderr)
        return False


def _classify_intent(text):
    """Return intent: vault|scan|find|queue|missing|last|none."""
    t = text.lower().strip()
    if not t:
        return "none"
    # Imperative verbs at start
    if re.match(r"^(vault|just\s+vaulted|vaulted|labeling|labeled|put\s+in\s+(the\s+)?vault|i\s+just\s+(put|vaulted))", t):
        return "vault"
    if re.match(r"^(scan|scanned|attach|attaching|i\s+scanned)", t):
        return "scan"
    if re.match(r"^(find|where(\s+is)?|what\s+is)\s+(aff|tct|spa|deed|tax|psa|id|crt|res|cont|corr|misc)[\s\-]?\d", t):
        return "find"
    if re.match(r"^(queue|what(\s+is)?(\s+the)?\s+queue|what'?s?\s+pending|what\s+should\s+i\s+work\s+on)", t):
        return "queue"
    if re.match(r"^(missing|what(\s+is)?\s+missing|what\s+(does|needs))", t):
        return "missing"
    if re.match(r"^(last|recent|what(\s+did)?\s+i\s+(do|vault)|show\s+(the\s+)?last)", t):
        return "last"
    # Mid-sentence hints
    if re.search(r"\bvault(ed|ing)?\b", t) and SECT_NUM_RE.search(text):
        return "vault"
    if "queue" in t or "pending" in t:
        return "queue"
    if "missing" in t:
        return "missing"
    return "none"


def handle(row):
    """Process one telegram_inbox row. Returns outcome dict."""
    text = row.get("text_content") or ""
    chat_id = row.get("chat_id")
    sender_name = row.get("sender_name") or "there"

    if not text:
        return {"handler": "vault", "outcome": "skip_no_text", "reply_sent": False}

    intent = _classify_intent(text)
    if intent == "none":
        return {"handler": "vault", "outcome": "not_vault_intent",
                "reply_sent": False}

    # Dispatch by intent
    if intent == "vault":
        return _do_vault(text, chat_id, sender_name)
    if intent == "scan":
        return _do_scan(text, chat_id, sender_name)
    if intent == "find":
        return _do_find(text, chat_id, sender_name)
    if intent == "queue":
        return _do_queue(chat_id)
    if intent == "missing":
        return _do_missing(text, chat_id, sender_name)
    if intent == "last":
        return _do_last(text, chat_id)
    return {"handler": "vault", "outcome": "unrecognized_intent", "reply_sent": False}


def _do_vault(text, chat_id, sender_name):
    m = SECT_NUM_RE.search(text)
    if not m:
        _reply(chat_id, "Got it. What section and number? Like AFF-1 or SPA-3.")
        return {"handler": "vault", "outcome": "asked_for_locator", "reply_sent": True}
    section, num_str = m.group(1).upper(), m.group(2)
    number = int(num_str)
    matter = _match_matter(text)
    if not matter:
        _reply(chat_id, f"Got the locator {section}-{number:03d}. Which matter? "
                       "Examples: the 4497 case, ARTA-1210, the OP case, the Balane case.")
        return {"handler": "vault", "outcome": "asked_for_matter", "reply_sent": True}
    # Description is everything else minus the locator + matter hint
    desc = SECT_NUM_RE.sub("", text)
    desc = EXPLICIT_MATTER_RE.sub("", desc)
    for pat in MATTER_LEXICON:
        desc = re.sub(pat, "", desc, flags=re.IGNORECASE)
    desc = re.sub(r"^(vault|just\s+vaulted|vaulted|i\s+just\s+(put|vaulted|labeled))\s*",
                  "", desc.strip(), flags=re.IGNORECASE)
    desc = re.sub(r"\bmatter\b", "", desc, flags=re.IGNORECASE).strip(" ,.:;-")
    if len(desc) < 3:
        desc = f"{section} entry {number}"

    # Pass sender_id so the endpoint auto-attaches a recent photo as the scan
    sender_id = row.get("sender_id") if isinstance(row, dict) else None
    body = {
        "section": section, "number": number,
        "description": desc, "matter_code": matter,
    }
    if sender_id:
        body["auto_attach_sender_id"] = sender_id
    result = _http_post("/api/vault/register", body)
    if result.get("ok"):
        scan_note = ""
        if result.get("scan_source") and result["scan_source"] != "placeholder":
            scan_note = " Photo attached as the digital scan."
        elif result.get("scan_source") == "placeholder":
            scan_note = " No scan attached yet — send the photo when you have it."
        _reply(chat_id, f"Logged {result['locator']} — {desc}, matter {matter}.{scan_note}")
        return {"handler": "vault", "outcome": f"registered:{result.get('doc_id')}",
                "reply_sent": True}
    err = result.get("error", "unknown")
    if "locator_taken" in err:
        _reply(chat_id, f"{section}-{number:03d} is already taken. Want this one to be {section}-{number+1:03d}?")
    elif "unknown_matter" in err:
        _reply(chat_id, f"Couldn't match matter '{matter}'. Try the exact code like MWK-TCT4497.")
    elif "unknown_section" in err:
        _reply(chat_id, f"Section {section!r} isn't recognized. Use one of: " + ", ".join(sorted(VAULT_SECTIONS)))
    else:
        _reply(chat_id, f"Couldn't register that — {err}.")
    return {"handler": "vault", "outcome": f"register_failed:{err[:80]}", "reply_sent": True}


def _do_scan(text, chat_id, sender_name):
    m = SECT_NUM_RE.search(text)
    if not m:
        _reply(chat_id, "Which one are you scanning? Tell me the section and number, like AFF-1.")
        return {"handler": "vault", "outcome": "scan_no_locator", "reply_sent": True}
    section, number = m.group(1).upper(), int(m.group(2))
    drive_match = re.search(r"(?:drive[\s:.-]+id[\s:.-]+|drive_file_id[\s:.-]+)?([A-Za-z0-9_-]{20,})", text)
    drive_id = drive_match.group(1) if drive_match else None
    if not drive_id:
        _reply(chat_id, f"Got {section}-{number:03d}. Send the drive file id or URL for the scan.")
        return {"handler": "vault", "outcome": "scan_no_drive_id", "reply_sent": True}
    result = _http_post("/api/vault/attach_scan", {
        "section": section, "number": number, "drive_file_id": drive_id})
    if result.get("ok"):
        _reply(chat_id, f"Scan attached to {section}-{number:03d}.")
        return {"handler": "vault", "outcome": "scan_attached", "reply_sent": True}
    _reply(chat_id, f"Couldn't attach scan: {result.get('error','unknown')[:120]}")
    return {"handler": "vault", "outcome": "scan_failed", "reply_sent": True}


def _do_find(text, chat_id, sender_name):
    m = SECT_NUM_RE.search(text)
    if not m:
        _reply(chat_id, "Which entry? Like find AFF-1.")
        return {"handler": "vault", "outcome": "find_no_locator", "reply_sent": True}
    section, number = m.group(1).upper(), int(m.group(2))
    r = _http_get("/api/vault/find", section=section, number=number)
    if r.get("ok"):
        mats = ", ".join(r.get("matter_codes") or []) or "no matter linked"
        scan = "scan attached" if r.get("digital_scan_id") else "no scan yet"
        loc = r.get("vault_location") or "no location noted"
        _reply(chat_id, f"{section}-{number:03d}: {r.get('smart_filename')}. Matter: {mats}. {scan}. Cabinet: {loc}.")
        return {"handler": "vault", "outcome": f"found:{r.get('id')}", "reply_sent": True}
    _reply(chat_id, f"Nothing at {section}-{number:03d} yet.")
    return {"handler": "vault", "outcome": "not_found", "reply_sent": True}


def _do_queue(chat_id):
    r = _http_get("/api/vault/queue")
    n = (r.get("counts") or {}).get("pending_scans", 0)
    if n == 0:
        _reply(chat_id, "Nothing pending right now. Vault is current.")
    else:
        items = r.get("pending_scans", [])[:3]
        names = "; ".join(it.get("smart_filename", "?") for it in items)
        _reply(chat_id, f"{n} vault {'entry' if n==1 else 'entries'} waiting for a scan. Top: {names}.")
    return {"handler": "vault", "outcome": f"queue:{n}", "reply_sent": True}


def _do_missing(text, chat_id, sender_name):
    matter = _match_matter(text)
    if not matter:
        _reply(chat_id, "Which matter? Examples: the 4497 case, ARTA-1210, the Balane case.")
        return {"handler": "vault", "outcome": "missing_no_matter", "reply_sent": True}
    r = _http_get("/api/vault/missing", matter_code=matter)
    if not r.get("ok"):
        _reply(chat_id, f"Couldn't pull the list: {r.get('error','unknown')[:80]}")
        return {"handler": "vault", "outcome": "missing_failed", "reply_sent": True}
    sugg = r.get("suggestions", [])
    if not sugg:
        _reply(chat_id, f"Nothing obvious needs vaulting for {matter}.")
    else:
        top = sugg[:3]
        lines = "; ".join(f"{s['suggested_section']} for {s['smart_filename'][:50]}" for s in top)
        _reply(chat_id, f"{matter} — {len(sugg)} likely vault candidates. Top three: {lines}.")
    return {"handler": "vault", "outcome": f"missing:{len(sugg)}", "reply_sent": True}


def _do_last(text, chat_id):
    n_match = re.search(r"\b(\d{1,2})\b", text)
    n = int(n_match.group(1)) if n_match else 5
    n = max(1, min(n, 20))
    r = _http_get("/api/vault/last", n=n)
    entries = r.get("entries", [])
    if not entries:
        _reply(chat_id, "Vault is empty so far.")
    else:
        lines = "; ".join(f"{e['vault_section']}-{e['vault_number']:03d}" for e in entries[:5])
        _reply(chat_id, f"Last {min(n,len(entries))} vault entries: {lines}.")
    return {"handler": "vault", "outcome": f"last:{len(entries)}", "reply_sent": True}
