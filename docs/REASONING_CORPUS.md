# Reasoning Corpus — educated, discerning equilibrium per interlocutor

**Status:** DESIGN (2026-07-16) · **Aligns with:** A70 · A71 · A75 · A76 · A79 · A5 · A25 · A32 · A85  
**Does not replace:** `docs/RELATIONSHIP_EQUILIBRIUM.md` · `docs/RECIPIENT_PROJECTION.md` · offline reasoning core (deploy_562)  
**Authority:** `MASTER_PLAN.md` for sequencing; this doc is the technical shape of *who Leo reasons as and for*.

---

## 1. Problem (grounded in what just happened)

Leo can **talk** (Telegram/Messenger) and **fetch** (title pack), but reasoning is still **shallow and uneven**:

| Symptom | Root |
|---------|------|
| Title fetch dumped many docs | Dose (A71) not applied to the **reasoning slice** — only patched for that tool |
| “I’ll fetch shortly” without delivery | Brain had **no tools / no obligation to ground** the promise |
| Same Ollama path for operator vs client | **Recipient plane** not fully driving the **internal assemble** |
| Property spine inject is ad hoc | `_property_context` is a bolt-on, not a governed **corpus slice** |
| Equilibrium is optional | A76 P2 is shadow; chat path barely consumes `internal_context` |

We do **not** need a second brain, a second vector store, or a “smarter prompt.”  
We need the **reasoning corpus**: the **smallest complete, client-walled, role-aware assembly** of what already exists in Postgres — computed **before** Leo speaks, projected **after**.

That is A70 (incorporate) + A76 (ego-network) + A75 (project) applied to **every conversational turn**, using the **local reasoning core** (A62/offline: facts · docs · law chunks · Ollama) as substrate.

---

## 2. Name and definition

### Reasoning Corpus (RC)

> The **per-turn, per-interlocutor, client-isolated package of verified and provisional structure** that Leo is allowed to reason over — assembled from the System of Record, never from a parallel “AI memory.”

| Property | Law |
|----------|-----|
| **One SoR** | Postgres is the corpus; Ollama only *reads* the RC slice (A85: no second owner of truth) |
| **Client wall first** | A5/A25 resolve WHO → `client_code` (or HOLD). No slice without a wall |
| **Role second** | A79 clamp parameters (`disclosure_ceiling`, `projection_profile`) shape what may leave; they do **not** dumb down the internal RC |
| **Two-plane (A76)** | **Internal RC** = maximal accuracy (facts, contradictions, readiness, parties, open items, graph alerts). **External emission** = dosed + projected (A71/A75) |
| **Dose is structural** | The RC itself is **narrow by purpose** (next increment for *this* ask), not “all MWK facts” |
| **Provenance intact internally** | doc:ID / provenance_level stay on the internal plane; human form strips jargon (A32/A34) |

**Not the reasoning corpus:** raw chat logs alone · unscoped RAG · Anthropic tool dumps · unauthenticated `/files/c` link spam · inventing files.

**Is the reasoning corpus (carriers already live):**

| Slice | Carrier (reuse) |
|-------|-----------------|
| Identity | `channel_users` · `comms_role_policy` · `internal_targets` · `platform_coordinator.client_of` |
| Verified facts | `matter_facts` (verified) · answer-gate cite rules |
| Deadlines / open items | `get_recent_context` · `surfaced_deadlines` · obligations views |
| Property / title | `property_assets` · `property_readiness` · `profitability_prep_moves` · parties |
| Relationship | `relationship_profile` · conversation turns · `v_comms_interactions` / `v_relationship_graph` |
| Equilibrium heat | `equilibrium_propagate` / `propagation_log` · contradictions · keystones |
| Incorporation self-knowledge | `incorporation_gate` / `matter_readiness` / `incorporation_verdicts` |
| Law (offline) | `legal_chunks` / local embed — only when the ask is legal-framed |
| Documents | **purpose-filtered** `documents` (filename + title bind), never full client dump |

---

## 3. Architecture (wire, don’t redesign)

