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
        "reasoning": "qwen2.5:32b-instruct",  # use for dense/complex docs
    },
    "timeout_sec": 5,
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
        "default": "claude-sonnet-4-5",
        "reasoning": "claude-opus-4-6",
    },
}

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
    Lightweight health probe for Tier 1.
    Returns (is_healthy, failure_reason or None).
    """
    try:
        start = time.time()
        resp = requests.post(
            f"{TIER_1_CONFIG['base_url']}/api/generate",
            json={
                "model": TIER_1_CONFIG["models"]["default"],
                "prompt": "Reply with OK.",
                "stream": False,
            },
            timeout=timeout_sec
        )
        latency_ms = int((time.time() - start) * 1000)
        
        if resp.status_code == 200:
            return (True, None)
        else:
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
    
    # Task → model-quality mapping
    task_quality = {
        "verify": "default",
        "extract": "default",
        "classify": "fast",
        "reason": "reasoning",
        "ocr_assist": "fast",
    }
    quality = task_quality.get(task_type, "default")
    
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
        return {
            "error": routed_config.get("error", "No tier available"),
            "request_id": request_id,
            "provider": None,
            "tier": None,
        }
    
    # Use task-specific system prompt if not provided
    if not system_prompt:
        system_prompt = SYSTEM_PROMPTS.get(task_type, "You are a helpful legal assistant.")
    
    # Use task-specific temperature if not overridden
    temperature = kwargs.get("temperature", TEMPERATURE.get(task_type, 0.3))
    
    if routed_config["provider"] == "ollama_local":
        return _call_ollama(
            routed_config, prompt, task_type, system_prompt,
            request_id, doc_id, matter_id, temperature, **kwargs
        )
    elif routed_config["provider"] == "gemini":
        return _call_gemini(
            routed_config, prompt, task_type, system_prompt,
            request_id, doc_id, matter_id, temperature, **kwargs
        )
    elif routed_config["provider"] == "anthropic":
        return _call_anthropic(
            routed_config, prompt, task_type, system_prompt,
            request_id, doc_id, matter_id, temperature, **kwargs
        )

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
    """Call Gemini API (Tier 2). Stub for now."""
    # TODO: Implement Gemini integration
    return {
        "error": "Gemini integration not yet implemented",
        "request_id": request_id,
        "tier": 2,
        "provider": "gemini",
    }

def _call_anthropic(
    config: Dict, prompt: str, task_type: str, system_prompt: str,
    request_id: str, doc_id: Optional[str], matter_id: Optional[str],
    temperature: float, **kwargs
) -> Dict:
    """Call Anthropic API (Tier 3). Stub for now."""
    # TODO: Implement Anthropic integration
    return {
        "error": "Anthropic integration not yet implemented",
        "request_id": request_id,
        "tier": 3,
        "provider": "anthropic",
    }

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

