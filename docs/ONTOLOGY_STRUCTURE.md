# ONTOLOGY.md — Structure, Conventions & Growth Guide

> **Purpose.** This is the *constitution for the ontology document itself* — how `ONTOLOGY.md` is
> organized, how a new domain or invariant is added, and how the file stays trustworthy as LandTek
> grows from a single-matter legal engine into a full Philippine property platform (titles, document
> intelligence, client comms, calendar, tenant management, payments, construction, case theory, and a
> fleet of AI agents). `ONTOLOGY.md` holds *content*; this file holds the *rules for the content*.
>
> **Design goal:** the ontology must grow **gracefully** — a new agent or service should slot into a
> known place with a known template, never force a renumber, and never silently drift from the live
> schema. Structure is what makes a 13-domain ontology as legible as a 3-domain one.

---

## 1. The named sections

Every line in `ONTOLOGY.md` belongs to exactly one **named section**. Each answers a different question
and must never be blended with another. *(Earlier drafts labelled these "Layer I–V"; the Roman numerals
were dropped — plain section names are clearer to reference.)*

| Section | Question it answers | Content granularity |
|---|---|---|
| **Core Concept Registry** | *What concepts exist, and which table is canonical for each?* | lightweight rows (concept → 🟢 table → notes) |
| **Domain Models** | *How does one domain work end-to-end — concepts, states, components, invariants?* | full rigor (mature, agent-heavy domains only) |
| **System Invariants** | *What must always be true, and is it enforced or merely asserted?* | the A-series, one monotonic registry |
| **Cross-Cutting Concerns** | *What spans every domain — client isolation, provenance, exposure, access?* | universal rules, one home each |
| **Component Mapping** | *Which agent/service reads and writes which concept?* | mostly *derived* (`agent_concept_map.py`) |
| **Future Domains** | *What is planned but not yet built?* | ○ placeholders, one line each |
| **Maintenance & Evolution** | *How does the ontology grow and stay honest?* | rules (this file) |

> **Rule of placement.** A concept starts life as a **Future Domain** placeholder, graduates to a
> lightweight **Registry** row when it gets a canonical table, and earns a full **Domain Model** only once
> it has meaningful agents, invariants, or governance requirements. A registry row that never grows agents
> stays a registry row — do not over-model. (Full lifecycle in the Domain Progression Model, §2.1 below.)

---

## 2. Target table of contents (the v1.0 structure)

This is the clean structure the document converges toward — the physical split of the lightweight
registry from full domain models. **It is the target for the planned v1.0 major bump, NOT the current
live numbering** (see §6, Migration to v1.0). The live doc reaches it in one mechanical migration, not
piecemeal.

```
1.  Purpose & Design Principles ... why this ontology exists + how to use it
2.  Core Concept Registry ......... fast lookup: canonical table per concept (lightweight rows)
      2.1  Corpus & Documents
      2.2  Actors, Clients & Tenancy
      2.3  Land Titles & Property
      2.4  Geometry & Mapping
      2.5  Facts & Provenance
      2.6  Communications
      2.7  Supervision & Workflow
      2.N  <lightweight registry entries append here>
3.  Domain Models ................. full rigor — MATURE, agent-heavy domains only
      3.1  Property Mapping & Geometry
      3.2  Document Intake & Corpus Connectivity
      3.3  Entity Resolution & Canonical Knowledge Base
      3.4  Client & Matter Separation
      3.5  Fact Harvesting & Truth
      3.6  Supervision & Governed Actions
      3.7  Communications & Platform Coordination
      3.N  <mature domains append here>
4.  System Invariants ............. the A-series, one monotonic registry, enforcement-marked
5.  Cross-Cutting Concerns
      5.1  Client Isolation
      5.2  Provenance & Truth
      5.3  External Exposure & Governance
      5.4  Access Control & Visibility
6.  Component Mapping ............. concept ↔ agent/table (derived from agent_concept_map.py)
7.  Future Domains & Planned Capabilities ... ○ placeholders
8.  Maintenance, Evolution & Governance Rules
```

