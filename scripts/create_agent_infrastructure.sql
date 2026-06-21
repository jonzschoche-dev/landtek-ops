-- AGENT INFRASTRUCTURE: Database schema for all 8 agents
-- Unified audit, decision logging, and observability layer

-- ──────────────────────────────────────────────────────────────
-- AGENT AUDIT (Core: every agent logs every decision here)
-- ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agent_audit (
    id BIGSERIAL PRIMARY KEY,
    agent_name TEXT NOT NULL,              -- discovery, execution_tracking, deadline_orchestration, etc.
    agent_id BIGINT,
    trigger TEXT,                           -- schedule | event | on_demand
    decision JSONB NOT NULL,                -- the full output/recommendation
    grounding_facts TEXT[],                 -- which Constitution facts support this?
    confidence REAL DEFAULT 0.5,            -- 0.0-1.0
    operator_action TEXT,                   -- approved | rejected | modified_to
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agent_audit_agent ON agent_audit(agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_audit_timestamp ON agent_audit(created_at DESC);

-- ──────────────────────────────────────────────────────────────
-- AGENT 1: Discovery Agent
-- ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS discovery_events (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,               -- new_filing | deadline_change | opponent_motion | court_order
    matter_id TEXT,
    description TEXT NOT NULL,
    filed_date DATE,
    source TEXT,                            -- email | docket | telegram | manual
    action_required TEXT,
    severity TEXT DEFAULT 'medium',         -- high | medium | low
    operator_notified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_discovery_matter ON discovery_events(matter_id);
CREATE INDEX IF NOT EXISTS idx_discovery_severity ON discovery_events(severity);

-- ──────────────────────────────────────────────────────────────
-- AGENT 2: Execution Tracking Agent
-- ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS execution_audit (
    id BIGSERIAL PRIMARY KEY,
    play_id INT,
    play_name TEXT,
    execution_status TEXT,                  -- executed | failed | partial
    verification_method TEXT,               -- docket_lookup | email_receipt | calendar_check
    docket_reference TEXT,                  -- RTC docket cite
    verified_at TIMESTAMPTZ,
    success BOOLEAN DEFAULT TRUE,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_execution_play ON execution_audit(play_id);
CREATE INDEX IF NOT EXISTS idx_execution_status ON execution_audit(execution_status);

-- ──────────────────────────────────────────────────────────────
-- AGENT 3: Deadline Orchestration Agent
-- ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS deadline_alerts (
    id BIGSERIAL PRIMARY KEY,
    matter_id TEXT,
    alert_type TEXT,                        -- upcoming_deadline | sol_expiry | court_order | evidence_cutoff
    target_date DATE NOT NULL,
    days_remaining INT,
    recommended_action TEXT,
    escalation_level TEXT DEFAULT 'medium', -- high | medium | low
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_deadline_matter ON deadline_alerts(matter_id);
CREATE INDEX IF NOT EXISTS idx_deadline_target_date ON deadline_alerts(target_date);
CREATE INDEX IF NOT EXISTS idx_deadline_escalation ON deadline_alerts(escalation_level);

-- ──────────────────────────────────────────────────────────────
-- AGENT 4: Narrative Generation Agent
-- ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS narrative_drafts (
    id BIGSERIAL PRIMARY KEY,
    play_id INT,
    document_type TEXT,                     -- motion | opposition | letter | email | brief
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    exhibits TEXT[],                        -- array of doc_ids
    status TEXT DEFAULT 'drafted',          -- drafted | attorney_reviewed | filed | rejected
    confidence REAL,
    attorney_notes TEXT,
    filed_reference TEXT,                   -- RTC docket cite if filed
    created_by TEXT DEFAULT 'agent',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_narrative_play ON narrative_drafts(play_id);
CREATE INDEX IF NOT EXISTS idx_narrative_status ON narrative_drafts(status);

-- ──────────────────────────────────────────────────────────────
-- AGENT 5: Cascade Verification Agent
-- ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS cascade_verifications (
    id BIGSERIAL PRIMARY KEY,
    cascade_id TEXT UNIQUE,                 -- balane_to_20_transferees, etc.
    cascade_name TEXT,
    test_case_id TEXT,                      -- which case tested this?
    result TEXT,                            -- confirmed | broken | unknown
    evidence TEXT,
    confidence REAL,
    implications TEXT,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cascade_result ON cascade_verifications(result);

-- ──────────────────────────────────────────────────────────────
-- AGENT 6: Opponent Modeling Agent
-- ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS opponent_models (
    id BIGSERIAL PRIMARY KEY,
    opponent_id TEXT,
    matter_id TEXT,
    known_facts TEXT[],
    unknown_facts TEXT[],
    likely_next_move TEXT,
    weak_points TEXT[],
    preemption_opportunities TEXT[],
    confidence REAL,
    updated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_opponent_matter ON opponent_models(matter_id);

-- ──────────────────────────────────────────────────────────────
-- AGENT 7: Cost-Outcome Agent
-- ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS cost_outcome_analysis (
    id BIGSERIAL PRIMARY KEY,
    matter_id TEXT,
    scenario TEXT,                          -- summary_judgment | trial | settlement
    win_probability REAL,
    expected_recovery DECIMAL,
    expected_cost DECIMAL,
    expected_value DECIMAL,
    recommendation TEXT,
    confidence REAL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cost_outcome_matter ON cost_outcome_analysis(matter_id);

-- ──────────────────────────────────────────────────────────────
-- AGENT 8: Settlement Valuation Agent
-- ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS settlement_valuations (
    id BIGSERIAL PRIMARY KEY,
    matter_id TEXT,
    opponent_id TEXT,
    opening_offer DECIMAL,
    target_settlement DECIMAL,
    walkaway_price DECIMAL,
    negotiation_strategy TEXT,
    phase TEXT,                             -- pre_negotiation | active_negotiation | endgame
    confidence REAL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_settlement_matter ON settlement_valuations(matter_id);

-- ──────────────────────────────────────────────────────────────
-- AGENT ORCHESTRATION & STATUS
-- ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agent_status (
    id BIGSERIAL PRIMARY KEY,
    agent_name TEXT UNIQUE,
    last_run_at TIMESTAMPTZ,
    last_successful_run_at TIMESTAMPTZ,
    next_scheduled_run TIMESTAMPTZ,
    error_count INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ──────────────────────────────────────────────────────────────
-- OBSERVABILITY VIEW: Agent Dashboard
-- ──────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW v_agent_dashboard AS
SELECT 
    agent_name,
    COUNT(*) as total_decisions,
    SUM(CASE WHEN operator_action = 'approved' THEN 1 ELSE 0 END) as approved,
    SUM(CASE WHEN operator_action = 'rejected' THEN 1 ELSE 0 END) as rejected,
    AVG(confidence)::NUMERIC(3,2) as avg_confidence,
    MAX(created_at) as last_decision
FROM agent_audit
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY agent_name
ORDER BY agent_name;

