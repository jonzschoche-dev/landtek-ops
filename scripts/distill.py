#!/usr/bin/env python3
"""distill.py — emission plane of reasoning equilibrium (A71 + A75 dose).

Internal MPRB / corpus work may be multi-angle and long.
What a human receives MUST be short, cold, and one-point.

Hard caps (operator-tolerable, not a data dump):
  MAX_LINES  = 6
  MAX_CHARS  = 700
  No greetings, no "let me know if", no scope lectures unless essential.
"""
from __future__ import annotations

import re

MAX_LINES = 6
MAX_CHARS = 700

_FLUFF = re.compile(
    r"(?i)^("
    r"hello\b|hi\b|kamusta|salamat|how can i|let me know|if you need|"
    r"anything else|how's everything|i'll check with the team|"
    r"basis:|scope:|not chat memory|i am not inventing"
    r").*"
)


def distill(text: str, *, max_lines: int = MAX_LINES, max_chars: int = MAX_CHARS) -> str:
    """Force human-tolerable length. Prefer early lines (already ordered as answer-first)."""
    if not text:
        return text
    lines = []
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        if not line.strip():
            if lines and lines[-1] != "":
                lines.append("")  # keep single blank sparingly
            continue
        if _FLUFF.match(line.strip()):
            continue
        # Drop long "Not counted" essays — keep one line max later
        lines.append(line)

    # Collapse multiple blanks
    out, prev_blank = [], False
    for line in lines:
        blank = line.strip() == ""
        if blank and prev_blank:
            continue
        out.append(line)
        prev_blank = blank

    # Prefer answer lines; if still too many, keep first max_lines non-empty
    non_empty = [l for l in out if l.strip()]
    if len(non_empty) > max_lines:
        non_empty = non_empty[:max_lines]
    body = "\n".join(non_empty).strip()
    if len(body) > max_chars:
        body = body[: max_chars - 1].rsplit("\n", 1)[0].rstrip()
        if len(body) > max_chars:
            body = body[: max_chars - 1].rstrip() + "…"
    return body
