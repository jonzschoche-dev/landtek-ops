# 006 — the Master Chief of Staff  (LandTek's administrator: goals in, fronts moving, results out)

*Charter + build plan. Written 2026-09-26 from Jonathan's directive: "administration should be at the core of
its functions keeping the company moving … agentic based on client goals, fighting bureaucracy through a drip
communication, marching us forward on all fronts … a usable product for all stakeholders … I'm trying to build
a master chief of staff bot." Grounded against the live VPS the same day (§2). Supersedes nothing — it is the
charter that the existing engines (pulse, drip, supervisor, Leo, play engine) were missing.*

---

## 1. Mandate (one paragraph)

The Chief of Staff (CoS) **is LandTek's administrator.** It takes each client's goals, breaks them into
fronts, and keeps every front moving every week — preparing the next move, getting it approved, getting it
served, starting the clock on proof of receipt, and firing the pre-built consequence when an office lapses
(the drip). It runs the people (Jonathan, Kristyle, officers, Allan, counsel, Patricia) and the bots toward
those results, each through a view and a voice fitted to their role. It is judged on **fronts moved, clocks
running, and results landed** (possession, pesos, registered rights) — not on documents ingested.

**It is the product.** One bot, many stakeholders, one governed brain.

## 2. Why every earlier attempt stalled (live, 2026-09-26)

| Engine (exists) | Where it stops |
|---|---|
| `client_goals` (6 rows) | all MWK; **0 target dates, 0% progress**; Paracale/NIBDC/LandTek-Corp have none; nothing reads them |
| drip — `office_obligation` (8) / `drip_edition` (1) | **0 served, 0 clocks running**; 5 `draft_held`, near-universal "NEEDS-COUNSEL at trigger"; DILG edition cleared-not-served |
| pulse → `work_orders` | 62 orders rotted unconsumed (cleaned 2026-09-26); uid churn re-fired daily (fixed deploy_1091) |
| matters (26 active) | 16 with no next deadline; 7 with a next deadline already past (CV-26360 still says "Aug 12") |
| Leo (the voice) | built as an **answerer**, not an administrator; one brain since deploys 962–968 (spec 004 done), BUT the Telegram path calls `generate_reply` directly and skips `process()` — no A79 clamp / A21 hold (tolerable only while TG is insiders-only); metered credits depleted |
| `/ops` cockpit | usable only by an engineer; shows system counts, not "what moves today" |

**Diagnosis:** capability was never the gap. The gap is the **closer** (staged → approved → served → proof →
clock) and an **owner** of the loop. Everything piles at "held for Jonathan", surfaced through tools only an
engineer can drive. The CoS is that owner.

## 3. Identity — one bot, not a second one

The CoS **is Leo, re-chartered** (Principle 10 / A85: one owner per surface). Leo keeps his channels
(Telegram, Messenger, email) and gains the administration loop. The reply-brain convergence (spec 004) is done (deploys 962–968); what remains is routing Telegram
through the full `process()` gate path before any external stakeholder is on it.
The name/persona is Jonathan's call.

## 4. The administration loop (the whole job)

```
CLIENT GOAL (dated, success criteria)
   └─ FRONTS (matters / workstreams)         every front has: objective · remedy · forum · next move · date · owner
        └─ NEXT MOVE → INSTRUMENT (drafted from the corpus, provenance-tagged)
             └─ APPROVE (one tap, Jonathan / signatory)            ← the only mandatory human act
                  └─ SERVE (Kristyle / email / LBC)  → PROOF OF RECEIPT (stamped copy / tracking)
                       └─ CLOCK (statutory, cited rule) → PERFORMED ✔ │ PARTIAL → same-day reply │ LAPSE → CONSEQUENCE (pre-built)
                            └─ NEXT EDITION (counters advanced) … until the goal lands
```

Invariants carried from the drip (spec 005): no clock without proof of receipt; a reply is not performance;
on lapse → consequence, never another letter to that officer; no invented periods; never merge matters.

## 5. Cadence

| When | What the CoS does |
|---|---|
| **Continuously** | Inbound (email, TG, scans, stamped copies) → attach to the right front → advance state (proof arrives ⇒ clock starts). |
| **Morning** | Sets the day: per stakeholder, their 1–3 moves. Jonathan gets ONE message (S14) with what needs him. |
| **Pulse (dates)** | T-14 prepare · T-7 review · T-3 confirm; clocks due; lapses → consequence staged. |
| **Evening** | Closes the day: what moved, what slipped, chases the owners of slipped moves. |
| **Weekly** | Goal review with Jonathan: every front moved? stalled ≥7 days → re-plan or escalate. Portfolio rebaseline into MASTER_PLAN. |

## 6. Stakeholder surfaces (usable product)

| Stakeholder | Sees | Does (one tap) | Exposure |
|---|---|---|---|
| Jonathan (owner) | "Today": fronts moved/stalled, clocks, approvals waiting | approve/reject, date a goal, rule a hold | internal — now |
| Kristyle / officers | task list: print · serve · LBC · pick up stamped copy, with address + deadline | mark served + upload receiving copy (starts the clock) | internal — now |
| Allan (opco owner + Paracale client) | his company's + Paracale fronts, next move, date | approve as signatory; answer what's asked | held until "ready" |
| Patricia (MWK principal) | estate goals, recovered/collected, quarterly accounting | acknowledge | held until "ready" |
| Counsel (per matter) | only their matters: bound PDF, what's due, what LandTek needs | accept / return packet | held until "ready" |
| Bots / desks | work orders assigned to them | complete / resolve / hand back | internal |

