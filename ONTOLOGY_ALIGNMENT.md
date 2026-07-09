# ONTOLOGY ↔ MASTER_PLAN — Alignment Bridge

> **Purpose.** The living bridge between **execution** (`MASTER_PLAN.md` — what we're building and when)
> and **governance** (`ONTOLOGY.md` — the concepts, canonical tables, and invariants that keep it honest).
> Neither file should drift from the other. `MASTER_PLAN` says *do X by Aug 12*; this file says *X is
> governed by concept §2.N and invariants A-k*, and flags where a plan item has **no** governance yet.
>
> **Grounded 2026-07-07** against `MASTER_PLAN.md` (v — Aug-12 north star, 7 pillars §4A) and `ONTOLOGY.md`
> v0.17 (concepts §2.1–2.16, invariants **A1–A40**, structure guide `docs/ONTOLOGY_STRUCTURE.md`).
> **Honesty rule:** this document does **not** overstate alignment. A pillar with no invariant is named as a gap.

---

## 1. Current state of divergence (honest assessment)

The two documents are **partially aligned**, and the alignment is **lopsided toward the governance-heavy
domains**:

- **Well-aligned (concept + invariants exist and match the plan):** Evidence & Knowledge (pillar 1),
  Legal Case Mgmt (pillar 2), Platform/Client-separation + Omnichannel (pillar 7), plus the net-new
  Mapping, Client Projection, and Ombudsman dimensions. These have real ontology domains (§2.1–2.16) and
  live invariants (A1–A40).
- **Plan-only, no ontology model (the real divergence):** Finance & Accounting (pillar 3), Property/Tenant
  Mgmt (pillar 4), and Forensic & Compliance (pillar 6) exist in the MASTER_PLAN roadmap but have **no
  domain model and no invariants** — some sit on *drift* tables (`finance_transactions` is §3 drift).
- **Structural disconnect (both directions):** `MASTER_PLAN.md` references **zero** A-numbers — execution
  items are not tied to the invariants that should govern them. Conversely `ONTOLOGY.md` names deploys but
  not MASTER_PLAN pillars/waves. The two are maintained in parallel, not in lockstep.
- **Connectivity domain — now modeled (deploy_760, was G4):** the §6B *Corpus Connectivity* work is modeled
  as ONTOLOGY **§2.17** with invariants **A41–A43** (all-5-signals · `model_used` earned · gate fail-closed).
  The last follow-on — the shadow **V8** DB write-guard on `model_used` — is now **BUILT (deploy_769, `log` mode)**,
  so this domain is fully modeled AND enforced (gate + batch + write-guard). Connectivity has no remaining ontology gap.

> **▶ Governance → Ontology desk — handoff/report (2026-07-08, deploy_773/774).** The **pilot-time V8→P0 alert
> is now ARMED** (governance-owned; mirror of the deploy_772 ingestion handoff). *Why it was needed:* V8 logs
> `ONTOLOGY_PROVENANCE_UNEARNED` via `ontology_reject`, which writes **every** finding at `severity='info'`, but
> `holes.p0_pusher` only Telegram-pushes `severity='P0'` — so a V8 finding (the O-pathway stamp-before-run
> corruption tripwire) would have sat **silent** during the `--stamp` pilot. *What governance added:*
> `scripts/v8_provenance_p0_elevator.py` + `landtek-v8-provenance-p0.timer` (3-min) — promotes any open V8 finding
> **info→P0** (so `p0_pusher` pages) and drops a **PAUSE-THE-PILOT** note into `notifications/pending.txt`,
> naming the doc (parsed from the finding text, since `ontology_reject` leaves `holes_findings.doc_id` null).
> Proven end-to-end with a synthetic finding; **dormant now (0 V8 findings)**. **It does NOT touch the V8 trigger
> or `ontology_reject`** — governance owns *escalation*, the ontology desk owns the *validator*.
> **Ownership, reaffirmed:** the ontology desk still owns the **V8 `log`→`block` flip** (`ontology_validator_config`
> `SET mode='block' WHERE check_code='V8'`) — execute **only** on the ingestion agent's clean-pilot request (shadow
> proves ordering before block enforces). Governance owns the P0 alert — **do not duplicate/alter it**.
> *FYI (not a request):* because `ontology_reject` writes all findings at `info`, V5/V6/V7 findings are likewise
> unescalated by `p0_pusher`; the elevator is intentionally scoped to V8/provenance (the pilot tripwire) only — if
> you want the others escalated, that's a separate ontology-desk decision. *Status:* pilot is Gemini-429-gated,
> **PILOT-READY=0**; provenance quota-stuck at 86.

