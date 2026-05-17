#!/usr/bin/env python3
"""LLM billing wrapper — instruments every Anthropic + Gemini call.

Drop-in helpers that:
  • make the API call
  • capture token counts from the vendor response
  • compute cost in USD from the model pricing table
  • write a row to llm_calls
  • return the original response unchanged

Usage:
    from llm_billing import anthropic_call, gemini_call

    resp = anthropic_call(
        client, model="claude-sonnet-4-6", max_tokens=400,
        system=SYS, messages=MSGS,
        called_from="truth_negotiator",
        purpose="challenger",
        case_file="MWK-001",
    )
    text = resp.content[0].text

Price table reflects published rates as of Jan 2026. Update PRICES when vendors change.
"""
import hashlib
import json
import time
import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# Prices in USD per 1M tokens (input, output). Cached input priced ~10% of input for Claude.
PRICES = {
    # Anthropic
    "claude-opus-4-7":                 (15.00, 75.00, 1.50),
    "claude-sonnet-4-6":               ( 3.00, 15.00, 0.30),
    "claude-haiku-4-5-20251001":       ( 0.80,  4.00, 0.08),
    "claude-haiku-4-5":                ( 0.80,  4.00, 0.08),
    # Google Gemini
    "gemini-2.5-flash":                ( 0.075, 0.30, 0.0075),
    "gemini-2.5-flash-lite":           ( 0.038, 0.15, 0.0038),
    "gemini-2.5-pro":                  ( 1.25,  5.00, 0.125),
    "gemini-2.0-flash":                ( 0.10,  0.40, 0.01),
}

def _price(model: str):
    """Return (in_per_M, out_per_M, cached_per_M) for the model, or (0,0,0) if unknown."""
    # Try exact match first, then strip date suffix
    if model in PRICES:
        return PRICES[model]
    # strip -YYYYMMDD suffix
    base = model.rsplit("-", 1)[0]
    return PRICES.get(base, (0, 0, 0))

def _cost(model: str, in_tok: int, out_tok: int, cached_tok: int = 0,
          cache_write_tok: int = 0, ttl_1h: bool = False) -> float:
    """Compute cost. Anthropic cache writes cost 1.25× input rate (5-min ephemeral)
    or 2× input rate (1h ephemeral); reads cost 10% of input rate regardless."""
    in_per_M, out_per_M, cached_per_M = _price(model)
    # 5-min ephemeral: 1.25×, 1h ephemeral: 2×
    cache_write_per_M = in_per_M * (2.0 if ttl_1h else 1.25)
    return (in_tok * in_per_M
            + out_tok * out_per_M
            + cached_tok * cached_per_M
            + cache_write_tok * cache_write_per_M) / 1_000_000

def _hash_prompt(system, messages) -> str:
    """sha256 of system+messages for dedup analysis. Truncated to 16 chars.

    system may be a plain string OR a list of content blocks (when using prompt caching).
    """
    h = hashlib.sha256()
    if isinstance(system, str):
        h.update((system or "").encode("utf-8", "ignore"))
    elif isinstance(system, list):
        # System content blocks (prompt caching form)
        for blk in system:
            text = blk.get("text", "") if isinstance(blk, dict) else str(blk)
            h.update(text.encode("utf-8", "ignore"))
    if isinstance(messages, list):
        for m in messages:
            content = m.get("content", "") if isinstance(m, dict) else str(m)
            if isinstance(content, list):
                content = json.dumps(content)
            h.update(str(content).encode("utf-8", "ignore"))
    return h.hexdigest()[:16]

