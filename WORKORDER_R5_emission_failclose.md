# Work Order — R5: verify + fail-close the emission path (A79 role clamp)

**For:** the downstream executor (comms/emission desk).
**From:** the ontology/governance desk, 2026-07-19. Source: the reasoning-layer audit (deploy_986), finding R5.
**Posture:** LATENT, not an active fire — grounded 2026-07-19: n8n **"Leos Workflow" active = False**, so no
text is currently reaching a live recipient. This is a **fix-before-the-switch-is-ever-flipped** job. That
lowers urgency but NOT importance: the whole point is that the emission plane must be trustworthy *before*
Telegram/Leo is activated, and the shadow telemetry that would justify activation is currently corrupt (see T2).

## What R5 is
A79 (the role clamp — the single emission gate that decides what a given recipient may receive) is in
**shadow** (validator V12 = `log`, confirmed live). The audit found the emission plane has three defects that
must be closed before A79 is ever flipped to enforce OR the workflow is activated:
1. the shadow **audit trail is systematically corrupted**, so a "clean soak" cannot currently be trusted;
2. the clamp may **fail OPEN** (return raw text) on a gate error — a single-lens claim that must be verified;
3. the A80 disclosure tier is **computed but never read** — a gate that gates nothing.

## Tasks (in order — read first, then fix; stop and surface if a pre-flight contradicts the audit)

### T0 — read the actual send path (do this before touching anything)
Map the real emission chain end-to-end and write down what you find:
- The n8n **"Leos Workflow"** (`workflow_entity` id `vSDQv1vfn6627bnA`) — pull the workflow JSON from n8n's own
  Postgres tables (the audit relied on MASTER_PLAN + endpoint code, NEVER the live topology — close that lens).
  Enumerate every Telegram send node ("Reply to Client", "Send to Target Contact", "Reply to Jonathan"), and
  confirm each carries BOTH the sim-guard (`chatId → '0'` when sender starts `999000`) and the A21 outward path.
- `leo_service.py` / `leo_instant.py` — the code-side reply/send path + its hardcoded-14B inference.
- `outward_guard.py` (A21) + `apply_comms_role_clamp` + `comm_agent_max.py` (L4) — where the clamp is applied.
- **Confirm TG-live status yourself** and record the activation preconditions (what would have to change for a
  real send to fire). If it is still inactive, this whole order stays preventive.

### T1 — verify the fail-open claim (single-lens in the audit — do not fix on faith)
Read the clamp/emission error path. Does a gate/clamp **exception** cause raw (unclamped) text to be returned
or sent? Confirm with the actual code (and, if safe + rolled-back, a forced-error probe). If it fails open →
that is the core R5 defect; if it already fails closed → downgrade R5 and say so. **Fail-closed is the law
(A21/A43):** any clamp/gate error must HOLD (no send, loud log), never emit raw.

### T2 — fix the corrupted shadow audit (the Tier-0 one-liner; prerequisite for trusting any soak)
`apply_comms_role_clamp` builds its policy row with `dict(zip(keys, r))` and NO `isinstance(r, dict)` guard, so
every **RealDictCursor** caller (`leo_instant`, `comm_agent_soak`) gets self-referential garbage → `would_clamp`
is **always False** in `channel_audit`. That is the one telemetry an A79 enforce-flip would rely on, and it is
systematically lying for counterparty rows. Fix: the `isinstance` guard (mirror the pattern used elsewhere in
the codebase). This changes NO emission behavior — it only makes the shadow record true.

### T3 — A80 disclosure tier: wire it or retire it
A80's disclosure tier is computed and threaded into `ctx` but `_clamp_decision` never reads it, and the two
enums don't share a vocabulary. Either (a) surface a directive to the ontology desk to reconcile the
ceiling/tier vocabularies, then have `_clamp_decision` compare them, or (b) remove the dead computation. Do not
leave a gate that gates nothing. **Vocabulary reconciliation is the desk's call — deliver it as a directive,
don't self-mint.**

### T4 — truth-floor (extend the pattern, negative-tested, into run_all.py)
`truth_tests/test_emission_failclose.py`:
1. **cursor-parity:** `apply_comms_role_clamp` returns identical output for a plain cursor vs a RealDictCursor
   on the same row (bites on the T2 bug if it regresses).
2. **fail-closed:** a forced clamp/gate error yields HOLD/no-emit, never raw text (bites on T1 if it regresses).
3. **sim-guard + outward floor:** grep-floor that every send node/path carries the sim-guard and routes through
   `outward_guard` (it cannot be silently unwired).
Negative-test each (a stripped guard / a fail-open path must bite).