Surfaces: Telegram/Messenger (voice, role-clamped by A79) + a "Today" web view per role on the existing Flask
app (token portal for external roles). Client separation (A5) and projection (A75) apply to every surface.

## 7. Authority ladder

| Tier | CoS acts alone? | Examples |
|---|---|---|
| T0/T1 internal, reversible | **yes** | attach inbound, re-date, draft instruments, dedupe, assign tasks, restart a unit, chase an internal owner |
| T2 knowledge / messages to insiders | yes, through the gates | promote a fact, message Jonathan (S14) or Kristyle |
| T3 outward / irreversible | **never alone** — stages, asks once, executes only on an authenticated approval (A63) | serve a demand, email an office, give counsel/client a view, invoice, print |

The CoS never practises law (counsel files suits), never gates by default on counsel (only real holds:
e.g. Engr. Balane as a CV-26360 defendant; court filings), never crosses clients.

## 8. The brain (the honest constraint)

Administration needs judgment. The routine path is **deterministic and $0** (loop state, dates, clocks,
assignments). Judgment — drafting instruments, re-planning a stalled front, reading an office's reply — needs a
strong model. Local Ollama (qwen2.5:14b) is not strong enough for that alone; metered Anthropic credits are
depleted. Options (Jonathan decides): (a) fund a capped metered model for the CoS's judgment calls only;
(b) run judgment in scheduled Claude Code sessions (the desk) that the deterministic tick feeds, Leo as voice;
(c) both — (b) now, (a) when credits exist. **Recommended: (c).**

## 9. Reuse map (no rebuild)

| Need | Existing piece |
|---|---|
| goals | `client_goals` (+ add dates, success criteria, front links) |
| fronts | `matters` (`next_event`, `next_deadline`, `next_event_owner`, `lead_counsel`, `forum`) |
| next moves | `matter_plays` (play engine) |
| drip / clocks | `office_obligation`, `drip_edition`, `drip_event` (spec 005) |
| work in flight | `work_orders` + `supervisor.py` (+ `assignee`) |
| the clock | `calendar_orchestrator.py` (pulse), `surfaced_deadlines` |
| voice | Leo (`leo_service`, `tg_send.py` S14, A79 role clamp, relationship profile) |
| instruments | `dossier_pipeline.py`, `case_bundle.py`, drip edition generator |
| roster / health | `fleet_registry.py`, `cos_bridge.py` (Grok+Claude seats → `agent_registry` + A76 `--pulse`), `supervisor_sentinel.py`, `meta_pulse.py` |

New code is only the connective tissue: `cos_tick.py`, the `assignee`/front links, the service-proof upload, and
the role "Today" views.

## 10. Build phases

1. **Goals drive the loop.** Date every `client_goals` row (propose from rules, never fabricate; ask
   Jonathan the rest); link goals → fronts; pulse reads goals; stalled-front (≥7d) finding.
2. **The closer.** Kristyle task list + "served + upload stamped copy" → clock starts in `office_obligation`;
   Jonathan one-tap approval on "Today". Remove default counsel gates (keep real ones).
3. **`cos_tick.py`.** The deterministic loop of §5 + one S14 morning message. Replaces the digest's role as
   Jonathan's daily touchpoint rather than adding another.
4. **Full gate path on every channel** — Telegram through `process()` (A79 clamp, A21 hold), and flip A21/A79/A80 from shadow to enforce, so the one voice is governed everywhere.
5. **External views**, one stakeholder at a time, each on Jonathan's explicit "ready".

## 11. Success metrics (reported weekly)

Fronts with a dated next move (target 100%) · fronts moved this week · clocks running · lapses converted to
consequences · approvals turned around <24h · goals with progress > 0 · pesos collected · results landed.
Failure signals: a second message before Jonathan replies · an order untouched >72h · a front stalled >7d
without escalation · any autonomous outward act.

## 12. Open decisions (Jonathan)

1. Drip items the counsel gate currently holds (Mayor ×2, Abla, Macale, Teope, RD) — servable on your approval alone?
2. After approval, may the CoS **send** the email itself (Gmail send scope re-mint; each send still individually approved)?
3. Brain option §8 — (a) / (b) / (c)?
4. Name/persona — stays "Leo", or a new name for the re-chartered bot?
5. Was the DILG edition served (when, how) — so its clock can start?


## 13. CoS ↔ Claude bridge (non-collision)

LandTek has two operator-facing brains. They share one stack; they must not step on each other.

| Lane | Who | Owns |
|---|---|---|
| CoS (Grok Bot) | this charter / Grok Chief of Staff | administration loop, Grok matter seats, Jonathan decision cards, outward gate |
| Claude | Claude Code + `.claude/agents/*` | code, migrations, VPS/scripts surgery, specialist packages (strategist, mapping, truth-qa, …) |

**Spine:** `agent_registry` ← `fleet_registry.py` (runtime) + `cos_bridge.py` (Grok + Claude seats) ← `config/cos_fleet_roster.json`. Snapshot: `ops/COS_FLEET_AWARENESS.md`. Reaction: reasoning equilibrium + A76 pulse (`cos_bridge.py --pulse` → `propagation_log` seed_type=`fleet`). Deploy census: `migrations/MIGRATIONS_INDEX.md`.

**Rules:** one owner per job · no parallel roster/MASTER_PLAN/brain · material acts go through work_orders + pulse · no dual-ping to Jonathan · `grok:*` ≠ `claude:*` · outward only on Jonathan's explicit go.

Binding copy also lives in MASTER_PLAN §0.12.

