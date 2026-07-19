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
