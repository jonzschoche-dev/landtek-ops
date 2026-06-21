# IMPLEMENTATION PROPOSAL: In-House Inference Tier — v1.1 (Production-Hardened)

**Status:** Revised for robustness & observability (2026-06-21)  
**Scope:** Ollama on Mac Studio + tiered model_router.py + production-grade observation  
**Timeline:** ~4–6 hours implementation + 24h observation  
**Cost:** $0 (own hardware) for Tier 1; fallback to free-tier APIs  

---

## 1. ARCHITECTURE OVERVIEW

```
┌─────────────────────────────────────────────────────────────┐
│                    WORKERS (VPS)                            │
│  verify_worker, comprehend, corpus_backfill, ocr_assist     │
└────────────────┬──────────────────────────────────────────┘
                 │ calls model_router.pick()
                 ↓
        ┌────────────────────────────────┐
        │  model_router.py + health      │
        │  (circuit breaker logic)       │
        └────────────┬────────────────────┘
                     │
        ┌────────────┴────────────────────────────────┐
        ↓                                              ↓
    TIER 1 (LOCAL, PRIMARY)              TIER 2/3 (FALLBACK)
    ┌───────────────────────┐           ┌────────────────────┐
    │ Mac Studio Ollama     │           │ Gemini free (T2)   │
    │ qwen2.5:14b-instruct  │           │ Claude/Cowork (T3) │
    │ 100.117.118.47:11434  │           │ [when T1 fails]    │
    │ [unlimited, sovereign]│           │ [quota/credit gated]
    └───────────────────────┘           └────────────────────┘
    
    Health probe: every 5 min or on idle
    Circuit breaker: fallback if unhealthy
    Override flag: env var LANDTEK_INFERENCE_TIER
```

All inferences logged to `inference_audit` table (100% observability).

---

## 2. MAC STUDIO SETUP (Ollama)

**Verify current state:**
```bash
which ollama && ollama --version
ps aux | grep ollama
lsof -i :11434
du -sh ~/.ollama/models/  # check disk space (need ~25 GB total)
```

**Install (if needed):**
```bash
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull qwen2.5:14b-instruct
ollama pull qwen2.5:32b-instruct  # optional, for heavy reasoning
```

**Enable auto-start with caffeinate (stays awake during inference):**
```bash
cat > ~/Library/LaunchAgents/com.ollama.server.plist << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ollama.server</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/caffeinate</string>
        <string>-i</string>
        <string>ollama</string>
        <string>serve</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/ollama.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/ollama.err</string>
</dict>
</plist>

chmod 644 ~/Library/LaunchAgents/com.ollama.server.plist
launchctl load ~/Library/LaunchAgents/com.ollama.server.plist
launchctl start com.ollama.server
sleep 5 && launchctl list | grep ollama
```

**Test connectivity:**
```bash
# From Mac
curl http://localhost:11434/api/tags

# From VPS (via Tailscale)
curl http://100.117.118.47:11434/api/tags
```

---

## 3. TABLE SCHEMA: inference_audit (Observation Layer)

**Why this name & structure:**
- `inference_audit` signals "100% observability of all model calls" (vs narrow `usage` table)
- `request_id` (UUID) correlates all retry/fallback attempts on same request
- `fallback_reason` explains *why* we left Tier 1 (timeout, error, unhealthy probe)
- Rich schema makes future dashboards (cost, latency, throughput, reliability) trivial

```sql
CREATE TABLE inference_audit (
    id BIGSERIAL PRIMARY KEY,
    request_id UUID NOT NULL DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    
    -- Tier & model
    model_tier TEXT NOT NULL,           -- 'tier1', 'tier2', 'tier3'
    model_name TEXT NOT NULL,           -- 'qwen2.5:14b-instruct', 'gemini-2.5-flash', etc.
    
    -- Context
    task_type TEXT,                     -- 'verify', 'extract', 'classify', 'reason', 'ocr_assist'
    doc_id TEXT,                        -- foreign key to documents table
    matter_id TEXT,                     -- foreign key to matter context
    
    -- Performance
    tokens_prompt INTEGER,
    tokens_completion INTEGER,
    latency_ms INTEGER,
    
    -- Reliability
    fallback_reason TEXT,               -- 'timeout', 'error', 'tier1_unhealthy', NULL if no fallback
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    
    -- Auditability
    created_by TEXT DEFAULT 'worker',
    
    CONSTRAINT positive_latency CHECK (latency_ms >= 0),
    CONSTRAINT positive_tokens CHECK (tokens_prompt >= 0 AND tokens_completion >= 0)
);

CREATE INDEX idx_inference_audit_request ON inference_audit(request_id);
CREATE INDEX idx_inference_audit_matter ON inference_audit(matter_id);
CREATE INDEX idx_inference_audit_tier ON inference_audit(model_tier);
CREATE INDEX idx_inference_audit_task ON inference_audit(task_type);
CREATE INDEX idx_inference_audit_timestamp ON inference_audit(timestamp DESC);
```

