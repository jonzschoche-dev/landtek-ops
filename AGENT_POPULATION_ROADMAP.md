# AGENT POPULATION ROADMAP

**Status:** Architecture complete, stubs created, ready for population  
**Scope:** Convert agent stubs to production implementations (Wave 1 first)  
**Timeline:** Wave 1 (4 agents) before Aug 12; Wave 2 (4 agents) post-observation  

---

## WAVE 1: CRITICAL FOR AUG 12

These 4 agents unlock the wartime mandate. Build in this order.

### Agent 1: Discovery Agent

**Current state:** Stub (logging works, no logic)

**To populate:**
1. **Email ingestion** — Read Barandon emails from Gmail API (labeled "cv26360" + "mwk")
   - New emails since last check
   - Parse for filing dates, court docket references, deadlines
   - Output: discovery_events table row

2. **RTC docket scraper** — Query court website or manual import
   - Check CV-26360 docket for new filings
   - Cross-reference with Constitution (is this expected or a surprise?)
   - Output: discovery_events table row with severity

3. **Barandon Telegram integration** — Leo forwards case updates
   - Parse structured messages ("FILED: Motion to..." timestamps)
   - Log as discovery_event

**Test:** Run manually, feed it 5 recent Barandon emails + docket check. Verify it surfaces "New Manifestation filed 2026-05-19" with severity=high.

**Success:** 100% of court filings detected within 24 hours of filing.

---

### Agent 2: Execution Tracking Agent

**Current state:** Stub

**To populate:**
1. **Play-to-docket linking** — Given a play ("File SJ Motion"), look up RTC docket
   - Play has metadata: case_id (CV-26360), doc_description ("Motion for Summary Judgment")
   - Query RTC website or manual upload for matching doc
   - Output: execution_audit row with docket_reference

2. **Email receipt verification** — Check Barandon email receipts
   - "Email sent to RTC on [date]" + "RTC acknowledged receipt [date]"
   - Log: execution_audit with verification_method="email_receipt"

3. **Calendar check** — If play triggered hearing, check calendar
   - "Hearing scheduled: Aug 12, 10:00 AM, Judge Maria Santos"
   - Log: execution_audit with verification_method="calendar_check"