**Why this beats the current layout:** it separates the lightweight **Registry** (fast lookup, grows
often) from full **Domain Models** (heavy, mature-only), so the document stays legible as it scales to
many agents; it gives invariants and cross-cutting rules dedicated homes instead of scattering them
across §1/§5/§6; and it makes the growth lifecycle (§5) explicit.

### Current → target section map (for the v1.0 migration)

| Current (live) | Target (v1.0) |
|---|---|
| §0 Ground planes + §1 Axiom | §1 Purpose & Design Principles (+ the axiom stays as a principle) |
| §2.1–§2.3, §2.5–§2.7 registry rows | §2 Core Concept Registry |
| §2.4, §2.8–§2.14 domain models | §3 Domain Models (§3.1–§3.N) |
| §4 Invariants (A-series) | §4 System Invariants *(A-numbers unchanged)* |
| §1 provenance + §5 client-iso + §6 access | §5 Cross-Cutting Concerns (5.1–5.4) |
| §8 Oriented Operational Map | §6 Component Mapping |
| §9 Future Domains | §7 Future Domains |
| §3 Drift/legacy + §7 regenerate + this file | §8 Maintenance, Evolution & Governance |

> **Invariant A-numbers never change** across this migration — only section numbers move — so every
> mechanical guard that cites `A5`/`A7`/`A15` (the `truth_tests`) is migration-safe.

### 2.1 Domain progression model (the lifecycle every domain follows)

A domain is never born a full model. It earns its place by maturing through four stages — this prevents
ad-hoc growth and keeps the heavy §3 Domain-Models section reserved for things that actually have agents.

| Stage | Lives in | What it is | Example |
|---|---|---|---|
| **1 · Future / Planned** | §7 Future Domains | a placeholder — name + one-line intent, ○ marker, no schema | Payments, Construction, Tenant Management |
| **2 · Registry Entry** | §2 Core Concept Registry | lightweight: canonical table(s) + basic notes; concept exists and is written | most current §2 rows |
| **3 · Full Domain Model** | §3 Domain Models | complete: definition + concept table + component mapping + 2–3 invariants | Property Mapping, Document Intake, Communications |
| **4 · Deprecated / Legacy** | §8 Maintenance (Drift/Legacy) | superseded; marked 🔴 with its canonical successor named | `audit_log`→`truth_audit_log`, `chain_of_title`→`title_chain` |

> **Promotion rule.** A domain advances **2 → 3 (earns a full model) only when it has meaningful agents,
> invariants, or governance requirements.** Until then it stays a registry row (stage 2) or a placeholder
> (stage 1). Demotion (3/2 → 4) happens the moment a canonical successor exists — record it, don't delete
> it (carry the lineage). Every promotion is a version bump + change-log entry + a green `--coverage`.

---

## 3. State markers (the single controlled vocabulary)

Every concept in a domain model carries exactly one state marker. Do not invent new glyphs.

| Marker | Meaning | Use when |
|---|---|---|
| 🟢 | **Canonical / active** | the table is the write target and is populated/live |
| 🟡 | **Partial / staging / underused** | schema exists but feeds a canonical, is sparsely used, or is dormant |
| 🔴 | **Drift / legacy** | do **not** write here; a canonical successor exists (list it in §3) |
| ○ | **Planned** | net-new; no schema yet — **do not build without governance sign-off** |
| ⛔ | **Intentionally schema-less** | an invariant, not a store (e.g. ephemeral device location) |

**Enforcement markers** (used in §4 invariants, distinct from state): 🟢 **ENFORCED** (DB trigger / NOT
NULL / constraint), 🟡 **asserted** (mechanical test or documented, not blocked at write), **flagged**
(a known gap awaiting a decision), **shadow** (logging-only, pre-enforcement), **doctrine** (a standing
policy enforced by process, e.g. mechanical-over-LLM).

---

## 4. The new-domain template (copy-paste)

