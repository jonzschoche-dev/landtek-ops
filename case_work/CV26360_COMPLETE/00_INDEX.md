# Civil Case No. 26-360 (Zschoche v. Balane): index of the working documents

Generated 2026-10-18 by `research/split_sections.py`. Every working document is split into one
Markdown file per section under `SECTIONS/`, so each piece of work can be found on its own. The sources (HTML/MD/PDF)
remain where they were; edit a source and re-run the script. Nothing here is filed; counsel signs and files.

## Where things are

| Folder | Document | Size | Source |
|---|---|---|---|
| [01_STRATEGY_TRAP_MAP](SECTIONS/01_STRATEGY_TRAP_MAP/README.md) | How this unfolds: the record, the lock-in, the trap | 8 sections | `MEMO_PACK_2026-10-15/05_TRAP_MAP.html` |
| [02_STRATEGY_BALANE_TRAJECTORY](SECTIONS/02_STRATEGY_BALANE_TRAJECTORY/README.md) | The Balanes' path to victory, and how we close it | 7 sections | `BALANE_TRAJECTORY_2026-10-16.html` |
| [03_STRATEGY_PROOF_PLAN](SECTIONS/03_STRATEGY_PROOF_PLAN/README.md) | The overwhelm / proof plan: demurrer, elements proved twice, rebuttal doors | 9 sections | `OVERWHELM_PLAN_2026-10-14.html` |
| [04_COUNSEL_FOCUS_SHEET](SECTIONS/04_COUNSEL_FOCUS_SHEET/README.md) | Counsel focus sheet: the case in one line, decisions, statute spine, calendar | 7 sections | `COUNSEL_FOCUS_SHEET_2026-10-14.html` |
| [05_COUNSEL_PACK_ACTIONS](SECTIONS/05_COUNSEL_PACK_ACTIONS/README.md) | Actions for counsel (memo pack cover, 15 Oct 2026) | 1 sections | `MEMO_PACK_2026-10-15/00_ACTION_COVER.html` |
| [06_COUNSEL_PACK_BRIEFING_MEMO](SECTIONS/06_COUNSEL_PACK_BRIEFING_MEMO/README.md) | Briefing memorandum to Atty. Barandon (15 Oct 2026) | 7 sections | `MEMO_PACK_2026-10-15/00_COVER_MEMO.html` |
| [07_CROSS_CHECKLIST](SECTIONS/07_CROSS_CHECKLIST/README.md) | Cross-examination checklist: Salvador, Princess, Erwin, Gloria | 6 sections | `MEMO_PACK_2026-10-15/04_CROSS_CHECKLIST.html` |
| [08_AUDIT_BALANE_PAYMENTS](SECTIONS/08_AUDIT_BALANE_PAYMENTS/README.md) | Forensic accounting audit of the Balane payments (Def. Exh. 5) | 12 sections | `FORENSIC_AUDIT_BALANE_PAYMENTS_2026-10-18.html` |
| [09_WITNESS_PATRICIA_REBUTTAL_JA](SECTIONS/09_WITNESS_PATRICIA_REBUTTAL_JA/README.md) | Patricia Keesey Zschoche: filled draft judicial affidavit (rebuttal) and counsel's notes | 8 sections | `PATRICIA_JUDICIAL_AFFIDAVIT_FILLED_DRAFT_2026-10-15.html` |
| [10_WITNESS_JONATHAN_CROSS_REDIRECT](SECTIONS/10_WITNESS_JONATHAN_CROSS_REDIRECT/README.md) | Jonathan's 14 October cross and re-direct notes | 6 sections | `JONATHAN_14OCT_CROSS_AND_REDIRECT_2026-10.md` |
| [11_BRING_TO_COURT_BUNDLE](SECTIONS/11_BRING_TO_COURT_BUNDLE/README.md) | Documents outside the record carried to each hearing (cover and tab list) | 4 sections | `BRING_TO_COURT_BUNDLE_2026-10.html` |
| [12_MASTER_TRIAL_PLAYBOOK](SECTIONS/12_MASTER_TRIAL_PLAYBOOK/README.md) | Master trial playbook (6 parts) | 9 sections | `MASTER_TRIAL_PLAYBOOK_2026-10.md` |
| [13_WAR_OF_THE_STATUTES](SECTIONS/13_WAR_OF_THE_STATUTES/README.md) | War of the Statutes | 15 sections | `WAR_OF_THE_STATUTES_2026-10.md` |
| [14_BAD_FAITH_DOSSIER_SUMMARY](SECTIONS/14_BAD_FAITH_DOSSIER_SUMMARY/README.md) | Bad-faith dossier: itemized summary (Parts 1 to 7; annexes in the PDF) | 9 sections | `BALANE_BAD_FAITH_SUMMARY_2026-10.html` |
| [15_MEMO_TO_BARANDON_12_OCT](SECTIONS/15_MEMO_TO_BARANDON_12_OCT/README.md) | Memorandum to Atty. Barandon, 12 October 2026 (A1-A10, C1-C14) | 10 sections | `MEMO_TO_BARANDON_2026-10-12.html` |
| [16_DRAFTS_HELD_RFA](SECTIONS/16_DRAFTS_HELD_RFA/README.md) | Draft request for admission (Rule 26), HELD in reserve, not filed | 1 sections | `MEMO_PACK_2026-10-15/02_REQUEST_FOR_ADMISSION.html` |
| [17_DRAFTS_HELD_PRODUCTION](SECTIONS/17_DRAFTS_HELD_PRODUCTION/README.md) | Draft motion for production (Rule 27), HELD in reserve, not filed | 1 sections | `MEMO_PACK_2026-10-15/03_MOTION_FOR_PRODUCTION.html` |
| [18_DRAFTS_SUBPOENA_REQUEST](SECTIONS/18_DRAFTS_SUBPOENA_REQUEST/README.md) | Draft request for subpoenas (ten custodians), for rebuttal | 2 sections | `SUBPOENA_REQUEST_2026-10/SUBPOENA_REQUEST_2026-10.html` |
| [19_DRAFTS_RD_OCC_REQUESTS](SECTIONS/19_DRAFTS_RD_OCC_REQUESTS/README.md) | Records requests to the Registry of Deeds and the Clerk of Court | 1 sections | `RD_OCC_REQUESTS_2026-10/RD_OCC_REQUESTS_2026-10.html` |

