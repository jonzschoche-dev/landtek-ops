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

## 1. The five logical layers

Every line in `ONTOLOGY.md` belongs to exactly one of five layers. They answer five different
questions and must never be blended within a section.

| Layer | Question it answers | Where it lives today |
|---|---|---|
| **I. Core Concepts** | *What concepts exist, and which table is canonical for each?* | §2 concept registry (§2.1–§2.3, §2.7) |
| **II. Invariants** | *What must always be true, and is it enforced or merely asserted?* | §4 (the A-series) |
| **III. Domain Models** | *How does one domain work end-to-end — concepts, states, components, invariants?* | §2.4 + §2.8–§2.13 (full-rigor domain sections) |
| **IV. Cross-Cutting Concerns** | *What spans every domain — provenance, tenancy, governance, access?* | §1, §5, §6 |
| **V. Component Mapping** | *Which agent/service reads and writes which concept?* | §8 Oriented Map + `agent_concept_map.py` (derived) |

**Supporting layers:** **Drift/Legacy** (§3 — do-not-write tables) and **Future Domains** (§9 — planned,
unbuilt) bracket the live content. **Maintenance** rules live in this file (§6 below).

> **Rule of placement.** A registry *row* (concept → canonical table) goes in Layer I. A *full domain
> write-up* (definition + concept table + invariants + component mapping) goes in Layer III. If a domain
> is important enough to have its own agents, it earns a Layer III section; until then it is a Layer I row.

---

## 2. Target table of contents

The clean structure the document converges toward. Existing section numbers are **stable** (referenced
across the codebase and memory) — we grow by *adding*, not renumbering. New domains append to §2 (as
§2.N) and, when they mature, get a Layer III model.

```
0.  Ground planes .......... domain vs n8n plumbing (never model across)
1.  The organizing axiom ... document = source of truth; provenance vocabulary   [Layer IV]
2.  Concept registry ....... canonical table per concept, grouped by family      [Layer I + III]
      2.1  Corpus / provenance root
      2.2  Real-world actors & tenancy
      2.3  Title / chain-of-title
      2.4  Geometry / Mapping                 (Layer III — full model)
      2.5  Knowledge / claims / facts
      2.6  Strategy / matter reasoning
      2.7  Interface / comms
      2.8–2.13  Domain models                 (Layer III — Case Theory … Truth & Reconciliation)
      2.N  <next domain>                       ← new domains append here
3.  Drift / legacy ......... do-not-write tables + consolidation backlog          [Supporting]
4.  Invariants ............. the A-series (system + domain), with enforcement     [Layer II]
5.  Client isolation ....... the tenancy firewall                                 [Layer IV]
6.  Access-model note ...... LandTek access vs n8n RBAC                           [Layer IV]
7.  How to regenerate ...... re-grounding protocol                               [Maintenance]
8.  Oriented Operational Map  concept → purpose → connection → state              [Layer V]
9.  Future Domains ......... planned, unbuilt (○ placeholders)                    [Supporting]
```

> **Known convergence debt (documented, not urgent):** (a) a duplicate `§2.6` heading (Strategy vs the
> deploy_719 "Gated-core" addendum) should be renamed on the next major bump; (b) §8's Oriented Map
> overlaps the §2.8–§2.13 domain models — as each domain graduates to a Layer III model, its §8 row
> becomes a one-line pointer. Neither is load-bearing; both are tracked in the change log.

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

When a domain earns a Layer III model, copy this skeleton verbatim and fill it in. Match the voice of
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

## 5. Invariant conventions (Layer II)

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
  so Layer V can't silently drift from reality.
- Re-ground rowcounts before trusting any older than a few weeks; the header dates the last grounding.

**Golden rules (learned the hard way):**
1. **Generate, don't hand-curate.** Completeness claims must be mechanically verified (a hand-curated §8
   once silently missed 100 populated tables). If you can't check it, don't assert it.
2. **Grow by appending.** Add §2.N and A-numbers; never renumber live sections — cross-references break.
3. **Honesty over optics.** 🟡/○/**flagged** is the correct state for unbuilt or unenforced things; a
   wall of green that isn't true is worse than an honest amber.
4. **A domain earns its Layer III model when it earns agents.** Until then it is a Layer I row or a §9
   Future-Domains placeholder — don't over-model vaporware.
5. **One concept, one canonical table.** Two tables for one concept ⇒ one is 🔴 drift; record it in §3.

**Adding a new AI agent/service:** register what it reads/writes (it will appear in `agent_concept_map`),
confirm every table it writes is a named concept (or add it), and confirm it inherits the system
invariants (§5) — especially client separation and the outward chokepoint. No agent ships outside those.
