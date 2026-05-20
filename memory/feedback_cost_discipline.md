---
name: feedback-cost-discipline
description: "Five operating rules for LLM cost discipline — Postgres-first filtering, strict Haiku/Sonnet tiering, pre-computed summaries, precision RAG, output minimization"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: bd418b71-6636-441c-8ebd-97897cec3394
---

Five hard rules for keeping Leo's LLM spend sustainable while preserving accuracy.

**Why:** Leo's infrastructure has to pay for itself. Tokens are not free; SQL is. Every interaction multiplied by daily volume × 90 days is the difference between Leo surviving and not. See [[project_financial_urgency]].

**How to apply:**

1. **Postgres-first filtering.** Never dump tables into a prompt for the LLM to sort/filter. Always write a strict `SELECT ... WHERE` in n8n's Execute SQL node or in Python, pass only the matching rows to the model. Example: "open MWK tasks" → SQL `SELECT * FROM action_items WHERE status='Open' AND case_file='MWK-001'`, then feed those rows only. Cuts input tokens ~90%.

2. **Strict Haiku/Sonnet tiering.**
   - **Claude Haiku** → 95% of the pipeline: extraction, classification (`party_filing_classifier`), routing, intent detection ("is this just 'Hello'?"), entity tagging.
   - **Claude Sonnet** → reserved strictly for high-level synthesis: the final Truth-Negotiator verdict, Jonathan's private strategic briefs. Nothing else.
   - The Truth-Negotiator challenger pass IS the verdict gate, so it gets Sonnet.

3. **Pre-computed memory caching.** Don't feed raw transcripts into prompts. Daily cron has Haiku produce a 3-sentence summary of each day's state into a `case_intelligence_update` column. Next day's Context Builder injects the summary only.

4. **Precision RAG.** Never feed a full PDF. Semantic search Qdrant for the top 3 most relevant chunks; feed those.

5. **Aggressive output constraints.** Strict JSON, no preambles ("Here is your data"), no blank fields, no conversational filler. Every word costs.

Related: [[feedback_reports_are_the_measure]] (output discipline), [[project_multi_channel_expansion]] (volume multiplier).
