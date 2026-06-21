# AGENT ARCHITECTURE BLUEPRINT

**Status:** Complete system design for autonomous legal/land operations  
**Scope:** 8 specialized agents + unified orchestration layer  
**Mandate:** Drive narrative, preempt moves, maintain Constitution, maximize portfolio ROI  

---

## SYSTEM OVERVIEW

```
CONSTITUTION (Operating Manual)
    ↓ (every agent reads first)
SYSTEM BIBLE (Verified Facts)
    ↓ (grounded source of truth)
8 AGENTS (Specialized Autonomy)
    ├─ 1. Discovery Agent (watches for new filings)
    ├─ 2. Execution Tracking Agent (confirms plays happened)
    ├─ 3. Deadline Orchestration Agent (countdown + escalation)
    ├─ 4. Narrative Generation Agent (auto-drafts filings)
    ├─ 5. Cascade Verification Agent (tests cascades)
    ├─ 6. Opponent Modeling Agent (digital twin)
    ├─ 7. Cost-Outcome Agent (EV + settlement advice)
    └─ 8. Settlement Valuation Agent (negotiation strategy)
    ↓
AGENT AUDIT (100% observability)
    ↓
PLAY ENGINE (strategy layer)
    ↓
OPERATOR (approves/executes)
```

---

## AGENT 1: DISCOVERY AGENT

**Mandate:** Continuously scan for new filings, docket updates, deadline changes, opponent moves. Operator must know immediately.

**Inputs:**
- Barandon emails (Gmail API, labeled "cv26360" + "mwk")
- RTC court docket (via web scraper or manual court portal)
- Law firm Telegram updates
- Opponent filing notifications

**Outputs:**
```json
{
  "event_type": "new_filing | deadline_change | opponent_motion | court_order",
  "matter_id": "CV-26360",
  "description": "Balane counsel filed Manifestation to Re-admit Affidavit (doc 1088)",
  "filed_date": "2026-05-19",
  "action_required": "REVIEW: May need Opposition within 5 days",
  "severity": "high | medium | low",
  "timestamp": "2026-06-21T08:15:00Z"
}
```

**Trigger:** Every 6 hours (court business hours) OR on-demand

