#!/usr/bin/env python3
"""model_router.py — route each task to the cheapest model that does it well: the
~70% inference-cut lever (MASTER_PLAN §4A). Every call is recorded via cost_governor so
the daily cap sees total spend.

TASK TIER → model ladder (tried in order; falls down the ladder on missing/depleted/error):
  classify / route   → Haiku   → Gemini Flash     (cheap labels)
  extract  / bulk    → Gemini Flash → GPT-4o-mini  (high-volume extraction)
  reason   (default) → Sonnet  → Gemini Flash
  synth    / legal   → Opus    → Sonnet            (hard legal synthesis only)

Because the ladder falls back, cheap work keeps running on Gemini's free tier even while
the Anthropic balance is at $0 — graceful degradation instead of a hard stop.

  python3 model_router.py classify "Label this as deed/affidavit/title/other: ..."
"""
import json
import os
import sys
import urllib.request
import urllib.error

sys.path.insert(0, "/root/landtek/scripts")
try:
    import cost_governor as cg
except Exception:
    cg = None

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")

LADDER = {
    "classify": [("anthropic", "claude-haiku-4-5-20251001"), ("gemini", "gemini-2.5-flash")],
    "extract":  [("gemini", "gemini-2.5-flash"), ("openai", "gpt-4o-mini")],
    "reason":   [("anthropic", "claude-sonnet-4-5-20250929"), ("gemini", "gemini-2.5-flash")],
    "synth":    [("anthropic", "claude-opus-4-5-20251101"), ("anthropic", "claude-sonnet-4-5-20250929")],
}


def _anthropic(model, system, prompt, max_tokens):
    if not ANTHROPIC_KEY:
        raise RuntimeError("no anthropic key")
    body = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
    if system:
        body["system"] = system
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
        headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=90) as r:
        p = json.loads(r.read())
    if cg:
        cg.record(model, p.get("usage", {}), source="router")
    return "".join(b.get("text", "") for b in p.get("content", []) if b.get("type") == "text")


def _gemini(model, system, prompt, max_tokens):
    if not GEMINI_KEY:
        raise RuntimeError("no gemini key")
    text = (system + "\n\n" if system else "") + prompt
    body = {"contents": [{"parts": [{"text": text}]}], "generationConfig": {"maxOutputTokens": max_tokens}}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_KEY}"
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=90) as r:
        p = json.loads(r.read())
    u = p.get("usageMetadata", {})
    if cg:
        cg.record("gemini-flash", {"input_tokens": u.get("promptTokenCount", 0),
                                   "output_tokens": u.get("candidatesTokenCount", 0)}, source="router")
    return "".join(pt.get("text", "") for pt in p["candidates"][0]["content"]["parts"])


def _openai(model, system, prompt, max_tokens):
    if not OPENAI_KEY:
        raise RuntimeError("no openai key")
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    body = {"model": model, "messages": msgs, "max_tokens": max_tokens}
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode(),
        headers={"authorization": f"Bearer {OPENAI_KEY}", "content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=90) as r:
        p = json.loads(r.read())
    if cg:
        u = p.get("usage", {})
        cg.record(model, {"input_tokens": u.get("prompt_tokens", 0), "output_tokens": u.get("completion_tokens", 0)},
                  source="router")
    return p["choices"][0]["message"]["content"]


_CALL = {"anthropic": _anthropic, "gemini": _gemini, "openai": _openai}


def route(tier, prompt, system=None, max_tokens=1024):
    """Try the model ladder for `tier`; return (text, 'provider:model'). Raises if all fail."""
    errs = []
    for provider, model in LADDER.get(tier, LADDER["reason"]):
        try:
            return _CALL[provider](model, system, prompt, max_tokens), f"{provider}:{model}"
        except urllib.error.HTTPError as e:
            errs.append(f"{provider}:{model}: http_{e.code}")
        except Exception as e:
            errs.append(f"{provider}:{model}: {str(e)[:80]}")
    raise RuntimeError("all providers failed → " + " | ".join(errs))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(0)
    tier, prompt = sys.argv[1], sys.argv[2]
    try:
        text, used = route(tier, prompt, max_tokens=256)
        print(f"[{used}]\n{text}")
    except Exception as e:
        print(f"ERROR: {e}")
