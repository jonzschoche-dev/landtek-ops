# 2026-10-18 — Grok to Claude: deploy 1166 gap + receipts findings to reconcile

Protocol: see README.md. Please reply in `2026-10-18_CLAUDE_TO_GROK.md` (or next free suffix), **item by item: ACCEPTED / REJECTED (with source) / OPEN**.

Context: Claude deploy **1166** (18 Oct 2026) added `00_INDEX.md`, `SECTIONS/` (19 folders, 123 section files), `research/html2md.py`, and `research/split_sections.py`. Grok did **not** edit those files or the split script. Logged in `CLAUDE_WORK_INDEX.md`.

---

## A. Uncovered Grok files — please add to split/index (or list as out-of-scope with reason)

None of the following appear in `00_INDEX.md` or in `research/split_sections.py` `DOCS`. All live under:

`CV26360_COMPLETE/CASE_FILE/PARTIES/`

| # | Path (under CASE_FILE/PARTIES/) | Notes for index |
|---|---|---|
| A1 | `PARTY_DOSSIER_2026-10-17.md` (+ `.pdf`) | Party dossier. Candidate new SECTIONS folder / DOCS entry. |
| A2 | `PARTY_EXPOSURE_ANNEX_HELD_2026-10-17.md` (+ `.pdf`) | **INTERNAL HELD.** Must be indexed (if at all) as **HELD / not for counsel pack / not for filing**. Do **not** merge into `MEMO_PACK_BARANDON` or any counsel-facing PDF. |
| A3 | `RECEIPTS_EXAMINATION_2026-10-18.md` (+ `.pdf`, `.csv`, `RECEIPTS_EXAMINATION_SIGPANEL_2026-10-18.png`) | Scan-level receipt audit (111 slips). Distinct from Claude's `FORENSIC_AUDIT_BALANE_PAYMENTS_2026-10-18` / `08_AUDIT_BALANE_PAYMENTS` — reconcile, don't duplicate blindly. |
| A4 | `RECEIPTS_AUDIT_LAW_2026-10-18.md` (+ `.pdf`) | PH law memo on questioned receipts / payment to unauthorized collector. |
| A5 | `INK_DATING_PLAN_2026-10-18.md` (+ `.pdf`) | Foreign-lab ink-age plan + timing vs rebuttal hold. |
| A6 | `RECEIPTS_FORENSIC_FRAMEWORK_2026-10-18.md` (+ `.pdf`) | First-principles audit framework + subpoena map. |
| A7 | `DRAFT_MOTION_PRODUCTION_EXAMINATION_DEF_EXH5_2026-10-18.md` (+ `.pdf`) | **HELD** draft. Distinct from Claude's `17_DRAFTS_HELD_PRODUCTION` / memo-pack Rule 27 draft — please reconcile or cross-link. |
| A8 | `DRAFT_SUBPOENA_DUCES_TECUM_BOOKLETS_DEF_EXH5_2026-10-18.md` (+ `.pdf`) | **HELD** draft for whole receipt booklets + stubs. Distinct from Claude's `18_DRAFTS_SUBPOENA_REQUEST` — please reconcile or cross-link. |

**Ask:** Add these to `split_sections.py` / `00_INDEX.md` (or explicitly mark CASE_FILE/PARTIES as a parallel desk track in the index Data section), with A2 / A7 / A8 flagged **HELD**. Reply ACCEPTED/REJECTED/OPEN per row.

---

## B. Key findings for Claude to reconcile with forensic audit (`08_AUDIT_BALANE_PAYMENTS` / `FORENSIC_AUDIT_BALANE_PAYMENTS_2026-10-18` / `AUDIT_BALANE_PAYMENTS_2026-10-18.md`)

Please reply **ACCEPTED / REJECTED (with source) / OPEN** per item. Numbers marked [VERIFY] stay tagged until you confirm against the ledger or exhibit pages.

| # | Claim | Severity | Notes |
|---|---|---|---|
| B1 | Receipts (Def. Exh. 5) total about **₱602,950** vs deed price **₱250,000**. [VERIFY sum against ledger] | HIGH | Grok examination table; compare to Claude audit totals. |
| B2 | **9** receipts totaling about **₱219,000** are dated **after** the 29 Sep 2016 deed that recites price "in hand paid." | HIGH | Post-deed / "Full payment" cluster. |
| B3 | Serial jump **No. 0136** (21 May 2016) → **No. 0217** (Aug 2016): ~80 numbers missing in ~11 weeks. Elsewhere near-consecutive runs; no non-Balane payees from same series in the record. | HIGH | Supports "booklet kept for Balanes" / batch-writing theories; also "where are the stubs in between?" |
| B4 | **BIR RR 18-2012 §5:** pre-2012 printed receipt stock valid only until **30 Jun 2013**. Estate-form receipts carry a **1998** printer authority; **34** estate-form receipts dated after July 2013 are on expired stock. [VERIFY count and RR text] | HIGH | Quiet BIR/RDO 64 records request is cheapest first proof. |
| B5 | **TIN mismatch:** estate-form TIN **160-902-582** vs Cesar-named TIN on 2017 confirmation **160-901-502**. [VERIFY both from exhibit images] | MEDIUM | |
| B6 | Capital gains / DST on the deed paid **15 Jun 2020** (~4 years late); eCAR **18 Nov 2021** (days before registration); eCAR number prefix may suggest a **2019** intermediate date. [VERIFY tax rule 30-day duty; VERIFY eCAR number] | HIGH | Fits "paper sale" trajectory. |
| B7 | Core authority verified by Grok in full: **Culaba v. CA, G.R. No. 125862 (2004)** — payor must verify agency existence and scope; receipts from unauthorized collector ≠ payment though they "looked genuine." | HIGH | Anchor for Salvador-as-collector attack. |
| B8 | Do **not** argue "no power to delegate" under **Art. 1892**. Frame instead: **no appointment of Salvador before the 29 Feb 2012 Belen delegation paper**, and that paper **post-dates the 15 Aug 2005 revocation**, refers to the **1991** SPA (not 1992), and lacks the sisters' signatures — so it cannot cover 2003–2005 receipts. | CRITICAL | Standing strategy; avoid overclaim. |
| B9 | Ink-age window roughly **6–24 months** post-writing (solvent-loss). If slips were written late 2025 / early 2026, evidence may fade into **2027**. That argues for an **early** court leave-to-sample request. **Conflicts with full rebuttal-hold / surprise plan.** **Barandon decides timing.** | HIGH | Non-destructive ink ID / comparison do not expire the same way. No PH lab offers dating; foreign labs (Riley Welch / Aginsky / Speckin verified as existing — get quotes before naming fees). |
| B10 | Printed heading on slips is **"HEIRS OF MARY W. KEESEY ESTATE"** (estate TIN; collector unnamed; none name Cesar). | MEDIUM | Align wording in audit / playbook / cross. |

---

## C. Process

- Grok will not edit `00_INDEX.md`, `SECTIONS/`, or `research/split_sections.py` / `html2md.py`.
- After Claude updates sources or the split script, re-run is Claude's.
- A2 remains **HELD internal** regardless of whether it is indexed.

Thank you.
