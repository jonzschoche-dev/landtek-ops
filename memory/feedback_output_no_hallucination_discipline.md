---
name: feedback-output-no-hallucination-discipline
description: "Every Telegram-bound message + every report + every output must cite source doc IDs for each fact, mark provenance (verified/asserted/inferred), and pass a pre-send audit"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: bd418b71-6636-441c-8ebd-97897cec3394
---

**Rule:** No fact ships in any Leo-generated output (Telegram message, daily digest, intake checklist, report, timeline summary) unless it carries:
1. A **source citation** (`doc#X` or `gmail#Y` or `tx#Z` or `extraction_chunk#N`), AND
2. A **provenance tag** (`verified` | `asserted_pending_primary_evidence` | `inferred_strong` | `inferred_weak`), AND
3. Has passed a **pre-send self-audit** against known anti-patterns (label≠fact, draft≠filed, doc-title≠legal-act).

**Why:** Jonathan 2026-05-17 (escalation): *"our outputs must be very structured and disciplined — all hallucinations lead to certain death."*
Earlier same day: *"these were the outputs to Jonathan needs to be refined loads of hallucinations and unable to scan a screenshot for text and context."*

The system's only product is trust. One unverifiable claim in a court output, a settlement letter, or a strategic brief = catastrophic loss of standing for the case AND the firm. Hallucinations are existential, not stylistic.

Multiple hallucinations have shipped to Telegram this session:
- Manuel Garrido "married to Helen Worrick" (present-tense, 1953) — Helen was already deceased
- Helen Worrick = "Mary's sister" (new finding) — was correct but Alice (third sister) was missed entirely
- "Deed of Donation = a donation occurred" — bypassed validity scrutiny
- Earliest MWK event = 1947 birth cert — missed 1912 T-111 anchor entirely
- doc#444 [DRAFT] cited as filed — confused label with status
- "Cesar de la Fuente" / "Cesar de la Puente" — name spelling variants not consistently flagged

Trust is the only product. Every false summary erodes it.

**How to apply:**

1. **Output structure for any factual claim:**
   ```
   <claim> [doc#N · provenance · validity_summary]
   ```
   Example:
   - ✗ Wrong: "Pretrial occurred May 13, 2026."
   - ✓ Right: "Pretrial occurred 2026-05-13 [doc#392 Notice of Pre-trial Conference · verified · INTERNALLY_VERIFIED]"

2. **No "summary" output without a cite-anchor.** If you summarize 5 events, each must reference a source. If you can't cite, mark `inferred` and explain the inference chain.

3. **Spelling-variant guardrail.** Names: track ALL spellings seen in corpus, never collapse without source-quote. The corpus contains:
   - Mary Worrick KEESY (1953 deed, oldest spelling)
   - MARY WORRICK KEESEY (1964+ titles)
   - "KESSEY" (OCR typo)
   - Cesar DE LA FUENTE vs Cesar DE LA PUENTE (OCR variants — possibly same person)
   - Cesar M. / Cesar N. (middle initial drift)
   Surface all variants. Don't pick one as "canonical" without primary evidence.

4. **Pre-send audit** (built into every generator going forward):
   - Run the message body through a checklist:
     - Any factual claim without `doc#X / gmail#Y / tx#Z` citation? → FAIL
     - Any legal act ("filed", "donation", "sale", "revocation") asserted without validity verdict? → FAIL
     - Any draft cited as filed? → FAIL
     - Any name spelling presented as canonical without source-quote? → FAIL
     - Any compound claim ("X happened ON DATE Y") where date isn't in source? → FAIL
   - If any FAIL → block send, surface to Jonathan for fix.

5. **Implementation queue:**
   - Build `output_audit.py` — pre-send linter for any generator
   - Hook into `daily_strategic_digest.py`, `tg_dispatcher.py` slash command outputs
   - Hook into the inquiry-queue dispatcher (linter runs before each enqueued message is sent)

**Anti-pattern to delete from future outputs:**
- Bare assertions without cites
- Smooth narrative prose that hides epistemic gaps
- "We know X" without "from doc#Y" suffix
- Over-confident timelines that fill gaps with inferred dates

**Linked memories:**
- [[feedback_no_invented_schemas]] — no inferring schema fields
- [[feedback_legal_status_awareness]] — stage trumps date / labels
- [[feedback_legal_act_validity_scrutiny]] — doc title ≠ proof of act
- [[project_title_origins_mwk]] — corrected MWK origins after the 1912 T-111 correction
