---
name: feedback-opus-pre-delivery-audit
description: "For high-stakes client-facing output (Master Case Bible, mediation memos, demand letters, briefs), fire a multi-pass Opus audit gate BEFORE delivery — Opus catches narrative-LLM hallucinations a single pass misses, and the cost is trivial vs the reputational risk"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: e79ca29b-b519-4fd9-b1a0-5f3538aad2af
---

**Rule:** Before any high-stakes client-facing output (Master Case Bible, mediation memo, demand letter, brief, evidence pack) goes to counsel or client, fire an Opus audit gate. Use the structured "FLAG don't rewrite" mandate. Expect — and welcome — NO-GO verdicts.

**Why:** Jonathan 2026-05-17: *"use opus to validate before the final output."* The first Master Case Bible PDF had a hallucination — Haiku's 2025 narrative attributed 2025 LRA certifications to Cesar dela Fuente, who **died 21 June 2017** per doc#364. If Atty. Barandon had spotted that in the delivered PDF, the bible's authority would have been destroyed. Opus caught it in seconds. The single audit pass also surfaced: wrong forum (MTC Mercedes vs RTC Camarines Norte), spelling inconsistency (Keesey vs Keesee), 24 events with CV-6839 title-bleed wrongly tagged TCT-4497, and a missing matter (MWK-ARTA-1212).

**How to apply:**

1. **Build a structured audit prompt** asking Opus to produce labeled sections (A through H) covering: distribution validation, hierarchy check, asset-separation, narrative audit, cross-reference spot-check, forward-risk memo, GO/NO-GO verdict. Use the exact headings — makes subsequent terminal extraction easier.

2. **The mandate must say "FLAG don't rewrite."** Opus has reasoning depth; if you let it regenerate, you pay for paragraph generation instead of audit reasoning. Always: *"Audit the architecture. Do not rewrite anything. Flag errors, misclassifications, over-anchoring, unsafe conclusions."*

3. **Provide critical domain rules in the prompt header.** Hardcode load-bearing facts Opus must enforce: death dates, venue, caption spellings, agrarian-title-set vs T-4497-chain boundary, distinct-party disambiguations (e.g., Alexander L. Pajarillo vs Amado V. Pajarillo).

4. **Use 1h ephemeral cache on the OPUS_SYSTEM prompt.** ~90% discount on repeated Opus calls within the audit chain.

5. **Be prepared for multiple passes.** Pass 1 produces NO-GO; Pass 2 verifies fixes landed; Pass 3 issues SHIP-WITH-NOTES. Total spend $1.00-$1.50 for the typical 3-pass audit — trivial vs the reputational cost of one un-citable claim.

6. **For LLM-narrator hallucinations specifically, prompt-hardening alone is not enough.** The Haiku narrator is faithful to source-doc OCR; if doc#421 contains "MTC Mercedes" in its draft caption, Haiku reproduces it even when the system prompt forbids it. Layer a deterministic post-processor (regex find-and-replace) AFTER narrative regen. See `narrative_postprocess.py`.

**Implementation:**
- `opus_audit_gate.py` — comprehensive 8-section audit with cross-contamination queries
- `opus_validate_bible.py` — narrative-only spot-audit
- `opus_reaudit_narratives.py` — post-fix verification
- `opus_final_check.py` — binary SHIP/NO-GO verdict
- `narrative_postprocess.py` — deterministic regex corrections, integrated into `generate_case_bible.py`

**Linked memories:**
- [[feedback_opus_as_advisor]] — Opus tiering rules
- [[feedback_output_no_hallucination_discipline]] — citation discipline
- [[feedback_legal_act_validity_scrutiny]] — same posture, document-level
