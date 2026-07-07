#!/usr/bin/env python3
"""ontology_migrate.py — staged, fail-closed harness for the ONTOLOGY.md v1.0 renumber.

The v1.0 migration (docs/ONTOLOGY_STRUCTURE.md §6.1) splits the lightweight Core Registry from full
Domain Models and gives cross-cutting rules their own section — a `major` bump that renumbers live
sections. It is deliberately NOT a one-button script: several domains split into a registry ROW (§2)
*and* a domain MODEL (§3), which is authoring (not substitution); and old/new section numbers share one
namespace (old §6 Access → new §5.4, while new §6 = Component Mapping), so a blind rewrite would corrupt
the doc. This harness therefore automates ONLY the deterministic parts and FLAGS the authored ones. It
NEVER edits ONTOLOGY.md prose.

Modes (read-only unless --write; ONTOLOGY.md body is never touched):
  --preflight   Read the LIVE ONTOLOGY.md, enumerate every numbered heading, and check each against the
                PLAN below. FAIL-CLOSED (exit 1) on any heading the plan doesn't cover — that means the
                parallel session added/renamed a section since the plan was authored, so update the PLAN
                before firing. This is the "is it still safe to fire?" gate.
  --refs        Scan the dependent files for ONTOLOGY section references, print each with its proposed new
                value split into CERTAIN (safe top-level renumbers) vs AUTHORED (the §2→§3 splits — human
                decides). --write applies ONLY the CERTAIN ones.
  (Post-migration acceptance gate: `ontology_check.py --structure` must go GREEN, then wire it to the gate.)

FIRE RUNBOOK — execute only when ONTOLOGY.md commits have gone quiet (clean status, no new pushes):
  1.  git checkout -b ontology-v1
  2.  python3 scripts/ontology_migrate.py --preflight            # must be CLEAN (plan covers every heading)
  3.  AUTHOR the body per docs/ONTOLOGY_STRUCTURE.md §2 map: split registry rows (§2) from domain models
      (§3), merge §0+§1, move §8→§6, fold §3-drift + §7-regenerate into §8. The A-numbers do NOT move.
  4.  python3 scripts/ontology_migrate.py --refs --write         # rewrite the CERTAIN cross-refs; hand-fix AUTHORED
  5.  python3 scripts/ontology_check.py --structure              # must be GREEN (0 violations)
  6.  python3 scripts/ontology_check.py --coverage              # must stay GREEN (VPS)
  7.  python3 truth_tests/run_all.py                            # must stay GREEN (VPS)
  8.  major version bump + change-log entry; deploy; then wire --structure into the deploy gate.
"""
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The migration PLAN, straight from docs/ONTOLOGY_STRUCTURE.md §2 "current → target" map.
# confidence: "certain" = a deterministic renumber safe to auto-rewrite in cross-references;
#             "authored" = a domain split/relocation the human performs (flagged, never auto-rewritten).
# Ordered longest-prefix-first so "8.19" matches "8.19"→"6.19" before the bare "8"→"6" rule.
PLAN = [
    # (old_section, new_section, confidence, note)
    ("2.4",  "3.1", "authored", "Geometry domain model → §3.1 (a lightweight §2.4 registry row is also authored)"),
    ("2.8",  "3.8", "authored", "Case Theory → Domain Models"),
    ("2.9",  "3.3", "authored", "Entity Resolution → Domain Models"),
    ("2.10", "3.4", "authored", "Client/Matter Separation → Domain Models"),
    ("2.11", "3.5", "authored", "Fact Harvesting & Provenance → Domain Models"),
    ("2.12", "3.6", "authored", "Supervision & Work Ordering → Domain Models"),
    ("2.13", "3.5", "authored", "Truth & Reconciliation → folds with Fact Harvesting (§3.5)"),
    ("2.14", "3.7", "authored", "Communications → Domain Models"),
    ("2.15", "3.9", "authored", "Client-Facing Projection → Domain Models"),
    # top-level renumbers — deterministic, safe to auto-rewrite
    ("8",    "6",   "certain",  "Oriented Operational Map → Component Mapping (all §8.x → §6.x)"),
    ("9",    "7",   "certain",  "Future Domains → §7"),
    ("5",    "5.1", "certain",  "Client isolation → Cross-Cutting §5.1"),
    ("6",    "5.4", "certain",  "Access-model note → Cross-Cutting §5.4"),
    ("7",    "8",   "certain",  "How to regenerate → Maintenance §8"),
    ("3",    "8",   "certain",  "Drift/legacy → Maintenance §8"),
    ("0",    "1",   "certain",  "Ground planes → merged into §1 Purpose & Design Principles"),
    # §1, §2, §2.1–§2.3, §2.5–§2.7, §4 keep their top number (registry stays §2; invariants stay §4)
    ("4",    "4",   "certain",  "System Invariants — number unchanged (A-series never moves)"),
    ("2.1",  "2.1", "certain",  "Corpus registry row — unchanged"),
    ("2.2",  "2.2", "certain",  "Actors registry row — unchanged"),
    ("2.3",  "2.3", "certain",  "Titles registry row — unchanged"),
    ("2.5",  "2.5", "authored", "Knowledge/facts — reconcile to a §2.5 Facts&Provenance registry row"),
    ("2.6",  "2.6", "authored", "DUPLICATE §2.6 in live doc (Strategy + Gated-core) — split/renumber by hand"),
    ("2.7",  "2.6", "authored", "Interface/comms → §2.6 Communications registry row"),
    ("2",    "2",   "certain",  "Core Concept Registry — top number unchanged"),
    ("1",    "1",   "certain",  "Axiom → §1 (provenance principle may also surface in §5.2)"),
]

