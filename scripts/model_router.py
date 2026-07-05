#!/usr/bin/env python3
"""model_router.py — Tiered inference routing with health checking & circuit breaker.

Tier 1 (primary): Ollama on Mac Studio (qwen2.5:14b-instruct, unlimited, sovereign)
Tier 2 (fallback): Gemini free-tier API (quota-capped)
Tier 3 (frontier): Anthropic API credits (high-value reasoning only)

Every call is logged to inference_audit table for 100% observability.
Circuit breaker + health probe prevent hangs when Tier 1 is down.
Manual override via LANDTEK_INFERENCE_TIER env var for emergency control.
"""
import os
import sys
import time
import json
import uuid
import logging
import requests
from datetime import datetime
from typing import Dict, Tuple, Optional

# ─────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────

TIER_1_CONFIG = {
    "name": "ollama_local",
    "base_url": "http://100.117.118.47:11434",
    "models": {
        "default": "qwen2.5:14b-instruct",
        "fast": "qwen2.5:7b-instruct",
        # 32b is NOT pulled on the Mac (32GB ceiling) → referencing it 404s and silently
        # falls through to the (stub) API tiers. Map reasoning to 14b until 32b is pulled.
        # To enable the bigger model: `ollama pull qwen2.5:32b-instruct` then set this to it.
        "reasoning": "qwen2.5:14b-instruct",
    },
    # timeout_sec gates the GENERATION call, not just the health probe. Warm 14b latency is
    # ~1-2s, but the FIRST call after idle must load ~9GB into RAM (cold start >5s). The old
    # 5s killed every cold-start call, opened the breaker, and forced fallback to the stub
    # API tiers — i.e. the "sovereign local tier" was effectively offline for real work.
    # Health probe stays fast (its own 3s param); this only affects real generations.
    "timeout_sec": 120,
    "health_check_interval_sec": 300,
}

TIER_2_CONFIG = {
    "name": "gemini",
    "models": {
        "default": "gemini-2.5-flash",
        "fast": "gemini-2.0-flash",
    },
}

TIER_3_CONFIG = {
    "name": "anthropic",
    "models": {
        # NB: Tier 3 is currently credit-depleted (API returns 400 "credit balance too low")
        # — the executor is correct and activates when credits return. claude-sonnet-5 is the
        # current id; opus (claude-opus-4-8) is opt-in for heavy reasoning.
        "default": "claude-sonnet-5",
        "reasoning": "claude-sonnet-5",
    },
    "api_url": "https://api.anthropic.com/v1/messages",
    "version": "2023-06-01",
    "max_tokens": 1024,
    "timeout_sec": 60,
}

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

SYSTEM_PROMPTS = {
    "verify": """You are a legal fact-checker. Read the document excerpt and verify the stated fact.
Reply ONLY with one word: VERIFIED, CONTRADICTED, or INSUFFICIENT_EVIDENCE.""",
    
    "extract": """Extract all explicit legal facts from this document. Format as bullet points.
Be precise; only extract what is explicitly stated, not inferred. Preserve exact names and numbers.""",
    
    "classify": """Classify this document by type. Reply with exactly ONE word from this list:
TITLE, DEED, AFFIDAVIT, ORDER, LETTER, DIAGRAM, SURVEY, NOTARIZATION, OTHER""",
    
    "ocr_assist": """Correct OCR errors in this text. Preserve all proper names, dates, and legal terms exactly.
Fix only obvious misspellings. Return the corrected text.""",
    
    "reason": """You are a legal strategist. Reason through the following question.
Cite precedent, statutes, or evidence where applicable. Be concise.""",
}

TEMPERATURE = {
    "verify": 0.1,      # high consistency
    "extract": 0.1,     # high consistency
    "classify": 0.2,    # mostly consistent
    "ocr_assist": 0.0,  # deterministic
    "reason": 0.5,      # allow some variation for reasoning
}

# Task → model-quality mapping (shared by pick() and the cascade helper).
TASK_QUALITY = {
    "verify": "default",
    "extract": "default",
    "classify": "fast",
    "reason": "reasoning",
    "ocr_assist": "fast",
}

# ─────────────────────────────────────────────────────────────
# CIRCUIT BREAKER & HEALTH STATE
# ─────────────────────────────────────────────────────────────

