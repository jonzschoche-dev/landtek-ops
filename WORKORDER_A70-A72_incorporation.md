# Work Order — Incorporate A70–A72 (the identity / cadence / usefulness axioms)

**For:** the ontology executor agent (VPS Claude, `/root/landtek`).
**From:** designer window (Mac, `~/landtek`) — A70–A72 already drafted into `ONTOLOGY.md §4`.
**Posture:** these three invariants are the STATED LAW now; your job is to validate them, wire
the first mechanical floor, and register the build path — WITHOUT phantom-enforcing anything.

---

## Context (what changed and why)

The operator's thesis: **LandTek's identity is cadence + awareness.** The whole (client-isolated)
must be incorporated before any stakeholder decision; the feed must be *hydroponic* — matched to
what the receiver can metabolize into a next action, never a firehose; and profit is the emergent
shadow of being genuinely useful to the operator, never a direct outward pursuit.

Three invariants were added to `ONTOLOGY.md §4` (after A69):

- **A70 — Incorporation precedes decision (the metabolism gate).** No stakeholder-facing
  deliverable emits until a fresh incorporation pass (a) assembles the client-isolated whole for
  that stakeholder's identity/role/purpose/timeline, (b) declares its verified/gap state, (c)
  refuses on a thin/gap-blind base. Generalizes the 1891 affidavit-readiness lesson to every output.
- **A71 — Hydroponic cadence.** Rate of incorporation/urging bounded by metabolizable capacity;
  over-feed = noise = violation. Push the next right increment, not the backlog.
- **A72 — Profit is the shadow of usefulness.** Profitability is emergent from usefulness to the
  operator; never overrides truth/isolation/pacing; money stays behind the A21 outward chokepoint.

All three are marked 🟡 (doctrine/planned) — intentionally. Do NOT mark them 🟢.

---

## Tasks (in order)

1. **Structural validation (no DB).**
   `python3 scripts/ontology_check.py --structure` — confirm unique section numbers + heading depth
   still pass after the A70–A72 insertion. Fix any numbering/format drift I introduced.

2. **Alignment check.**
   `python3 scripts/ontology_check.py --alignment` and `--invariants`. A70–A72 name no specific
   live artifact yet (they're planned), so they must land in the "conceptual/schema, no artifact"
   bucket — NOT as broken enforcement refs. Confirm they don't trip `--enforcement` (no mode claim
   = no phantom enforcement). If any check flags them, adjust the enforcement-cell wording so they
   read as doctrine/planned, never as ENFORCED.

3. **Wire the FIRST mechanical floor for A70 (the identity gate) — smallest real step.**
   Build `require_incorporation(matter, stakeholder) -> Verdict` (suggest `scripts/incorporation_gate.py`),
   fusing the pieces that already exist:
     - `matter_readiness` (readiness score),
     - the dossier verified/gap counts (`case_dossier.py` / the INDEX),
     - A57/A67 timeline presence for the matter.
   Verdict = {READY | HOLD:thin | HOLD:gap-blind} + the recorded reason. Fail-closed: HOLD on a
   thin or gap-blind base. Wire it into ONE deliverable path first: the **Ombudsman/affidavit
   builder** (the `ombudsman_1891.json` playbook path). It must call the gate and refuse to draft
   when the matter is un-incorporated (1891 today = 0 verified → HOLD is the correct output).

4. **Truth-test floor.**
   Add `truth_tests/test_incorporation_gate.py`: assert no governed deliverable path emits without
   a recorded incorporation verdict; negative-test it (a thin matter must produce HOLD, not a draft).
   Wire into `run_all.py` (deploy gate + nightly). Only after it's green + negative-tested may A70's
   enforcement cell move from 🟡 planned toward 🟢 — and only for the wired path, not the whole stack.

5. **A71/A72 stay doctrine for now.** Do NOT build speculative floors. Just confirm the wording is
   coherent and file the graduation triggers already stated in their cells (A71: per-receiver
   metabolizable-batch ceiling + truth_test; A72: usefulness metric per deliverable + no monetary
   path outside A21). Leave them 🟡.

---

## Guardrails (do not violate)

- **No phantom enforcement.** Never mark A70–A72 🟢 without a live, named, negative-tested artifact.
  The `--enforcement` check exists precisely to catch a mode claim with no backing trigger.
- **Provenance sacred.** The incorporation gate reads `_safe`/verified tiers only; it must not
  promote inferred/proposed facts to satisfy readiness.
- **Isolation first.** The "whole" A70 assembles is the CLIENT-ISOLATED whole (A5/A35). The gate
  must resolve `client_code` and never pull another client's facts into the readiness base.
- **KISS/DRY.** Reuse `matter_readiness` + dossier counts; do not build a parallel readiness engine.
- **Commit discipline.** Per the two-agent protocol: you (VPS) commit/push. Run `run_all.py` +
  `ontology_check.py --structure --alignment --enforcement` GREEN before the deploy gate.

## Definition of done

- [ ] `--structure` / `--alignment` / `--enforcement` green with A70–A72 present as doctrine.
- [ ] `incorporation_gate.py` exists, fail-closed, client-isolated, reused (not reinvented).
- [ ] The Ombudsman/affidavit builder calls it and HOLDs on 1891 (0-verified) instead of drafting.
- [ ] `test_incorporation_gate.py` green + negative-tested, wired into `run_all.py`.
- [ ] A70 enforcement cell updated to reflect the wired path (🟡→🟢 only for that path); A71/A72
      remain 🟡 doctrine with their graduation triggers recorded.