```
 inbound message
      │
      ▼
 ┌────────────────────────────────────────────────────────────┐
 │ 0. RESOLVE (A25)                                           │
 │    channel + channel_user_id → client_code, role, is_op    │
 │    unresolved → HOLD / onboard (no RC, no invent)          │
 └────────────────────────────┬───────────────────────────────┘
                              ▼
 ┌────────────────────────────────────────────────────────────┐
 │ 1. PURPOSE CLASSIFY (cheap, deterministic)                   │
 │    title_fetch · status · deadline · party · legal · chitchat│
 │    → selects which RC modules run (A71: only needed modules) │
 └────────────────────────────┬───────────────────────────────┘
                              ▼
 ┌────────────────────────────────────────────────────────────┐
 │ 2. ASSEMBLE REASONING CORPUS (internal plane, A70+A76)     │
 │    RC = { identity, purpose, facts_n, open_items,          │
 │           property?, parties?, equilibrium?,               │
 │           incorporation_verdict?, convo_memory,            │
 │           doc_handles? }                                   │
 │    Each module is an EXISTING query/function.              │
 │    Cap per module (dose). Log assembly hash (A39).         │
 └────────────────────────────┬───────────────────────────────┘
                              ▼
 ┌────────────────────────────────────────────────────────────┐
 │ 3. DISCERN (deterministic gates before LLM)                │
 │    · thin base → refuse or escalate (A70 floor pattern)    │
 │    · contradiction heat → force hedge language (A76)       │
 │    · purpose=title_fetch → title_fetch.py (no LLM promise) │
 │    · outward + sensitive → A21 hold path                   │
 └────────────────────────────┬───────────────────────────────┘
                              ▼
 ┌────────────────────────────────────────────────────────────┐
 │ 4. REASON (local Ollama) over RC text only                 │
 │    Prompt = SYSTEM + WHO + RC blocks + message             │
 │    Forbid inventing docs/dates not in RC                   │
 └────────────────────────────┬───────────────────────────────┘
                              ▼
 ┌────────────────────────────────────────────────────────────┐
 │ 5. EMIT (A79 clamp → A75 project → A21 send)               │
 │    dose check: one point / one primary artifact            │
 │    human form · no §/doc# leak unless operator internal    │
 └────────────────────────────────────────────────────────────┘
```

**A85:** One path owns assembly (`scripts/reasoning_corpus.py` or fold into `leo_service._build_prompt` as the sole assembler). Telegram and Messenger **call the same assembler**. No third chat brain.

---

## 4. Discernment rules (educated, not chatty)

### 4.1 Purpose → module set (equilibrium of attention)

| Purpose (detected) | Modules ON | Default dose |
|--------------------|------------|--------------|
| **title_fetch** | identity · property · **one** doc handle | 1 file + status (shipped deploy_927) |
| **title_status** | identity · property · prep moves (top 3) | no file links unless asked |
| **deadline / when** | identity · open_items · surfaced_deadlines | 1 next date |
| **who / party** | identity · parties (role-filtered) | ≤5 names |
| **case status** | identity · facts (≤8) · open_items · incorporation | 1 paragraph + 1 next step |
| **legal theory** | identity · facts · legal_chunks (scoped) · contradictions | hedge if thin |
| **chitchat** | identity · convo only | no corpus dump |

### 4.2 Role → ceiling (A79 / A75)

| Role | Internal RC depth | What may emit |
|------|-------------------|---------------|
| **operator** | Full modules for client scope; strategy OK | candid; doc links OK (still dose-1) |
| **counsel** | Full facts + strategy for scoped matters | formal; cites OK in machine form |
| **client** | Own matters only; no cross-client; no strategy dump | plain language; estimated tags |
| **prospect** | onboarding + public capability only | no matter corpus |
| **counterparty** | **RC empty for facts/strategy** | refuse / human-only (A79) |
| **unknown** | onboarding only | no titles, no facts |

### 4.3 Thin-base refusal (A70 pattern on chat)

If purpose needs verified ground and:

- `incorporation_verdict` would be HOLD:thin / gap-blind for the relevant matter, **or**
- zero verified facts and no property row for a status ask,

then emission is:

> “I don’t have a grounded answer yet — [what’s missing]. I’ll flag the team.”

Not a fluent invention. Same spirit as Ombudsman incorporation gate.

### 4.4 Document release (security equilibrium)

| Step | Rule |
|------|------|
| Query | Client-scoped only (A5) |
| Select | Filename/token match; rank 0; **cap 1** unless widen phrase |
| Send | A21: internal send · outward HOLD |
| Link type | Today: `/files/c/<id>` (unauthenticated stream — **disclosure**). Target: token-scoped `/client/<token>/doc/<id>` for non-operator |
| Log | Record `disclosure: {doc_ids, role, client, purpose, dose}` on the turn (A39 / A80 direction) |

---

## 5. What already exists vs what to wire

| Piece | State | Wire into RC |
|-------|--------|--------------|
| `leo_service._build_prompt` | partial (facts, items, who, prop bolt-on) | **Become the RC renderer** of a structured package |
| `_property_context` / `title_fetch` | live | modules: `property`, `title_fetch` |
| `get_recent_context` | live | module: `open_items` |
| `relationship_profile` | live on some paths | module: `relationship` — always when channel known |
| `equilibrium_propagate` | P2 shadow | module: `equilibrium` — call shadow; inject heat only |
| `incorporation_gate` | Ombudsman path | module: `incorporation` — for status/legal purposes |
| `recipient_projection` | 3 paths | emission step 5 for all chat |
| `comms_role_policy` / A79 | shadow clamp | step 0 role + step 5 clamp |
| Telegram vs Messenger | dual entry, one Ollama | **one** `assemble_reasoning_corpus()` |

---

## 6. Proposed API (single module, no bloat)