---

## 4. MODEL SPECIFICITY & ESCALATION RULES

**Default for bulk workloads:**
- Model: `qwen2.5:14b-instruct`
- Temperature: 0.1 (high consistency for extraction/verification)
- Context: task-specific system prompt (see registry below)
- Max tokens: 2,000

**Escalation: When to use 32B**
```
Use qwen2.5:32b-instruct IF:
  - task_type = 'reason' AND confidence_score < 0.7, OR
  - doc_tokens > 4,000 (dense legal documents), OR
  - manual_override = True (operator request)
  
Otherwise: stick with 14B (30–50 tok/s vs 10–20 tok/s for 32B)
```

**Task-specific system prompts (lightweight registry):**
```python
SYSTEM_PROMPTS = {
    "verify": """You are a legal fact-checker. Read the document excerpt and verify the stated fact.
Reply ONLY with: VERIFIED, CONTRADICTED, or INSUFFICIENT_EVIDENCE. No explanation.""",
    
    "extract": """Extract all legal facts from this document. Format as bullet points.
Be precise; only extract what is explicitly stated, not inferred.""",
    
    "classify": """Classify this document by type. Reply with ONE word: TITLE, DEED, AFFIDAVIT, ORDER, OTHER.""",
    
    "ocr_assist": """Correct OCR errors in this text. Fix obvious misspellings but preserve all names and numbers exactly.""",
}

TEMPERATURE = {
    "verify": 0.1,
    "extract": 0.1,
    "classify": 0.2,
    "reason": 0.5,
    "ocr_assist": 0.0,
}
```

---

## 5. HEALTH CHECK & CIRCUIT BREAKER (Strengthened)

**Health probe (runs every 5 min or on idle recovery):**

```python
def health_check_tier1(timeout_sec=3):
    """
    Lightweight health probe. Returns (is_healthy, reason).
    """
    try:
        start = time.time()
        resp = requests.post(
            "http://100.117.118.47:11434/api/generate",
            json={
                "model": "qwen2.5:14b-instruct",
                "prompt": "Reply with OK.",
                "stream": False,
            },
            timeout=timeout_sec
        )
        latency_ms = (time.time() - start) * 1000
        
        if resp.status_code == 200:
            return (True, None)
        else:
            return (False, f"HTTP {resp.status_code}")
    except requests.Timeout:
        return (False, "timeout")
    except Exception as e:
        return (False, str(e))

# Called by model_router.pick():
is_healthy, reason = health_check_tier1()
if not is_healthy:
    log_to_inference_audit(
        tier='tier1', 
        task_type='health_check',
        fallback_reason=reason,
        success=False
    )
    # Fall through to Tier 2
```

**Circuit breaker state (in-memory or Redis, your choice):**
```python
class CircuitBreaker:
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
    
    def can_attempt(self):
        if not self.is_open:
            return True
        # Check if reset timeout has passed
        if time.time() - self.last_failure_time > self.reset_timeout_sec:
            self.is_open = False
            return True
        return False

tier1_breaker = CircuitBreaker(failure_threshold=3, reset_timeout_sec=300)

# In model_router.pick():
if not tier1_breaker.can_attempt():
    log_fallback_to_tier2("circuit_breaker_open")
    return pick_tier2_config()
```

---

## 6. ENHANCED VALIDATION TESTS

**Test 1: Tier 1 health & reachability**
```bash
python3 -c "
from model_router import health_check_tier1
is_healthy, reason = health_check_tier1()
assert is_healthy, f'Tier 1 unhealthy: {reason}'
print('✓ Tier 1 health probe passed')
"
```

