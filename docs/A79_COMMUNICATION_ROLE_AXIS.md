# A79 — The Communication Role Axis (design, for review)

**Status:** DESIGN ONLY — no schema, no code, no ontology edit. For Jonathan's review before any build.
**Ties to:** A76 (relationship equilibrium / agentic relationship engine) · A75 (projection) · A71 (dose) ·
A21/A26 (outward gate) · A5 (client isolation) · the gate-as-contract (ARCHITECTURE.md / SUPERVISION_DIRECTIVE.md).
**Grounded 2026-07-12:** A79 is an open slot (highest live = A78). Comms spine populated (v_comms_interactions
4,945 / v_comms_relationship 21) but passive. COMM-AGENT-MAX + P2 not functionally built. No role-policy table.

---

## 1. The idea in one line

**A role is not a label — it is a policy vector that the gate reads to decide, for one recipient, how much
of the truth reaches them, in what form, how often, and whether a human must approve first.** The role axis
is the parameter source the projection boundary (A75/A71) and the outward gate (A21/A26) consume. It "feeds
both" the bot (COMM-AGENT-MAX) and the engine (A76/P2) by living at the **one exit both already pass through**
— not by being wired into each. One policy, one contract, every consumer bound.

## 2. Why it must exist BEFORE the engine and the bot

A76's core split: **accuracy lives internal (the full hot graph); gentleness lives external (each recipient's
dosed marginal increment).** The thing that decides *which side of that boundary a recipient sits on, and how
far* — is their role. If COMM-AGENT-MAX or P2 externalize before the role axis is at the gate, they emit
**ungoverned-by-role**: a counterparty (an adversary) could receive an auto-generated disclosure. So A79 is
the **precondition**, not a peer, of the functional builds. Build order: **A79 (contract) → COMM-AGENT-MAX
(perturb) → P2 (propagate)**, each externalizing only through the role-clamped gate.

## 3. Canonical role set (reconcile the three vocabularies)

Today three overlapping sets exist. A79 unifies them into ONE canonical set + an alias map (no data
migration — the map resolves legacy values at read):

| Canonical role | Side | Merges from | One-line meaning |
|---|---|---|---|
| `operator` | INTERNAL | channel_users `operator`; sim `owner` | you / the desk — full hot graph |
| `owner` | INTERNAL | channel_users `owner` | principal/beneficial owner of a matter — internal-grade |
| `counsel` | EXTERNAL-trusted | channel_users/approve `counsel` | engaged lawyer — highest external accuracy (they need detail) |
| `client` | EXTERNAL-served | channel_users/approve `client` | the served party — their own matter, gentle |
| `partner` | EXTERNAL-scoped | approve `partner` | collaborator (LGU ally, co-venturer) — scoped, no privilege |
| `prospect` | EXTERNAL-cold | approve `prospect`; sim `new_prospect` | pre-engagement — onboarding only |
| `counterparty` | ADVERSARY | channel_users `counterparty` | opposing party — **zero auto; human-authored + T3 only** |
| `unknown` | UNCLASSIFIED | channel_users `unknown`; sim `unauthorized` | not yet resolved — onboarding flow, never matter content |

*(Impersonators / sim shape personas stay refused as today — S1–S4, out of scope of client-bearing roles.)*
**Scope note:** role is per `(channel_user → mapped_client_code)`. A person who is counsel to one client and
counterparty to another is TWO `channel_users` rows (one per client), each with its own role — A5 already
keeps them separate, so role is never ambiguous within a client.

## 4. The policy vector — five orthogonal axes (this is the sophistication)

A role names a point in a 5-axis policy space; the table lets each axis be tuned + versioned independently:

| Axis | What it governs | Feeds which engine/gate step |
|---|---|---|
| **disclosure_ceiling** | the max content tier + which relationship-graph **edge types** may reach them | A76 propagation-to-recipient filter |
| **posture** | `auto` / `hold` / `never` — the default outward stance | A21/A26 gate decision |
| **dose_ceiling** | max marginal increment per metabolic window | A71 dose |
| **cadence** | when the engine may proactively surface to them | A76 `cadence_trigger` |
| **form** | HUMAN-narrative / MACHINE-typed / formal-legal — the projection shape | A75 form (`recipient_projection.py`) |

### Proposed matrix (the values are the decision — see §8)

| role | disclosure_ceiling | posture | dose_ceiling | cadence | form |
|---|---|---|---|---|---|
| `operator` | **full internal** — all edges, all contradictions, hot | auto | unbounded | real-time | machine/hot |
| `owner` | own matters: verified + strategy summary | auto | high | material change | human, candid |
| `counsel` | own matter: full evidentiary detail + citations | **hold (T3)** | high | material + deadline | precise, cited |
| `client` | own matter: verified facts + status only (no strategy, no contradictions, no other-client) | **hold → approve** | medium | material change | plain, gentle, no jargon |
| `partner` | scoped shared facts only (per explicit share) | **hold (T3)** | low | on shared-item change | formal, minimal |
| `prospect` | onboarding copy only — no matter content | onboarding flow | minimal | n/a | onboarding copy |
| `counterparty` | **NOTHING auto** | **never** (human-authored + T3 only) | **zero-auto** | never proactive | formal/legal (when human sends) |
| `unknown` | onboarding copy only | onboarding flow | minimal | n/a | onboarding copy |

