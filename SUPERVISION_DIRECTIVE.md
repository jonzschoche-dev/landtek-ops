# SUPERVISION DIRECTIVE — how the ~52 agents coordinate through the Supervisor

> **Purpose.** The rules by which every agent connects to the Supervisor so the fleet is *coordinated*
> and *governed* — without turning the Supervisor into a puppet-master or a framework. This is the
> operating contract for agent authors. Companion to `GOVERNED_ACTIONS.md` (what's allowed) and
> `ONTOLOGY.md` (what's true). The Supervisor = `scripts/supervisor.py` + the `work_orders` table.
>
> **Version 1.0 (2026-07-06).**

---

## 0. The one principle

> **The Supervisor coordinates by TIER, not by controlling every agent.** It is a **coordination spine**
> — the single ledger of *consequential work in flight*, the uniform enforcer of the governed path, and
> the keeper of the connection contract. It is **NOT** a scheduler, **NOT** a framework, and **NOT** a
> caller of the 52 agents. Most agents keep running on their own timers; only their *consequential* work
> passes through the spine.

Why tiered: putting all 52 agents under per-action work orders would recreate the very sprawl the stack
has burned on. Reversible internal work does not need a governor; consequential and outward work does.

---

## 1. The tiered coordination model (READ THIS FIRST)

Classify every agent's **actions** by tier (`GOVERNED_ACTIONS.md`), and connect accordingly:

| Tier | Example agents/actions | How it connects to the Supervisor |
|---|---|---|
| **T0 / T1** — read-only, reversible, internal | OCR/backfill, embed, classify, verify_worker, comprehend, sentinels, geometry, dedup | **Stay autonomous on their timers. REPORT health only** (heartbeat). The Supervisor *observes* — it does **not** gate each action. Do not create a work order per document. |
| **T2** — writes knowledge/canon, proposes, or messages the operator | fact promotion, entity-canon merge, constitution regen, strategist gathers, ombudsman leads, matter-plays | **Register a work order for the consequential unit.** The write/propose passes the Supervisor's gates (derive-at-birth + connection/provenance). The order is the coordination point. |
| **T3** — outward / irreversible | file a pleading, send to a party/court, expose a client view, mark "filed" | **MUST route through the Supervisor and HOLD fail-closed for a human.** Never self-executed. Ceiling = `held_for_human`. |

**If you are a T0/T1 agent, you are already "coordinated" by reporting health — do not over-integrate.**
**If you touch T2/T3, your work is not real until it is a `work_order`.**

---

## 2. The connection rules (every T2/T3 agent honors these)

1. **One work-state ledger.** `work_orders` is the *single* record of consequential work in flight.
   No T2/T3 action exists outside it. If it's not a work order, it didn't happen — and no other agent
   can see, coordinate, or govern it.
2. **Derive at birth, don't assert.** A work order must trace to a real source (a `gap_key` from
   `v_evidence_gaps`, a `--target doc:<id>`, an audited `--override`). Free-text/phantom work is refused
   at enqueue. Gaps and facts are *queried*, not invented.
3. **Fail-closed governance.** Any T3, outward-verb, or untagged step is held for a human automatically.
   No agent reimplements this and no agent bypasses it.
4. **Connect-or-reject.** An agent's output that changes the corpus must pass the connection gate
   (provenance stamped · re-scored · re-embedded · typed) or the order is held. Half-integrated output
   is never accepted (the `connect-verify` pattern).
5. **Handoffs are explicit.** Frontier-reasoning or human steps are `handoff`/`T3` — a session or human
   does them and reports back via `supervisor.py complete/resolve`. The Supervisor never fakes a step it
   cannot deterministically run. (Existing agents are queue-daemons, not callable functions — so `auto`
   step execution is deferred; do not assume the Supervisor can call your daemon.)
6. **No second source of truth.** Work, gaps, and pending actions live in the DB (`work_orders`,
   `v_evidence_gaps`, the registers) — **not** in prose worklists or markdown. A gap in a `.md` file is
   invisible to the fleet and unenforced. Retire or derive such lists.
7. **Idempotent + resumable.** State lives in the row (steps + `current_step` + `audit`), so work
   survives a restart and any agent can resume it. Nothing consequential lives only in an agent's memory.
8. **Degrade, don't crash.** Report status even when idle; distinguish *expected-idle* from *failure*;
   keep `systemctl --failed` at zero. A supervised agent that dies silently is worse than one that holds.

---

## 3. How to connect an agent (the mechanics)

1. **Declare your work-kind** in `supervisor.py` `KINDS` — its typed steps, each with `mode`
   (`handoff` | `check` | `auto`) and `tier` (`T0`–`T3`). Routing is *data*, not code.
2. **Own your step(s).** Name your agent on the step it performs. The Supervisor surfaces the order to
   you (`list --awaiting`); you do the work and report (`complete`/`resolve`/`cancel`).
3. **Tag tiers honestly.** A mis-tagged T3-as-T1 is caught by fail-closed defaults, but tag correctly —
   the tier *is* the governance.
4. **T0/T1 agents: skip all of the above.** Just keep your heartbeat current so the Supervisor can see
   you're alive. Health, not work orders.

---

## 4. What the Supervisor guarantees back to the fleet

- **One view of all consequential work** and its state (`supervisor.py status` / `list`).
- **Uniform governance** — every agent gets fail-closed T3 holds for free; none reimplements it.
- **An audit trail** on every transition (who/what/when), so coordination is legible and reviewable.
- **The connection contract** — a single definition of "correctly integrated into the corpus."

---

## 5. Scope guard — what the Supervisor is NOT (do not drift it)

- **Not the scheduler.** Timers + `agent_orchestrator.py` decide *when* agents run. The Supervisor tracks
  *work*, not cadence.
- **Not a framework.** It is a Postgres table + a loop — same primitives as everything else. No LangGraph.
- **Not a puppet-master.** It does not call the 52 agents; agents report to it. (Queue-daemon reality.)
- **Not a home for T1 churn.** Do not file a work order per embedding/OCR/verify. That is the sprawl trap.
- **Grow kinds only as real flows demand them.** Two flows today (`evidence_gap`, `ocr_remediation`);
  add a kind when a *real* consequential flow needs coordination — never speculatively.

---

## 6. The coordination invariant (one line)

> **Every *outward or irreversible* move the operation makes — legal filing, offensive complaint,
> message to a party/official/client, client-facing exposure, invoice/retainer, product release — is a
> T3 `work_order` held for a human, no matter which domain agent originates it. Internal work in every
> domain (analysis, drafting, mapping-audit, verification, OCR) stays autonomous under its own gate.**

The Supervisor is not a document coordinator — it is **the single governed chokepoint for the whole
operation's outward moves.** Documents/OCR are one lane; the coordination that matters spans all domains.

---

## 7. The fleet is more than documents — classification by domain × tier

The ~52 agents run a full legal/land-ops operation. Group them by DOMAIN, then apply the tier:

| Domain | Consequential move | Tier |
|---|---|---|
| **Evidence & knowledge** (verify, gaps, OCR remediation, contradiction) | promote fact · close gap | T2-write · T2-flow |
| **Legal strategy** (analyst, case_synthesizer, legal_agent, brief_drafter, cross_matter, strategist) | adopt a case theory · commit a prong | T2-flow |
| **Forums & procedure** (agency:ARTA/CIVIL/CSC/OMBUDSMAN, forum_router, execution_tracker, filing_monitor) | route to forum · **file a pleading** | T2 → **T3** |
| **Offense** (ombudsman_hunter) | rank officer · **file a Complaint-Affidavit** | T2 → **T3** |
| **Comms / omnichannel** (leo, channels, build_digest, correspondence) | message operator (T2/S14) · **message a party/official/client** | T2 → **T3** |
| **Client & matter mgmt** (matter_readiness, case_builder_ui, onboarding) | onboard matter · **expose a client cockpit** | T2-flow → **T3** |
| **Revenue & GTM** (revenue-engineer, retainers, ROI) | price a retainer · **send an invoice/retainer** | T2 → **T3** |
| **Mapping / geospatial** (mapping-agent, parcel audits) | plot/audit · **hand out a client map link** | T1 → **T3** |
| **Product / shipping** (ship-packager, product-hardener) | build surface · **expose it to a client** | T2 → **T3** |
| **Governance / QA** (truth-qa-gate, dossier_verify, cross_client_sentinel) | gate everything before it ships | T1 |

**Every "→ T3" cell above funnels through ONE governed kind: `outward_action`.**

## 8. The outward chokepoint — `outward_action` (the mechanism)

Any domain agent that wants to make an outward move does NOT send it — it enqueues:
```
supervisor.py enqueue --kind outward_action --target <domain:ref> --title "<what's going out>"
   # e.g. --target ombudsman:officer-X · forum:CV-26360 · client:MWK-portal · revenue:invoice-123 · map:parcel-Y
```
Flow: `prepare` (handoff — the domain agent drafts the artifact) → `approve` (**T3 — held fail-closed for a
human**). The system **never dispatches outward autonomously**; reaching `approve` means a human is cleared
to send. **One kind, domain-parameterized — not one kind per domain** (anti-sprawl). This is the single
place the whole operation's outward moves converge and are governed.

**Distribution of the fleet:** ~38 T1 (report health) · ~3 T2-write (DB write-gate governs them) ·
~10 T2-flow (register a work order) · every outward move → `outward_action`. So "connecting 52 agents"
is: ~41 just report health, ~10 register flows, and **all outward moves share one held chokepoint.**

## 9. GOVERNANCE HANDOFF — ontology desk → supervision desk (2026-07-09, deploy_806)

*Filed per the `GovernanceHandoff` pattern (ONTOLOGY §2.12): directive → grounded review → invariants →
recorded sign-off → explicit graduation trigger. The governing invariants are **A59** and **A61**
(ONTOLOGY v0.27, §2.18) — both 🟡 with the graduation conditions below. The ontology desk defines the
invariants; the supervision desk owns the build. Reply/sign-off in this section when picked up.*

### D1 — Supervisor Phase 2, scoped by A59 (governed task completion)
**Directive.** Wire LIVE work through `work_orders` — but only the work A59 actually governs: tasks that
are **deadline-bound or mutate governed data**. Start with the three that already have shapes:
`ocr_remediation` (a registered kind), `evidence_gap` (the enforced write-path exists), and deliverable
production (`dossier_pipeline`/`case_bundle` runs — the future A58 WorkProduct producers). Everything else
(report-health daemons, ~41 of the fleet) stays OUTSIDE work orders by design — do not wrap the world.
**Invariant honored:** every wrapped task reaches a terminal state — `done` / `held` / `failed`-with-reason —
never silently abandoned (A59). **Graduation:** A59 🟡→🟢 when live work runs through orders AND D2 is active.

### D2 — Stalled-order sentinel (the "or surfaces" half of A59)
**Directive.** A `work_orders` row past its review horizon (suggest: no state change in 72h while
non-terminal) writes a `holes_findings` row + a `notifications/pending.txt` line — the same surfacing
pattern as the offline/incorporation nightly steps. Mechanical, creditless, ~30 lines. Without this, Phase 2
just moves silent abandonment into a table; WITH it, "finishes or surfaces" is real.

### D3 — One enumerable fleet roster (prerequisite for A61's tier registry)
**Directive.** `scripts/agents.py` catalogs ~50 agents, but a second automation layer (~56 systemd/cron
scripts: `refresh_*`, sim, sweeps) runs OUTSIDE that roster. **A supervisor cannot supervise what it cannot
enumerate.** Merge both into ONE registry — one row per agent/script: name · kind (daemon/timer/cron/
on-demand) · **tier (T0–T3)** · owner · heartbeat source. This is deliberately ALSO the A61 substrate: once
tier is a column, a tier RAISE becomes a recorded row-change (metric evidence + human sign-off), and A61
graduates 🟡→🟢. Suggest: extend `agents.py` to emit/reconcile the registry rather than a new framework.
**Graduation:** A61 🟡→🟢 when the registry exists AND a documented tier-raise procedure references it.

*Sequencing suggestion: D3 → D2 → D1 (enumerate, then surface, then wire) — D3 is cheapest and unblocks the
other two. Nothing here is Aug-12-blocking; slot behind live-matter work per MASTER_PLAN §1 wartime posture.*