**Net:** where a domain needs *governance* (isolation, provenance, exposure), the ontology leads. Where a
domain is *product roadmap not yet built* (finance/tenants/forensic), the ontology is silent — correctly
(don't model vaporware) but the plan should say so explicitly via a Future-Domains link.

---

## 2. Key gaps

| # | Gap | MASTER_PLAN says | ONTOLOGY says | Severity |
|---|---|---|---|---|
| G1 | **Finance domain unmodeled** | Pillar 3 (v1.5); `finance_transactions`, `v_matter_pnl/roi`, QuickBooks MCP | `finance_transactions` is 🔴 **drift** (§3); no Finance domain model, no invariant | 🟠 med — roadmap, but on a drift table |
| G2 | **Property/Tenant domain unmodeled** | Pillar 4 (v2.0); tenants/rent/leases | `property_assets` (83) only; no Tenant domain, no invariant | 🟡 low — genuinely future |
| G3 | **Forensic domain unmodeled** | Pillar 6; `fraud_indicators`, `forensic_hash`, OpenTimestamps | tables exist but no domain model / invariant (integrity, chain-of-custody) | 🟠 med — evidence-grade needs governance |
| G4 | ~~Connectivity domain not in ontology~~ **RESOLVED (deploy_760)** | §6B live plan; 5-signal connect-verify (86/1579) | **modeled §2.17 + A41–A43**; shadow-V8 write-guard BUILT (deploy_769) | ✅ closed |
| G5 | **No task→invariant linkage** | roadmap items, Wave 1/2 agents | invariants exist but plan never cites them | 🔴 high — the core alignment gap this file starts to close (§5) |
| G6 | **Client-projection enforcement** | pillar 7 "per-client Leo / product surface" | A32 🟡 (portal not fully rendering through projection) | 🟠 med — highest product-impact enforcement gap |
| G7 | **Structural debt in the ontology itself** | — | §2.6 duplicated; §2.8–2.16 authored as H2 (should be H3/§3.x) | 🟡 low — staged for the v1.0 migration (`ontology_migrate.py`) |

---

## 3. Alignment vision (target state)

1. **Every product pillar has an ontology home** — a §2.N registry row or full domain model, or an explicit
   §9 Future-Domains placeholder. No pillar is silently unmodeled.
2. **Every high-priority MASTER_PLAN item names its governing invariant(s)** — so a plan reader knows what
   *must always hold* while building it, and inherits the system invariants (client sep, provenance,
   outward chokepoint) for free.
3. **One monotonic A-series is the shared governance vocabulary** — the plan cites A-numbers; the ontology
   is their registry; `ontology_check.py --invariants` proves each names a real enforcement artifact.
4. **Divergence is mechanically visible** — a plan item touching money/tenants/forensic without an inherited
   invariant is a flagged alignment gap, not a silent one.

---

## 4. Phased alignment plan

**Short term (now → next few sessions, meta-layer only):**
- Keep this file current: on every ontology change, update §5 mapping; on every MASTER_PLAN roadmap change,
  check the touched pillar has an ontology home.
- ~~Model the Connectivity domain~~ **DONE (deploy_760: §2.17 / A41–A43; deploy_769: shadow-V8 write-guard on `model_used`).**
- Land the client-projection **A32 render-audit** guard (G6) — the highest product-impact enforcement.
- **Extended document/semantic model — GRADUATED (deploy_788).** `docs/DOCUMENT_MODEL_DRAFT.md` (the converged
  design of the ontology desk + ingestion agent, deploy_785/787) is now folded into ONTOLOGY **§2.17 + A44–A49**:
  DocumentSignal · DocumentClassification · DocumentRole · DocumentFiling/Inventory + the Semantic layer
  (Entity/Fact/Relationship). **A48 was grounded-corrected before graduating** — falsified as "fact ⇐ ConnectedDocument"
  (971 fact-source docs, 84 connected), re-asserted as fact-requires-`text` (`truth_tests/test_fact_requires_text.py`).
  Q6: `knowledge_graph_triples` canonical. Additive/design-only; `document_signals`/`document_classifications`/filing
  stores are ○ proposed (ingestion agent's to build, shadow-first). No new gap — formalizes reality + reserves the
  agentic/projection locus.

**Medium term (as pillars 3/6 get built):**
- Add a **Finance** registry row + move `finance_transactions` off drift → a canonical table + a
  cost/ledger invariant (G1). Add a **Forensic** domain model (integrity, chain-of-custody invariant) (G3).
- Execute the **v1.0 structural migration** (`ONTOLOGY_STRUCTURE.md` §6.1) — fixes G7 and gives Finance/
  Forensic/Tenants clean §3 domain-model slots.

**Long term (v1.5–v2.0):**
- Full **Tenant/Property** domain model when pillar 4 is built (G2).
- Drive the amber invariants (A18/A21/A25/A26/A31/A38–A40) up the enforcement ladder to `block`.
- MASTER_PLAN adopts A-number citations as a standing convention (§6 discipline below).

---

## 5. Task → invariant mapping (high-priority MASTER_PLAN items)

*The start of the shared vocabulary. "—" = **no governing invariant yet** (an alignment gap to close).*

| MASTER_PLAN item | Pillar | Ontology concept | Governing invariants |
|---|---|---|---|
| Grounded facts / citations / write-gate | 1 Evidence | §2.1 Corpus · §2.5/2.11 Facts | **A1, A2, A19, A20** (provenance/inbox≠ledger) |
| Legal case mgmt · dossier · chain-of-title | 2 Legal | §2.3 Titles · §2.8 Case Theory | **A3, A4, A7, A8, A13, A14** |
| Client separation · per-client surfaces | 7 Platform | §2.10 Client/Matter Sep | **A5, A16, A18** (client isolation) |
| Omnichannel go-live (Telegram→Email→Meta) | 7/Omni | §2.14 Communications | **A25–A31, A38–A40** |
| Client dashboard / product surface | 7 Platform | §2.15 Client Projection | **A32, A33, A34** + A11 (no external exposure) |
| Mapping (client parcel map, "locate me") | +Geo | §2.4 Geometry | **A9, A10, A11** |
| Ombudsman offense (RA 3019/6713) | 2/offense | §2.16 Offensive Leverage | **A35, A36, A37** |
| Supervision / Wave-1 agent wiring to Leo | 5 Proactive | §2.12 Supervision | **A21, A22** (outward chokepoint / governed step) |
| Corpus connectivity (§6B live plan) | 1 Evidence | §2.17 Document Connectivity | **A41, A42, A43** (defined; A42 shadow-V8 write-guard built deploy_769) |
| Truth invariants checked mechanically | all | — (doctrine) | **A24** |
| Finance & accounting / per-matter ROI | 3 Finance | *(none — G1)* | **—** *(gap: needs a cost/ledger invariant)* |
| Property / tenant management | 4 Property | *(none — G2)* | **—** *(gap)* |
| Forensic / signature-auth / OpenTimestamps | 6 Forensic | *(none — G3)* | **—** *(gap: needs an integrity/chain-of-custody invariant)* |

---

## 6. Recommendations for operating discipline (both sides)

1. **Plan cites invariants.** When MASTER_PLAN adds a roadmap item that writes client/fact/geometry/comms
   data, it names the invariant(s) it inherits (from §5). An item with a "—" is a governance gap to close
   *before* build, not after.
2. **No domain ships without an ontology home.** A new pillar/agent gets a §2.N registry row (or §9
   placeholder) + its reads/writes appear in `agent_concept_map --triage` + it inherits the system
   invariants (client sep, provenance, outward chokepoint). Enforced by `--coverage` (every populated table
   named) — keep it green.
3. **One monotonic A-series, one direction.** Never reuse/renumber an A-number; new invariants append. The
   plan and ontology share this vocabulary; `--invariants` proves each 🟢 names a real artifact.
4. **Honesty over optics, both files.** 🟡/○/flagged is the correct state for unbuilt/unenforced things.
   A wall of green that isn't true is worse than an honest amber. Build-status glyphs (`●/◐/○`) in the plan
   map to ontology state markers (🟢/🟡/○).
5. **This file is updated in the same commit as the change it reflects** — an ontology edit that adds an
   invariant updates §5 here; a plan edit that adds a pillar updates §2/§5 here. Drift between the three
   files is itself the failure this bridge exists to prevent.
6. **Meta-layer stays meta.** This bridge governs *concepts and invariants*, never case content or pipeline
   code. Enforcement changes (moving an invariant to `block`) are proposed here, executed as code/config by
   the live layer.

---

---

## 7. Mechanisms — how the plan references invariants (the standing practice)

The bridge is only useful if it's *operated*, not just written once. Three lightweight, machine-parseable
conventions turn §5 from a table into a habit:

**7.1 The `Respects:` tag (inline in MASTER_PLAN).** Every roadmap item, pillar, or agent that writes
governed data (client / fact / geometry / comms / matter) carries a one-line tag naming the invariants it
must honor:
```
- W1 Discovery agent → wire to Leo HIGH alert.   Respects: A5, A21, A22
- Client dashboard per-matter status view.        Respects: A5, A11, A32, A33, A34
- Finance ledger + per-matter ROI (v1.5).         Respects: —   (GAP: no cost/ledger invariant yet)
```
Parse: `Respects:\s*(—|A\d+(?:\s*,\s*A\d+)*)`. The tag lives *in the plan*, so a plan reader sees the
governance without cross-referencing — and a `—` is a visible, grep-able gap.

**7.2 The domain-admission gate (before a new domain/agent enters MASTER_PLAN).** A 3-question checklist,
answerable in a minute:
1. **Home?** Does it have an ontology concept (§2.N registry row) or a §9 Future-Domains placeholder? If no → add one first.
2. **Inheritance?** Does it inherit the system invariants — **A5** (client sep), **A1/A2/A20** (provenance),
   **A21** (outward chokepoint)? These are non-negotiable; a new domain never re-litigates them.
3. **New invariant?** Does it need a domain-specific invariant (e.g. Finance→cost/ledger, Forensic→
   chain-of-custody)? If yes → it's a `Respects: —` gap until that invariant is authored.
Fail any → the item is admitted **with an explicit `Respects: —` gap**, not silently.

**7.3 The `—` is a tracked gap, not a blank.** A `Respects: —` means *planned but ungoverned* — it must be
closed **before build**, not after. The live list of ungoverned-but-planned work is
`grep 'Respects: —' MASTER_PLAN.md`. Today that list is: **Finance (G1), Property/Tenant (G2), Forensic (G3)**.

**7.4 Optional mechanical guard (recommended, not yet built).** A `ontology_check.py --alignment` mode could
(a) grep MASTER_PLAN for governed items missing a `Respects:` tag, and (b) verify every `A#` the plan cites
exists in ONTOLOGY §4 (no dangling reference). This would make alignment a *check*, like `--coverage`. Flagged
as a small follow-on — meta-layer, in-lane.

## 8. Priority items to map now (active work — assign `Respects:` this cycle)

These are the near-term MASTER_PLAN items (Aug-12 focus + product surface) that should carry `Respects:` tags
immediately; the future pillars (Finance/Property/Forensic) stay `—` gaps until modeled:

| Priority | MASTER_PLAN item | `Respects:` |
|---|---|---|
| 1 | Client dashboard / per-client status + next-action (product surface) | **A5, A11, A32, A33, A34** |
| 2 | Legal case mgmt · dossier · chain-of-title (Aug-12 deliverable) | **A2, A3, A4, A13, A14, A20** |
| 3 | Wave-1 agent wiring to Leo (Discovery/Execution/Deadline/Narrative) | **A5, A21, A22** |
| 4 | Omnichannel go-live (Email→Meta/Viber) + PlatformCoordinator | **A5, A25–A31, A38–A40** |
| 5 | Mapping rollout (client parcel map) | **A5, A9, A10, A11** |
| 6 | Ombudsman offense (leads only, filing human-gated) | **A5, A35, A36, A37** |
| — | Finance / Property-Tenant / Forensic | **—** (close the gap before build — §2, G1–G3) |

---

*Companion files: `MASTER_PLAN.md` (execution) · `ONTOLOGY.md` (concepts + invariants) ·
`docs/ONTOLOGY_STRUCTURE.md` (how the ontology grows) · `ontology_check.py --invariants/--coverage/--structure`
(the mechanical guards that keep all three honest).*

## 9. Validator graduation checklist — the standing bar for every log→block flip (2026-07-09)

Codifies the `GovernanceHandoff` discipline (ONTOLOGY §2.12) that ran the V9/V10 composition flip
(deploys 801–804) — the template the ingestion agent executed and the desk verified. **Every future
flip (V5–V8 next) clears ALL five, in order:**

1. **Observation window** — ≥7d of shadow over an ACTIVE pipeline (`--shadow-status` 0-findings is
   necessary, not sufficient; a dormant pipeline or fresh guard is trivially clean — judge from the
   validator's deploy date + the guarded table's write traffic).
2. **Pre-flight query** — prove 0 existing rows violate the invariant (the flip must not strand live data).
3. **Rolled-back exception test** — in a transaction, force a violating write in block mode, confirm the
   exception RAISES, roll back. Enforcement proven, no state changed.
4. **Scope note** — the ONTOLOGY §4 row states exactly WHICH table(s) the trigger guards today and what
   it extends to later (never claim a phantom table is guarded — the A54 `filing_exhibits` lesson).
5. **Desk verification + record** — the ontology desk independently re-grounds mode+trigger
   (`ontology_check.py --enforcement` now makes this mechanical) and records the graduation in the
   invariant row + the handoff doc.

**Post-flip standing check:** `--enforcement` (deploy_806) verifies every §4 mode CLAIM against the live
config + `ontvv_v*` triggers — phantom enforcement (doc claims block, validator un-flipped/dropped) fails
the check + writes a `phantom_enforcement` finding via the daily sentinel. First run caught 3 stale
under-claims (A2/V3 was already block; A9/V6 was already applied) — both rows re-grounded same day.

**Open governance-desk item — blocked-write visibility:** V3/V4/V9/V10 now `block` in production, but a
rejected write only raises to the writer; nobody else learns it fired. Build: a daily digest line
("N writes blocked by Vn this week") sourced from the validators' exception path (extend `ontology_reject`
to log block-mode RAISEs, not just log-mode findings). Passive-tier visibility only — per-event paging
stays reserved for validators with an active supervised operation (the V8-elevator discipline).
