"""Split every working document of the case into one Markdown file per section, under SECTIONS/, and write
00_INDEX.md at the case-folder root. Generated: edit the source documents, then re-run.

Run:  python3 research/split_sections.py
"""
import os, re, datetime
from html2md import html_to_md

BASE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(BASE)
OUT = os.path.join(ROOT, "SECTIONS")
PACK = os.path.join(ROOT, "MEMO_PACK_2026-10-15")

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
- `CASE_FILE/` — the other desk's case file (untracked; consultation gap plan, SPA dissection, T-52540 scope).
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
