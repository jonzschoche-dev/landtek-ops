"""Build the reviewer pack for an outside deep-research review (Gemini).

One consolidated Markdown file (+ HTML/PDF) from the SECTIONS/ working documents and the evidence spine,
scrubbed of personal identifiers, privileged counsel mail, and the standing exclusions. Nothing here is
sent anywhere by this script; Jonathan uploads the output himself.

  python3 research/build_gemini_pack.py
"""
import os, re, subprocess, datetime
from md2html import convert

BASE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(BASE)
SEC = os.path.join(ROOT, "SECTIONS"); OUT = os.path.join(ROOT, "GEMINI_PACK_2026-10-19")
SPINE = os.path.join(ROOT, "..", "MWK-001", "BALANE_EVIDENCE_SPINE.md")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# (part title, [SECTIONS folders in reading order])
PARTS = [
 ("A. The case on paper", ["46_DOCUMENTS_ONLY_CASE", "13_WAR_OF_THE_STATUTES", "39_DRAFT_MOTION_TO_RESOLVE_SJ"]),
 ("B. The record in order, and the court's form", ["12_MASTER_TRIAL_PLAYBOOK", "04_COUNSEL_FOCUS_SHEET", "14_BAD_FAITH_DOSSIER_SUMMARY"]),
 ("C. Strategy: rollout, traps, their path to victory", ["01_STRATEGY_TRAP_MAP", "03_STRATEGY_PROOF_PLAN", "02_STRATEGY_BALANE_TRAJECTORY", "07_CROSS_CHECKLIST"]),
 ("D. Witnesses", ["45_WITNESSES_IN_THE_COURTS_FORM", "40_WITNESS_PACK_NEIGHBOURS", "43_RESEARCH_KING_CASES_DIG", "09_WITNESS_PATRICIA_REBUTTAL_JA", "10_WITNESS_JONATHAN_CROSS_REDIRECT"]),
 ("E. The payments: forensic audit and second-reviewer analyses", ["08_AUDIT_BALANE_PAYMENTS", "22_GROK_RECEIPTS_EXAMINATION", "23_GROK_RECEIPTS_AUDIT_LAW", "24_GROK_INK_DATING_PLAN", "25_GROK_RECEIPTS_FORENSIC_FRAMEWORK"]),
 ("F. The 1992 power: clause, class, consultation (second-reviewer analyses)", ["30_GROK_SPA_CLAUSE_DISSECTION", "29_GROK_CONSULTATION_MEANING", "28_GROK_CONSULTATION_GAP_PLAN", "31_GROK_SPA_LANGUAGE_JURISPRUDENCE", "32_GROK_T52540_SPA_SCOPE"]),
 ("G. Parties and held instruments (not filed; for opinion on timing only)", ["20_GROK_PARTY_DOSSIER", "18_DRAFTS_SUBPOENA_REQUEST", "16_DRAFTS_HELD_RFA", "17_DRAFTS_HELD_PRODUCTION", "26_GROK_HELD_DRAFT_MOTION_PRODUCTION_EXH5", "27_GROK_HELD_DRAFT_SUBPOENA_BOOKLETS"]),
]