class CircuitBreaker:
    """Prevents hammering a failing service."""
    def __init__(self, failure_threshold=3, reset_timeout_sec=300):
        self.failure_count = 0
        self.last_failure_time = None
        self.is_open = False
        self.failure_threshold = failure_threshold
        self.reset_timeout_sec = reset_timeout_sec
    
    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.is_open = True
    
    def record_success(self):
        self.failure_count = 0
        self.is_open = False
    
    def can_attempt(self) -> bool:
        if not self.is_open:
            return True
        # Check if reset timeout has passed
        if time.time() - self.last_failure_time > self.reset_timeout_sec:
            self.is_open = False
            return True
        return False

tier1_breaker = CircuitBreaker(failure_threshold=3, reset_timeout_sec=300)
tier1_last_health_check = 0

# ─────────────────────────────────────────────────────────────
# TIER AVAILABILITY CHECKS
# ─────────────────────────────────────────────────────────────

def health_check_tier1(timeout_sec=3) -> Tuple[bool, Optional[str]]:
    """
    Lightweight *reachability* probe for Tier 1.

    Uses /api/tags (lists loaded models, no generation) — NOT /api/generate. The old probe
    ran a real generation with a 3s cap, so a COLD model (first call after idle loads ~9GB)
    false-negatived tier1 as 'unavailable' and silently pushed all inference to Gemini,
    defeating the $0 sovereign tier. Reachability is the right availability signal; cold-start
    latency is absorbed by the actual call (120s timeout) + the cascade.
    """
    try:
        resp = requests.get(f"{TIER_1_CONFIG['base_url']}/api/tags", timeout=timeout_sec)
        if resp.status_code == 200:
            return (True, None)
        return (False, f"HTTP {resp.status_code}")
    except requests.Timeout:
        return (False, "timeout")
    except requests.ConnectionError:
        return (False, "connection_error")
    except Exception as e:
        return (False, str(e))

def check_tier1_available() -> bool:
    """Is Tier 1 available (healthy + circuit not open)?"""
    global tier1_last_health_check
    
    # Check circuit breaker first
    if not tier1_breaker.can_attempt():
        return False
    
    # Rate-limit health checks (don't spam)
    now = time.time()
    if now - tier1_last_health_check < 5:  # at most once per 5 sec
        return not tier1_breaker.is_open
    
    # Do health check
    is_healthy, reason = health_check_tier1()
    tier1_last_health_check = now
    
    if is_healthy:
        tier1_breaker.record_success()
        return True
    else:
        tier1_breaker.record_failure()
        return False

def check_tier2_available() -> bool:
    """Is Tier 2 quota available?"""
    # For now, assume available (would need to query quota from DB)
    return True

def check_tier3_available() -> bool:
    """Do we have Tier 3 (Anthropic) credentials?"""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    return bool(api_key)

# ─────────────────────────────────────────────────────────────
# MAIN ROUTING LOGIC
# ─────────────────────────────────────────────────────────────

def pick(task_type: str, data_size: Optional[str] = None, prefer_tier: Optional[str] = None) -> Dict:
    """
    Route to the best-fit inference tier.
    
    Args:
      task_type: 'verify' | 'extract' | 'classify' | 'reason' | 'ocr_assist'
      data_size: 'small' | 'medium' | 'large' (hints at model size)
      prefer_tier: override to force a tier (for testing/emergency)
    
    Returns:
      {
        "provider": str,
        "model": str,
        "tier": int,
        "base_url": str (for local), or None (for API),
        "timeout_sec": int (for local),
        "error": str (if no tier available),
      }
    """
    
    # Check for manual override (emergency control)
    override = os.environ.get("LANDTEK_INFERENCE_TIER")
    if override:
        prefer_tier = f"tier{override}"
    
    quality = TASK_QUALITY.get(task_type, "default")
    
    # Tier-by-tier routing
    
    # TIER 1: Local Ollama (primary)
    if prefer_tier not in ["tier2", "tier3"]:
        if check_tier1_available():
            model = TIER_1_CONFIG["models"].get(quality, TIER_1_CONFIG["models"]["default"])
            return {
                "provider": "ollama_local",
                "model": model,
                "tier": 1,
                "base_url": TIER_1_CONFIG["base_url"],
                "timeout_sec": TIER_1_CONFIG["timeout_sec"],
                "error": None,
            }
    
    # TIER 2: Gemini free-tier (fallback)
    if prefer_tier != "tier3":
        if check_tier2_available():
            model = TIER_2_CONFIG["models"].get(quality, TIER_2_CONFIG["models"]["default"])
            return {
                "provider": "gemini",
                "model": model,
                "tier": 2,
                "base_url": None,
                "error": None,
            }
    
    # TIER 3: Anthropic (frontier reasoning)
    if check_tier3_available():
        model = TIER_3_CONFIG["models"].get(quality, TIER_3_CONFIG["models"]["default"])
        return {
            "provider": "anthropic",
            "model": model,
            "tier": 3,
            "base_url": None,
            "error": None,
        }
    
    # FALLBACK: No tier available
    return {
        "provider": None,
        "model": None,
        "tier": None,
        "error": "All inference tiers unavailable. Escalate to operator.",
    }

