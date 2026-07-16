#!/usr/bin/env python3
"""emission dose — ONE authority (A85), short by construction.

Peer correction (2026-07-16): post-hoc line/char truncation is NOT distillation.
It keeps the ramble and can drop the conclusion. Structured answerers must
EMIT already-short text. This module only:

  1. strip_fluff() — drop greeting/filler lines (no length chop)
  2. EMISSION_CAP  — must match S14 HUMAN_MESSAGE_CAP (280) for operator-facing
     free text; preformed packs MUST be built under this cap by the answerer.

If text exceeds the cap, that is an answerer bug — we log and take the LAST
complete sentence(s) (conclusion-preserving), not the first lines.
"""
from __future__ import annotations

import re
import sys

# Single dose authority — keep in lockstep with scripts/tg_send.HUMAN_MESSAGE_CAP
EMISSION_CAP = 280

_FLUFF_LINE = re.compile(
    r"(?i)^("
    r"hello\b|hi\b|kamusta|salamat|how can i|let me know|if you need|"
    r"anything else|how's everything|i'll check with the team|"
    r"basis:|scope:|not chat memory|i am not inventing"
    r").*"
)


def strip_fluff(text: str) -> str:
    """Remove greeting/filler lines only. Does not truncate."""
    if not text:
        return text or ""
    lines = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if _FLUFF_LINE.match(line.strip()):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def prefer_conclusion(text: str, cap: int = EMISSION_CAP) -> str:
    """If over cap, keep the END (conclusion), not the start (ramble).

    Prefer whole sentences. Only for free LLM prose that violated the system
    prompt — structured packs must never need this.
    """
    t = strip_fluff(text or "")
    if len(t) <= cap:
        return t
    # Last sentences that fit
    parts = re.split(r"(?<=[.!?])\s+", t)
    out = []
    for p in reversed(parts):
        candidate = (p + (" " + " ".join(reversed(out)) if out else "")).strip()
        if len(candidate) <= cap:
            out.insert(0, p)
        else:
            if not out:
                # single long sentence — hard cut on word boundary from end
                return t[-cap:].lstrip()
                # better from start of last window:
                chunk = t[-(cap - 1):]
                sp = chunk.find(" ")
                return (chunk[sp + 1:] if sp > 0 else chunk) + ""
            break
    return " ".join(out).strip()


def distill(text: str, *, max_lines: int = 6, max_chars: int = EMISSION_CAP) -> str:
    """Deprecated name kept for callers. Fluff-strip + conclusion-preserving cap only.

    max_lines is ignored for truncation of body (construction owns line count).
    """
    t = strip_fluff(text or "")
    if max_chars and len(t) > max_chars:
        print(
            f"[distill] WARN over cap {len(t)}>{max_chars} — answerer should be short by construction",
            file=sys.stderr,
        )
        t = prefer_conclusion(t, max_chars)
    return t