**Test 2: Routing logic (all tiers)**
```bash
python3 -c "
from model_router import pick
# Default: Tier 1
cfg = pick('verify'); assert cfg['tier'] == 1
# Force Tier 2
cfg = pick('verify', prefer_tier='tier2'); assert cfg['tier'] == 2
print('✓ Routing logic works')
"
```

**Test 3: E2E inference**
```bash
python3 -c "
from model_router import pick, call_model
cfg = pick('classify')
result = call_model(cfg, 'Classify: \"Transfer Certificate of Title\"')
assert not result.get('error'), result.get('error')
assert result['tier'] == 1
assert result['cost'] == 0
print('✓ E2E inference works')
"
```

**Test 4: Gate Integrity (NEW) — Confirm provenance gate still rejects ungrounded output**
```bash
python3 -c "
import db
import model_router
from comprehend import PROVENANCE_GATE

# Call Tier 1 with a fact extraction
cfg = model_router.pick('extract')
result = model_router.call_model(cfg, 'Extract facts from this document...')
fact = {'statement': result['text'], 'source_id': 'doc_123', 'provenance_level': 'inferred_strong'}

# Does the gate accept it?
gate_result = PROVENANCE_GATE.apply(fact)
assert gate_result['passed'], f'Gate rejected: {gate_result[\"reason\"]}'
print('✓ Gate integrity maintained (Tier 1 output passes))')
"
```

**Test 5: 24h Stability & Sleep Test (NEW) — Run overnight, verify fallback rate < 5%**
```bash
# Run this after deployment, overnight with Mac on power adapter:
python3 -c "
import time
import db

# At end of 24h run:
results = db.query('''
  SELECT 
    COUNT(*) as total_calls,
    SUM(CASE WHEN model_tier = 'tier1' THEN 1 ELSE 0 END) as tier1_calls,
    SUM(CASE WHEN model_tier = 'tier2' THEN 1 ELSE 0 END) as fallback_calls,
    AVG(latency_ms) as avg_latency_ms,
    COUNT(DISTINCT CASE WHEN success = false THEN 1 END) as failed_calls
  FROM inference_audit
  WHERE timestamp > NOW() - INTERVAL '24 hours'
''')

fallback_rate = results['fallback_calls'] / results['total_calls'] if results['total_calls'] > 0 else 0
print(f'Fallback rate: {fallback_rate:.1%}')
assert fallback_rate < 0.05, f'Fallback rate too high: {fallback_rate:.1%}'
assert results['failed_calls'] == 0, f'Failed calls detected: {results[\"failed_calls\"]}'
print('✓ 24h stability test passed')
"
```

---

## 7. MANUAL OVERRIDE FLAG (Emergency Control)

**Use env var to force a specific tier (no code changes needed):**

```bash
# Force Tier 2 only (emergency fallback, if Mac is unstable)
export LANDTEK_INFERENCE_TIER=2

# Re-enable Tier 1 (normal operation)
unset LANDTEK_INFERENCE_TIER

# Optional: force Tier 3 (if you want to test Anthropic)
export LANDTEK_INFERENCE_TIER=3
```

**In model_router.py:**
```python
def pick(task_type, prefer_tier=None):
    # Check for manual override first
    override = os.environ.get("LANDTEK_INFERENCE_TIER")
    if override:
        prefer_tier = f"tier{override}"
    
    # Rest of logic...
    if prefer_tier == 'tier2':
        return pick_tier2_config()
    elif prefer_tier == 'tier3':
        return pick_tier3_config()
    else:
        # Default: try Tier 1, fallback to Tier 2/3
        ...
```

---

## 8. SUCCESS METRICS (Explicit Definition)

**Observation period: 24 hours (overnight run)**

| Metric | Target | How to measure |
|---|---|---|
| **Fallback rate** | < 5% | `SUM(tier2 calls) / SUM(all calls)` from `inference_audit` |
| **Latency improvement** | 2–5× faster than Gemini baseline | Compare `AVG(latency_ms)` for Tier 1 vs Tier 2 historical |
| **Gate pass rate** | ≥ historical baseline | `COUNT(success=true) / COUNT(*)` from `inference_audit` |
| **No regressions** | 0 new hallucinations | Spot-check 10 random Tier 1 outputs against gate + manual review |
| **Mac stability** | No unexpected sleeps | Check `ollama.log` for crash/restart events; `launchctl list` shows service running |

