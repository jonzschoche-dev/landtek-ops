-- inference_audit table: 100% observability of all model inference calls
-- Logs every call (success or failure) with full context for analysis & dashboards

CREATE TABLE IF NOT EXISTS inference_audit (
    id BIGSERIAL PRIMARY KEY,
    
    -- Request tracking (correlates retries/fallbacks)
    request_id UUID NOT NULL DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    
    -- Tier & model information
    model_tier TEXT NOT NULL,           -- 'tier1', 'tier2', 'tier3'
    model_name TEXT NOT NULL,           -- 'qwen2.5:14b-instruct', 'gemini-2.5-flash', etc.
    
    -- Task & document context
    task_type TEXT,                     -- 'verify', 'extract', 'classify', 'reason', 'ocr_assist'
    doc_id TEXT,                        -- foreign key to documents table
    matter_id TEXT,                     -- foreign key to matter context
    
    -- Performance metrics
    tokens_prompt INTEGER,              -- tokens in the prompt
    tokens_completion INTEGER,          -- tokens in the completion
    latency_ms INTEGER,                 -- wall-clock latency in milliseconds
    
    -- Reliability & fallback info
    fallback_reason TEXT,               -- why we fell back to another tier ('timeout', 'error', 'tier1_unhealthy', NULL if no fallback)
    success BOOLEAN DEFAULT TRUE,       -- did the call succeed?
    error_message TEXT,                 -- error details (if success=false)
    
    -- Auditability
    created_by TEXT DEFAULT 'worker',
    
    -- Constraints
    CONSTRAINT positive_latency CHECK (latency_ms IS NULL OR latency_ms >= 0),
    CONSTRAINT positive_tokens CHECK (tokens_prompt IS NULL OR tokens_prompt >= 0),
    CONSTRAINT positive_tokens_completion CHECK (tokens_completion IS NULL OR tokens_completion >= 0)
);

-- Indexes for operational queries
CREATE INDEX IF NOT EXISTS idx_inference_audit_request ON inference_audit(request_id);
CREATE INDEX IF NOT EXISTS idx_inference_audit_matter ON inference_audit(matter_id);
CREATE INDEX IF NOT EXISTS idx_inference_audit_tier ON inference_audit(model_tier);
CREATE INDEX IF NOT EXISTS idx_inference_audit_task ON inference_audit(task_type);
CREATE INDEX IF NOT EXISTS idx_inference_audit_timestamp ON inference_audit(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_inference_audit_doc ON inference_audit(doc_id);

-- View: Summary metrics for operational dashboard
CREATE OR REPLACE VIEW v_inference_audit_24h AS
SELECT 
    model_tier,
    COUNT(*) as total_calls,
    SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful_calls,
    SUM(CASE WHEN fallback_reason IS NOT NULL THEN 1 ELSE 0 END) as fallback_count,
    ROUND(100.0 * SUM(CASE WHEN fallback_reason IS NOT NULL THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as fallback_pct,
    AVG(latency_ms)::INT as avg_latency_ms,
    MAX(latency_ms) as max_latency_ms,
    MIN(latency_ms) as min_latency_ms,
    AVG(tokens_prompt)::INT as avg_tokens_in,
    AVG(tokens_completion)::INT as avg_tokens_out
FROM inference_audit
WHERE timestamp > NOW() - INTERVAL '24 hours'
GROUP BY model_tier
ORDER BY model_tier;