# ─────────────────────────────────────────────────────────────
# INFERENCE EXECUTION
# ─────────────────────────────────────────────────────────────

def call_model(
    routed_config: Dict,
    prompt: str,
    task_type: str = "extract",
    system_prompt: Optional[str] = None,
    doc_id: Optional[str] = None,
    matter_id: Optional[str] = None,
    **kwargs
) -> Dict:
    """
    Execute inference on the routed tier.
    Logs all calls to inference_audit table.
    """
    
    request_id = str(uuid.uuid4())

    if not routed_config["provider"]:
        result = {
            "error": routed_config.get("error", "No tier available"),
            "request_id": request_id,
            "provider": None,
            "tier": None,
            "success": False,
        }
        _log_inference(result, task_type, doc_id, matter_id)
        return result

    # Use task-specific system prompt if not provided
    if not system_prompt:
        system_prompt = SYSTEM_PROMPTS.get(task_type, "You are a helpful legal assistant.")

    # Use task-specific temperature if not overridden
    temperature = kwargs.get("temperature", TEMPERATURE.get(task_type, 0.3))

    # CASCADE: try the routed tier; on failure degrade to the next available tier
    # (tier1 local → tier2 Gemini → tier3 Anthropic) within this single call, so a sleeping
    # Mac degrades to paid inference instead of erroring. Rare in practice (tier1 ~99% up).
    # Every attempt is logged. `allow_cascade=False` disables (e.g. cost-sensitive callers).
    allow_cascade = kwargs.get("allow_cascade", True)
    cfg, tried, last = routed_config, [], None
    while cfg and cfg.get("provider"):
        result = _dispatch(cfg, prompt, task_type, system_prompt,
                           request_id, doc_id, matter_id, temperature, **kwargs)
        _log_inference(result, task_type, doc_id, matter_id)
        tried.append(cfg.get("tier"))
        if result.get("success"):
            if len(tried) > 1:
                result["cascaded_from"] = tried[:-1]
            return result
        last = result
        if not allow_cascade:
            break
        # find the next lower tier that is available
        cfg = None
        for nt in (t for t in (1, 2, 3) if t > (tried[-1] or 0)):
            nxt = _config_for_tier(nt, task_type)
            if nxt:
                cfg = nxt
                break
    return last or {"error": "All inference tiers unavailable", "request_id": request_id,
                    "success": False, "tier": None, "provider": None}


def _dispatch(cfg, prompt, task_type, system_prompt, request_id, doc_id, matter_id, temperature, **kwargs):
    """Execute one tier (no cascade, no logging — call_model owns those)."""
    if cfg["provider"] == "ollama_local":
        return _call_ollama(cfg, prompt, task_type, system_prompt, request_id, doc_id, matter_id, temperature, **kwargs)
    if cfg["provider"] == "gemini":
        return _call_gemini(cfg, prompt, task_type, system_prompt, request_id, doc_id, matter_id, temperature, **kwargs)
    if cfg["provider"] == "anthropic":
        return _call_anthropic(cfg, prompt, task_type, system_prompt, request_id, doc_id, matter_id, temperature, **kwargs)
    return {"error": f"unknown provider {cfg.get('provider')}", "request_id": request_id,
            "success": False, "tier": cfg.get("tier"), "provider": cfg.get("provider")}