**Database:**
```sql
CREATE TABLE discovery_events (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT,
    matter_id TEXT,
    description TEXT,
    filed_date DATE,
    source TEXT,  -- email | docket | telegram | manual
    action_required TEXT,
    severity TEXT,
    operator_notified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Success Metric:** Catches 100% of filed motions within 24 hours of filing

---

## AGENT 2: EXECUTION TRACKING AGENT

**Mandate:** Verify that plays actually executed. "We filed the SJ motion" means nothing if it's not in the docket.

**Inputs:**
- play_queue table (plays marked "executed")
- RTC docket lookup (case number + doc description)
- Email receipts (proof of sending)
- Calendar events (hearing scheduled?)

**Outputs:**
```json
{
  "play_id": 12345,
  "play_name": "File SJ Motion on Prong A",
  "status": "executed | failed | partial",
  "verification": {
    "filed_in_docket": true,
    "docket_reference": "CV-26360, doc 393, 24 Apr 2026",
    "judge_assigned": "Maria Santos",
    "court_acknowledged": true
  },
  "verified_at": "2026-06-21T10:30:00Z"
}
```

**Trigger:** Every 12 hours after execution OR on-demand

**Database:**
```sql
CREATE TABLE execution_audit (
    id BIGSERIAL PRIMARY KEY,
    play_id INT,
    play_name TEXT,
    execution_status TEXT,
    verification_method TEXT,
    docket_reference TEXT,
    verified_at TIMESTAMPTZ,
    success BOOLEAN DEFAULT TRUE,
    notes TEXT
);
```

**Success Metric:** 100% of filed motions verified in docket within 2 days of filing

---

## AGENT 3: DEADLINE ORCHESTRATION AGENT

**Mandate:** Proactive calendar. System knows what must move *when* and escalates 30/14/7/3 days before.

**Inputs:**
- Constitution (hard dates: Aug 12, SoL per transferee, court calendar)
- matter_deadlines table (RTC order deadlines, statute-of-limitations dates)
- play dependencies (this play must finish before that one can start)

**Outputs:**
```json
{
  "alert_type": "upcoming_deadline | sol_expiry | court_order | evidence_cutoff",
  "matter_id": "CV-26360",
  "date": "2026-07-13",  // SoL expiry for Pascual
  "days_remaining": 22,
  "recommended_action": "File cross-claim against Pascual (statute of limitations expires 2026-07-13)",
  "escalation_level": "high",
  "timestamp": "2026-06-21"
}
```

**Trigger:** Daily (00:01 UTC)

**Database:**
```sql
CREATE TABLE deadline_alerts (
    id BIGSERIAL PRIMARY KEY,
    matter_id TEXT,
    alert_type TEXT,
    target_date DATE,
    days_remaining INT,
    recommended_action TEXT,
    escalation_level TEXT,
    acknowledged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Success Metric:** Zero missed deadlines; every statute-of-limitations event caught with 30+ days warning

---

## AGENT 4: NARRATIVE GENERATION AGENT

**Mandate:** Auto-draft filings, client comms, opponent demands. Operator edits, not writes from scratch.

**Inputs:**
- A selected play ("file SJ reply to Manifestation")
- Constitution (grounded strategy + cascades)
- System Bible (verified facts + citations)
- Document pool (prior motions, precedent, evidence)

**Outputs:**
```json
{
  "play_id": 12346,
  "document_type": "motion | opposition | letter | email | brief",
  "title": "PLAINTIFF'S OPPOSITION TO DEFENDANT'S MANIFESTATION RE: RE-ADMISSION OF AFFIDAVIT",
  "body": "[Full draft text with citations, 2,500 words]",
  "exhibits": ["doc_246_SPA.pdf", "doc_441_revocation_affidavit.pdf"],
  "status": "ready_for_attorney_review",
  "confidence": 0.82,  // how grounded is this in Constitution + Bible?
  "timestamp": "2026-06-21T09:00:00Z"
}
```

**Trigger:** On-demand when operator selects a play + "generate narrative"

**Database:**
```sql
CREATE TABLE narrative_drafts (
    id BIGSERIAL PRIMARY KEY,
    play_id INT,
    document_type TEXT,
    title TEXT,
    body TEXT,
    exhibits TEXT[],
    status TEXT,  -- drafted | attorney_reviewed | filed | rejected
    confidence REAL,
    created_by TEXT DEFAULT 'agent',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Success Metric:** Drafts are coherent, cite verified facts only, require <30 min attorney red-line

---

## AGENT 5: CASCADE VERIFICATION AGENT

**Mandate:** Test whether assumed cascades are actually true. If Balane ruling breaks the void-SPA cascade, we need to know immediately.

**Inputs:**
- Constitution verified cascades (e.g., "Balane void SPA → 20 transferees void")
- Court rulings + opinions (does the judge cite our theory?)
- Outcome for linked cases (did Victa's case settle on the same void-SPA logic?)

**Outputs:**
```json
{
  "cascade_id": "balane_to_20_transferees",
  "cascade_name": "1992 SPA void (Balane) → void for all 20 transferees",
  "test_case": "CV-26360 (Balane)",
  "result": "confirmed | broken | unknown",
  "evidence": "Court ruling (June 21) cites nemo dat + void SPA operative clause as dispositive; holding applies *a fortiori* to all co-grantees",
  "confidence": 0.95,
  "implications": "Cascade CONFIRMED — strategy for remaining 19 transferees unchanged. Proceed with parallel filings.",
  "timestamp": "2026-06-21T14:00:00Z"
}
```

**Trigger:** After major court ruling OR monthly check

**Database:**
```sql
CREATE TABLE cascade_verifications (
    id BIGSERIAL PRIMARY KEY,
    cascade_id TEXT,
    cascade_name TEXT,
    test_case_id TEXT,
    result TEXT,  -- confirmed | broken | unknown
    evidence TEXT,
    confidence REAL,
    implications TEXT,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Success Metric:** 100% of cascades verified before portfolio-wide strategy relies on them

---

## AGENT 6: OPPONENT MODELING AGENT

**Mandate:** Build a digital twin of opponent's case. What do they know/not know? What's their likely next move?

**Inputs:**
- Opponent filings (Balane's affidavit, counsel motions, evidence submissions)
- Public case law they cite (authority search)
- Gaps in their arguments (what they *don't* cite)
- Timeline of their moves (defensive pattern?)

**Outputs:**
```json
{
  "opponent": "Balane / Gloria Balane",
  "matter_id": "CV-26360",
  "known_facts": [
    "Tenancy from 1975–2016 (₱50/mo rent)",
    "2016 deed from Cesar (her main evidence)",
    "No annotation on T-4497 to warn her"
  ],
  "unknown_facts": [
    "2005 formal revocation (not published until 2020)",
    "7-layer void doctrine (they cite none of it)",
    "Bautista-Spille precedent on narrow SPA (not in their filings)"
  ],
  "likely_next_move": "Re-filing the excluded affidavit (doc 1089) to establish long possession + good faith",
  "weak_points": [
    "Affidavit admits never asking Keeseys to verify authority (T43)",
    "Admitted T30 verbal assurance from Cesar, not written authority",
    "No evidence of independent title search"
  ],
  "preemption_opportunities": [
    "File SJ reply citing Bautista-Spille before they file counter-motion",
    "Reference her public-official status (higher duty of inquiry) in brief"
  ],
  "confidence": 0.78,
  "timestamp": "2026-06-21T11:00:00Z"
}
```

**Trigger:** Weekly (matches opponent filing cycle) OR after new opponent filing

**Database:**
```sql
CREATE TABLE opponent_models (
    id BIGSERIAL PRIMARY KEY,
    opponent_id TEXT,
    matter_id TEXT,
    known_facts TEXT[],
    unknown_facts TEXT[],
    likely_next_move TEXT,
    weak_points TEXT[],
    preemption_opportunities TEXT[],
    confidence REAL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Success Metric:** Predicts opponent's next move 70%+ accurately within 7 days

---

## AGENT 7: COST-OUTCOME AGENT

**Mandate:** Tie spend to outcomes. Should we fight or settle? What's the expected value per play?

**Inputs:**
- matter_spend (filing fees, attorney hours, expert fees)
- case_strength (win probability per play, per scenario)
- settlement_offers (if any)
- portfolio_strategy (are we fighting or settling this one?)

**Outputs:**
```json
{
  "matter_id": "CV-26360",
  "scenario": "summary_judgment | trial | settlement",
  "win_probability": {
    "summary_judgment": 0.80,
    "trial": 0.65,
    "settlement": 1.0
  },
  "ev": {
    "summary_judgment": "₱2.1M (0.80 × ₱2.6M recovery - ₱0.4M SJ legal fees)",
    "trial": "₱1.2M (0.65 × ₱2.6M recovery - ₱0.9M trial legal fees)",
    "settlement": "Settlement offer: ₱800K (reject if <₱1.5M)"
  },
  "recommendation": "Pursue Summary Judgment (highest EV). Reject settlement <₱1.5M.",
  "confidence": 0.72,
  "timestamp": "2026-06-21T15:30:00Z"
}
```

**Trigger:** After major development OR monthly reconciliation

**Database:**
```sql
CREATE TABLE cost_outcome_analysis (
    id BIGSERIAL PRIMARY KEY,
    matter_id TEXT,
    scenario TEXT,
    win_probability REAL,
    expected_recovery DECIMAL,
    expected_cost DECIMAL,
    expected_value DECIMAL,
    recommendation TEXT,
    confidence REAL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Success Metric:** EV estimates within 15% of actual outcomes (measured post-case)

---

## AGENT 8: SETTLEMENT VALUATION AGENT

**Mandate:** When negotiation starts, system models the game. What to offer, when to walk away.

**Inputs:**
- Opponent's likely walkaway price (inferred from Cost-Outcome Agent)
- Our minimum acceptable settlement
- Negotiation precedent (other cases in this jurisdiction)
- Opponent's financial capacity to pay

**Outputs:**
```json
{
  "matter_id": "CV-26360",
  "opponent": "Balane",
  "phase": "pre_negotiation | active_negotiation | endgame",
  "opening_offer": "₱800K",
  "target_settlement": "₱1.2M",
  "walkaway_price": "₱1.5M (above this, we trial)",
  "negotiation_strategy": [
    "Open at ₱800K (they'll counter ₱500K)",
    "Respond ₱1.0M (cite our SJ strength)",
    "If they go ₱1.3M, accept (within walkaway range)",
    "If they stay <₱900K after 3 rounds, declare impasse and proceed to trial"
  ],
  "confidence": 0.65,
  "timestamp": "2026-06-21"
}
```

**Trigger:** On-demand when settlement discussions begin

**Database:**
```sql
CREATE TABLE settlement_valuations (
    id BIGSERIAL PRIMARY KEY,
    matter_id TEXT,
    opponent_id TEXT,
    opening_offer DECIMAL,
    target_settlement DECIMAL,
    walkaway_price DECIMAL,
    negotiation_strategy TEXT,
    phase TEXT,
    confidence REAL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Success Metric:** Negotiations close within 1 round of system recommendation (operator approves strategy)

---

## UNIFIED LAYER: agent_audit TABLE

**Every agent logs every decision here. 100% observability.**

```sql
CREATE TABLE agent_audit (
    id BIGSERIAL PRIMARY KEY,
    agent_name TEXT,  -- discovery, execution_tracking, etc.
    agent_id INT,
    trigger TEXT,  -- schedule | event | on_demand
    decision TEXT,  -- the output/recommendation
    grounding_facts TEXT[],  -- which Constitution facts + System Bible entries support this?
    confidence REAL,
    operator_action TEXT,  -- approved | rejected | modified_to
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## INTEGRATION POINTS

### Constitution → Agents
- Every agent reads Constitution first (operating manual)
- If Constitution says "Balane cascade to 20 transferees," Cascade Verification Agent tests it
- If Constitution says "Aug 12 testimony," Deadline Agent counts down

### System Bible → Agents
- Discovery Agent finds new facts → feeds System Bible
- System Bible updates Constitution (via constitution_generator.py)
- Agents read updated Constitution next cycle

### Agents → play_engine
- Deadline Agent: "30 days to SoL expiry" → suggests play "File cross-claim by [date]"
- Cost-Outcome Agent: "EV is ₱2.1M" → plays ranked by EV
- Opponent Modeling Agent: "Weak point: they didn't cite Bautista-Spille" → suggests play "File SJ relying on Bautista-Spille"

### Agents → Operator
- Via Constitution alerts (Telegram via Leo)
- Via operator dashboard (`/ops/agent-status`)
- Urgent (severity=high): immediate Telegram
- Medium/Low: batched in daily digest

---

## SHIPPING ORDER (Priority + Dependencies)

**Wave 1 (This week, unblock Aug 12):**
- Agent 1: Discovery (watch for opponent moves)
- Agent 2: Execution Tracking (confirm our plays landed)
- Agent 3: Deadline Orchestration (countdown + escalation)
- Agent 4: Narrative Generation (draft filings for attorney review)

**Wave 2 (Post-Aug-12, post-Tier-1 observation, next 2 weeks):**
- Agent 5: Cascade Verification (test our strategy's core logic)
- Agent 6: Opponent Modeling (preemption layer)
- Agent 7: Cost-Outcome (EV per scenario)
- Agent 8: Settlement Valuation (negotiation game theory)

---

## IMPLEMENTATION TEMPLATE (Per Agent)

Each agent repo location: `/root/landtek/scripts/agent_<name>.py`

```python
#!/usr/bin/env python3
"""agent_<name>.py — [Mandate]"""
import os
import sys
import time
from datetime import datetime
import psycopg2
from langchain.prompts import PromptTemplate
from model_router import pick, call_model

# Read Constitution first
CONSTITUTION = open('/root/landtek/SYSTEM_CONSTITUTION.md').read()

class Agent<Name>:
    def __init__(self):
        self.db = psycopg2.connect(os.environ['PG_DSN'])
        self.name = "<name>"
    
    def read_system_bible(self):
        """Query grounded facts from database."""
        # Example: SELECT statement, source_id FROM matter_facts WHERE matter_code='CV-26360' AND provenance_level='verified'
        pass
    
    def reason(self, inputs):
        """Run inference on grounded facts."""
        config = pick("reason")  # Use Tier 1 (or higher if needed)
        prompt = f"""
        You are the [Name] Agent. Your mandate is [mandate].
        
        CONSTITUTION (Operating Manual):
        {CONSTITUTION}
        
        SYSTEM BIBLE (Verified Facts):
        [Grounded facts from read_system_bible()]
        
        INPUT:
        {inputs}
        
        OUTPUT: [JSON schema defined above]
        """
        result = call_model(config, prompt, task_type="reason")
        return result
    
    def log_decision(self, decision, grounding_facts, confidence):
        """Log to agent_audit table."""
        cur = self.db.cursor()
        cur.execute("""
            INSERT INTO agent_audit 
            (agent_name, decision, grounding_facts, confidence, created_at)
            VALUES (%s, %s, %s, %s, NOW())
        """, (self.name, decision, grounding_facts, confidence))
        self.db.commit()
    
    def run(self):
        """Main execution."""
        facts = self.read_system_bible()
        result = self.reason(facts)
        self.log_decision(result['output'], result['grounding'], result['confidence'])
        return result

if __name__ == "__main__":
    agent = Agent<Name>()
    agent.run()
```

---

## SUCCESS CRITERIA (Whole System)

- ✅ 8 agents designed + database schemas committed
- ✅ Wave 1 (4 agents) shipping before Aug 12
- ✅ Every agent reads Constitution (operating manual)
- ✅ Every agent grounded in System Bible (verified facts)
- ✅ 100% audit trail (agent_audit table)
- ✅ Zero hallucinations (provenance gate still controls)
- ✅ Operator remains decision-maker (agents propose, operator executes)

---

**This is the complete agent fleet. No missing pieces. Ship all 8.**

