# Feedback — counsel/client deliverables MUST pass the truth-qa-gate before send (P0)

**Banked:** 2026-09-03, after the Botor trial-memo failure. **Severity: P0 — this is the
project's founding discipline and it was skipped.**

## What happened

A trial-briefing memo for consulting counsel (Atty. Botor, CV 26-360, six days before trial) was
drafted and iterated **inline, from secondary work products, without running the truth-qa-gate**.
The operator caught it ("totally amateur… not checking what our client needs"). A late gate run
returned **FAIL — 11 BLOCK findings**, including claims contradicted by our own evidence:

- "35–40 derivative titles" (a transposed noun — the real figures: ~35 *entries on the title
  face*, 17 first-gen derivative *titles*, 20 named transferees exactly);
- "sales continued for eleven years after revocation" (only Balane's sale post-dates 2005 — our
  own root theory says most of the campaign predates it);
- "the deeds are pullable on request" (the RD has *certified in writing* the de la Fuente-era
  deeds are NOT on file — doc:353);
- "nothing was ever annotated on the mother title" (the SPAs ARE annotated — PE-170453 on T-4497;
  the 1991 SPA on seven derivatives incl. T-52540);
- "proceeds never reached us" stated flat (contested — Salvador swears otherwise, doc 407 S24;
  it is an Art. 1891 accounting claim, not a settled fact);
- an unreconciled discrepancy between our two certified copies of the 1992 SPA's operative
  clause (doc 246 "Llamanzares" vs doc 369 pp17–19 "Teofi- Ramirez" [HV]) handed to counsel as
  settled;
- a cover message promising folder contents (the SPAs, the deed bundle) that were not in the
  folder; and stale dates referencing an already-lapsed court deadline as future.

## The rules (do not regress)

1. **Any deliverable addressed to counsel, a client, a court, or any external party runs the
   `truth-qa-gate` agent BEFORE it is called ready** — same as the "_safe views only" rule for
   legal output. Iterating with the operator does not substitute for the gate; the operator's
   corrections are inputs to the gate, not a bypass of it.
2. **Numbers come from the authoritative ledger, not from narrative docs.** For MWK scale
   figures: `drafts/t4497_transaction_ledger_2026-06-30.md` (title face + derivatives) and
   `case_theories/_shared.py` (the 20-transferee roster). The MASTER_CASE_FILE (2026-06-14) is
   STALE on theory and figures — treat as background only.
3. **Preserve upstream hedges.** If the source says contested / [HV] / draft / proposal, the
   deliverable says it too. Stripping a hedge during summarization is the failure mode that
   compounds into hallucination (Principle 9).
4. **Distinguish the eras.** Pre-1990s dismemberment = Llamanzares-era; de la Fuente = the
   1992-SPA era (7 transactions identified: 6 deeds + 1 confirmation-affidavit-only). Never
   write "all through one agent."
5. **Never promise an artifact's contents without listing the artifact** (folder, annex, PDF).
6. **Deliverables carry the send-date, recomputed countdowns, and no lapsed deadlines phrased
   as future.**

## Standing verification items surfaced by the gate (carry until closed)

- Reconcile doc 246 vs doc 369 pp17–19 on the 1992 SPA's prior-administrator name (human read).
- Elect the ONE operative Balane deed (doc 233 per the doc 240 Confirmation vs doc 415 pleaded
  in the spine/index) — counsel's election.
- Balane JA errata are QUESTIONS for counsel (deed-date drift 24 vs 29 Sep 2016; area 28,891 vs
  28,981 and area-of-what), not one-way corrections.
- Add docs 246, 72/82, 590, 413 to the Botor Drive folder (promised "this week").
- Von bundle + Von 1995 tax-payment PDF: **awaiting upload from Jonathan** (MWK-DLF README §96).
