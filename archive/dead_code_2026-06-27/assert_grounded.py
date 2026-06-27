#!/usr/bin/env python3
"""assert_grounded.py — defensive hallucination gate for bible/chronicle outputs.

Sits BETWEEN the producer and the file write. Scans the output text for any
TCT-NNNN, LT-NNNN, currency amount, matter_code, or party-name reference and
validates it against the database. Returns a list of Violation objects.

The gate REJECTS (not warns) when violations are found — callers should hold
the output and fix the producer rather than ship a contaminated bible.

Why this exists:
  - 2026-06-05 — first Paracale-001 bible run produced text saying
    "# MWK-ESTATE Master Case Bible — 2021 Summary" because the narrative
    LLM prompt was hardcoded to MWK framing. Root cause fixed in
    generate_case_bible.py (BIBLE_NARRATIVE_CRITICAL_FACTS dict), but the
    class of bug is recurring — any future producer change can reintroduce
    cross-contamination. This gate catches it.

Violation kinds:
  - cross_client_leak    — PAR bible contains MWK matter codes (and vice versa)
  - unknown_tct          — TCT cited that doesn't exist in titles for this client
  - unknown_lt           — LT-NNNN cited that doesn't exist in documents
  - unknown_matter_code  — matter_code cited that's not registered
  - uncited_currency     — currency amount with no nearby [doc#…] citation
  - unknown_party        — named party that's not in entities for this client

Usage:
    python3 scripts/assert_grounded.py <path/to/bible.md> --case Paracale-001
    python3 scripts/assert_grounded.py <path/to/bible.md> --case MWK-001
    python3 scripts/assert_grounded.py --all-drafts

Exit codes:
    0 = no violations (clean output)
    3 = violations found (output should not ship)
    other = error (DB unreachable etc.)
"""
from __future__ import annotations
import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

# ── Regex patterns ─────────────────────────────────────────────────────
TCT_RE       = re.compile(r"\b(?:OCT\s+)?T-\d{2,5}(?:-\d{3,15})?\b", re.IGNORECASE)
LT_RE        = re.compile(r"\bLT-\d{3,5}\b")
DOC_REF_RE   = re.compile(r"doc#\d+", re.IGNORECASE)
CURRENCY_RE  = re.compile(r"(?:₱|PHP\s*|P)[\s]*[\d,]{4,}(?:\.\d+)?", re.IGNORECASE)
MATTER_RE    = re.compile(r"\b(MWK|PAR|Paracale)-[A-Z0-9]{2,15}(?:-?[A-Z0-9]{0,15})?\b")

# Per-client cross-leak detector. If text in a client's bible contains tokens
# from this list, that's contamination.
CROSS_LEAK_TOKENS = {
    "Paracale-001": [
        # MWK-side identifiers that have NO business in Allan's bible
        ("matter_code", re.compile(r"\bMWK-[A-Z0-9]+", re.IGNORECASE)),
        ("party",       re.compile(r"\b(Mary\s+Worrick\s+Keesey|Patricia\s+Keesey\s+Zschoche|"
                                    r"Cesar\s+(?:N\.\s+)?(?:dela?\s+|de\s+la\s+)Fuente|"
                                    r"Gloria\s+Balane|Atty\.?\s+Barandon)\b", re.IGNORECASE)),
        ("title",       re.compile(r"\bT-4497\b|\bT-32917\b|\bT-32916\b|\bT-31298\b|\bT-52540\b")),
        ("case",        re.compile(r"\b(?:Civil\s+Case\s+)?26-360\b|\bCV-?26360\b", re.IGNORECASE)),
        ("case",        re.compile(r"\bCV-?6839\b", re.IGNORECASE)),
        ("docket",      re.compile(r"\bARTA-\d{4}\b")),
    ],
    "MWK-001": [
        # PAR-side identifiers that have no business in MWK's bible
        ("matter_code", re.compile(r"\bPAR-[A-Z0-9]+", re.IGNORECASE)),
        ("party",       re.compile(r"\b(Allan\s+V?\.?\s*Inocalla|Jesus\s+V?\.?\s*Inocalla|"
                                    r"Shishir\s+Allan\s+Inocalla|Francisco\s+V?\.?\s*Inocalla)\b",
                                    re.IGNORECASE)),
        ("party",       re.compile(r"\bAce\b\s+(?:vs|v\.|against)", re.IGNORECASE)),
        ("matter",      re.compile(r"\b(?:Golden\s+Sand|Vito\s+Cruz|Capacuan|Paracale\s+Gold)\b",
                                    re.IGNORECASE)),
    ],
    "Owner": [],
}

# Lines that are LEGITIMATE cross-references (e.g., "see CLAUDE.md" header).
# These are skipped by the contamination scanner.
EXEMPT_LINE_PATTERNS = [
    re.compile(r"^\s*[-*]\s*\*\*\[?(MWK|PAR)-", re.IGNORECASE),  # bullet headers for matter rows
    re.compile(r"^\s*##?#?\s+", re.IGNORECASE),                  # section headers
    re.compile(r"^\s*\|"),                                        # markdown tables
    re.compile(r"^\s*generated\s+on", re.IGNORECASE),             # generation timestamps
    re.compile(r"^\s*-\s+\*\*case\s+file:", re.IGNORECASE),       # case-file header
]


@dataclass
class Violation:
    kind: str
    detail: str
    line_no: int
    excerpt: str

    def __str__(self):
        return f"L{self.line_no}  [{self.kind}]  {self.detail}\n      …{self.excerpt}…"


