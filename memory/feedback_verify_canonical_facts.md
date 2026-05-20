---
name: feedback-verify-canonical-facts
description: "Canonical facts (party names, dates, dockets) must be verified against the primary corpus BEFORE being treated as authoritative — seed memory in CLAUDE.md is hint, not truth; one wrong seed cascades through Opus, Haiku, and post-processors"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: e79ca29b-b519-4fd9-b1a0-5f3538aad2af
---

**Rule:** Names, dates, dockets, and other canonical facts must be **verified against the primary corpus** before being used in any downstream output (LLM prompts, post-processors, audit gates, narratives). Seed memory (CLAUDE.md, prior chat context) is a *hint to investigate*, not a *fact to assert*.

**Why:** Jonathan 2026-05-17: *"somehow the system has even misspelled Patricia Keesey Zschoche name."*

The error chain:
1. `CLAUDE.md` was seeded with "Patricia Keesee Zschoche" (a typo at project setup).
2. The first Opus audit prompt fed that bad seed in as "standing context: KEESEE is the caption spelling."
3. Opus saw "Keesey" in the Haiku-generated 2025 narrative, "Keesee" in the seed, flagged inconsistency, and ruled in favor of the seed (the supposed authority).
4. The narrative post-processor enforced `Keesey → Keesee` regex-wide.
5. **The post-processor literally introduced spelling errors into a document about to go to Atty. Barandon, against a corpus that contains "Keesey" 307× and "Keesee" 0×.**

Same defect would have happened on any "canonical fact" that was wrong in CLAUDE.md: dates, dockets, addresses, capacity. Anything we treat as load-bearing without corpus verification is a hallucination waiting to happen — and worse, an *authoritative-looking* hallucination because it carries the weight of "the system's project memory says X."

**How to apply:**

1. **For every canonical fact about to be asserted in output, run a corpus-count query first.** Three-line SQL:
   ```sql
   SELECT 'variant_A', COUNT(*) FROM documents WHERE extracted_text ILIKE '%variant A%' AND case_file='X'
   UNION ALL SELECT 'variant_B', COUNT(*) FROM documents WHERE extracted_text ILIKE '%variant B%' AND case_file='X';
   ```
   If one variant beats the other 100:0, that's your canonical spelling. If they're close, escalate to a human.

2. **Distinguish hint-grade memory from fact-grade memory.** CLAUDE.md should mark canonical-fact entries explicitly as *"verified against corpus on YYYY-MM-DD"* with the count. Anything that doesn't carry that verification stamp is a hint, not a fact.

3. **Never let an LLM audit pass be the only check on a canonical fact.** Opus trusts the seed in the prompt; if the seed is wrong, the audit will *enforce* the wrongness. The corpus check is the only ground truth.

4. **Never let a regex post-processor enforce a canonical fact without corpus verification.** A find-and-replace is a force multiplier; if the target is wrong, you propagate the error to every occurrence in one pass.

5. **When a user reports a fact-level error, immediately run the corpus-count check before fixing.** The user's report is the diagnosis trigger, but the count is the diagnosis. Then fix AND update CLAUDE.md AND remove the bad regex.

**Implementation evidence (the case study):**
- Corpus: 307 Keesey vs 0 Keesee across MWK-001 docs.
- Primary instruments confirming Keesey: Patricia's birth certificate doc filename, the RTC Order in CV-26-360 caption ("Patricia Keesey Zschoche Vs. Spouses Efren Balane..."), the ARTA filing caption ("PATRICIA KEESEY ZSCHOCHE represented by Jonathan Paul Zschoche"), 108 Geraldine Keesey, 109 Marcia Keesey.
- The deploy_166 fix reversed 20 wrong-spelling instances, fixed CLAUDE.md, and reversed the post-processor regex.

**Linked memories:**
- [[feedback_opus_pre_delivery_audit]] — Opus audit gate must include corpus-verification step for canonical facts
- [[feedback_no_invented_schemas]] — same principle: don't infer, verify
- [[feedback_output_no_hallucination_discipline]] — citation discipline
