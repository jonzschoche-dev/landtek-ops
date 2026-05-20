---
name: same-surname-not-family
description: P0 — Same last name does NOT imply family relation. Default to independent actors. Family link requires corpus-anchored primary-document evidence.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: bd418b71-6636-441c-8ebd-97897cec3394
---

Same last name is by NO MEANS the same family. The system defaults to treating same-surname persons as INDEPENDENT ACTORS until corpus-anchored primary-document evidence establishes a relation.

**Why:** Jonathan flagged this 2026-05-19 after the Erwin Balane (Municipal Engineer, ARTA respondent) vs Gloria Balane (CV-26360 defendant) conflation. The system had auto-suggested family link based on shared "Hansol" middle name plus surname coincidence. Jonathan confirmed they ARE related but explicitly rejected the system inferring family on surname alone — "we need first principle evidence connections."

**How to apply:**

1. `entities.family_group` may ONLY be populated when `family_evidence_provenance` cites a corpus document or court finding that explicitly names the relation. Acceptable provenance:
   - "doc_anchored — caption parties X and Y identified as spouses in [doc#NNN]"
   - "doc_anchored — birth certificate [doc#NNN] establishes parent-child"
   - "doc_anchored — sworn affidavit [doc#NNN] paragraph X identifies sibling"
   - "court_finding — judgment in [docket NNN] establishes heir-relation"

2. User-asserted family ties (no corpus doc) are LOGGED in `entities.notes` with timestamp + asserter, but **must NOT populate `family_group`**. The user's belief is recorded; the system does not act on it.

3. The matter-tagger MUST NOT cross-tag matters based on surname coincidence. A valid cross-tag requires substantive overlap on: same canonical entity_id, same title/property, same docket cross-reference, OR same factual transaction. See [[verify-canonical-facts]] and the entity-resolution layer (added 2026-05-19).

4. When asked about a "family" by surname, the right answer is: "I have N entities matching that surname; here's their roles and any doc-anchored relationships among them." Never assert family-link without citation.

**Concrete examples to never repeat:**
- Erwin H. Balane (Municipal Engineer, ARTA respondent) and Gloria Balane (CV-26360 defendant) — same surname, DIFFERENT canonical entities, NO doc-anchored family link in corpus → do not cross-tag matters.
- Alexander L. Pajarillo (Mayor) and Amado V. Pajarillo (CV-6922 deceased landowner) — same surname, DIFFERENT canonical entities, no family link in corpus → never conflate.
- "Cesar M." vs "Cesar K." vs "Cesar N." dela Fuente — likely OCR variants of the SAME person. Disambiguation via spelling alone is unreliable; consolidate under one canonical_id only when other attributes (date, signature, role) confirm.

**Architectural anchor:** `entities` table now has `canonical_id`, `role`, `affiliation`, `family_group`, `family_evidence_provenance` columns (added 2026-05-19). Layer 1 of the entity-awareness architecture per [[same-surname-not-family]] discipline.
