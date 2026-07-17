#!/usr/bin/env python3
"""test_no_second_brain.py — A85 at the reply layer (agent_specs/004 done-when): exactly ONE brain
owns replies. No channel handler may carry its own LLM chat loop — the governed spine (leo_service)
is the only generation path, and model choice lives in the spine's config, never in a handler."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run, TruthFailure

ROOT = "/root/landtek" if os.path.isdir("/root/landtek/landtek_telegram") else \
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

# every channel-handler surface that must NOT own a model call
HANDLER_FILES = [
    "landtek_telegram/handlers/llm.py",
    "landtek_telegram/handlers/vault.py",
    "landtek_telegram/handlers/fallback.py",
    "landtek_telegram/router.py",
    "landtek_telegram/inbox.py",
]
FORBIDDEN = re.compile(r"api\.anthropic\.com|ANTHROPIC_API_KEY|claude-\d|/api/generate|/api/chat")


def handlers_carry_no_model_loop(cur):
    hits = []
    for rel in HANDLER_FILES:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            continue
        for n, line in enumerate(open(path, encoding="utf-8", errors="replace"), 1):
            s = line.strip()
            if s.startswith("#"):
                continue                       # comments may document the retirement
            if FORBIDDEN.search(s):
                hits.append(f"{rel}:{n}: {s[:70]}")
    if hits:
        raise TruthFailure("a channel handler owns a model call (A85 second-brain breach):\n  "
                           + "\n  ".join(hits[:6]))


def tg_llm_handler_is_spine_only(cur):
    """The TG conversation handler's only generation route is the sovereign spine."""
    path = os.path.join(ROOT, "landtek_telegram/handlers/llm.py")
    src = open(path, encoding="utf-8", errors="replace").read()
    if "_sovereign_ollama_reply" not in src or "leo_service" not in src:
        raise TruthFailure("TG llm handler no longer routes through the sovereign spine.")
    for bad in ("_call_anthropic", "SYSTEM_PROMPT_GROUP_TEMPLATE", "allow_anthropic"):
        if bad in src:
            raise TruthFailure(f"retired Anthropic-loop artifact still present: {bad}")


TESTS = [
    ("no_second_brain.handlers_carry_no_model_loop", handlers_carry_no_model_loop),
    ("no_second_brain.tg_llm_handler_is_spine_only", tg_llm_handler_is_spine_only),
]

if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
