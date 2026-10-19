"""Split every working document of the case into one Markdown file per section, under SECTIONS/, and write
00_INDEX.md at the case-folder root. Generated: edit the source documents, then re-run.

Run:  python3 research/split_sections.py
"""
import os, re, datetime
from html2md import html_to_md

BASE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(BASE)
OUT = os.path.join(ROOT, "SECTIONS")
PACK = os.path.join(ROOT, "MEMO_PACK_2026-10-15")
CF = os.path.join(ROOT, "CASE_FILE")

# (folder, title, source, kind)  kind: html | md
DOCS = [
 ("01_STRATEGY_TRAP_MAP", "How this unfolds: the record, the lock-in, the trap", os.path.join(PACK, "05_TRAP_MAP.html"), "html"),
 ("02_STRATEGY_BALANE_TRAJECTORY", "The Balanes' path to victory, and how we close it", os.path.join(ROOT, "BALANE_TRAJECTORY_2026-10-16.html"), "html"),
 ("03_STRATEGY_PROOF_PLAN", "The overwhelm / proof plan: demurrer, elements proved twice, rebuttal doors", os.path.join(ROOT, "OVERWHELM_PLAN_2026-10-14.html"), "html"),
 ("04_COUNSEL_FOCUS_SHEET", "Counsel focus sheet: the case in one line, decisions, statute spine, calendar", os.path.join(ROOT, "COUNSEL_FOCUS_SHEET_2026-10-14.html"), "html"),
 ("05_COUNSEL_PACK_ACTIONS", "Actions for counsel (memo pack cover, 15 Oct 2026)", os.path.join(PACK, "00_ACTION_COVER.html"), "html"),
 ("06_COUNSEL_PACK_BRIEFING_MEMO", "Briefing memorandum to Atty. Barandon (15 Oct 2026)", os.path.join(PACK, "00_COVER_MEMO.html"), "html"),
 ("07_CROSS_CHECKLIST", "Cross-examination checklist: Salvador, Princess, Erwin, Gloria", os.path.join(PACK, "04_CROSS_CHECKLIST.html"), "html"),
 ("08_AUDIT_BALANE_PAYMENTS", "Forensic accounting audit of the Balane payments (Def. Exh. 5)", os.path.join(ROOT, "FORENSIC_AUDIT_BALANE_PAYMENTS_2026-10-18.html"), "html"),
 ("09_WITNESS_PATRICIA_REBUTTAL_JA", "Patricia Keesey Zschoche: filled draft judicial affidavit (rebuttal) and counsel's notes", os.path.join(ROOT, "PATRICIA_JUDICIAL_AFFIDAVIT_FILLED_DRAFT_2026-10-15.html"), "html"),
 ("10_WITNESS_JONATHAN_CROSS_REDIRECT", "Jonathan's 14 October cross and re-direct notes", os.path.join(ROOT, "JONATHAN_14OCT_CROSS_AND_REDIRECT_2026-10.md"), "md"),
 ("11_BRING_TO_COURT_BUNDLE", "Documents outside the record carried to each hearing (cover and tab list)", os.path.join(ROOT, "BRING_TO_COURT_BUNDLE_2026-10.html"), "html"),
 ("12_MASTER_TRIAL_PLAYBOOK", "Master trial playbook (6 parts)", os.path.join(ROOT, "MASTER_TRIAL_PLAYBOOK_2026-10.md"), "md"),
 ("13_WAR_OF_THE_STATUTES", "War of the Statutes", os.path.join(ROOT, "WAR_OF_THE_STATUTES_2026-10.md"), "md"),
 ("14_BAD_FAITH_DOSSIER_SUMMARY", "Bad-faith dossier: itemized summary (Parts 1 to 7; annexes in the PDF)", os.path.join(ROOT, "BALANE_BAD_FAITH_SUMMARY_2026-10.html"), "html"),
 ("15_MEMO_TO_BARANDON_12_OCT", "Memorandum to Atty. Barandon, 12 October 2026 (A1-A10, C1-C14)", os.path.join(ROOT, "MEMO_TO_BARANDON_2026-10-12.html"), "html"),
 ("16_DRAFTS_HELD_RFA", "Draft request for admission (Rule 26), HELD in reserve, not filed", os.path.join(PACK, "02_REQUEST_FOR_ADMISSION.html"), "html"),
 ("17_DRAFTS_HELD_PRODUCTION", "Draft motion for production (Rule 27), HELD in reserve, not filed", os.path.join(PACK, "03_MOTION_FOR_PRODUCTION.html"), "html"),
 ("18_DRAFTS_SUBPOENA_REQUEST", "Draft request for subpoenas (ten custodians), for rebuttal", os.path.join(ROOT, "SUBPOENA_REQUEST_2026-10", "SUBPOENA_REQUEST_2026-10.html"), "html"),
 ("19_DRAFTS_RD_OCC_REQUESTS", "Records requests to the Registry of Deeds and the Clerk of Court", os.path.join(ROOT, "RD_OCC_REQUESTS_2026-10", "RD_OCC_REQUESTS_2026-10.html"), "html"),
 # ---- Grok desk (CASE_FILE/): Grok's files; Claude does not edit them; HELD = internal, never into a counsel pack ----
 ("20_GROK_PARTY_DOSSIER", "[Grok desk] Party dossier: defense counsel and defendants", os.path.join(CF, "PARTIES", "PARTY_DOSSIER_2026-10-17.md"), "md"),
 ("21_GROK_HELD_PARTY_EXPOSURE_ANNEX", "[Grok desk, INTERNAL HELD: not for counsel pack, not for filing] Party exposure annex", os.path.join(CF, "PARTIES", "PARTY_EXPOSURE_ANNEX_HELD_2026-10-17.md"), "md"),
 ("22_GROK_RECEIPTS_EXAMINATION", "[Grok desk] Def. Exh. 5 receipts: scan-level examination record (111 slips; CSV and signature panel alongside)", os.path.join(CF, "PARTIES", "RECEIPTS_EXAMINATION_2026-10-18.md"), "md"),
 ("23_GROK_RECEIPTS_AUDIT_LAW", "[Grok desk] Auditing Def. Exh. 5: Philippine law and practice", os.path.join(CF, "PARTIES", "RECEIPTS_AUDIT_LAW_2026-10-18.md"), "md"),
 ("24_GROK_INK_DATING_PLAN", "[Grok desk] Ink-dating plan for Def. Exh. 5 (timing decision for counsel)", os.path.join(CF, "PARTIES", "INK_DATING_PLAN_2026-10-18.md"), "md"),
 ("25_GROK_RECEIPTS_FORENSIC_FRAMEWORK", "[Grok desk] Forensic framework for the payment trail and subpoena map", os.path.join(CF, "PARTIES", "RECEIPTS_FORENSIC_FRAMEWORK_2026-10-18.md"), "md"),
 ("26_GROK_HELD_DRAFT_MOTION_PRODUCTION_EXH5", "[Grok desk, HELD draft] Motion for production and examination of Def. Exh. 5 (parallel to Claude's held Rule 27 draft, 17_)", os.path.join(CF, "PARTIES", "DRAFT_MOTION_PRODUCTION_EXAMINATION_DEF_EXH5_2026-10-18.md"), "md"),
 ("27_GROK_HELD_DRAFT_SUBPOENA_BOOKLETS", "[Grok desk, HELD draft] Subpoena duces tecum for the receipt booklets and stubs (parallel to Claude's subpoena request, 18_)", os.path.join(CF, "PARTIES", "DRAFT_SUBPOENA_DUCES_TECUM_BOOKLETS_DEF_EXH5_2026-10-18.md"), "md"),
 ("28_GROK_CONSULTATION_GAP_PLAN", "[Other desk] Consultation gap plan (SPA par. 7 'after prior consultation')", os.path.join(CF, "08_GAPS_TO_OBTAIN", "CONSULTATION_GAP_PLAN.md"), "md"),
 ("29_GROK_CONSULTATION_MEANING", "[Other desk] What 'prior consultation' means", os.path.join(CF, "08_GAPS_TO_OBTAIN", "CONSULTATION_MEANING.md"), "md"),
 ("30_GROK_SPA_CLAUSE_DISSECTION", "[Other desk] Clause-by-clause dissection of the 1992 SPA", os.path.join(CF, "08_GAPS_TO_OBTAIN", "SPA_CLAUSE_DISSECTION.md"), "md"),
 ("31_GROK_SPA_LANGUAGE_JURISPRUDENCE", "[Other desk] SPA language jurisprudence", os.path.join(CF, "08_GAPS_TO_OBTAIN", "SPA_LANGUAGE_JURISPRUDENCE.md"), "md"),
 ("32_GROK_T52540_SPA_SCOPE", "[Other desk] T-52540 against the SPA's property description", os.path.join(CF, "08_GAPS_TO_OBTAIN", "T52540_SPA_SCOPE.md"), "md"),
 ("33_GROK_EXERCISES_REVIEW", "[Grok desk] Review of Claude's exercises (with the Cesar signature comparison PDF alongside)", os.path.join(CF, "GROK_REVIEW", "CLAUDE_EXERCISES_REVIEW.md"), "md"),
 ("35_FEED_PLAN_BARANDON", "Feeding Atty. Barandon: one page, one topic, one decision at a time (plan and sequence)", os.path.join(ROOT, "BARANDON_FEED", "00_FEED_PLAN_2026-10-18.html"), "html"),
 ("36_FEED_NOTE_1_WHERE_WE_ARE", "Note 1 to counsel: where we are after 14 October (draft, not sent)", os.path.join(ROOT, "BARANDON_FEED", "01_WHERE_WE_ARE_2026-10-18.html"), "html"),
 ("37_FEED_NOTE_2_SUMMARY_JUDGMENT", "Note 2 to counsel: the summary judgment motion, on paper (draft, not sent)", os.path.join(ROOT, "BARANDON_FEED", "02_SUMMARY_JUDGMENT_2026-10-18.html"), "html"),
 ("38_FEED_NOTE_3_PATRICIA", "Note 3 to counsel: my mother testifies on rebuttal (draft, not sent)", os.path.join(ROOT, "BARANDON_FEED", "03_PATRICIA_REBUTTAL_2026-10-18.html"), "html"),
 ("39_DRAFT_MOTION_TO_RESOLVE_SJ", "Draft Motion to Resolve the Motion to Render Summary Judgment, with Rule 35 s.4 alternative prayer and Annex A (the narrative: 16 facts), for counsel's signature", os.path.join(ROOT, "BARANDON_FEED", "DRAFT_MOTION_TO_RESOLVE_SJ_2026-10-18.html"), "html"),
 ("40_WITNESS_PACK_NEIGHBOURS", "Witness pack: the three neighbours (De Leon, King, de los Reyes): one thing each, lines to withdraw, cross, documents for counsel, the jurat commission question", os.path.join(ROOT, "WITNESS_PACK_NEIGHBOURS_2026-10-19.html"), "html"),
 ("41_FEED_NOTE_4_NEIGHBOURS_JURAT_ORDER", "Note 4 to counsel: the neighbours, who goes first and the notarial stamp (draft, not sent)", os.path.join(ROOT, "BARANDON_FEED", "04_NEIGHBOURS_JURAT_AND_ORDER_2026-10-19.html"), "html"),
 ("42_FEED_NOTE_5_KING_CASES_NOTICE", "Note 5 to counsel: what Mrs. King's cases prove: ownership never decided; Bicol Post served on the Balane side's lawyer 9 Jul 2021 (draft, not sent)", os.path.join(ROOT, "BARANDON_FEED", "05_KING_CASES_NOTICE_2026-10-19.html"), "html"),
 ("34_GROK_REVIEW_ROUNDS", "[Grok desk] Review rounds T1-T6 and our Phase 1-3 responses (folder; see its GROK_INDEX.md)", os.path.join(CF, "09_REVIEW", "GROK_INDEX.md"), "md"),
]