## Data and builders

- `research/balane_receipts_ledger.py` / `.csv` — the receipt-by-receipt ledger of Def. Exh. 5 (111 slips).
- `research/annex_spec.json` + `research/build_dossier.py` — the bad-faith dossier with annexes (PDF, 227 pp).
- `research/build_memo_pack.py` — the counsel pack `MEMO_PACK_BARANDON_2026-10-15.pdf` (action cover + Annexes A-H).
- `research/build_bring_bundle.py` — `BRING_TO_COURT_BUNDLE_2026-10.pdf` (17 tabs of documents outside the record).
- `research/build_forensic_audit.py` — the audit PDF, HTML, and `AUDIT_BALANE_PAYMENTS_2026-10-18.md`.
- `research/build_cross_binders.py` — the five cross binders.
- `research/TRACK_A..E_*.md` — the research tracks (knowledge, papering, notice, jurisprudence, Judge Cu).
- `GROK_REVIEW/` — the second-chair review rounds and our responses.
- `CASE_FILE/` — the other desk's case file (untracked; consultation gap plan, SPA dissection, T-52540 scope).
- `drive_local/CV26360 - GROK PACK (2026-10-14)/` — copies for the second chair.

## Standing rules (short form)

Lead with the class limit in SPA paragraph 7; revocation is the backup; never argue Art. 1922 both ways. Case-in-chief =
pre-marked exhibits + the Answer's admissions; custodians and held records go to rebuttal; Patricia testifies on rebuttal.
No discovery motions. Jonathan adds nothing on the stand and has no contact with occupants or defense witnesses. Exclusions:
Garrido, Ida correspondence, CV 6839, OP petitions, NBI/forgery, privileged mail, ARTA referrals in chief, "syndicate",
any characterization of a defendant or of the judge's 2020 orders.
