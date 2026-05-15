"""LLM dispatch — Claude Sonnet/Opus primary, OpenAI GPT-4o fallback.

Per-pass model routing:
  - heavy passes (synthesis, cross-doc): claude-opus-4-6
  - medium passes (entity extraction, classification, critic, verification): claude-sonnet-4-6
  - light passes (triage if used): claude-haiku-4-5

If ANTHROPIC_API_KEY is missing, falls back to GPT-4o for everything.

Returns parsed JSON dict, raises on unrecoverable failures (bubble up to caller).
"""
from __future__ import annotations
import json, time
from typing import Optional, List, Dict, Any
import httpx

from config import (
    OPENAI_API_KEY, ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL_HEAVY, ANTHROPIC_MODEL_MEDIUM, ANTHROPIC_MODEL_LIGHT,
    OPENAI_MODEL_FALLBACK,
)


# ---------------------------------------------------------------------------
# Provider primitives
# ---------------------------------------------------------------------------
def _strip_md_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        # remove leading ```json or ``` and trailing ```
        t = t.strip("`")
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
        # remove trailing fence
        if "\n```" in t:
            t = t.split("\n```")[0]
    return t.strip()


def _anthropic_call(
    *, model: str, system: Optional[str], prompt: str,
    max_tokens: int, temperature: float, timeout_s: float,
) -> str:
    """Returns the assistant's raw text content."""
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body: Dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system
    with httpx.Client(timeout=timeout_s) as client:
        r = client.post("https://api.anthropic.com/v1/messages",
                        headers=headers, json=body)
        if r.status_code >= 400:
            raise RuntimeError(f"Anthropic {r.status_code}: {r.text[:500]}")
        data = r.json()
    parts = data.get("content", [])
    text_blocks = [p.get("text", "") for p in parts if p.get("type") == "text"]
    return "".join(text_blocks)


def _openai_call(
    *, model: str, system: Optional[str], prompt: str,
    max_tokens: int, temperature: float, timeout_s: float,
    json_mode: bool,
) -> str:
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    messages: List[Dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    body: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    with httpx.Client(timeout=timeout_s) as client:
        r = client.post("https://api.openai.com/v1/chat/completions",
                        headers=headers, json=body)
        if r.status_code >= 400:
            raise RuntimeError(f"OpenAI {r.status_code}: {r.text[:500]}")
        data = r.json()
    return data["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def call_llm_text(
    prompt: str,
    *,
    weight: str = "medium",          # heavy | medium | light
    system: Optional[str] = None,
    max_tokens: int = 4000,
    temperature: float = 0.0,
    timeout_s: float = 240.0,
    retries: int = 2,
    backoff_s: float = 2.0,
) -> str:
    """Returns the assistant's raw text. Use for free-form output."""
    last_err: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            if ANTHROPIC_API_KEY:
                model = {
                    "heavy": ANTHROPIC_MODEL_HEAVY,
                    "medium": ANTHROPIC_MODEL_MEDIUM,
                    "light": ANTHROPIC_MODEL_LIGHT,
                }.get(weight, ANTHROPIC_MODEL_MEDIUM)
                return _anthropic_call(
                    model=model, system=system, prompt=prompt,
                    max_tokens=max_tokens, temperature=temperature,
                    timeout_s=timeout_s,
                )
            elif OPENAI_API_KEY:
                return _openai_call(
                    model=OPENAI_MODEL_FALLBACK, system=system, prompt=prompt,
                    max_tokens=max_tokens, temperature=temperature,
                    timeout_s=timeout_s, json_mode=False,
                )
            else:
                raise RuntimeError("No LLM credentials available (set ANTHROPIC_API_KEY or OPENAI_API_KEY).")
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(backoff_s * (attempt + 1))
            else:
                raise
    raise RuntimeError(f"unreachable: {last_err}")


def call_llm_json(
    prompt: str,
    *,
    weight: str = "medium",
    system: Optional[str] = None,
    max_tokens: int = 4000,
    temperature: float = 0.0,
    timeout_s: float = 240.0,
    retries: int = 2,
) -> Dict[str, Any]:
    """Returns parsed JSON. Strips markdown fences if present.

    For Anthropic we append a JSON-only instruction; for OpenAI we use json_object mode.
    On parse failure, raises RuntimeError with a short excerpt of the bad output.
    """
    if ANTHROPIC_API_KEY:
        full_prompt = prompt + "\n\nRespond with a single JSON object only. No markdown, no prose, no code fences."
        text = call_llm_text(
            full_prompt, weight=weight, system=system,
            max_tokens=max_tokens, temperature=temperature,
            timeout_s=timeout_s, retries=retries,
        )
        text = _strip_md_fences(text)
    elif OPENAI_API_KEY:
        # Use json_object mode directly
        last_err: Optional[Exception] = None
        for attempt in range(retries + 1):
            try:
                text = _openai_call(
                    model=OPENAI_MODEL_FALLBACK, system=system, prompt=prompt,
                    max_tokens=max_tokens, temperature=temperature,
                    timeout_s=timeout_s, json_mode=True,
                )
                break
            except Exception as e:
                last_err = e
                if attempt < retries:
                    time.sleep(2.0 * (attempt + 1))
                else:
                    raise
    else:
        raise RuntimeError("No LLM credentials available.")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"LLM returned non-JSON: {e.msg} at pos {e.pos}. "
            f"Excerpt: {text[:300]!r}"
        )


def active_provider() -> str:
    if ANTHROPIC_API_KEY:
        return "anthropic"
    if OPENAI_API_KEY:
        return "openai"
    return "none"
