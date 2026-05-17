#!/usr/bin/env python3
"""output_audit — pre-send linter that BLOCKS any output containing
unverifiable factual claims.

Per [[feedback_output_no_hallucination_discipline]] + Jonathan 2026-05-17:
"hallucinations lead to certain death." Every Leo-generated text (Telegram
message, digest, report, intake) must pass this lint before send.

Returns (passed: bool, findings: list[dict]) — when passed=False the caller
must NOT send. Use audit_text() before any tg_send / file write / report
emit. Use audit_file() to lint a generated markdown file.

Cost: zero LLM. Pure regex.
"""
import argparse
import json
import re
import sys
from pathlib import Path

# ─── Risk patterns ──────────────────────────────────────────────────────
# Any sentence that asserts a FACT must be paired with a citation tag
# within the same line/sentence/bullet.
CITATION_PATTERNS = [
    r"\bdoc#\d+",
    r"\bgmail#\d+",
    r"\btx#\d+",
    r"\bdeadline#\d+",
    r"\bintake#\d+",
    r"\bextraction_chunks#\d+",
    r"\bPE-\s*\d",
    r"\bCTN\s*SL-?\d",
    r"\bCivil Case No\.?\s*\d",
    r"\bC[Vv]-?\s*\d{2,4}-?\s*\d+",
    r"\bTCT[\s-]?(?:No\.?)?\s*[T-]?\d",
    r"\bOCT[\s-]?(?:No\.?)?\s*[T-]?\d",
    r"\bdraft|placeholder|TBD|asserted|inferred|pending_primary",
    r"verified|inferred_strong|inferred_weak|government_issued|executed_filed|executed_notarized",
    r"\(per .+\)",
    r"\bAuto-",
]

# Sentence patterns that ASSERT a fact (without context = hallucination risk)
ASSERTIVE_FACT_PATTERNS = [
    # "X died on Y" "X was filed on Y"
    (r"\b(died|deceased|passed away)\s+(?:on|in)\s+\S{2,15}\s+\d{4}", "death assertion"),
    (r"\b(was|were|is|are)\s+(?:filed|executed|notarized|registered|cancelled|issued)\s+(?:on|in|by)?\s*", "execution status assertion"),
    (r"\b(occurred|happened|transpired)\s+(?:on|in)\s+\d", "event-occurred assertion"),
    (r"\b(donated|granted|conveyed|transferred|sold)\s+(?:on|in|to)", "transfer/donation assertion"),
    (r"\bdied\s+(?:before|after|by)\s+\S+\s+\d{4}", "date-bounded death assertion"),
    (r"\b(?:married|widowed|deceased)\s+(?:to|by)\s+\w+", "marital/death relation assertion"),
]

# Soft-confidence words that paper over uncertainty
HEDGE_RED_FLAGS = [
    r"\blikely\b", r"\bappears\s+to\b", r"\bseems\s+to\b",
    r"\bprobably\b", r"\bperhaps\b", r"\bpresumably\b",
]


def has_citation_nearby(line: str) -> bool:
    """A line is OK if it carries at least one citation token."""
    for pat in CITATION_PATTERNS:
        if re.search(pat, line, re.IGNORECASE):
            return True
    return False


def is_assertive_fact(line: str) -> tuple[bool, str | None]:
    for pat, label in ASSERTIVE_FACT_PATTERNS:
        if re.search(pat, line, re.IGNORECASE):
            return True, label
    return False, None


def has_hedge(line: str) -> bool:
    return any(re.search(p, line, re.IGNORECASE) for p in HEDGE_RED_FLAGS)


def is_structural_line(line: str) -> bool:
    """Lines that are pure structure (headers, table headers, separators) get a pass."""
    s = line.strip()
    if not s:
        return True
    if re.match(r"^[#*\-=_|]+$", s):
        return True
    if s.startswith("#"):
        return True
    if s.startswith("|") and re.fullmatch(r"\|[\s:|\-]+\|", s):
        return True
    if s.startswith("```"):
        return True
    return False


def audit_text(text: str, strict: bool = True) -> tuple[bool, list[dict]]:
    """Lint a text body. Returns (passed, findings).

    Default 'strict' = True blocks any assertive fact lacking a citation.
    For loose mode (warn-only), strict=False.
    """
    findings = []
    for i, line in enumerate(text.splitlines(), 1):
        if is_structural_line(line):
            continue
        assertive, label = is_assertive_fact(line)
        cited = has_citation_nearby(line)
        hedged = has_hedge(line)
        if assertive and not cited:
            findings.append({
                "line": i,
                "severity": "high",
                "issue": f"assertive_fact_no_citation ({label})",
                "snippet": line.strip()[:200],
            })
        if hedged and not cited:
            findings.append({
                "line": i,
                "severity": "low",
                "issue": "hedge_word_without_citation",
                "snippet": line.strip()[:200],
            })
    high_findings = [f for f in findings if f["severity"] == "high"]
    passed = (len(high_findings) == 0) if strict else True
    return passed, findings


def audit_file(path: Path, strict: bool = True):
    text = path.read_text(errors="ignore")
    return audit_text(text, strict=strict)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", help="path to markdown/text to audit")
    ap.add_argument("--strict", action="store_true", default=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    passed, findings = audit_file(Path(args.file), strict=args.strict)
    if args.json:
        print(json.dumps({"passed": passed, "findings": findings}, indent=2))
    else:
        if passed:
            print(f"✓ {args.file} passed ({len(findings)} low-severity notes)")
        else:
            high = [f for f in findings if f["severity"] == "high"]
            print(f"✗ {args.file} FAILED — {len(high)} high-severity issues:")
            for f in high[:20]:
                print(f"  line {f['line']}: {f['issue']}")
                print(f"    {f['snippet']}")
            if len(high) > 20:
                print(f"  ... +{len(high)-20} more")
        if findings:
            n_low = sum(1 for f in findings if f["severity"] == "low")
            if n_low:
                print(f"  ({n_low} hedge-word notes)")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