When a domain earns a full Domain Model (§3), copy this skeleton verbatim and fill it in. Match the voice of
§2.4 / §2.10 exactly: one-sentence definition, a state-marked concept table, a component-mapping line,
and 2–3 invariants continuing the A-series.

```markdown
## 2.N <Domain Name> — *<one-line essence, in italics>*

> **Definition.** <One sentence: what this domain is, what it turns an input into, and where it sits
> between adjacent domains (cross-reference §X).>

| Concept | Canonical home | State | Notes |
|---|---|---|---|
| <Concept 1> | 🟢 `table_a` (rows) | active | <what it holds; key columns> |
| <Concept 2> | 🟡 `table_b` (rows) | partial | <why partial; what it feeds> |
| <Concept 3> | ○ `planned_table` | **NET-NEW** | <held behind governance; the switch> |
| <Concept 4> | ⛔ schema-less by design | invariant | <why never persisted> |

*Components: `agent_x` · `service_y` (the code that reads/writes these). **Invariants: A<n>–A<m>.***
```

**Checklist before adding a domain (all mechanical):**
1. **Ground it.** Query live rowcounts (`pg_stat_user_tables`) — never author counts from memory.
2. **Name the canonical table** for every concept; if two tables overlap, one is 🔴 → add it to §3.
3. **Assign states honestly** — 🟡/○ are not failures; an unbuilt concept marked ○ is *correct*.
4. **Write 2–3 invariants** (§5 below) and add them to §4 with an honest enforcement marker.
5. **Add the component-mapping line** so `agent_concept_map.py` and the doc agree.
6. **Bump the version + change log** (§6). Run `ontology_check.py --coverage` — it must stay green.

---

## 5. Invariant conventions

Invariants are the load-bearing part of the ontology: they are what a mechanical guard can check.

**Numbering.** One monotonic series, `A1, A2, …`, never reused or renumbered. Each invariant is one
sentence stating what must *always* hold, plus an enforcement marker. Domain sections reference their
invariants by number; §4 is the single registry.

**Two tiers.** Tag each invariant so the system-level ones are visible at a glance:
- **System invariants** — hold across *every* domain and every new agent. These are non-negotiable and a
  new domain inherits them for free. (See the recommended set below.)
- **Domain invariants** — specific to one domain's concepts.

**The enforcement ladder (always drive an invariant up it):**
```
documented → asserted (mechanical test) → shadow (logged) → ENFORCED (blocked at write)
```
Prefer **DB-resident enforcement** (triggers / constraints) so *every* writer is bound — Python workers,
`psql`, and the n8n LangChain.js path alike. A guard that lives in one application path is not an
invariant, it is a hope. When enforcement isn't yet possible, a **`truth_tests/` assertion** (deploy-gate
+ nightly) is the mechanical floor — and it must be **negative-tested to bite** before it counts as 🟢.

**Recommended SYSTEM-LEVEL invariants** (every domain, present and future, inherits these):

| Theme | Invariant (must always hold) | Canonical enforcement |
|---|---|---|
| **Provenance** | Every fact-bearing row carries a `provenance_level`; `verified` ⇒ cited doc + verbatim excerpt. | A1/A2/A20 (triggers) |
| **Client separation** | Every matter/doc/fact/geometry belongs to exactly one client; nothing crosses except via an audited allowlist. | A5/A9/A16/A18 |
| **Immutability** | A locked/cited row is immutable until explicitly unlocked. | A4 |
| **Temporal integrity** | No instrument is executed by an actor outside their lifespan. | A3 |
| **Governance / outward** | Every outward action funnels through one fail-closed chokepoint; a governed step only runs on a governed path. | A21/A22 |
| **Truth is mechanical** | Truth invariants are checked by deterministic tests + triggers, never a standing LLM harness. | A24 (doctrine) |
| **Inbox ≠ ledger** | Proposed/candidate rows are never authoritative; only gated ledgers are quoted downstream. | A19 |
| **Offline sovereignty** | Every guard degrades to a safe hardcoded floor if its config/DB is unreachable. | doctrine |

