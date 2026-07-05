# LandTek — Governed Actions Registry

> **Purpose.** One legible place for *what the system is allowed to DO*, its risk tier, and the control
> that already gates it — so a new agent or script can't violate the outward-action invariant unknowingly.
> This is the execution-side companion to `ONTOLOGY.md` (data model) and the governance map in
> `ARCHITECTURE.md` §8.
>
> **Grounded against the live code/timers on 2026-07-05.** This is a *codification of controls that already
> exist*, not a new enforcement system — see "Scope" below.
>
> **Registry version: v0.1 (2026-07-05).**

---

## 0. The core invariant (this is the whole point)

> **THE SYSTEM TAKES NO AUTONOMOUS OUTWARD OR IRREVERSIBLE ACTION.** Every filing, every send to a party /
> court / official, every external client exposure, and every "mark as filed" is **human-gated or
> switch-held by design.** Autonomous execution is confined to **internal, reversible** work: ingest,
> classify, propose, write-through-a-gate, and alert-the-operator.

This is not aspirational — it is enforced in three independent places (verified 2026-07-05):

1. **Agent charters.** Every acting subagent's definition ends the same way. `case-26360-strategist`:
   *"never file, never send anything outside the company, never contact a party, witness, court, or
   official."* `ombudsman-hunter`: *"status tops out at `held_for_filing` … propose, never auto-execute."*
   `mapping-agent`: *"NEVER files, sends, or exposes a client map externally without Jonathan's go."*
2. **Switch-holds on external channels.** `whatsapp_channel_bridge.py`: *"token IS the external switch —
   provisioning it opens the channel by design"*; Viber/WhatsApp report *"not provisioned yet"* and exit
   clean. External send is OFF until a human provisions it (`memory/no-external-exposure-until-ready`).
3. **The comms chokepoint (S14).** Every outbound message is sanitized + pace-gated; sim senders are
   rewritten to `chat_id='0'`; the only autonomous recipient is **Jonathan himself** (and even that is
   no-double-tap gated). 14,345 `outbound_blocks` rows are this rule working.

**Corollary:** an agent that adds an autonomous outward action (a real send, a filing POST, an external
link handed out) is violating the invariant and must be stopped in review — regardless of how useful it is.

---

## 1. Risk tiers

| Tier | Meaning | Governing control |
|---|---|---|
| **T0** | No effect / read-only / not-provisioned | none needed |
| **T1** | Autonomous, internal, low-blast-radius, reversible (ingest, classify, surface) | pipeline QA + provenance |
| **T2** | Autonomous **write to the knowledge/canon** or **outbound text to the operator** | provenance gate · `ontology_validator` · S14 |
| **T3** | **Outward / irreversible** (file, send to a party, expose externally, mark filed) | **HUMAN-GATED — never autonomous** (invariant §0) |

---

## 2. Action registry (grounded in live timers/agents)

### Autonomous — allowed, with the gate that governs them

| Action | Where | Touches | Tier | Existing control |
|---|---|---|---|---|
| Ingest / OCR / classify docs | `corpus-backfill`, `reocr-sweep`, `ingest_drive_folder`, `geometry-drip` | `documents`, `rag_local`, extracted text | T1 | dedup + provenance on write |
| Propose facts → gate → `matter_facts` | `verify` / `verify-worker`, `comprehend` | knowledge layer | **T2** | provenance write-gate + **`ontology_validator` V3/V4** |
| Entity-canon merge / rename | `cross-client` (`entity_resolve --apply-auto`, `--apply-canon`) | `entities` canon | **T2** | verification_lock + confidence; **watch-item (§3)** |
| Regenerate `SYSTEM_CONSTITUTION.md` | `cross-client` (`constitution_generator --write`) | the system's knowledge boundary | **T2** | generated only from `_safe` views |
| Parcel area audit | `parcel-audit` | `parcels.area_flag` only | T1 | writes a flag, never geometry |
| Surface deadlines / proactive nudges | `deadline-refresh`, `proactive` | `surfaced_deadlines`, alerts | T1 | read-mostly |
| Ontology + inference health | `ontology-check`, `inference-sentinel` | `holes_findings` (alert rows) | T1 | best-effort, never blocks |
| Daily digest | `digest` (`build_digest.py`) | **outbound to Jonathan only** | T1 | S14 (single operator recipient) |
| Inbound email/channel ingest | `email-bridge` | inbound → corpus | T1 | **send held** (inbound only) |
| Leo Telegram replies | n8n AI-Agent node | outbound text to operator/authorized | **T2** | S14 + sim gates (S1–S4) |
| Spend metering | `spend-bridge` | `llm_spend` (internal) | T1 | read/record only |

### Human-gated — NEVER autonomous (the T3 invariant made explicit)

| Action | Held by | Ceiling the system may reach |
|---|---|---|
| File an ARTA / Ombudsman / court pleading | agent charter + engine `status` cap | *drafted, `held_for_filing`* |
| Send a demand letter / manifestation | agent charter | *draft handed to Jonathan/counsel* |
| Contact a party / witness / court / official | agent charter | *never* |
| Expose a client map / portal externally | `mapping-agent` + switch-off | *seeded, switch OFF* |
| Provision an external channel (WhatsApp/Viber/Email-send) | token switch-hold | *code-ready, unprovisioned* |
| Mark anything "filed" / advance status to `filed` | engine status cap | *`held_for_filing`* |

---

## 3. Watch-list — the genuine execution-governance surface (5 autonomous writes worth explicit eyes)

These are all **internal, gated** — but they are the autonomous actions whose *silent* error would compound,
so they are named here for explicit oversight (each already has, or now has, a detector):

1. **Fact promotion → `matter_facts`** — mitigated by provenance gate + `ontology_validator` V3 (grounding). ✅
2. **Cross-client fact/link writes** — `ontology_validator` V4 caught 6 mis-filed Paracale facts on day one. ✅ detector live
3. **Entity-canon auto-merge** (`cross_client_sentinel --apply-canon`) — a wrong merge silently corrupts identity resolution. *Control: `verification_lock`; recommend a periodic "auto-merges last 24h" line in the digest.* ⬜
4. **`comprehend` high-confidence overwrite of title status** — a confident-but-wrong OCR read overwrites a default. *Control: reconciles vs. verified `title_chain`; low-conf flags operator.* ✅ (per `title-comprehension-layer`)
5. **Constitution regeneration** — auto-rewrites the system's knowledge boundary. *Control: `_safe`-views only; recommend a diff-summary on regen.* ⬜

The two ⬜ items are the only *net-new* governance suggestions this registry surfaces — both are **cheap
digest/log additions**, not enforcement systems.

---

## 4. Scope — what this registry is NOT

- **Not a runtime action-gating engine.** The gates already exist (agent charters, S14, provenance gate,
  `ontology_validator`, switch-holds). Building a separate execution-governance runtime would duplicate
  them and is *ahead of need* — the invariant §0 holds today without it.
- **Not a rewrite of the agent charters.** Those are the authoritative source; this doc *indexes* them.
- **Enforcement stays where it is** (DB triggers + charters + S14), for the same reason the ontology gate
  stays in Postgres: a doc that agents "should consult" binds nothing; the invariant is bound by the
  charters + switch-holds + gates, and this registry just makes it legible and auditable.

**Change log**
- v0.1 (2026-07-05) — first grounded registry; codifies the no-autonomous-outward-action invariant;
  2 net-new cheap watch-items (canon-merge visibility, constitution-regen diff).