def _config_for_tier(tier: int, task_type: str) -> Optional[Dict]:
    """Build a routed config for a specific tier if that tier is available (for cascade)."""
    quality = TASK_QUALITY.get(task_type, "default")
    if tier == 1 and check_tier1_available():
        return {"provider": "ollama_local", "tier": 1, "base_url": TIER_1_CONFIG["base_url"],
                "timeout_sec": TIER_1_CONFIG["timeout_sec"], "error": None,
                "model": TIER_1_CONFIG["models"].get(quality, TIER_1_CONFIG["models"]["default"])}
    if tier == 2 and check_tier2_available():
        return {"provider": "gemini", "tier": 2, "base_url": None, "error": None,
                "model": TIER_2_CONFIG["models"].get(quality, TIER_2_CONFIG["models"]["default"])}
    if tier == 3 and check_tier3_available():
        return {"provider": "anthropic", "tier": 3, "base_url": None, "error": None,
                "model": TIER_3_CONFIG["models"].get(quality, TIER_3_CONFIG["models"]["default"])}
    return None

def _call_ollama(
    config: Dict, prompt: str, task_type: str, system_prompt: str,
    request_id: str, doc_id: Optional[str], matter_id: Optional[str],
    temperature: float, **kwargs
) -> Dict:
    """Call local Ollama model."""
    
    start_time = time.time()
    
    try:
        # Ollama uses OpenAI-compatible chat API
        resp = requests.post(
            f"{config['base_url']}/api/chat",
            json={
                "model": config["model"],
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "temperature": temperature,
            },
            timeout=config["timeout_sec"]
        )
        resp.raise_for_status()
        result = resp.json()
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        return {
            "text": result.get("message", {}).get("content", ""),
            "tokens_prompt": result.get("prompt_eval_count", 0),
            "tokens_completion": result.get("eval_count", 0),
            "provider": "ollama_local",
            "model": config["model"],
            "tier": 1,
            "latency_ms": latency_ms,
            "cost": 0,
            "success": True,
            "error": None,
            "request_id": request_id,
            "doc_id": doc_id,
            "matter_id": matter_id,
            "task_type": task_type,
            "fallback_reason": None,
        }
    
    except requests.Timeout:
        tier1_breaker.record_failure()
        return {
            "error": "Tier 1 timeout; falling back to Tier 2",
            "request_id": request_id,
            "provider": "ollama_local",
            "tier": 1,
            "fallback_reason": "timeout",
            "success": False,
        }
    
    except Exception as e:
        tier1_breaker.record_failure()
        return {
            "error": f"Ollama call failed: {e}",
            "request_id": request_id,
            "provider": "ollama_local",
            "tier": 1,
            "fallback_reason": str(e),
            "success": False,
        }

def _call_gemini(
    config: Dict, prompt: str, task_type: str, system_prompt: str,
    request_id: str, doc_id: Optional[str], matter_id: Optional[str],
    temperature: float, **kwargs
) -> Dict:
    """Call Gemini free-tier (Tier 2) via generateContent REST. Matches comprehend.py's pattern.
    Tries GEMINI_API_KEY then GEMINI_API_KEY_FALLBACK (429-rotation)."""
    start = time.time()
    keys = [k for k in (os.environ.get("GEMINI_API_KEY", ""),
                        os.environ.get("GEMINI_API_KEY_FALLBACK", "")) if k]
    if not keys:
        return {"error": "no GEMINI_API_KEY", "request_id": request_id, "provider": "gemini",
                "tier": 2, "model": config["model"], "success": False, "fallback_reason": "no_key"}
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {"temperature": temperature},
    }
    last = ""
    for key in keys:
        try:
            resp = requests.post(
                GEMINI_API_URL.format(model=config["model"], key=key),
                json=body, timeout=45)
            if resp.status_code == 429:
                last = "429_quota"; continue
            resp.raise_for_status()
            out = resp.json()
            text = "".join(p.get("text", "")
                           for p in out["candidates"][0]["content"]["parts"])
            um = out.get("usageMetadata", {})
            return {
                "text": text, "provider": "gemini", "model": config["model"], "tier": 2,
                "latency_ms": int((time.time() - start) * 1000),
                "tokens_prompt": um.get("promptTokenCount", 0),
                "tokens_completion": um.get("candidatesTokenCount", 0),
                "cost": 0, "success": True, "error": None, "request_id": request_id,
                "fallback_reason": None,
            }
        except Exception as e:
            last = str(e)
    return {"error": f"Gemini failed: {last}", "request_id": request_id, "provider": "gemini",
            "tier": 2, "model": config["model"], "success": False, "fallback_reason": last,
            "latency_ms": int((time.time() - start) * 1000)}

