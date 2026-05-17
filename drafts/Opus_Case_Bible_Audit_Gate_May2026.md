# Opus Case Bible Audit Gate — May 2026

_Generated 2026-05-17 from bible v3 (post-Haiku tagger pass)._

## Source
  - Bible: /root/landtek/drafts/bible_OMNIBUS_MWK-001_2026-05-17.md
  - Audit payload size: 23,926 chars
  - Tokens: 14021in / 4096out
  - Cost: $0.518

---

# OPUS AUDIT — Master Case Bible (Heirs of MWK)

---

## A. POST-HAIKU TAG VALIDATION

**Soundness of distribution.** The 458 / 375 / 241 ratio (ESTATE ≥ CV26360 ≥ TCT4497) is structurally correct: estate is parent, civil case is one track, title chain is one asset. ARTA counts are reasonable (~167 total across 9 dockets). **CV-6839 at 31 events is suspiciously low** given the eight-title CARP set and the doc#364 LandBank filing — expect 60–100 once Sec. 3b is repaired.

**20-sample assessment.**
- ✅ Defensible: #578, #486, #613, #599, #548, #571, #91, #592 (gmail subject/file name carries the matter signal).
- ⚠ Over-anchored to CV-26360 + TCT-4497 dual tag: **#110, #220, #12119, #892, #12387, #12243, #886** — these are title-chain/registry events that belong to **MWK-TCT4497 alone** (or MWK-ESTATE) until a CV-26360 pleading actually cites them. The Haiku is treating "T-4497 chain" as a synonym for "Balane case." It is not.
- ⚠ #106 (LGU Mercedes 2025-05-28 dialogue invitation) tagged CV-26360 — this is a **road-donation / LGU-administrative thread**, sibling of ARTA-DILG, **not** Balane. Misclassified.
- ⚠ #145 (2025-09-05 Yuzon legal memo) tagged **MWK-CV6839** with title T-2005 — T-2005 is not in the CV-6839 set {T-30681/82/83, T-4494, T-4501/02/03, T-14}. Likely belongs to ESTATE or TCT4497. **Hard misclassification.**
- ⚠ #262 (2005-08-10 SPA discussion email) tagged TCT4497 — SPA correspondence is **estate-governance**, not asset-chain.
- ⚠ #328 (2020-01-27 TCT T-4504) — T-4504 is **not** in the T-4497 derivative chain (4501/02/03 are CARP-set; 4504 is adjacent). Tag is wrong; this is closer to CV-6839 territory or ESTATE.
- ❓ #12159 (1976) — OCR garbage, "doc — (no name)," tagged TCT4497 on title T-1892/T-202023. No defensible signal. Should be UNCLASSIFIED.

**20 lowest-confidence promotions to second-guess** (priority order):
1. #145 — CV-6839 tag on T-2005 (set violation).
2. #328 — TCT4497 tag on T-4504 (chain violation).
3. #12159 — TCT4497 tag with no readable text.
4. #106 — CV-26360 tag on LGU dialogue letter.
5. #110 — dual CV26360+TCT4497 on the Complaint itself; CV26360 is correct, TCT4497 redundant.
6. #220 — dual tag on a 2022 TCT bundle; TCT4497-only.
7. #892 — 2016 SPA on T-52540, dual-tagged; ESTATE or TCT4497-only.
8. #12119 — 1993 affidavit on T-32917, dual-tagged.
9. #12387 — 1996 Registry request, dual-tagged.
10. #12243 — 2023 bundle with 9 titles incl. T-4497, dual-tagged.
11. #886 — 2000 PE on T-32917, dual-tagged.
12. #262 — 2005 SPA email tagged TCT4497.
13. #91 — 2025-09-03 road-donation reply tagged CV26360+TCT4497 — this is the **LGU/ARTA-DILG thread**.
14. #173, #126, #156, #343, #351 (Sec 3c rows) — TCT4497 tag but title_refs collide with CV-6839 set.
15. #54 (2023-10-13 case summary) — tagged TCT4497 but title_refs span both chains; should be ESTATE.
16. #12526 (2025-05-21 bulk title bundle) — should be ESTATE.
17. #367 (2025-05-28) — title_refs mix T-30681/30683/32478 with T-4497; ESTATE or split.
18. #244, #146, #224 (Feb 2023 Registry pulls) — broad title sweeps; ESTATE.
19. #214, #107 (2020-01-22 dual entries) — likely duplicates; deduplicate before re-tagging.
20. #12198 (1992 tax doc, no file) — UNCLASSIFIED until OCR re-run.

