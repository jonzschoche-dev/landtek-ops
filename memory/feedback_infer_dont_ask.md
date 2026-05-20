---
name: infer-scope-from-knowledge-base
description: "On LandTek, infer Civil Case 26-360 scope membership and title correlations from the existing knowledge base before asking Jonathan. He is the backstop, not the first resort."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6d129aad-aef2-4031-8003-fa0de0a89100
---

When working with title data on the LandTek project, **derive correlations and
case-scope from the knowledge base before asking Jonathan**. He has explicitly
said: "26-360 is very clear to understand the titles involved — the system
should establish which are involved. We have a problem with a broader sense
of correlations and a keen sense based on OCR where these fit. I'm willing to
answer questions but the system should be able to decipher these things based
on the knowledge base."

**Why:** asking him "is title X part of 26-360?" or "what's the scope here?"
flips the relationship — he's there to validate ambiguous edge cases, not to
provide a list the system should be able to compute. The data layers below
already encode enough to answer most scope questions deterministically.

**How to apply — the scope-inference cascade:**

For any title, build the case-scope decision from these signals in order:

1. **Direct membership in chain_of_title** — if registrant_full_name is in the
   canonical 3-owner trio (GERALDINE K. HOPPE / MARCIA ELLEN KEESEY / PATRICIA
   K. ZSCHOCHE) or Mary Worrick Keesey, the title is in the MWK chain that
   underpins 26-360.
2. **Verified derivation chain via title_chain** — if walking title_chain
   parent-edges reaches T-4497 (the MWK mother title) through `verified` edges,
   the title is in scope.
3. **Lot-code structural pattern** — lots in the Lot 2-X-6-* or Lot 2-X-4-*
   family (under (LRC) Psd-256008 root) are subdivisions of T-32917 → T-4497,
   thus in MWK chain. Lot codes like "Lot D / E / F of (LRC) Psd-11738" are
   the Manguisoc-Mercedes sibling line (NOT 26-360).
4. **20 named transferees** — if the current registrant is one of the
   transferees in the `transferees` table (Gloria Balane + 19 others), the
   title is a target of the accion reinvindicatoria, by definition in 26-360.
5. **Case Complaint exhibits** — if the title appears in the Civil Case 26-360
   email-attachment exhibits (case_thread #1, role='supporting'), it's in
   evidentiary scope even if the structural chain isn't yet verified.
6. **CLAUDE.md explicit exclusions** — T-30683 (Manguisoc Mercedes), T-4494
   (Cabanbanan San Vicente), the Manguisoc-Mercedes sibling line (T-111 /
   T-4493 / T-4502 / T-4503 / T-30681 / T-32478 / etc.) — explicitly marked
   as separate matters, NOT 26-360.

**Only escalate to Jonathan when:**
- A title's registrant is genuinely unknown (Gemini failed to extract or the
  extraction conflicts with the verified data layer)
- A title appears in the case Complaint but doesn't match any of the above
  signals — those are the genuine edge cases
- The structural inference contradicts explicit CLAUDE.md guidance

**Operational test:** before asking "is title X in 26-360?", run the
inference query. If it returns a clean answer with provenance ≥ 'verified',
state the conclusion as a fact. Cite the basis (e.g., "in scope: T-47655 →
T-32917 → T-4497 via verified title_chain edges + Hoppe/Keesey/Zschoche trio
in chain_of_title").

Related: [[no-invented-schemas]], [[user-role]].
