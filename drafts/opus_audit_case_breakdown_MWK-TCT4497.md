# Opus Pre-Delivery Audit — MWK-TCT4497 Case Breakdown

**Source:** `drafts/case_breakdown_MWK-TCT4497.md`
**Audited:** 2026-05-20 by Opus 4.7
**Cost:** $0.3415  ·  Tokens: 5,304in / 3,492out

---

# Critique: MWK-TCT4497 Case Breakdown Draft

The founder said "ugly, totally unusable." He's right. Here is why, in order of how badly each problem damages the document.

---

## A. SIGNALING PROBLEMS — this is the worst category and the reason the founder called it unusable

These are the tells that make the memo read as machine-generated database output rather than a lawyer's work product. Every one of these must die before the document can be shown to a partner, let alone a client.

1. **The header line "Generated 2026-05-20 from `matters`, `titles`, `title_chain`, `instruments_on_title`, `fraud_indicators`, `transferees`, `client_history`, `case_deadlines`."** This is the single most damaging sentence in the memo. It announces, in the first ten words, that this is a database dump dressed up in headings. Partners write memos from *evidence and analysis*, not from "rows." Strip every reference to tables, columns, NULLs, and row counts. The founder does not care that `matters.lead_counsel is NULL`; he cares that no lawyer is assigned.

2. **Backtick-wrapped field names throughout** (`matters.lead_counsel`, `case_deadlines.id=2`, `accion_status='unknown'`, `provenance_level='verified'`, `lifecycle_status`). A litigation memo never contains schema references. Ever. This belongs in an internal engineering ticket, not a partner-facing document on an *accion reinvindicatoria*.

3. **A literal SQL statement in the action plan**: `UPDATE case_deadlines SET assigned_to='ops' WHERE id=2;`. This is disqualifying on its own. No founder reads a case memo and expects to find SQL. If the junior wanted to recommend assigning ownership, they write a sentence.

4. **Memory-rule wikilinks** (`[[feedback_opus_pre_delivery_audit]]`, `[[project_civil_case_26_360_load_bearing_dates]]`, `[[feedback_landtek_management_style]]`, `[[feedback_reports_are_the_measure]]`). These are internal pipeline artifacts. They mean nothing to a reader and they scream "auto-generated." Delete all of them.

5. **The "Self-audit checklist" at the bottom** with checkboxes against memory rules. The founder is the auditor. He does not need the document to grade itself, and the checklist confirms in writing that this was machine-assembled against a rubric. Cut entirely.

6. **References to "Opus pre-delivery audit," "the disambiguator," "comms_send audience-routing," "canonical-name post-processor," "instruments_under_authority view"**. These are tool names. A lawyer does not narrate the tooling. They narrate the legal substance.

7. **"Provenance level"** as a recurring phrase. Lawyers say "verified," "documentary," "testimonial," "hearsay," "primary," "secondary." "Provenance level" is data-pipeline vocabulary.

8. **The ASCII title-tree diagram.** It looks clever but it is unreadable on print, unreadable when pasted into Word, unreadable in an email, and it conveys less than a clean table or a short prose paragraph would. It also surfaces tags like `[inferred_strong]` to the reader, which is another machine-output tell.

**Net signaling effect:** the founder will conclude — in the first 30 seconds — that no lawyer actually wrote or read this. That is fatal.

---

## B. CONTENT PROBLEMS — substantive errors and gaps a partner will catch immediately

1. **The matter is framed wrong.** The memo's opening says the purpose is "force the Registry of Deeds … to update the official title-history record." That is not the legal purpose of the matter. The legal purpose is to recover the property via *accion reinvindicatoria* (Civil Case 26-360); the RD demand letter is one administrative step inside that strategy. The memo has confused a task with the case. A partner reading the first paragraph will think the junior does not understand the matter.

2. **No legal authority cited anywhere.** This is a Philippine property-recovery case with a void-instrument theory, an SPA revocation argument, and post-mortem execution facts. Where are the citations to Articles 1409, 1874, 1919 of the Civil Code? Where is the Torrens-system framework? Where is *Heirs of [X] v. [Y]* on void deeds? A case-breakdown memo without a single legal citation is not a legal memo.

3. **The void-chain theory is asserted, not analyzed.** "Every instrument Cesar executed after the revocation is therefore void ab initio" is presented as obvious. It isn't. There are doctrines of apparent authority, innocent purchaser for value, laches, and Torrens indefeasibility that all cut against this theory and that Balane's counsel *will* raise. The memo does not even name these defenses, let alone address them.