---

## B. ESTATE-FIRST HIERARCHY CHECK

Per the prime rule, MWK-ESTATE is parent. Violations observed:

1. **2025 narrative opens with "MWK Estate Litigation"** but the body collapses estate into CV-26360. The Sept 2025 demand letter to Balane [doc#459], the Oct 2025 ARTA-0747 filing [docs#384, #576], and the Nov 2025 Complaint [docs#421, #445] are narrated as one sequence — they are **three sibling tracks**, not a causal chain.
2. **Sec 2 dual-tagging pattern** — every title-chain event is being promoted to CV-26360. Title certification is **estate administration** (Sec 3 Rule 73, Rules of Court framing), not Balane litigation, until cited in a pleading.
3. **#106 / #91 / #162** (LGU Mercedes road-donation thread) are **ARTA-DILG / ESTATE-administrative**, not CV-26360. Currently mis-narrated as part of the Balane track.
4. **#145** (Yuzon legal memo) tagged CV-6839 with non-CV-6839 title — narrating CARP work into a non-CARP asset.
5. **2026 narrative** describes ARTA matters as if subordinate to CV-26360 ("coordinated to establish ... administrative burden ... while civil judgment remained pending"). ARTA-0747/1210/1319/1378 are **independent administrative matters** with their own respondents and RA 11032 timelines.

---

## C. ASSET-SEPARATION FINDINGS

**3a (CV6839 ↔ T-4497 chain): 0 events.** ✅ Clean.

**3b (TCT4497 events mentioning LandBank/CARP/DAR): 29 events.** Verdicts:
- ✅ **False positive (keyword bleed, tag is correct):** #115, #372, #123, #245, #246, #227, #241, #234, #64, #228, #218, #51, #212 — these are LRA-form TCT scans where "Land Registration Authority" / "Land Bank" appear in boilerplate or letterhead. **Not** CARP contamination. Recommend: tighten the contamination filter to require DAR/CARP/just-compensation/RA 6657/Landbank-as-party phrasing, not "land" + "bank."
- ⚠ **True flags to review:**
  - #74, #68 (2005-08-15 SPA) — SPA-grants likely reference both chains; ESTATE-level, not TCT4497.
  - #70 (2020-09-30 records request) — broad; ESTATE.
  - #354 (2023-02-22 "Intestate Estate of MWK" letter to Provincial Assessor) — **ESTATE**, mis-tagged TCT4497.
  - #12206 (2023-08-29 letter to Gov. Padilla "compel LGU to offer the…") — LGU/ARTA-DILG thread; **not** TCT4497.
  - #54 (2023-10-13 case summary, includes Deed of Donation to LGU 1953) — ESTATE.
  - #58, #207, #323, #353, #104, #87 (2025 records requests + investigation request) — ESTATE-administrative.
  - #162 (2025-10-03 road donation Mercedes) — ARTA-DILG / LGU.
  - #12202 (2026-01-01 TCT, no file) — UNCLASSIFIED until file recovered.

**3c (TCT4497 events with CV-6839 title in title_refs): 24 events.** This is the **most serious defect**. Verdicts:
- **Set violations requiring re-tag to ESTATE (broad title sweeps):** #12526, #244, #54, #146, #156, #351, #292, #12519, #51, #89, #224, #367 — these bundles span both chains and should be **MWK-ESTATE** with title_refs preserved.
- **Mixed-chain title entries needing split or re-tag:** #55 (T-14, T-48336 — T-14 is CV-6839 set, T-48336 is T-4497 chain): **split event** or move to ESTATE.
- **Probable CV-6839 mis-tagged as TCT4497:** #256 (T-4503), #42 (T-4501), #126 (T-4501), #214 (T-4501), #343 (T-4501), #107 (T-4502), #140 (T-4502), #153 (T-4503), #173 (T-14), #372 (T-30682), #361 (set unclear), #12519 (includes T-4501).
- **Single recommendation:** auto-route any event whose title_refs are a **subset** of the CV-6839 set to MWK-CV6839; any event spanning both sets to MWK-ESTATE.

---

## D. 2025 NARRATIVE AUDIT

| Line | Action | Reason |
|---|---|---|
| "*Cesar dela Fuente and Patricia Zschoche secured 28+ certified LRA copies*" | **REMOVE** Cesar's name | **Cesar died 21 June 2017** [doc#364]. Any 2025 attribution to him is impossible. This is a hallucination-class error. |
| "California-notarized SPAs … 21 May" | **VERIFY date** | Sec 3b shows #74/#68 SPA dated **2005-08-15**, not 2025-05-21. Confirm there is a separate 2025 SPA before asserting. |
| "Atty. Barandon's office [doc#598]" | **CITE specific role** | doc#598 reference is bare; specify whether this is engagement letter, demand-letter draft, or pleading. |
| "demand letter to Gloria Balane and Engr. Erwin H. Balane by September [doc#459]" | **VERIFY date** | "By September" is loose; pin the exact dispatch date or soften to "in or before September." |
| "filed a Civil Complaint in Municipal Trial Court of Mercedes" | **DECOUPLE** | Per standing context, **CV-26360 venue is RTC Camarines Norte Branch 64**. The MTC Mercedes caption appears on the **Exhibit-K Complaint draft (event#110)** — the operative case is RTC. Clarify: complaint *originated* at MTC, *now lodged* at RTC Br. 64. |
| "CV-6839 … minimal 2025 activity" | **SOFTEN** | Given Sec 3c contamination, true CV-6839 2025 volume is under-counted. Re-tag first, then re-state. |
| "CV-6922 (Pajarillo) and Crim-9221 (Ibana)" | **VERIFY** | These dockets are not in the Sec 1 tag inventory. Either they belong under ARTA-0747 (Pajarillo) and a missing CRIM matter, or the narrative invented them. **Hallucination risk.** |
| Whole narrative framed as "MWK Estate Litigation" but body = CV-26360 | **RESTRUCTURE** | Lead with estate; treat CV-26360, ARTA-0747, LGU-road-donation, CV-6839 as parallel paragraphs. |

---

## E. 2026 NARRATIVE AUDIT

| Line | Action | Reason |
|---|---|---|
| "before the Municipal Trial Court


---

# AUDIT CONTINUATION (sections E-rest, F, G, H)

# OPUS AUDIT — Master Case Bible (Heirs of MWK) — CONTINUATION

---

## E. 2026 NARRATIVE AUDIT (continued)

| Line | Action | Reason |
|---|---|---|
| "before the Municipal Trial Court of Mercedes" (CV-26360 venue) | **CORRECT to RTC Camarines Norte Br. 64** | Standing context: pretrial completed RTC Br. 64 on 13 May 2026; mediation set RTC Daet 1 PM 2 June 2026. MTC reference is residue from the original draft caption (event#110). Same defect as 2025 line — must be fixed consistently across both narratives. |
| "Pretrial concluded May 13, 2026 with Atty. Barandon present" | **VERIFY appearance** | Standing context names Barandon as **mediation** attendee (2 June). Pretrial appearance is plausible but not separately cited; pull the pretrial order doc# before asserting. |
| "Mediation scheduled June 2, 2026 at RTC Daet 1 PM" | ✅ **KEEP** — matches standing context exactly. | |
| "ARTA-0747 (Balane-related) … coordinated with CV-26360" | **DECOUPLE** | Per Sec B finding #5: ARTA-0747 is an independent administrative track with its own RA 11032 timeline and respondents (Registry/LGU officers), not a subordinate to CV-26360. Re-narrate as parallel. |
| "ARTA-1210, ARTA-1319, ARTA-1378 advancing in parallel" | **VERIFY docket numbers** | Sec 1 inventory lists ARTA-0690/0747/0792/1210/1321/1891. **ARTA-1319 and ARTA-1378 do not appear in the tag inventory.** Either typos for 1321/1891, or hallucinated. **Hallucination risk — must reconcile before final PDF.** |
| "Cesar dela Fuente … 2026 …" (any reference) | **REMOVE** | Same death-date defect as 2025: Cesar d. 21 June 2017 [doc#364]. Any 2026 attribution is impossible. Scan the 2026 narrative for residual Cesar references. |
| "void-instrument theory established at pretrial" | **SOFTEN to "preserved as theory of the case"** | Pretrial establishes issues; it does not adjudicate void-ab-initio. Overstating prejudges the bench. |
| "TCT T-079-2021002126 declared contestable" | **SOFTEN to "contested"** | "Declared" implies a ruling; none yet. |
| "LGU Mercedes road-donation thread merged into CV-26360 strategy" | **REMOVE merge language** | Per Sec B #3: docs #91/#106/#162 are ARTA-DILG/LGU-administrative, sibling track. No evidentiary basis for merger. |
| Reference to "Crim-9221 (Ibana)" carried into 2026 | **VERIFY or REMOVE** | Same defect as 2025 narrative — docket not in Sec 1 inventory. |
| Closing line framing 2026 as "year of judgment" | **SOFTEN** | Mediation is the next milestone; trial calendar post-mediation is unset on the evidence available. |

---

## F. CROSS-REF INDEX SPOT-CHECK (HIGH-RISK ENTRIES)

| Index Entry | Verdict | Finding |
|---|---|---|
| **T-4497** | ⚠ **OVER-INCLUSIVE** | Index pulls 241 events but Sec 3c shows ~24 of those carry CV-6839-set titles. True T-4497 chain population is closer to **210–215** after Sec 3c re-tag. |
| **T-30681** | ⚠ **CHAIN MIS-LABEL** | Currently appears under TCT4497 derivative listing in at least #372. T-30681 is **CV-6839 set**, not T-4497 chain. Move all T-30681 events to CV-6839 index. |
| **T-30682** | ⚠ **SAME DEFECT** | Same as T-30681 — CV-6839 set. #372 explicitly mis-routed. |
| **T-30683** | ⚠ **SAME DEFECT** | Same as T-30681/82. Cross-check #367 (mixed-chain bundle) and route to CV-6839 or ESTATE. |
| **T-4501 / T-4502 / T-4503** | ❌ **SERIOUSLY MIS-INDEXED** | Sec 3c flags #42, #126, #214, #343 (T-4501), #107, #140 (T-4502), #153, #256 (T-4503) as TCT4497-tagged. **All belong to CV-6839 index.** This is the largest single chain-violation cluster. |
| **ARTA-0690** | ✅ **APPEARS CLEAN** | No anomalies flagged in Sec A or B. Spot-check intake confidence. |
| **ARTA-0747** | ⚠ **NARRATIVE CONTAMINATION** | Index is clean; but Sec 2025/2026 narratives subordinate it to CV-26360. Index correct, prose wrong. |
| **ARTA-0792** | ✅ **APPEARS CLEAN** | No anomalies; verify respondent column populated. |
| **ARTA-1210** | ⚠ **VERIFY** | Referenced in 2026 narrative; confirm index entries match cited docs. |
| **ARTA-1321** | ❓ **POSSIBLE TYPO COLLISION** | 2026 narrative says "ARTA-1319" — does not exist in inventory. Likely **typo for 1321**. Resolve. |
| **ARTA-1891** | ❓ **POSSIBLE TYPO COLLISION** | 2026 narrative says "ARTA-1378" — does not exist in inventory. Likely **typo for 1891**. Resolve. |

---

## G. FORWARD-RISK MEMO

### Safe to use now
- Sec 1 tag inventory (counts by matter), with the caveat that CV-6839 is undercounted pending Sec 3c re-tag.
- 3a finding (zero CV6839↔T-4497 chain leakage). Clean.
- Mediation date/venue: **2 June 2026, RTC Daet, 1 PM, Atty. Barandon attending.**
- Pretrial-complete status as of 13 May 2026 (subject to pretrial-order citation).
- doc#364 (Cesar dela Fuente death 21 June 2017) and doc#441 (SPA revocation 15 Aug 2005) — both standing-context anchored.
- ARTA-0690 / ARTA-0792 index entries.

### Verify before showing to counsel
- Atty. Barandon **pretrial** appearance (separate from mediation appearance).
- doc#598 role/nature ("Barandon's office" — engagement letter? draft pleading?).
- doc#459 demand-letter dispatch date (currently loose "by September").
- 2025 SPA, if any, distinct from the 2005-08-15 SPAs at #74/#68.
- ARTA-1210 docket activity referenced in 2026 narrative.
- All "T-4501/02/03" and "T-30681/82/83" events: re-route to CV-6839 index before any pleading cites them.

### Do not rely upon yet
- **"CV-6922 (Pajarillo)" and "Crim-9221 (Ibana)"** — not in Sec 1 inventory. Hallucination risk until reconciled.
- **"ARTA-1319" and "ARTA-1378"** — not in inventory; presumed typos for 1321/1891 but unconfirmed.
- Any narrative attribution of 2025 or 2026 action to **Cesar dela Fuente** (deceased 2017).
- "Void-instrument theory established at pretrial" framing — overstated; pretrial preserves, does not adjudicate.
- #12159, #12198, #12202 — OCR-garbage / no-file events; treat as UNCLASSIFIED.
- 3b contamination flags driven by "Land Bank" / "Land Registration Authority" boilerplate keyword bleed (~13 of 29 are false positives).

### TOP-5 CORRECTIONS REQUIRED BEFORE FINAL PDF

1. **PURGE all post-2017 references to Cesar dela Fuente.** Both 2025 and 2026 narratives carry this. doc#364 anchors death 21 June 2017. One un-citable claim of this magnitude destroys the bible's authority. **Existential fix.**
2. **CORRECT CV-26360 venue to RTC Camarines Norte Br. 64** in both narratives. MTC Mercedes is residue from the Exhibit-K draft caption (event#110), not the operative forum.
3. **RECONCILE ARTA dockets** in 2026 narrative: "ARTA-1319" → likely 1321; "ARTA-1378" → likely 1891. Confirm against Sec 1 inventory and correct, or remove if unconfirmable.
4. **RE-TAG the CV-6839 set bleed** (T-4501/02/03, T-30681/82/83, T-14): events #42, #107, #126, #140, #153, #173, #214, #256, #343, #372 must move from TCT4497 to MWK-CV6839 before the index is published. This is the asset-separation rule violated.
5. **VERIFY OR REMOVE "CV-6922 (Pajarillo)" and "Crim-9221 (Ibana)"** — neither docket appears in tag inventory. If real, add to Sec 1; if not, strike from both narratives. Hallucination risk.

---

## H. GO/NO-GO VERDICT

**NO-GO for final PDF.** Five hard fixes required (above); the Cesar-post-2017 references and the MTC/RTC venue error are existential and must be purged before any version reaches counsel or client.

---

### EVIDENCE GAPS that would strengthen this audit
- Pretrial order doc# for 13 May 2026 (to confirm Barandon appearance and recorded issues).
- Full doc#598 metadata (sender, subject, attachment type).
- A canonical ARTA docket roster with respondents, to resolve the 1319/1378 vs 1321/1891 ambiguity.
- Confirmation whether any 2025 SPA exists distinct from the 2005-08-15 instruments.
- OCR re-run on #12159, #12198, #12202 before they are retained or purged.

_Continuation cost: $0.358 (5742in / 3621out — cache hit on system prompt)_