```python
# scripts/reasoning_corpus.py  (design target — implement in a later deploy)

def assemble(cur, *, channel, channel_user_id, message, client_code, role) -> ReasoningCorpus:
    """A70+A76 internal plane. Deterministic. $0. No LLM."""

def render_for_llm(rc: ReasoningCorpus) -> str:
    """Blocks for Ollama prompt. Caps enforced."""

def emit_plan(rc: ReasoningCorpus, candidate_text: str) -> EmitPlan:
    """A79/A75/A71: dose, form, hold?, primary_doc?"""
```

`leo_service.process` and Telegram `handle` both:

1. resolve → 2. `assemble` → 3. short-circuit if purpose is pure tool (title_fetch) → 4. LLM on `render_for_llm` → 5. `emit_plan` + deliver.

**No new tables in v1.** Optional later: `reasoning_corpus_log (turn_id, client, role, purpose, module_bits, doc_ids, hash)` for audit — only if nightly/ops needs it (A39).

---

## 7. Phased delivery (shadow-first, A85)

| Phase | Deliverable | Done when |
|-------|-------------|-----------|
| **RC0** | This design + inventory (no code) | Desk agrees vocabulary |
| **RC1** | `assemble()` + `render_for_llm()` wrapping existing queries; both TG + Messenger call it | Same prompt blocks on both channels; truth_test: client wall + dose caps |
| **RC2** | Purpose classifier + module matrix (§4.1); title_fetch already exemplar | Narrow ask never loads full facts+all docs |
| **RC3** | Incorporation thin-base refuse on chat status asks | No fluent empty-status lies |
| **RC4** | Equilibrium heat always in RC when graph has signal | Contradictions force hedge |
| **RC5** | Disclosure log + prefer token doc URLs for non-operator | Security matches client portal |

Do **not** start RC5 before RC1–2 (dose + one assembler).  
Do **not** add Redis/vector dual stores. Offline reasoning core stays the substrate.

---

## 8. Success metrics (discernment, not volume)

1. **Dose:** median docs linked per “fetch title” turn = 1; widen only on request.  
2. **Wall:** 0 cross-client fact/doc IDs in RC for non-operator tests.  
3. **Grounding:** 0 replies that name a TCT/date/docket absent from that turn’s RC (gate already helps; RC makes the set explicit).  
4. **Parity:** Telegram and Messenger produce the same RC hash for the same identity+message (channel-independent reason).  
5. **Role:** counterparty purpose never receives fact/strategy modules.  
6. **Thin:** status ask with 0 verified + no readiness → explicit hold language, not invention.

---

## 9. Relation to “reasoning corpus” already in the stack

Operator language and deploy_562 **offline reasoning core** = the **substrate** (PG + Ollama + text + law + facts).  
This design’s **Reasoning Corpus** = the **per-turn, per-person cut** of that substrate under A5/A70/A71/A75/A76.

So:

- **Reasoning core** = what the machine can know offline.  
- **Reasoning corpus (this doc)** = what Leo is allowed to use **for this person, this ask, this moment** — educated and discerning by construction.

---

## 10. Explicit non-goals

- New LLM provider or multi-agent debate loop  
- Replacing `matter_facts` with chat memory  
- Full-graph recompute per message (ego-network only — A76)  
- Public authenticated CDN before dose/assembler land  
- Parallel “smart retrieval service” (A85 violation)

---

## 11. Recommended first build (when operator says go)

**RC1 only:** extract `scripts/reasoning_corpus.py` from current `leo_service._build_prompt` + `_property_context` + role/who + caps; Telegram sovereign path and Messenger `process()` both call it; truth tests for wall + cap. Title fetch stays the deterministic exemplar of purpose-gated dose.

That deepens equilibrium **without** a redesign: one assembler, existing tables, local brain, recipient-shaped emission.

---

## 13. MPRB execution (Phases A–C — landed design)

Fold-in of the three-phase plan (parity → cutover → MPRB). **One doc, no rival.**

| Phase | What shipped |
|-------|----------------|
| **A — Parity** | `leo_service.try_purpose_route` — title_fetch + corpus_answer + mprb status. Callers: `process`, `comm_agent_max`, Telegram `llm` handler. `preformed=True` skips A75 rewrite; clamp/A21 still apply. |
| **B — Cutover** | `LEO_ORCH_LIVE=channel:uid,...` on `leo_instant` — those identities use CAM live (`force_shadow=False`); else process live + CAM shadow. Operator-first. Rollback = unset env. |
| **C — MPRB v1** | `scripts/matter_brief.py`: resolve_matters, assemble (angles with data/empty/not_instrumented), render, answer_structured (verified-only). Wired into purpose route + LLM prompt injection. |

Truth-tests: `truth_tests/test_mprb_router.py` (OP oracle 3, preformed packs, structured basis).

**preformed contract:** clamp decides whether/to-whom; projection does **not** rewrite packs or `/files/c` links.