4. **Balane is called the "flagship attack" with no analysis of Balane.** Who is Balane? What does she claim her source of title is? Is she an IPV? Is she in actual possession? Is she occupying, leasing, selling? The memo names her as the target and tells us nothing about her.

5. **Critical fact buried in a table caption.** "Cesar died 2017-06-21 — so the 2021 entries are executed in his name after his death entirely." A deed notarized in the name of a man four years dead is the single strongest fact in this case. It should be in the headline, not in a parenthetical under Layer 2. The post-mortem instrument is more probative than the SPA-revocation theory because it does not depend on a missing 2005 document.

6. **The 20 transferees are listed by name with no analysis whatsoever.** Twenty named individuals with `accion_status='unknown'` is not a deliverable — it's an admission that the work has not been done. Either characterize them or do not list them; a bare list of 20 names with no facts is filler that makes the case look less developed than it is.

7. **The ARTA filings against Mun. Mercedes officials** are mentioned in passing twice with case numbers but no explanation of what they are, what they allege, or how they relate. Either they matter (and need a paragraph) or they don't (and should be cut).

8. **No statute of limitations / prescription analysis.** *Accion reinvindicatoria* has a 30-year prescriptive period for registered land; the 2016 deed is now ~10 years old; the original chain reaches back to instruments from 1993. A partner will ask "are we still in time on every claim?" and the memo has no answer.

9. **No client identification, no opposing counsel, no court, no docket caption, no date of complaint filing.** Standard memo header is absent.

---

## C. STRUCTURAL PROBLEMS

1. **No executive summary.** "Headline" is not an executive summary; it is a status update. A partner needs three to five sentences answering: what is the case, where do we stand, what is the recommendation, what is the biggest risk. None of that is on page one.

2. **The "Open issues" and "Next moves" sections duplicate each other.** Issue #1 is "demand letter not sent"; Action #1 is "send demand letter." Issue #4 is "2005 revocation missing"; Action #4 is "locate revocation." Six issues become six identical actions. Collapse into one section.

3. **The "Risk + posture" section is misordered.** Procedural risk should not follow reputational risk; the load-bearing-fact problem (testimonial-only 2005 revocation) is a *case-fatal* risk and should be elevated above everything else, not buried as a final bullet.

4. **Evidence inventory is split into three categories that overlap confusingly** ("Verified," "Asserted-pending-primary-evidence," "Not yet acquired"). The 2005 SPA revocation appears in two of them. Pick a taxonomy.

5. **No chronology.** A property case spanning 1993–2026, with key dates in 2005, 2016, 2017, 2021, is impossible to follow without a clean timeline. The memo gestures at dates inside prose and a table but never gives the reader a single chronological spine.

---

## D. VISUAL/TONAL PROBLEMS

1. **Bold is overused to the point of meaninglessness.** When 30+ phrases are bold across the document, none of them stand out. Pick the five facts that matter and bold those.

2. **Emoji-style checkmarks (✓)** in the self-audit. Not in a legal memo.

3. **Tone is uneven.** "Flagship attack" in the transferee list is breezy and inappropriate next to "void ab initio." "Brittle here" is colloquial; partners do not use it in writing.

4. **Inline code formatting in prose** (`demand_letter_pending_send`, `email_sent`) makes paragraphs visually jagged and unprofessional.

5. **No firm letterhead, no "Privileged & Confidential / Attorney Work Product" header, no addressee, no author, no date in proper memo format.** This looks like a Notion page, not a legal memo.

---

## E. WOULD I LET THIS LEAVE THE FIRM UNDER MY NAME?

No. Not in this draft, not after light edits, not after heavy edits.

Three independent reasons, any one of which is sufficient:

- **It does not read as legal work product.** Schema references, SQL statements, wikilinks, and tool names tell the reader this was extruded from a system. My name on it would make me look like I outsourced thinking to a database.
- **It contains no legal analysis.** No Civil Code citations, no jurisprudence, no engagement with the defenses Balane will obviously raise. A memo that does not do law is not a legal memo regardless of how well-formatted it is.
- **It misframes the matter.** Treating the RD demand letter as the case's purpose, rather than as one administrative tactic within an *accion reinvindicatoria*, is a category error a partner cannot put their name on.

The junior has clearly done real underlying work — the post-mortem-execution finding and the chain analysis are valuable. But the document as written hides that work behind machine-output presentation.

---

## F. VERDICT

**HOLD AND REBUILD.**

The underlying facts are strong enough to support a real partner-grade memo, but this draft must be reconstructed from a blank page as a legal document — not edited — because its structure, vocabulary, and framing are all wrong at the foundation.