# Standing exclusions: any line carrying these is dropped (counted, reported).
EXCLUDE = re.compile(r"Garrido|Ordoveza|Buenaventura|Botor|6839|\bNBI\b|forg(e|ed|ery|eries)|syndicate|privileged|gmail#|Gmail msg", re.I)
# Identifier scrubs
SCRUB = [
 (re.compile(r"\b\d{4}-\d{4}-\d{4}-\d{4}\b"), "[ID no. withheld]"),             # PhilID
 (re.compile(r"\bB7011742\b|\bE01-96-019846\b"), "[licence no. withheld]"),
 (re.compile(r"\b160-9\d{2}-\d{3}\b|\b160-90-\d{3}\b"), "[TIN withheld]"),
 (re.compile(r"\b09\d{2}[ -]?\d{3}[ -]?\d{4}\b"), "[mobile withheld]"),
 (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[email withheld]"),
 (re.compile(r"\b(4814|4816|4914) Adele Court[^;.,)]*|20802 Wood\w+ Lane[^;.,)]*|49 Pidgeon Street[^;.,)]*", re.I), "[residence withheld]"),
]

def clean(md):
    kept, dropped = [], 0
    for ln in md.splitlines():
        if ln.lstrip().startswith("<!--"): continue
        if EXCLUDE.search(ln): dropped += 1; continue
        for rx, rep in SCRUB: ln = rx.sub(rep, ln)
        kept.append(ln)
    return "\n".join(kept), dropped

def folder_md(folder):
    d = os.path.join(SEC, folder)
    readme = open(os.path.join(d, "README.md")).read()
    title = readme.splitlines()[0].lstrip("# ").strip()
    files = re.findall(r"\]\((\d\d_[^)]+\.md)\)", readme)
    body = []
    for f in files:
        t = open(os.path.join(d, f)).read()
        t = re.sub(r"^\*\*Document:\*\*.*?\n---\n\n", "", t, flags=re.S)  # strip generated header
        body.append(t)
    return title, "\n\n".join(body)

os.makedirs(OUT, exist_ok=True)
parts, total_dropped, toc = [], 0, []
for ptitle, folders in PARTS:
    parts.append(f"\n\n# {ptitle}\n")
    toc.append(f"- **{ptitle}**")
    for fo in folders:
        title, md = folder_md(fo)
        md, dr = clean(md); total_dropped += dr
        # demote headings two levels so part/document headings stay on top
        md = re.sub(r"^(#{1,4})\s", lambda m: "#" * (len(m.group(1)) + 2) + " ", md, flags=re.M)
        parts.append(f"\n\n## {title}\n\n{md}")
        toc.append(f"  - {title}")
if os.path.exists(SPINE):
    sp, dr = clean(open(SPINE).read()); total_dropped += dr
    sp = re.sub(r"^(#{1,4})\s", lambda m: "#" * (len(m.group(1)) + 2) + " ", sp, flags=re.M)
    parts.append("\n\n# H. The evidence spine and scenario tree\n\n## Balane evidence spine\n\n" + sp)
    toc.append("- **H. The evidence spine and scenario tree**")

today = datetime.date.today().isoformat()
head = f"""# Zschoche v. Balane, Civil Case No. 26-360: reviewer pack

Prepared {today} for an outside, balanced review. Internal working documents of the plaintiff's side, consolidated and
scrubbed (personal identifiers withheld; counsel correspondence and certain unrelated lines removed). Nothing in this
pack has been filed; drafts marked HELD have not been served. All page and exhibit references are to the record of
Civil Case No. 26-360, MTC Mercedes, Camarines Norte. Tags used throughout: [VERIFY] (not yet checked against a certified
copy), [INFERRED] (the writer's conclusion), [CONDITIONAL] (depends on a ruling), [COUNSEL] (counsel's call), HELD (not filed).

## Contents

{chr(10).join(toc)}
"""
md = head + "".join(parts)
open(os.path.join(OUT, "01_CASE_PACK.md"), "w").write(md)
css = """<style>@page{size:8.5in 13in;margin:0.8in}body{font-family:'Times New Roman',serif;font-size:11pt;line-height:1.3}
h1{font-size:18pt;page-break-before:always}h1:first-of-type{page-break-before:auto}h2{font-size:14pt;border-bottom:1px solid #000}
h3{font-size:12pt}table{border-collapse:collapse;width:100%}th,td{border:0.5px solid #000;padding:3pt;font-size:9.5pt;vertical-align:top}
th{background:#eee}tr{page-break-inside:avoid}code{font-size:9.5pt}</style>"""
html = "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Zschoche v. Balane reviewer pack</title>" + css + "</head><body>" + convert(md) + "</body></html>"
hp = os.path.join(OUT, "01_CASE_PACK.html"); open(hp, "w").write(html)
subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={os.path.join(OUT, '01_CASE_PACK.pdf')}", f"file://{hp}"], capture_output=True)
print(f"pack: {len(md):,} chars; lines dropped under exclusions: {total_dropped}")