def slug(s, n=60):
    s = re.sub(r'<[^>]+>', '', s); s = re.sub(r'[^A-Za-z0-9]+', '_', s).strip('_')
    return s[:n].rstrip('_') or 'section'


def split_md(md):
    """Split Markdown text at '## ' headings; the preamble before the first '## ' is section 00."""
    parts = re.split(r'\n(?=## )', '\n' + md)
    out = []
    for i, p in enumerate(parts):
        p = p.strip('\n')
        if not p: continue
        m = re.match(r'## (.*)', p)
        title = m.group(1).strip() if m else "Preamble and summary"
        out.append((title, p))
    return out


index_lines = []
total = 0
os.makedirs(OUT, exist_ok=True)
# clear stale generated files
for d in os.listdir(OUT):
    dp = os.path.join(OUT, d)
    if os.path.isdir(dp):
        for f in os.listdir(dp):
            if f.endswith('.md'): os.remove(os.path.join(dp, f))

for folder, title, src, kind in DOCS:
    if not os.path.exists(src):
        index_lines.append(f"| {folder} | {title} | (source missing: {os.path.relpath(src, ROOT)}) |"); continue
    raw = open(src).read()
    md = html_to_md(raw) if kind == "html" else raw
    secs = split_md(md)
    d = os.path.join(OUT, folder); os.makedirs(d, exist_ok=True)
    rel_src = os.path.relpath(src, ROOT)
    mtime = datetime.date.fromtimestamp(os.path.getmtime(src)).isoformat()
    files = []
    for n, (stitle, body) in enumerate(secs):
        fname = f"{n:02d}_{slug(stitle)}.md"
        hdr = (f"<!-- generated by research/split_sections.py from {rel_src} (modified {mtime}); edit the source, then re-run -->\n"
               f"**Document:** {title}  \n**Source:** `{rel_src}`  \n**Section:** {stitle}\n\n---\n\n")
        open(os.path.join(d, fname), "w").write(hdr + body + "\n")
        files.append((fname, stitle)); total += 1
    readme = [f"# {title}", f"Source: `{rel_src}` (modified {mtime}). One file per section:", ""]
    readme += [f"- [{st}]({fn})" for fn, st in files]
    open(os.path.join(d, "README.md"), "w").write("\n".join(readme) + "\n")
    index_lines.append(f"| [{folder}](SECTIONS/{folder}/README.md) | {title} | {len(files)} sections | `{rel_src}` |")