**The load-bearing property:** when a keystone fact shifts, the engine propagates the *internal* edge
(operator sees it real-time) AND simultaneously clamps the counterparty's projection to **nothing** — the
effect propagates in the graph, the disclosure does not leave the building. The machine never tells an
adversary anything.

## 5. The direct relationship to the engine (the money section)

A76's edge equation is `e = (source, target, type, accuracy_weight, dose_ceiling, direction, cadence_trigger)`.
For any edge whose projection targets a recipient, **their role supplies three of those terms directly**
(`dose_ceiling`, `cadence_trigger`, and the `type`-disclosure filter), and A76 step-4 ("project per recipient
via A75 form + A71 dose") **is literally `form(role) ∘ dose(role)`**. Role is not adjacent to the engine's
math — it is inside it. A75 already says *"one truth, N projections, never N sources"*; A79 is the **source
of the per-recipient shape** A75 demands. So the ontology tie is exact:

```
A76 computes hot equilibrium  ──▶  GATE (the contract)  ──▶  output
                                     │  reads recipient role
                                     │  → comms_role_policy (A79)
                                     │  → clamp: disclosure · posture · dose · cadence · form
                                     ▼
      COMM-AGENT-MAX reply ─┐        A5 (refuse cross-client) already here
      P2 dosed increment  ─┼──▶ same gate, same clamp
      A75 pulse output    ─┘
```

## 6. The A79 invariant (for the ontology desk to mint — NOT me)

> **A79 — Communication is role-governed at the exit.** No output reaches a recipient exceeding their role's
> `disclosure_ceiling`, and the projection form/dose/cadence obey their role policy; a `counterparty` never
> receives an auto-generated disclosure (human-authored + T3 only). Role policy is resolved at the gate (one
> contract for the bot, the engine, and the pulse alike), is versioned + audited (a policy change is a T3
> action), and rides A5 (client isolation is refused, not clamped). The role axis feeds both the agentic
> relationship engine (A76) and the outbound bot; neither may externalize outside it.

## 7. Schema + enforcement (my lane — proposed, shadow-first)

```sql
-- comms_role_policy: the versioned role→policy vector the gate reads. Shadow-first.
CREATE TABLE comms_role_policy (
  role               text PRIMARY KEY,     -- canonical role (§3)
  disclosure_ceiling text NOT NULL,        -- controlled vocab: none|onboarding|status|verified|evidentiary|internal
  posture            text NOT NULL,        -- auto | hold | never | onboarding
  dose_ceiling       text NOT NULL,        -- zero | minimal | low | medium | high | unbounded
  cadence            text NOT NULL,        -- never | on_change | material | material_deadline | realtime
  form               text NOT NULL,        -- onboarding | plain | formal | precise_cited | machine
  version            int  NOT NULL DEFAULT 1,
  updated_by         text, updated_at timestamptz DEFAULT now()
);
CREATE TABLE comms_role_alias (legacy text PRIMARY KEY, canonical text NOT NULL);  -- the vocab reconciliation
```

**Enforcement path (mirrors V4/V6/V7 discipline):**
1. **Shadow** — the gate resolves role→policy and **logs what it WOULD clamp** (a `role_clamp` decision in
   the outward audit), blocks nothing. Prove zero false-clamps on real traffic.
2. **Wire the clamp into the gate** (`outward_guard.guard()` — the single exit): resolve recipient →
   `channel_users.role` → alias → `comms_role_policy`; apply disclosure/posture/dose/form. `counterparty`
   posture `never` becomes a hard hold in block mode.
3. **Truth-test** `test_role_axis.py` — negative-bite: a `counterparty`-targeted auto output is REFUSED; a
   `client` output carrying strategy/other-client content is clamped; `unknown` gets onboarding only. Wire
   into `run_all.py`.
4. **Graduate** to block per role after a clean shadow window (counterparty can go block **first** — it's
   fail-safe: over-holding an adversary is never harmful).

## 8. The decision that's yours (the matrix values)

The §4 matrix is a **legal/business judgment**, not an engineering choice — especially:
- **`counterparty` = never auto-anything** (my strong default; the safe floor).
- **`client` posture** — `hold → approve` (every client reply needs your OK) vs a carve-out where pure
  *status* replies (“your RPT is recorded”) auto-send but anything substantive holds.
- **`counsel` posture** — hold(T3) vs auto for their own matter (they're trusted + need speed).

## 9. Scope boundaries (what this design does NOT do)
- Does not build COMM-AGENT-MAX (a) or P2 — A79 is their precondition, built first, shadow-only.
- Does not edit ONTOLOGY.md — the A79 invariant + CommunicationRole concept are the desk's to mint (§6 is a
  proposal to hand them).
- Shadow-first, reversible, $0. No live behavior change until a role graduates to block with your sign-off.

---

*Review question: does the 5-axis policy vector at the gate, with this matrix, match how you want bots +
engine to treat each kind of person? Adjust any row in §4; the rest is mechanical.*
