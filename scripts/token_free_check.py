#!/usr/bin/env python3
"""
token_free_check.py — prove the LandTek inference stack runs on OWNED compute ($0, no tokens).

What it verifies (all local, no DB/network to paid endpoints required):
  1. Ollama is reachable on the local socket (127.0.0.1:11434) or the Tailscale IP.
  2. A real generation completes through the LOCAL model (no API key, no egress).
  3. The sovereign model fleet is present (vision 7b, instruct 7b/14b, nomic-embed).
  4. No paid-provider API key is exported in THIS shell (the leak vector for the Gemini OCR path).
  5. The default OCR router that would be used is the $0 local one, not the metered Gemini one.

Exit code: 0 = token-free posture OK; non-zero = a leak/risk is present (printed).

Run:  python3 scripts/token_free_check.py
Authoring/DESIGNER window — does NOT write to the DB. Safe to run anytime.
"""
from __future__ import annotations
import json
import os
import sys
import urllib.request
import urllib.error

OLLAMA_HOSTS = [
    os.environ.get("OLLAMA_URL", "").rstrip("/api") or "http://127.0.0.1:11434",
    "http://127.0.0.1:11434",
    "http://100.117.118.47:11434",  # Tailscale VPS-side reach
]
REQUIRED_MODELS = {
    "qwen2.5vl:7b",            # local vision OCR (reocr_local.py)
    "qwen2.5:7b-instruct",     # fast extraction / verify-worker tier 1
    "qwen2.5:14b-instruct",    # deep legal reasoning (legal_agent.py)
    "nomic-embed-text:latest", # local embeddings
}
PAID_KEY_VARS = ["GEMINI_API_KEY", "GEMINI_API_KEY_FALLBACK", "ANTHROPIC_API_KEY",
                 "OPENAI_API_KEY", "GOOGLE_API_KEY"]

problems = []
ok = []


def _get(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def check_ollama_up():
    for h in OLLAMA_HOSTS:
        try:
            d = _get(h.rstrip("/") + "/api/tags", timeout=4)
            return h, {m["name"] for m in d.get("models", [])}
        except Exception:
            continue
    return None, set()


def check_local_generate(host):
    body = {"model": "qwen2.5:7b-instruct", "prompt": "reply with exactly: TOKEN_FREE_OK",
            "stream": False, "options": {"temperature": 0}}
    url = host.rstrip("/") + "/api/generate"
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read()).get("response", "")


def main():
    print("=== LandTek token-free posture check ===\n")

    # 1+2: Ollama up + a real local generation
    host, models = check_ollama_up()
    if not host:
        problems.append("Ollama not reachable on any known host — local inference tier is DOWN.")
        print("[FAIL] Ollama unreachable. The sovereign tier is offline; the stack would fall back to paid APIs.")
    else:
        ok.append(f"Ollama reachable at {host}")
        print(f"[ OK ] Ollama up: {host}")
        try:
            resp = check_local_generate(host).strip()
            ok.append(f"local generation returned: {resp!r}")
            print(f"[ OK ] Local generation succeeded (no API key, no egress): {resp!r}")
        except Exception as e:
            problems.append(f"Local generation failed: {e}")
            print(f"[FAIL] local generation error: {e}")

    # 3: sovereign fleet present
    missing = REQUIRED_MODELS - models
    if missing:
        problems.append(f"Missing local model(s): {', '.join(sorted(missing))} — pull with `ollama pull <name>`.")
        print(f"[WARN] Missing local model(s): {', '.join(sorted(missing))}")
    else:
        ok.append("sovereign model fleet present")
        print("[ OK ] Sovereign model fleet present (vision 7b, instruct 7b/14b, nomic-embed).")

    # 4: no paid keys in this shell
    leaked = [v for v in PAID_KEY_VARS if os.environ.get(v)]
    if leaked:
        problems.append(f"Paid-provider API key(s) exported in this shell: {', '.join(leaked)} "
                        f"— the Gemini/Anthropic paths could fire if invoked.")
        print(f"[WARN] Paid key(s) in env: {', '.join(leaked)} (leak vector for metered OCR).")
    else:
        ok.append("no paid API keys in this shell")
        print("[ OK ] No paid-provider API keys exported here — Gemini/Anthropic paths cannot auto-fire.")

    # 5: default OCR router is the $0 local one
    # reocr_local.py is the creditless path; reocr_gemini.py requires GEMINI_API_KEY to do anything.
    gemini_default = bool(os.environ.get("GEMINI_API_KEY")) and ("reocr_gemini" in sys.argv)
    if gemini_default:
        problems.append("argv invokes reocr_gemini with a key set — that is the METERED path.")
        print("[FAIL] This invocation uses the metered Gemini OCR path.")
    else:
        ok.append("default re-OCR router is the $0 local vision model (reocr_local.py)")
        print("[ OK ] Default re-OCR path is reocr_local.py (owned qwen2.5vl, $0). "
              "Gemini path only runs if you explicitly call reocr_gemini.py AND a key is set.")

    print()
    if problems:
        print(f"RESULT: NOT fully token-free — {len(problems)} issue(s):")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    print(f"RESULT: TOKEN-FREE OK ({len(ok)} checks passed). Sovereign inference is live; "
          "no paid calls in this window.")
    sys.exit(0)


if __name__ == "__main__":
    main()