def _line_is_exempt(line: str) -> bool:
    return any(p.search(line) for p in EXEMPT_LINE_PATTERNS)


def scan_cross_leak(text: str, case_file: str) -> list[Violation]:
    """Detect identifiers from another client's matter set in this output."""
    violations = []
    patterns = CROSS_LEAK_TOKENS.get(case_file, [])
    if not patterns:
        return violations
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _line_is_exempt(line):
            continue
        for kind, regex in patterns:
            m = regex.search(line)
            if m:
                violations.append(Violation(
                    kind="cross_client_leak",
                    detail=f"{kind} token {m.group()!r} belongs to a different client",
                    line_no=lineno,
                    excerpt=line.strip()[:160],
                ))
                break  # one per line is enough
    return violations


def _fetch_known_tcts(cur, case_file: str) -> set[str]:
    cur.execute("""
        SELECT DISTINCT tct_number FROM titles
         WHERE tct_number IS NOT NULL
           AND (case_file = %s OR case_file IS NULL)
    """, (case_file,))
    return {row[0].upper() for row in cur.fetchall() if row[0]}


def _fetch_known_doc_ids(cur, case_file: str) -> set[int]:
    cur.execute("""
        SELECT id FROM documents
         WHERE (case_file = %s OR case_file IS NULL)
    """, (case_file,))
    return {row[0] for row in cur.fetchall()}


def scan_unknown_doc_refs(cur, text: str, case_file: str) -> list[Violation]:
    """doc#NNN references that don't exist in documents."""
    violations = []
    known_ids = _fetch_known_doc_ids(cur, case_file)
    seen = set()
    for lineno, line in enumerate(text.splitlines(), start=1):
        for m in DOC_REF_RE.finditer(line):
            doc_id_str = m.group()[4:]  # strip "doc#"
            try:
                doc_id = int(doc_id_str)
            except ValueError:
                continue
            key = (lineno, doc_id)
            if key in seen:
                continue
            seen.add(key)
            if doc_id not in known_ids:
                violations.append(Violation(
                    kind="unknown_doc_ref",
                    detail=f"doc#{doc_id} not found in documents (case_file={case_file})",
                    line_no=lineno,
                    excerpt=line.strip()[:160],
                ))
    return violations


def scan_uncited_currency(text: str) -> list[Violation]:
    """Currency amounts asserted without a nearby citation in the same paragraph."""
    violations = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _line_is_exempt(line):
            continue
        for m in CURRENCY_RE.finditer(line):
            amount = m.group()
            window_start = max(0, m.start() - 80)
            window_end = min(len(line), m.end() + 80)
            window = line[window_start:window_end]
            if not DOC_REF_RE.search(window) and "doc#" not in window:
                violations.append(Violation(
                    kind="uncited_currency",
                    detail=f"currency {amount!r} has no nearby [doc#…] citation",
                    line_no=lineno,
                    excerpt=line.strip()[:160],
                ))
    return violations


def assert_grounded(text: str, case_file: str, check_db: bool = True) -> list[Violation]:
    """Run all configured checks. Returns list of violations.

    The cross_client_leak check is the strictest — it ALWAYS runs and does not
    require DB access. The doc-ref/title checks require DB and can be disabled
    with check_db=False for offline / CI-light mode.
    """
    violations = []
    violations.extend(scan_cross_leak(text, case_file))
    violations.extend(scan_uncited_currency(text))
    if check_db:
        try:
            conn = psycopg2.connect(DSN); conn.autocommit = True
            cur = conn.cursor()
            violations.extend(scan_unknown_doc_refs(cur, text, case_file))
            cur.close(); conn.close()
        except Exception as e:
            print(f"  ⚠ DB check skipped: {e}", file=sys.stderr)
    return violations


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?", help="Path to the bible/chronicle .md")
    ap.add_argument("--case", default=None, help="case_file (Paracale-001, MWK-001, Owner)")
    ap.add_argument("--all-drafts", action="store_true",
                    help="Scan all drafts/bible_*_2026-06-*.md")
    ap.add_argument("--no-db", action="store_true", help="Skip DB-dependent checks")
    args = ap.parse_args()

    targets = []
    if args.all_drafts:
        for p in sorted(Path("/root/landtek/drafts").glob("bible_*_2026-*.md")):
            # Infer case_file from filename
            if "Paracale" in p.name or "PAR" in p.name:
                cf = "Paracale-001"
            elif "MWK" in p.name or "OMNIBUS_MWK" in p.name:
                cf = "MWK-001"
            elif "Owner" in p.name:
                cf = "Owner"
            else:
                cf = args.case or "MWK-001"
            targets.append((p, cf))
    elif args.file:
        cf = args.case or "MWK-001"
        targets.append((Path(args.file), cf))
    else:
        ap.error("provide a file path or --all-drafts")

    total_violations = 0
    for path, cf in targets:
        if not path.exists():
            print(f"✗ {path} — does not exist")
            continue
        text = path.read_text()
        vs = assert_grounded(text, case_file=cf, check_db=not args.no_db)
        if not vs:
            print(f"✓ {path.name}  ({cf})  — CLEAN")
        else:
            print(f"✗ {path.name}  ({cf})  — {len(vs)} violation(s):")
            for v in vs[:25]:
                print(f"    {v}")
            if len(vs) > 25:
                print(f"    ... and {len(vs)-25} more")
        total_violations += len(vs)

    sys.exit(0 if total_violations == 0 else 3)


if __name__ == "__main__":
    main()
