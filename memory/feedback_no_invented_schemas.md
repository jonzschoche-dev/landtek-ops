---
name: no-invented-schemas
description: Never invent or guess column lists when creating database tables on this project. Always get the spec from Jonathan first.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6d129aad-aef2-4031-8003-fa0de0a89100
---

Never create a database table with invented/inferred columns on this project.
Always get the authoritative schema spec from Jonathan first — even when he says
"use your recommended approach", schemas are not the right place for inferred
defaults.

**Why:** This is an evidence-grade legal RAG database for Civil Case 26-360.
Schemas that hold case-relevant audit trails (escalations_log, phase_log,
cooldown_log, service_recoveries, etc.) need real specs because downstream code
will write to them with expected column names. A guessed schema becomes either
silently wrong (data lands in the wrong column) or breaks future deploys that
expected different columns. The cost of pausing to ask is one round-trip; the
cost of an invented schema can be wasted writes and broken integrations.

**How to apply:** When asked to "deploy the remaining tables" or similar without
a spec on disk or in the cowork pipeline:
- Do NOT propose schemas and apply.
- Do NOT pick "recommended: use inferred schemas" even if I offer it.
- ASK explicitly for the column list, types, and constraints. Wait for it.
- If a usage example was given (like an `INSERT INTO X (col1, col2) VALUES ...`),
  that defines the minimum required columns but not necessarily the full schema —
  still ask for the rest.

**Specific tables affected on 2026-05-12 (need to be re-checked against real specs
or dropped+rebuilt when authoritative specs arrive):**
- public.escalations_log
- public.phase_log
- public.cooldown_log
- public.service_recoveries

Related: [[user-role]], the project's hallucination-proof discipline rule in
CLAUDE.md applies to schema creation, not just legal output.