**Test:** Run it on our known SJ motion (filed 24 April, doc #393, in docket). Verify it finds the docket entry + confirms judge assigned.

**Success:** 100% of executed plays verified in docket within 2 days of filing.

---

### Agent 3: Deadline Orchestration Agent

**Current state:** Stub

**To populate:**
1. **Constitution deadline parser** — Read Constitution, extract all hard dates
   - "Aug 12, 2026 — Jonathan testifies"
   - "SoL Pascual expires 2026-07-13"
   - "Pre-trial order: evidence due 2026-06-30"
   - Parse into deadline_alerts table rows

2. **Matter deadline aggregation** — Scan matter_deadlines + title_chain for SoL dates
   - Each transferee has a SoL expiry (6 years from discovery, 2020 → 2026)
   - Compute days remaining
   - Flag 30/14/7/3-day escalations

3. **Play dependency logic** — If a play must finish before another, schedule accordingly
   - "File cross-claim against Pascual before SoL expires (22 days)"
   - Recommended action: file now (takes 5 days, leaves 17 days buffer)

**Test:** Run it with Constitution + transferee list. Verify it generates alerts like "SoL Pascual in 22 days; file cross-claim immediately."

**Success:** Zero missed deadlines; every SoL event caught 30+ days in advance.

---

### Agent 4: Narrative Generation Agent

**Current state:** Stub

**To populate:**
1. **Prompt construction** — Given a play, build a detailed prompt
   - Read Constitution (strategy, cascades)
   - Read System Bible (verified facts, citations)
   - Retrieve relevant prior filings (SJ motion, reply, opposing affidavits)
   - Assemble into prompt: "Draft a 2,000-word Opposition citing the void-SPA doctrine"

2. **Model call** — Route to Tier 1 (Ollama) or Tier 3 (Anthropic) for reasoning
   - Task: "reason" (high-quality narrative needed)
   - System prompt: "You are a Philippine civil litigation expert. Ground every claim in Constitution + System Bible."

3. **Output formatting** — Convert model output to narrative_drafts table
   - Extract title, body, exhibits
   - Compute confidence (what % of claims are grounded in Constitution?)
   - Mark status="drafted" (ready for attorney red-line)

**Test:** Run it on "Draft Opposition to Manifestation" (the actual live play). Compare output to what a human drafter would produce. Verify citations are real (not hallucinated).

**Success:** Drafts require <30 min attorney review; every citation is grounded.

---

## DEPLOYMENT: Wave 1 (Before Aug 12)

```bash
# 1. Create all agent tables
psql -U n8n -d n8n -f scripts/create_agent_infrastructure.sql

# 2. Populate Agent 1 (Discovery)
python3 scripts/agent_discovery.py              # manual test
systemd timer: agent_discovery.timer (every 6 hours)

# 3. Populate Agent 2 (Execution Tracking)
python3 scripts/agent_execution_tracking.py     # manual test
systemd timer: agent_execution_tracking.timer (every 12 hours)

# 4. Populate Agent 3 (Deadline Orchestration)
python3 scripts/agent_deadline_orchestration.py # manual test
systemd timer: agent_deadline_orchestration.timer (daily 00:01 UTC)

# 5. Populate Agent 4 (Narrative Generation)
# On-demand only (triggered when operator selects "generate narrative")

# 6. Orchestrator runs all
python3 scripts/agent_orchestrator.py wave1
```

---

## WAVE 2: ENTERPRISE HARDENING (Post-Aug-12, Post-Tier-1-Observation)

Once Tier 1 is proven stable and Aug 12 testimony is complete, build Wave 2 agents.

### Agent 5: Cascade Verification Agent

**Mandate:** After Balane ruling, confirm "Balane void SPA → 20 transferees void" holds.

**Implementation:**
- Read court ruling (RTC decision on CV-26360)
- Parse legal reasoning (does judge cite nemo dat? void SPA doctrine?)
- Compare to Constitution cascade definition
- Output: cascade_verifications table row (confirmed | broken | unknown)

**Success metric:** Every cascade verified before portfolio-wide strategy depends on it.

---

### Agent 6: Opponent Modeling Agent

**Mandate:** What does Balane know/not know? Where is she weak?

**Implementation:**
- Ingest all opponent filings (her affidavit, counsel motions)
- Extract facts she claims (long possession, good faith, tenancy)
- Extract case law she cites (or doesn't cite)
- Generate opponent_models table row with known/unknown facts + weak points

**Success metric:** Predicts opponent's next move 70%+ accurately within 7 days.

---

### Agent 7: Cost-Outcome Agent

**Mandate:** What's the expected value of Summary Judgment vs. Trial vs. Settlement?

**Implementation:**
- Assess case strength per scenario (SJ: 80% win; Trial: 65% win)
- Estimate legal costs per scenario
- Compute expected value = (win_probability × recovery) - costs
- Generate cost_outcome_analysis table row with recommendation

**Success metric:** EV estimates within 15% of actual outcomes.

---

### Agent 8: Settlement Valuation Agent

**Mandate:** When negotiation starts, model the game. What to offer, when to walk.

**Implementation:**
- Input: our minimum acceptable settlement, opponent's likely walkaway price
- Game theory: simulate negotiation rounds
- Output settlement_valuations table row with opening bid, target, walkaway, strategy

**Success metric:** Negotiations close within 1 round of agent recommendation.

---

## INTEGRATION: Agent → Constitution → Operator

**Flow:**

```
Agent runs → decision logged to agent_audit
              ↓
           Constitution updated (constitution_generator.py)
              ↓
           Operator reads new alerts via dashboard + Telegram
              ↓
           Operator approves/modifies decision
              ↓
           Play engine ranks plays by strategy + EV
              ↓
           Operator executes selected play
              ↓
           Execution tracking verifies play landed
              ↓
           Discovery alerts on opponent's response
              ↓
           Cascade verification confirms strategy still valid
              ↓
           [Loop continues autonomously]
```

---

## TESTING EACH AGENT

**Generic test template:**

```python
# 1. Load Constitution
constitution = open('/root/landtek/SYSTEM_CONSTITUTION.md').read()
assert "NORTH STARS" in constitution

# 2. Load test data from System Bible
test_facts = query_system_bible("SELECT * FROM matter_facts WHERE matter_code='CV-26360' LIMIT 10")
assert len(test_facts) > 0

# 3. Run agent
agent = Agent<Name>()
result = agent.run(test_data=test_facts)

# 4. Verify grounding
for grounding_fact in result['grounding_facts']:
    assert grounding_fact in constitution or grounding_fact in test_facts

# 5. Log to audit
agent.log_decision(result['output'], result['grounding_facts'], result['confidence'])

# 6. Verify logging
audit_entry = query_agent_audit(f"WHERE agent_name='{agent.name}' ORDER BY created_at DESC LIMIT 1")
assert audit_entry['confidence'] > 0.5
```

---

## SUCCESS CRITERIA (Whole Fleet)

- ✅ Wave 1 (4 agents) shipped before Aug 12
- ✅ Every agent reads Constitution (operating manual)
- ✅ Every agent grounded in System Bible (verified facts only)
- ✅ 100% audit trail (agent_audit table, v_agent_dashboard view)
- ✅ Zero hallucinations (provenance gate still controls narrative)
- ✅ Operator remains decision-maker (agents propose, operator executes)
- ✅ Observability (dashboard shows agent decisions, confidence, grounding)

---

**The agents are designed. The stubs are in place. Time to populate them.**