def _log_call(vendor, model, called_from, purpose, in_tok, cached_tok, out_tok,
              cost_usd, duration_ms, success, prompt_hash, metadata, case_file):
    try:
        conn = psycopg2.connect(DSN); conn.autocommit = True
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO llm_calls
              (vendor, model, called_from, purpose, input_tokens, cached_input_tokens,
               output_tokens, cost_usd, duration_ms, success, prompt_hash, call_metadata, case_file)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
        """, (vendor, model, called_from, purpose, in_tok, cached_tok, out_tok,
              cost_usd, duration_ms, success, prompt_hash,
              json.dumps(metadata) if metadata else None, case_file))
        cur.close(); conn.close()
    except Exception as e:
        # Never let billing failure break the actual call. Just stderr.
        import sys
        print(f"[llm_billing] log write failed: {e}", file=sys.stderr)


def anthropic_call(client, *, called_from, purpose=None, case_file=None, **kwargs):
    """Wrapper for anthropic.Anthropic().messages.create().

    Pass all the same kwargs as `client.messages.create()`. Returns the same Message object.
    Logs the call to llm_calls.
    """
    t0 = time.time()
    model = kwargs.get("model", "unknown")
    system_text = kwargs.get("system", "")
    messages = kwargs.get("messages", [])
    prompt_hash = _hash_prompt(system_text, messages)
    success = True
    in_tok = out_tok = cached_tok = 0
    metadata = {}
    try:
        resp = client.messages.create(**kwargs)
        usage = getattr(resp, "usage", None)
        if usage:
            in_tok = getattr(usage, "input_tokens", 0) or 0
            out_tok = getattr(usage, "output_tokens", 0) or 0
            cached_tok = getattr(usage, "cache_read_input_tokens", 0) or 0
            cache_creation_tok = getattr(usage, "cache_creation_input_tokens", 0) or 0
            if cache_creation_tok:
                metadata["cache_creation_input_tokens"] = cache_creation_tok
            metadata["_cache_write_tok"] = cache_creation_tok  # passed to _cost in finally
        return resp
    except Exception as e:
        success = False
        metadata["error"] = str(e)[:200]
        raise
    finally:
        duration_ms = int((time.time() - t0) * 1000)
        cache_write_tok = metadata.pop("_cache_write_tok", 0) if metadata else 0
        # Detect 1h TTL caching from system prompt (passed in kwargs)
        system = kwargs.get("system")
        ttl_1h = False
        if isinstance(system, list):
            for blk in system:
                if isinstance(blk, dict):
                    cc = blk.get("cache_control") or {}
                    if cc.get("ttl") == "1h":
                        ttl_1h = True
                        break
        cost = _cost(model, in_tok, out_tok, cached_tok, cache_write_tok, ttl_1h=ttl_1h)
        _log_call("anthropic", model, called_from, purpose,
                  in_tok, cached_tok, out_tok, cost, duration_ms, success,
                  prompt_hash, metadata or None, case_file)


def gemini_call(model_obj, *, called_from, purpose=None, case_file=None,
                model_name=None, contents=None, **kwargs):
    """Wrapper for google.genai's model.generate_content().

    Pass `model_obj` (the GenerativeModel instance), `model_name` for cost lookup,
    plus the standard contents/kwargs.
    """
    t0 = time.time()
    model = model_name or getattr(model_obj, "model_name", "gemini-2.5-flash")
    prompt_hash = _hash_prompt("", contents if isinstance(contents, list) else [{"content": str(contents)}])
    success = True
    in_tok = out_tok = 0
    metadata = {}
    try:
        resp = model_obj.generate_content(contents, **kwargs)
        # google.genai returns usage_metadata
        usage = getattr(resp, "usage_metadata", None)
        if usage:
            in_tok = getattr(usage, "prompt_token_count", 0) or 0
            out_tok = getattr(usage, "candidates_token_count", 0) or 0
            cached = getattr(usage, "cached_content_token_count", 0) or 0
            if cached:
                metadata["cached_tokens"] = cached
        return resp
    except Exception as e:
        success = False
        metadata["error"] = str(e)[:200]
        raise
    finally:
        duration_ms = int((time.time() - t0) * 1000)
        cost = _cost(model, in_tok, out_tok)
        _log_call("gemini", model, called_from, purpose,
                  in_tok, 0, out_tok, cost, duration_ms, success,
                  prompt_hash, metadata or None, case_file)


def anthropic_tool_call(client, *, tool_name: str, input_schema: dict,
                        called_from: str, purpose: str = None, case_file: str = None,
                        tool_description: str = None, **kwargs):
    """Programmatic tool-calling variant — forces the model to emit STRUCTURED
    output via Anthropic's tool-use API. No regex/JSON parsing needed.

    Returns the validated `block.input` dict from the tool_use block.

    Benefits over plain text+json.loads:
      • Anthropic validates the schema server-side
      • No code-fence / "Extra data" / silent json.loads failures
      • Forces compliance via tool_choice={'type':'tool','name':tool_name}
      • cache_control on system prompt still works
      • Cleaner caller code (~10 lines saved per script)

    Usage:
        result = anthropic_tool_call(
            client,
            tool_name="submit_party_classification",
            input_schema={
                "type": "object",
                "properties": {
                    "party": {"type": "string", "enum": ["plaintiff","respondent","court","agency","third_party"]},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "reason": {"type": "string"},
                },
                "required": ["party","confidence","reason"]
            },
            called_from="party_filing_disambiguator",
            purpose="disambiguate_party",
            case_file="MWK-001",
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=PROMPT,
            messages=[{"role":"user", "content": ...}],
        )
        # result is already a dict: {"party": "plaintiff", "confidence": 0.92, "reason": "..."}
    """
    tools = [{
        "name": tool_name,
        "description": tool_description or f"Submit the {tool_name} result with the structured schema fields.",
        "input_schema": input_schema,
    }]
    kwargs["tools"] = tools
    kwargs["tool_choice"] = {"type": "tool", "name": tool_name}
    resp = anthropic_call(client,
                          called_from=called_from,
                          purpose=purpose,
                          case_file=case_file,
                          **kwargs)
    for block in resp.content:
        if hasattr(block, "type") and block.type == "tool_use" and block.name == tool_name:
            return block.input  # already a validated dict
    raise RuntimeError(
        f"anthropic_tool_call({tool_name}): no tool_use block in response — "
        f"got types {[getattr(b,'type',None) for b in resp.content]}"
    )


# Convenience: get today's running total
def today_total_usd() -> float:
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(SUM(cost_usd),0) FROM llm_calls WHERE called_at >= date_trunc('day', NOW())")
    total = float(cur.fetchone()[0])
    cur.close(); conn.close()
    return total


if __name__ == "__main__":
    # Smoke test: just print today's total
    print(f"Today's LLM spend: ${today_total_usd():.4f}")