index = f"""# Civil Case No. 26-360 (Zschoche v. Balane): index of the working documents

Generated {datetime.date.today().isoformat()} by `research/split_sections.py`. Every working document is split into one
Markdown file per section under `SECTIONS/`, so each piece of work can be found on its own. The sources (HTML/MD/PDF)
remain where they were; edit a source and re-run the script. Nothing here is filed; counsel signs and files.

## Where things are

| Folder | Document | Size | Source |
|---|---|---|---|
{chr(10).join(index_lines)}

## Data and builders

- `research/balane_receipts_ledger.py` / `.csv` — the receipt-by-receipt ledger of Def. Exh. 5 (111 slips).
- `research/annex_spec.json` + `research/build_dossier.py` — the bad-faith dossier with annexes (PDF, 227 pp).
- `research/build_memo_pack.py` — the counsel pack `MEMO_PACK_BARANDON_2026-10-15.pdf` (action cover + Annexes A-H).
- `research/build_bring_bundle.py` — `BRING_TO_COURT_BUNDLE_2026-10.pdf` (17 tabs of documents outside the record).
- `research/build_forensic_audit.py` — the audit PDF, HTML, and `AUDIT_BALANE_PAYMENTS_2026-10-18.md`.
- `research/build_cross_binders.py` — the five cross binders.
- `research/TRACK_A..E_*.md` — the research tracks (knowledge, papering, notice, jurisprudence, Judge Cu).
- `GROK_REVIEW/` — the second-chair review rounds and our responses.
- `CASE_FILE/` — the Grok desk's case file. Its documents are split under SECTIONS/20_ to 34_ with the tag [Grok desk] or [Other desk]; Claude does not edit them (proposals go through `case_work/CLAUDE_GROK_HANDOFF/`). Anything tagged **HELD** is internal only: never into a counsel pack, never filed.
- `case_work/CLAUDE_GROK_HANDOFF/` — the Claude-Grok channel: dated notes, the work index, the protocol README.
- `drive_local/CV26360 - GROK PACK (2026-10-14)/` — copies for the second chair.

## Standing rules (short form)

Lead with the class limit in SPA paragraph 7; revocation is the backup; never argue Art. 1922 both ways. Case-in-chief =
pre-marked exhibits + the Answer's admissions; custodians and held records go to rebuttal; Patricia testifies on rebuttal.
No discovery motions. Jonathan adds nothing on the stand and has no contact with occupants or defense witnesses. Exclusions:
Garrido, Ida correspondence, CV 6839, OP petitions, NBI/forgery, privileged mail, ARTA referrals in chief, "syndicate",
any characterization of a defendant or of the judge's 2020 orders.
"""
open(os.path.join(ROOT, "00_INDEX.md"), "w").write(index)
print("sections:", total, "| docs:", len(DOCS))