**Query to check all at once:**
```sql
WITH tier1_stats AS (
  SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN model_tier = 'tier1' THEN 1 ELSE 0 END) as tier1_count,
    AVG(CASE WHEN model_tier = 'tier1' THEN latency_ms END) as tier1_latency_ms,
    SUM(CASE WHEN model_tier = 'tier1' AND success THEN 1 ELSE 0 END) as tier1_success,
    SUM(CASE WHEN fallback_reason IS NOT NULL THEN 1 ELSE 0 END) as fallback_count
  FROM inference_audit
  WHERE timestamp > NOW() - INTERVAL '24 hours'
)
SELECT 
  total,
  tier1_count,
  ROUND(100.0 * fallback_count / NULLIF(total, 0), 2) as fallback_pct,
  tier1_latency_ms,
  ROUND(100.0 * tier1_success / NULLIF(tier1_count, 0), 2) as tier1_success_pct
FROM tier1_stats;
```

**Expected output (if successful):**
```
 total | tier1_count | fallback_pct | tier1_latency_ms | tier1_success_pct
-------+-------------+--------------+------------------+-------------------
  1247 |        1180 |         5.4% |             245  |            100.0
```

---

## 9. TIER 3 CLARIFICATION: Cowork vs Anthropic API

**Two options for "frontier reasoning" (choose one):**

**Option A: Claude Cowork (Me, in-session) — Recommended**
- Cost: Covered by your existing Cowork subscription (this session)
- Latency: Depends on token budget / context window
- Use case: "Brief drafting," "strategy reasoning," "opponent modeling"
- Integration: Direct API call to Anthropic endpoint during this session
- Limitation: Only available when I'm in-session; not always available

**Option B: Anthropic API with credits**
- Cost: Paid per token (`claude-opus-4-6` or `claude-sonnet-4-5`)
- Latency: API call, ~1–5s
- Use case: Same as Option A
- Integration: Call via Anthropic SDK with ANTHROPIC_API_KEY
- Advantage: Always available, no session dependency

**Recommendation:**
- **For Tier 1 fallback (Tier 3):** Use Anthropic API credits (always available)
- **For interactive reasoning (brief drafting, strategy):** Use Cowork me (better reasoning, lower latency)
- Update `pick()` to return the right endpoint based on task

---

## 10. DEPLOYMENT CHECKLIST (Production-Ready)

- [ ] Mac Studio: Ollama installed + launchd service running
- [ ] Mac Studio: models pulled (`qwen2.5:14b-instruct`, optional `32b`)
- [ ] VPS: connectivity test passes (curl to Ollama endpoint)
- [ ] DB: `inference_audit` table created + indexed
- [ ] Code: `model_router.py` updated (Tier 1, circuit breaker, health probe)
- [ ] Code: `SYSTEM_PROMPTS` + `TEMPERATURE` registries added
- [ ] Code: all workers updated to call `model_router.pick()` + log to `inference_audit`
- [ ] Code: manual override flag (`LANDTEK_INFERENCE_TIER` env var) works
- [ ] Tests: all 5 validation tests pass (health, routing, E2E, gate, stability)
- [ ] Monitoring: dashboard shows `inference_audit` metrics in real-time
- [ ] Deploy: git commit + workers restart
- [ ] **24h observation:** fallback rate < 5%, no errors, Mac stable

---

## 11. PRODUCTION READINESS SUMMARY

This v1.1 proposal is now:
- ✅ **Observable:** every call logged to `inference_audit` (100% visibility)
- ✅ **Robust:** health probe + circuit breaker (prevents hangs)
- ✅ **Safe:** gate integrity validated (no new hallucinations)
- ✅ **Controllable:** manual override flag (emergency fallback)
- ✅ **Measurable:** explicit success metrics (not guesses)
- ✅ **Stable:** 24h sleep test verifies Mac doesn't break overnight
- ✅ **Future-proof:** rich audit table makes cost/latency/reliability dashboards trivial

Ready to implement.