A new domain that touches money, tenants, or construction does **not** get to re-litigate these — it
inherits them and adds only its domain-specific invariants on top.

---

## 6. Maintenance & evolution

**Versioning (semver, already in the header):** *patch* = a new alias/deprecation/rowcount re-ground;
*minor* = a new concept class or domain section; *major* = a canonical table changes or sections renumber.

**Change log:** one dated entry per version at the foot of `ONTOLOGY.md`, newest first, naming the
sections/invariants touched and *why*. The change log is the audit trail — never rewrite history.

**Re-grounding protocol (the anti-drift guarantee):**
- `ontology_check.py --coverage` — every populated domain table must be named in the map (200/200 today).
  Wired to the daily sentinel; a new unnamed table raises a finding. **"Nothing orphaned" is a check, not a claim.**
- `agent_concept_map.py --triage / --review / --orphans` — derives the concept↔agent binding from code+DB,
  so Component Mapping (§6) can't silently drift from reality.
- Re-ground rowcounts before trusting any older than a few weeks; the header dates the last grounding.

**Golden rules (learned the hard way):**
1. **Generate, don't hand-curate.** Completeness claims must be mechanically verified (a hand-curated §8
   once silently missed 100 populated tables). If you can't check it, don't assert it.
2. **Grow by appending.** Add §2.N and A-numbers; never renumber live sections — cross-references break.
3. **Honesty over optics.** 🟡/○/**flagged** is the correct state for unbuilt or unenforced things; a
   wall of green that isn't true is worse than an honest amber.
4. **A domain earns its full Domain Model when it earns agents.** Until then it is a registry row or a §9
   Future-Domains placeholder — don't over-model vaporware.
5. **One concept, one canonical table.** Two tables for one concept ⇒ one is 🔴 drift; record it in §3.

**Adding a new AI agent/service:** register what it reads/writes (it will appear in `agent_concept_map`),
confirm every table it writes is a named concept (or add it), and confirm it inherits the system
invariants (§5) — especially client separation and the outward chokepoint. No agent ships outside those.

### 6.1 Migration to v1.0 (the deferred renumber — planned, not now)

The v1.0 target TOC (§2) physically splits the registry from domain models and gives cross-cutting rules
their own section. It is the right end-state — but it is a **`major` bump that renumbers live sections**,
so it is executed **once, mechanically, deliberately — not piecemeal and not yet.**

**Reference-breakage cost (measured 2026-07-06):** ~15–20 external references to ONTOLOGY section numbers
across ~6 files (`ontology_check.py`, `agent_concept_map.py`, `test_superseded_tables_empty.py`,
`ontology_validator_spec.md`, the `*_INTEGRATION.md` docs) + ~19 internal `§8.x` self-references. All
mechanically fixable with the §2 current→target map. **The A-series numbers do not move**, so every
`truth_tests` guard is migration-safe.

**Why deferred — one live blocker (checked, not assumed):**
- **Concurrent authorship.** The ontology is under **active, high-cadence authorship by a parallel
  session** — ONTOLOGY.md shipped v0.10→v0.13 across deploy_736–739 at roughly one push every ~8 minutes,
  and that session is itself **reconciling the A-series numbering** (A25–A33, "A20–A23 reconciled"). A
  whole-doc renumber now would collide on the peer's next push and risk corrupting their in-flight
  invariant reconciliation. **This is the only gate: migrate the moment ONTOLOGY.md commits go quiet**
  (a settle window of clean status + no new commits, not a calendar date). *(An earlier draft also cited
  the pre-Aug-12 litigation window; that is not a constraint — the sole real gate is authorship quiescence.)*

**Execution plan when both clear:** (1) branch; (2) apply the §2 current→target map in one pass; (3) `sed`
the ~35 references using the map; (4) run `ontology_check.py --coverage` (must stay green) + the full
`truth_tests` suite; (5) `major` version bump + change-log entry. Until then, keep growing under the
current numbering by **appending** — the target structure is the compass, not a same-day action.