DEP_FILES = [
    "scripts/ontology_check.py",
    "scripts/agent_concept_map.py",
    "truth_tests/test_superseded_tables_empty.py",
    "docs/ontology_validator_spec.md",
]

HEADING_RE = re.compile(r'^#{1,6}\s+(\d+(?:\.\d+)*)\b')
# A section cross-reference in prose/code: "§8.19", "§ 2.10", "sec2", "sec 3", "section 8.1".
REF_RE = re.compile(r'(?:§\s*|\bsec(?:tion)?\s*)(\d+(?:\.\d+)*)', re.I)
# A §N that belongs to ANOTHER document's numbering — must never be rewritten as if it were ONTOLOGY.md.
OTHER_DOC_RE = re.compile(r'(STRUCTURE|ARCHITECTURE|MASTER_PLAN|CONSTITUTION|README)', re.I)


def _classify_ref(text, m):
    """Classify one section-reference match: ('other'|'unchanged'|'certain'|'authored', num, new, note)."""
    num = m.group(1)
    ctx = text[max(0, m.start() - 45):m.end() + 5]
    if OTHER_DOC_RE.search(ctx):
        return "other", num, None, None            # a ref into another doc's numbering — leave untouched
    hit = _plan_lookup(num)
    if not hit or hit[0] == num:
        return "unchanged", num, None, None
    new, conf, note = hit
    return conf, num, new, note


def _plan_lookup(num):
    """Longest-prefix match of a section number against the PLAN. Returns (new, confidence, note) or None."""
    for old, new, conf, note in PLAN:
        if num == old:
            return new, conf, note
    for old, new, conf, note in PLAN:                      # prefix (e.g. 8.19 under the bare 8→6 rule)
        if num.startswith(old + "."):
            return new + num[len(old):], conf, note
    return None


def cmd_preflight():
    """Read the live ONTOLOGY.md; every numbered heading must be covered by the PLAN. Fail-closed on drift."""
    try:
        with open(os.path.join(REPO, "ONTOLOGY.md")) as f:
            lines = f.read().splitlines()
    except Exception:
        print("cannot read ONTOLOGY.md"); return 2
    seen, uncovered = [], []
    for ln, line in enumerate(lines, 1):
        m = HEADING_RE.match(line)
        if not m:
            continue
        num = m.group(1)
        hit = _plan_lookup(num)
        seen.append((num, hit, line.strip()[:52], ln))
        if hit is None:
            uncovered.append((num, ln, line.strip()[:52]))
    print(f"=== v1.0 migration PREFLIGHT — {len(seen)} numbered headings in the live ONTOLOGY.md ===")
    for num, hit, text, ln in seen:
        if hit:
            new, conf, _ = hit
            tag = "  " if conf == "certain" else "✎ "   # ✎ = authored (human moves it)
            print(f"  {tag}§{num:<5} → §{new:<5} [{conf}]   {text}")
        else:
            print(f"  ⚠️  §{num:<5} → ??????  [UNMAPPED]  {text}")
    if uncovered:
        print(f"\n  ✗ NOT SAFE TO FIRE — {len(uncovered)} heading(s) the plan doesn't cover "
              f"(the doc changed since the plan was authored). Update PLAN before migrating:")
        for num, ln, text in uncovered:
            print(f"      §{num} (line {ln}) — {text}")
        return 1
    print(f"\n  ✓ every heading is covered by the plan. ✎ = authored move (human), blank = deterministic.")
    return 0


def cmd_refs(write):
    """Report ONTOLOGY section cross-references in the dependent files; --write applies only CERTAIN ones."""
    certain_edits, authored_flags, other_skips = [], [], []
    for rel in DEP_FILES:
        path = os.path.join(REPO, rel)
        try:
            with open(path) as f:
                text = f.read()
        except Exception:
            print(f"  (skip, unreadable: {rel})"); continue
        for m in REF_RE.finditer(text):
            conf, num, new, note = _classify_ref(text, m)
            frag = text[max(0, m.start() - 22):m.end() + 18].replace("\n", " ")
            if conf == "certain":
                certain_edits.append((rel, num, new, frag))
            elif conf == "authored":
                authored_flags.append((rel, num, new, note, frag))
            elif conf == "other":
                other_skips.append((rel, num, frag))
        if write:
            def _sub(m):
                conf, num, new, _ = _classify_ref(m.string, m)
                return m.group(0).replace(num, new) if conf == "certain" else m.group(0)
            new_text = REF_RE.sub(_sub, text)
            if new_text != text:
                with open(path, "w") as f:
                    f.write(new_text)
    total = len(certain_edits) + len(authored_flags)
    print(f"=== v1.0 migration cross-reference report — {total} ONTOLOGY section ref(s) that move ===")
    print(f"\n  CERTAIN — safe to auto-rewrite ({len(certain_edits)}){' [WRITTEN]' if write else ' [dry — pass --write]'}:")
    for rel, num, new, frag in certain_edits:
        print(f"    {rel}: §{num} → §{new}    …{frag}…")
    print(f"\n  ✎ AUTHORED — hand-fix after the body split ({len(authored_flags)}), NEVER auto-rewritten:")
    for rel, num, new, note, frag in authored_flags:
        print(f"    {rel}: §{num} → §{new}?  ({note})    …{frag}…")
    print(f"\n  ⏭  SKIPPED — refs into OTHER docs' numbering ({len(other_skips)}), left untouched by design:")
    for rel, num, frag in other_skips:
        print(f"    {rel}: §{num} (other-doc)   …{frag}…")
    return 0


def main():
    if "--preflight" in sys.argv:
        sys.exit(cmd_preflight())
    if "--refs" in sys.argv:
        sys.exit(cmd_refs("--write" in sys.argv))
    print(__doc__)
    sys.exit(0)


if __name__ == "__main__":
    main()