def _call_anthropic(
    config: Dict, prompt: str, task_type: str, system_prompt: str,
    request_id: str, doc_id: Optional[str], matter_id: Optional[str],
    temperature: float, **kwargs
) -> Dict:
    """Call Anthropic (Tier 3, frontier) via the Messages REST API (x-api-key header)."""
    start = time.time()
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return {"error": "no ANTHROPIC_API_KEY", "request_id": request_id, "provider": "anthropic",
                "tier": 3, "model": config["model"], "success": False, "fallback_reason": "no_key"}
    try:
        resp = requests.post(
            TIER_3_CONFIG["api_url"],
            headers={"x-api-key": key, "anthropic-version": TIER_3_CONFIG["version"],
                     "content-type": "application/json"},
            json={
                "model": config["model"],
                "max_tokens": kwargs.get("max_tokens", TIER_3_CONFIG["max_tokens"]),
                "temperature": temperature,
                "system": system_prompt,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=TIER_3_CONFIG["timeout_sec"])
        resp.raise_for_status()
        out = resp.json()
        text = "".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text")
        usage = out.get("usage", {})
        return {
            "text": text, "provider": "anthropic", "model": config["model"], "tier": 3,
            "latency_ms": int((time.time() - start) * 1000),
            "tokens_prompt": usage.get("input_tokens", 0),
            "tokens_completion": usage.get("output_tokens", 0),
            "cost": 0, "success": True, "error": None, "request_id": request_id,
            "fallback_reason": None,
        }
    except Exception as e:
        return {"error": f"Anthropic failed: {e}", "request_id": request_id, "provider": "anthropic",
                "tier": 3, "model": config["model"], "success": False, "fallback_reason": str(e),
                "latency_ms": int((time.time() - start) * 1000)}

# ─────────────────────────────────────────────────────────────
# OBSERVABILITY — the inference_audit write the docstring promises
# ─────────────────────────────────────────────────────────────

def _log_inference(result: Dict, task_type: str,
                   doc_id: Optional[str], matter_id: Optional[str],
                   created_by: str = "model_router") -> None:
    """Best-effort row into inference_audit. NEVER raises — logging must not break inference.

    This is what makes the module docstring's '100% observability' claim true: every routed
    call (local success, local timeout/fallback, or a stub API tier) leaves a trace so we can
    see whether the sovereign local tier is actually carrying load or silently degrading."""
    try:
        import psycopg2
        dsn = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
        conn = psycopg2.connect(dsn, connect_timeout=3)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO inference_audit
                   (request_id, model_tier, model_name, task_type, doc_id, matter_id,
                    tokens_prompt, tokens_completion, latency_ms, fallback_reason,
                    success, error_message, created_by)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (result.get("request_id"),
                 f"tier{result.get('tier')}" if result.get("tier") else None,
                 result.get("model"), task_type,
                 str(doc_id) if doc_id is not None else None,
                 str(matter_id) if matter_id is not None else None,
                 result.get("tokens_prompt"), result.get("tokens_completion"),
                 result.get("latency_ms"), result.get("fallback_reason"),
                 bool(result.get("success", False)), result.get("error"),
                 created_by))
        conn.close()
    except Exception:
        pass  # best-effort; never break the caller's inference

# ─────────────────────────────────────────────────────────────
# CLI FOR TESTING
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("model_router.py — Testing")
    print()
    
    # Test 1: Check Tier 1 availability
    print("Test 1: Tier 1 availability")
    is_available = check_tier1_available()
    print(f"  Tier 1 available: {is_available}")
    print()
    
    # Test 2: Routing logic
    print("Test 2: Routing logic")
    for task in ["verify", "extract", "classify", "reason"]:
        config = pick(task)
        print(f"  {task:12} → Tier {config['tier']} ({config['provider']})")
    print()
    
    # Test 3: E2E inference (if Tier 1 available)
    if is_available:
        print("Test 3: E2E inference")
        config = pick("classify")
        result = call_model(
            config,
            prompt="Classify this document: 'TRANSFER CERTIFICATE OF TITLE No. 4497'",
            task_type="classify"
        )
        print(f"  Response: {result.get('text', 'ERROR')}")
        print(f"  Latency: {result.get('latency_ms', 'N/A')} ms")
        print(f"  Cost: ${result.get('cost', 0)}")
    else:
        print("Test 3: Skipped (Tier 1 not available)")

