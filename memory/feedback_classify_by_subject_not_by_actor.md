---
name: feedback-classify-by-subject-not-by-actor
description: "Jonathan acts for multiple clients (MWK + Inocalla + others); classify docs by SUBJECT MATTER (property, docket, adverse parties), never by \"Jonathan's name appears\""
metadata: 
  node_type: memory
  type: feedback
  originSessionId: bd418b71-6636-441c-8ebd-97897cec3394
---

**Rule:** Document classification (case_file, matter_code, party tagging) is determined by **subject matter** — which property, which docket, which adverse parties, which underlying transaction. **NEVER** by whether Jonathan's name appears in the doc.

**Why:** Jonathan 2026-05-17: *"important to know that Jonathan works with Inocalla and MWK so those documents should be further classified and never just filed because Jonathan's name is on them."*

Jonathan acts in multiple capacities:
- **MWK-001** — Attorney-in-Fact / counsel-coordinator for Patricia Keesey Zschoche (heirs of Mary Worrick Keesey)
- **Paracale-001** — counsel for Allan Villafria Inocalla (and likely other Inocalla family relations)
- **Owner** — his own personal matters
- Potential future clients

A document where Jonathan signs as counsel for ONE client can never be auto-tagged based on his name being present. The case_file and matter_code must be derived from:
1. **Docket number** in the doc (Civil Case No. X, ARTA CTN SL-Y, etc.)
2. **Adverse parties** named (e.g., Inocalla family disputes vs Balane/Pajarillo)
3. **Subject property** (TCT/OCT number; lot location)
4. **Counter-parties + signatories that are NOT Jonathan**

**How to apply:**

1. **Classifier (doc_meta_extractor, party_filing_classifier, etc.) must:**
   - Look for docket numbers → match against `matters.docket_number`
   - Look for adverse-party names → use the entities table to map to client_code
   - Look for TCT/OCT references → resolve via `title_chain` to a known client's chain
   - ONLY THEN fall back to filename / context heuristics

2. **Anti-pattern:**
   - ✗ "Jonathan signed this affidavit, so it's MWK-001."
   - ✓ "This affidavit is captioned 'Civil Case No. 13-131220' which is an Inocalla matter; Jonathan signed AS counsel/AIF — case_file = Paracale-001."

3. **Audit pass needed:**
   - Re-scan all docs tagged MWK-001 OR Paracale-001 based on Jonathan-name-presence alone.
   - For each, verify the SUBJECT (docket + adverse parties + property) matches the tagged case_file.
   - Flag mismatches → re-tag.

4. **Concrete examples of subject-driven correctness (from 2026-05-17 audit):**
   - doc#796 "Joint Affidavit Worrick Lineage" → SUBJECT = Worrick lineage → MWK-001 ✓ (re-tagged correctly today)
   - doc#797 "Family Tree Patricia Ann Keesey" → SUBJECT = Keesey genealogy → MWK-001 ✓
   - doc#646 "Administrative complaint vs Barangay Captain Rowena T. Chua" filed by Allan Inocalla → SUBJECT = Inocalla matter → Paracale-001 ✓ (correctly stayed Paracale)
   - doc#441 "Judicial Affidavit Jonathan Paul Zschoche" in Civil Case 26-360 → SUBJECT = MWK reinvindicatoria → MWK-001 ✓ (correct)

5. **Implementation queue:**
   - Update doc_meta_extractor system prompt to explicitly ignore "Jonathan" presence; require docket / adverse-party / property anchor before classifying.
   - Add meta-agent invariant: any doc where the ONLY actor name is "Jonathan Zschoche" and there's no docket / adverse party → flag for manual review.
   - Build a one-time re-classification audit pass on the full corpus.

**Linked memories:**
- [[feedback_legal_status_awareness]] — substance trumps labels
- [[feedback_legal_act_validity_scrutiny]] — doc title ≠ proof
- [[feedback_output_no_hallucination_discipline]] — every fact must trace to a substantive anchor, not a name