## Guardrails (violations are rollbacks)
- **Do NOT flip A79 to enforce** and **do NOT activate the workflow** as any part of this order. R5 makes the
  emission plane trustworthy; the flip is a separate operator decision AFTER (a) T2 lands so the soak telemetry
  is true, (b) a clean shadow window is observed, (c) operator sign-off — the ALIGNMENT §9 graduation ladder.
- Fail-closed is non-negotiable (A21/A43). No silent flips. Client-isolation (A5) holds in every path.
- Two-desk git: `pull --rebase`, specific paths, leave peer-dirty files, gates green before push (the geometry
  service is FAILED right now for an unrelated reason — note it, don't let it mask your run).

## Definition of done
- [ ] T0 send-path map written (incl. the live n8n topology lens) + TG-live status recorded.
- [ ] T1 fail-open verified true/false with code evidence; fixed to fail-closed if true.
- [ ] T2 isinstance guard landed; `would_clamp` proven correct for a RealDict caller.
- [ ] T3 A80 tier wired or retired (vocab-reconciliation directive filed to the desk if wired).
- [ ] `test_emission_failclose.py` green + negative-tested + in run_all.py.
- [ ] Close-out block + the A79-enforce graduation criteria restated for the operator.

## Close-out
*(executor appends here)*

### R5 executor close-out — deploy_989 (comms/emission desk, 2026-07-20)

**TG-live status (re-confirmed on the live topology lens):** `workflow_entity` id `vSDQv1vfn6627bnA`
"Leos Workflow" **active = FALSE**. `outward_guard_config.mode = shadow`. So R5 stays LATENT/preventive —
nothing reaches a live recipient via the n8n plane. One correction to the brief: the "A79 = validator V12"
label is wrong — live `ontology_validator_config` V12 is **A81 property-spine isolation**, not the role
clamp. A79's shadow state is real but governed by `outward_guard_config.mode=shadow` **+ the code being
unconditionally shadow** (`apply_comms_role_clamp` always returns `proposed_output`), not by any validator
row. Material fact (A79 not enforcing) holds; only the mechanism label was off. Not a STOP.

**Send-path map (T0):**
- **n8n plane (INACTIVE):** 95-node workflow. 10 Telegram *send* nodes — Ask Clarification, Reply to
  Jonathan, Reply to Client, Send to Target Contact, Notify Jonathan of Resolution, Confirm Context To
  Jonathan, Notify File Location, Send Files Link to Recipient, Send Slash Help, Send Onboarding Reply.
  **All 10 carry the sim-guard** (`String(from.id).startsWith("999") ? "0" : <real chatId>`; note it uses
  the broader `999`, a superset of the `999000` sim range — more conservative, fine). **Key finding:** the
  n8n send nodes emit *directly* via the Telegram node — they do **NOT** route through the Python
  `outward_guard`/A21/A79 plane. That governance lives only in the CODE plane. So activating the workflow
  would emit through a plane protected ONLY by the sim-guard, not by A21/A79. (This is the agent_specs/004
  convergence decision — flagged for the operator; out of scope to resolve here.)
- **Code plane (LIVE, headless):** `leo_channel_mode` telegram=`headless`, messenger=`headless` (all others
  n8n/shadow). `leo_service.process → _deliver` can actually send on those channels. But every outward send
  is gated by **`_send_decision` (fail-CLOSED by construction:** internal→send · outward w/ consumed human
  approval→send · outward w/o approval→HOLD+enqueue at T3). `tg_send.send` additionally passes
  `outward_guard.guard()` before dispatch. So outward parties cannot get an auto-send on the code plane
  either. The A79 clamp (`apply_comms_role_clamp`) is SHADOW everywhere and does **not** gate any send.

**T1 — fail-open verdict: PARTIALLY TRUE, and NARROWER than the audit implied → downgraded.**
- The A79 **clamp** does NOT fail open into a send: it is shadow and never decides emission (it returns
  `proposed_output` unchanged; on a policy-read error it falls to `_SAFE_DEFAULT_POLICY`, the most
  restrictive — fail-*closed* on the policy read).
- The **primary code send gate** `_send_decision` is fail-CLOSED (outward-without-approval holds).
- The real fail-open was in **`outward_guard.guard()`'s error handler**: `except Exception: return
  ("allow", ...)` — a documented "degrade, don't crash" fail-safe. In **shadow** it's moot (guard never
  blocks anyway), but once flipped to **block/enforce**, a guard error on an outward send would have
  returned `allow` → the unapproved outward send dispatches. That violates A21/A43. So the "clamp fails
  open returning raw" claim is FALSE as stated (the clamp isn't the send gate), but a genuine
  **enforce-mode error-path fail-open existed in the guard belt** — now closed.
- **Fix (fail-closing only, no mode flip):** `guard()`'s except now reads the mode on its own fresh
  connection (`_safe_mode`) and, **only in block mode for an outward recipient**, returns `("hold", …)`;
  internal (operator/sim, floor-classified without the DB) always `allow` (offline-sovereignty); shadow
  always `allow` (shadow never blocks a real send). Net: **behaviour changes ONLY on the block-mode error
  path, which is not active today** — the future enforce switch is now trustworthy, with zero change to
  present shadow behaviour. Verified with a forced-error probe (block+outward→hold, shadow+outward→allow,
  block+internal→allow).

**T2 — corrupted shadow audit: FIXED.** `apply_comms_role_clamp` built its policy with
`dict(zip(keys, r))` and no `isinstance` guard, so every RealDictCursor caller (leo_instant,
comm_agent_soak, comm_agent_max) got a self-referential policy → `would_clamp` always False in
`channel_audit`. Added the `isinstance(r, dict)` guard (mirrors `comm_agent_max._role_policy`). No emission
behaviour change — the shadow record now tells the truth. Proven live: for a counterparty+facts row, a
plain cursor and a RealDictCursor now BOTH log `would_clamp` (before: plain=`would_clamp`, RealDict=`clear`).
(Live `channel_audit` distribution beforehand: 67 would_clamp / 200 clear — the clear bucket was
contaminated by the RealDict garbage.)

**T3 — A80 disclosure tier: directive filed (wired-pending, not self-minted).** Confirmed the tier
(`{contradiction, cross_matter_cascade, verified_fact, general}`) is computed + shadow-logged but never
compared against the role `disclosure_ceiling` (`{none, machine_typed, facts_plus_strategy, full}`) — two
different axes, no shared vocabulary. Per the guardrail (don't self-mint ontology), I did NOT wire the
comparison. Filed **`docs/DIRECTIVE_A80_disclosure_vocab.md`** to the ontology desk requesting the
reconciled lattice + a minted invariant number; annotated `_clamp_decision` and `comm_agent_max` as
advisory-pending. The dead computation is retained (it is the exact input the wiring will consume), not
removed.

**T4 — truth floor: `truth_tests/test_emission_failclose.py`, 6 legs, auto-discovered by run_all.py.**
cursor-parity · fail-closed(block/outward) · negative shadow-allows · negative internal-allows · sim-guard
on every live Telegram send node · code-plane-still-governed grep floor. Result vs the live DB: **6/6 green.**
Negative-tested and confirmed to bite: reverting the T2 fix → cursor-parity leg reds (`['clear',
'would_clamp']`); reverting the T1 except to `allow` → fail-closed leg reds ("FAILED OPEN … raw unapproved
text would dispatch"); a synthetic un-guarded send node → sim-guard leg flags it. No regression:
`test_comms_role_clamp` still 5/5 green against the new `outward_guard`.

**Files changed:** `scripts/outward_guard.py` (T1 `_safe_mode` + fail-closed except; T2 isinstance guard;
T3 annotation) · `leo_tools/comm_agent_max.py` (T3 annotation) · `truth_tests/test_emission_failclose.py`
(new) · `docs/DIRECTIVE_A80_disclosure_vocab.md` (new) · this file.

**Pre-existing reds noted (NOT mine, did not fix):** (1) `test_case_file_domain.no_unknown_values` reds on
3 rows with `case_file='PENDING_TRIAGE'` — a peer-desk data-triage issue, unrelated to R5, but it
HARD-BLOCKS the shared `run_all.py` deploy gate. (2) `landtek-geometry-drip.service` FAILED (per the
deploy_987 note). Neither masks the R5 run; the case_file red is the only thing standing between this
deploy and a fully-green shared gate.

**A79-enforce graduation criteria (restated for the operator — the flip is YOUR decision, not this order's):**
1. **T2 landed** so the soak telemetry is TRUE (done — `would_clamp` no longer lies for counterparty rows).
2. A **clean shadow window** observed on the *corrected* `channel_audit` (re-baseline: pre-fix "clear"
   counts are contaminated and must be discarded).
3. **A80 tier reconciled** (the filed directive lands + `_clamp_decision` wired) — otherwise the tier still
   gates nothing at enforce.
4. Decide the **n8n-vs-code emission convergence** (agent_specs/004): the n8n send plane bypasses A21/A79
   entirely, so *activating the workflow* is NOT equivalent to *flipping A79* — do not conflate them.
5. Operator sign-off (ALIGNMENT §9 ladder). The flip itself = act on `would_clamp` / `next_action` at the
   single gate, in `block` mode — a separate, deliberate change, never a side effect.

