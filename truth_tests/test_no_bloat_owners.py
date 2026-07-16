#!/usr/bin/env python3
"""test_no_bloat_owners.py — A85 floor: one owner per external surface.

Telegram dual-owner (webhook + getUpdates gateway both live) produced ~30k
HTTP 409 Conflict lines and a useless poll loop. This test fails that shape.

Checks (VPS / host with systemd + bot token when available):
  1. Not both: webhook URL set AND landtek-telegram-gateway active
  2. telegram_gateway.py still contains the A85 refuse guard (code floor)
  3. llm.py is Ollama-first (LANDTEK_ALLOW_ANTHROPIC_CHAT optional path)
"""
from __future__ import annotations

import os
import subprocess
import sys
import urllib.parse
import urllib.request
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run, TruthFailure

ROOT = os.environ.get("LANDTEK_ROOT", "/root/landtek")
if not os.path.isdir(ROOT):
    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _systemctl_active(unit: str) -> bool:
    try:
        r = subprocess.run(
            ["systemctl", "is-active", unit],
            capture_output=True, text=True, timeout=5,
        )
        return (r.stdout or "").strip() == "active"
    except Exception:
        return False


def _bot_token() -> str:
    env_path = os.path.join(ROOT, ".env")
    if os.path.exists(env_path):
        for line in open(env_path):
            line = line.strip()
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def _webhook_url(token: str) -> str:
    if not token:
        return ""
    try:
        url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read().decode())
        return ((data.get("result") or {}).get("url") or "").strip()
    except Exception:
        return ""


def no_dual_telegram_owner():
    """A85: webhook owner XOR getUpdates gateway — never both active."""
    gw = _systemctl_active("landtek-telegram-gateway.service")
    # If we cannot see systemd (dev laptop without units), skip live half.
    try:
        subprocess.run(["systemctl", "--version"], capture_output=True, timeout=3, check=True)
        have_systemd = True
    except Exception:
        have_systemd = False

    token = _bot_token()
    wh = _webhook_url(token) if token else ""

    if have_systemd and gw and wh:
        raise TruthFailure(
            f"A85 breach: telegram gateway ACTIVE while webhook is set ({wh[:80]}). "
            "Disable landtek-telegram-gateway OR stop webhook_anchor + deleteWebhook — one owner only."
        )
    return {
        "gateway_active": gw,
        "webhook": (wh[:60] + "…") if len(wh) > 60 else (wh or "(none/unknown)"),
        "have_systemd": have_systemd,
        "ok": not (gw and wh),
    }


def gateway_code_refuses_dual_owner():
    path = os.path.join(ROOT, "scripts", "telegram_gateway.py")
    if not os.path.isfile(path):
        raise TruthFailure(f"missing {path}")
    src = open(path).read()
    if "A85 refuse" not in src and "A85" not in src:
        raise TruthFailure("telegram_gateway.py missing A85 refuse guard")
    if "getWebhookInfo" not in src and "_webhook_url" not in src:
        raise TruthFailure("telegram_gateway.py must check webhook before polling")
    return {"guard": "present"}


def llm_ollama_first():
    path = os.path.join(ROOT, "landtek_telegram", "handlers", "llm.py")
    if not os.path.isfile(path):
        raise TruthFailure(f"missing {path}")
    src = open(path).read()
    if "LANDTEK_ALLOW_ANTHROPIC_CHAT" not in src:
        raise TruthFailure("llm.py must gate Anthropic behind LANDTEK_ALLOW_ANTHROPIC_CHAT (A85)")
    if "_sovereign_ollama_reply" not in src:
        raise TruthFailure("llm.py must call sovereign Ollama path")
    # Ollama must be attempted before Anthropic in handle()
    i_sov = src.find("_sovereign_ollama_reply")
    i_ant = src.find("_call_anthropic(system_prompt")
    if i_sov < 0 or i_ant < 0 or i_sov > i_ant:
        raise TruthFailure("llm.py must try Ollama before Anthropic in handle()")
    return {"order": "ollama_then_optional_anthropic"}


if __name__ == "__main__":
    run("A85_no_dual_telegram_owner", no_dual_telegram_owner)
    run("A85_gateway_code_refuses", gateway_code_refuses_dual_owner)
    run("A85_llm_ollama_first", llm_ollama_first)
