# RECIPIENT PROJECTION — one truth, N recipient-shaped projections (never N sources)

**Status:** DESIGN (step 1 of the 2026-07-11 directive) · **Invariant:** A75 (ONTOLOGY §4, 🟡 planned)
**Lineage:** generalizes `ClientProjection` (A32/A33, `leo_tools/client_ontology.py`) from *one* audience
(the paying client) to *every* recipient of the pulse — clients, agents, workers, the operator.
*(The directive drafted this as "A73"; A73/A74 were taken by deploy_843 — it ships as A75.)*

## 1. The problem, stated once

One incorporated truth (A70) must reach many recipients, and the two recipient species FAIL IN OPPOSITE
DIRECTIONS:

| | Humans | Agents |
|---|---|---|
| Failure mode | **too much** — flood → noise → disengagement | **too little** — ambiguity → wrong action or stall |
| Therefore | narrative, ONE point, paced (S14), plain confidence (A34) | typed, **complete-in-one-payload**, provenance handles intact |

A pulse event that reaches any recipient un-projected is a defect: raw internal fields leak to humans
(the A32 lesson), and prose ambiguity starves agents.

## 2. The four axes every projection fixes

1. **WHO** — identity + role + the client-isolation boundary (A5/A35). The scope is a *wall*, not a filter
   preference: what this recipient may and should see. Never crossed, never widened by a rendering step.
2. **PURPOSE** — the recipient's **next actionable increment** (A71), not their whole backlog. A projection
   answers "what should this recipient do next," not "what does the system know."
3. **FORM** — `HUMAN` (narrative · one point · plain-language confidence per A34 — translated, never
   upgraded) vs `MACHINE` (typed dict · doc/fact IDs and provenance enums INTACT — an agent must be able
   to cite and verify, so handles are load-bearing, never prettified away).
4. **DOSE / CADENCE** — the metabolizable rate. **The dose axis differs by delivery mode:**
   - **PUSHED feeds** (digest · reminder · alert): an items-per-window ceiling (A71); over-feed = violation.
     S14 floors the human channel (one point, no double-tap).
   - **PULLED work-slices** (an agent asking for its work): completeness wins — the slice is
     complete-in-one-payload for its declared purpose (an agent starved by pagination fails from
     too-little, the exact failure the axis exists to prevent). The ceiling governs *push*, never truncates *pull*.

## 3. RecipientProfile — the schema

```
RecipientProfile {
  key:      "rent-agent" | "tenant:<client_code>" | "ombudsman-hunter" | "operator" ...
  kind:     human | agent
  who:      { client_code | matter_scope, role }         # A5/A35 wall — resolved, never inferred
  purpose:  one sentence — the next-increment this recipient exists to take
  form:     HUMAN | MACHINE
  dose:     { push_max_per_window, window } | PULL_COMPLETE
  channel:  telegram | email | api | cli ... + its A26 switch state (token-as-switch; outward = gated)
}
```

Registry: **code-first** (a reviewed, versioned dict in `leo_tools/recipient_projection.py`), mirroring
how `client_ontology` itself is code. Promote to a table only when profiles multiply beyond review
(the GeometrySource pattern: fix the vocabulary now, give a future store a target).

## 4. Worked example — the SAME fact, two projections

Source of truth (one row, never duplicated): a verified `matter_facts` row — *"Monthly rent of ₱12,000 due
on the 15th under the lease"* citing doc 1042, `provenance_level='verified'`, matter LSE-004 (client PAR-001).

**→ tenant (human):**
> Your rent of ₱12,000 is due this Friday, June 15. Reply here to confirm payment.

*(one point · no docket/doc# · plain terms · S14-paced · sent only through the A26-switched channel)*

**→ rent-agent (machine):**
```json
{"obligation_id": 88213, "kind": "rent_due", "due_at": "2026-06-15", "client_code": "PAR-001",
 "matter_code": "LSE-004", "amount_php": 12000, "status": "unpaid",
 "source_doc_id": 1042, "fact_id": 55231, "provenance_level": "verified"}
```

*(typed · complete · provenance handles intact so the agent can cite/verify — and its own writes stay
inside the A49 propose→adjudicate gate)*

Same truth. Neither recipient saw the other's shape. Neither saw a raw row.

## 5. Guardrails (inherited, not new)

- **Reuse, don't fork:** human-form rendering calls `client_ontology` (A32/A33 totality + `_flag_unmapped`
  fallback); machine form is a *pass-through of handles*, not a second vocabulary.
- **A5 is the WHO axis** — scope enforced in the query, not the formatter.
- **A34 for humans** (confidence translated, never upgraded) · **A42-handles for machines** (never strip
  `source_doc_id`/`provenance_level` from an agent payload).
- **No recipient reads raw un-projected data** — graduation for A75 is per consuming path, like A70's floors.

## 6. Build path (step 3 = smallest real step, DONE with this doc)

The missing species is **agent-facing** projection — agents read raw tables today. First proof:
`ombudsman_hunter._fetch_facts` now takes its scoped, typed work-slice through the
`ombudsman-hunter` profile (MACHINE · client-scoped · PULL_COMPLETE) instead of a raw query.
Next candidates, one at a time: verify-worker's slice · the pulse orchestrator's per-agent work orders ·
the tenant/rent pair when Property v2.0 lands (§4A pillar 4).
