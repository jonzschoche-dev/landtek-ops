#!/usr/bin/env python3
"""proof.py — corrective QA pass on a final output: lint for professional-FORM defects. $0.

The gate before anything ships to counsel. Checks the markdown source AND the rendered PDF text for
what makes output look unprofessional:
  • markdown leaked into the PDF (** , ## , raw | table pipes, unconverted [links](url))
  • placeholders left in (TODO/TBD/XXX/____/[ ]/<...>/INSERT)
  • internal machine tokens surfaced (doc:N, [F#], MWK-/PAR- codes, DB column names)
  • empty sections (a heading with no content before the next heading)
  • mixed date formats
  • missing form essentials (a title; a 'Page X of Y' footer)
Optional --llm runs a local-Ollama professional-editor review (form/tone/typos only, not legal substance).

  python3 scripts/proof.py doc.md [--pdf doc.pdf] [--llm]
Exit code 0 = clean, 1 = issues found (use as a delivery gate).
"""
import json
import os
import re
import sys
import urllib.request

MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
OLLAMA = os.environ.get("OLLAMA_URL", "http://100.117.118.47:11434")
MODEL = os.environ.get("LANDTEK_EDITOR_MODEL", "qwen2.5:14b-instruct")


def _pdf_text(path):
    try:
        import fitz
        return "\n".join(p.get_text() for p in fitz.open(path))
    except Exception:
        return ""


def lint(src, pdf):
    issues = []
    if pdf:
        for pat, label in [(r"\*\*", "bold markers **"), (r"(?m)^#{1,3}\s", "heading hashes ##"),
                           (r"\]\(https?://", "unconverted [link](url)"), (r"(?m)^\s*\|.*\|", "raw table pipe row")]:
            if re.search(pat, pdf):
                issues.append(("FORM", f"markdown leaked into the PDF: {label}"))
        if "Page 1 of" not in pdf:
            issues.append(("FORM", "no 'Page X of Y' footer in the rendered PDF"))
    for pat in [r"\bTODO\b", r"\bFIXME\b", r"\bTBD\b", r"\bXXX\b", r"_{3,}", r"\[\s*\]",
                r"\blorem\b", r"<[a-z_]{2,}>", r"\bINSERT\b", r"\bPLACEHOLDER\b", r"\bDRAFT ONLY\b"]:
        m = re.search(pat, src, re.I)
        if m:
            issues.append(("PLACEHOLDER", f"'{m.group(0).strip()}' left in the source"))
    blob = src + "\n" + pdf
    for pat, label in [(r"\bdoc:\d+", "doc:N id"), (r"\[F\d+", "fact-id [F#]"),
                       (r"\bMWK-[A-Z0-9-]+", "matter code MWK-…"), (r"\bPAR-[A-Z0-9-]+", "matter code PAR-…"),
                       (r"\bsource_id\b|\bprovenance_level\b|\bmatter_code\b", "DB column name")]:
        m = re.search(pat, blob)
        if m:
            issues.append(("MACHINE", f"internal token surfaced: {label} ('{m.group(0)}')"))
    lines = [l.strip() for l in src.splitlines()
             if l.strip() and not l.startswith("#!") and not l.lstrip().startswith("# #")]
    for i in range(len(lines) - 1):
        # a ## / ### section with no body before the next heading (a lone # title + ## subtitle is fine)
        if re.match(r"#{2,3}\s", lines[i]) and re.match(r"#{1,3}\s", lines[i + 1]):
            issues.append(("EMPTY", f"section '{lines[i][:44]}' has no content before the next heading"))
    styles = set()
    if re.search(rf"\b\d{{1,2}}\s({MONTHS})\s\d{{4}}", src):
        styles.add("'D Month YYYY'")
    if re.search(rf"\b({MONTHS})\s\d{{1,2}},\s\d{{4}}", src):
        styles.add("'Month D, YYYY'")
    if re.search(r"\b\d{4}-\d{2}-\d{2}\b", src):
        styles.add("'YYYY-MM-DD'")
    if len(styles) > 1:
        issues.append(("DATE", "mixed date formats: " + ", ".join(sorted(styles)) + " — pick one"))
    if src.count("**") % 2:
        issues.append(("FORM", "odd number of '**' (unbalanced bold)"))
    if not re.search(r"(?m)^#\s", src):
        issues.append(("FORM", "no top-level title (# heading)"))
    return issues


def llm_review(src):
    prompt = ("You are a meticulous professional legal-document editor. Review the document below for FORM "
              "and PRESENTATION ONLY — not legal substance or strategy. Flag: inconsistent formatting, "
              "tone that is not professional, typos, awkward or run-on phrasing, inconsistent capitalization "
              "or numbering, and anything that would look unpolished to a lawyer. Return a short numbered list "
              "of concrete, specific fixes. If it is already clean, say so.\n\n---\n" + src[:9000])
    try:
        req = urllib.request.Request(f"{OLLAMA}/api/generate",
                                     data=json.dumps({"model": MODEL, "prompt": prompt, "stream": False,
                                                      "options": {"temperature": 0.2}}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read().decode()).get("response", "").strip()
    except Exception as e:
        return f"(LLM editor unavailable: {e})"


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: proof.py doc.md [--pdf doc.pdf] [--llm]")
    md = sys.argv[1]
    pdf = sys.argv[sys.argv.index("--pdf") + 1] if "--pdf" in sys.argv else (md[:-3] + ".pdf" if md.endswith(".md") else "")
    src = open(md).read() if os.path.exists(md) else ""
    pdftxt = _pdf_text(pdf) if pdf and os.path.exists(pdf) else ""
    issues = lint(src, pdftxt)
    print(f"=== PROFESSIONAL-FORM REPORT — {os.path.basename(md)} ===")
    print(f"source: {len(src)} chars · pdf: {'read ('+str(len(pdftxt))+' chars)' if pdftxt else 'not checked'}")
    if not issues:
        print("✓ CLEAN — no form defects detected.")
    else:
        by = {}
        for cat, msg in issues:
            by.setdefault(cat, []).append(msg)
        for cat in by:
            print(f"\n[{cat}] {len(by[cat])}")
            for m in by[cat]:
                print(f"  • {m}")
    if "--llm" in sys.argv:
        print("\n=== EDITORIAL REVIEW (local LLM — form/tone only) ===")
        print(llm_review(src))
    sys.exit(0 if not issues else 1)


if __name__ == "__main__":
    main()
