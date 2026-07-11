#!/usr/bin/env python3
"""universalize_report.py — the truth-floor for A75 (recipient projection) + A70
(incorporation gate) universalization. READ-ONLY. Makes the remaining un-wired paths
ENUMERATED, not invisible (deploy_845 truth-floor requirement).

It does NOT enforce or wire anything — it reports, per-path, who is wired vs who still
reads raw. Graduation is per-path (A70 pattern), so this is the checklist that shrinks.

  A75 lane — every agent that reads the VERIFIED FACT LEDGER (`matter_facts`) should take
             its slice through a RecipientProfile (recipient_projection.project_fact_slice),
             so WHO=A5-wall / FORM=handles-intact-or-A34-translated / DOSE=push-ceiling.
             Un-wired = reads `matter_facts` raw and does not import recipient_projection.
  A70 lane — every stakeholder-facing DELIVERABLE EMITTER should call
             require_incorporation(matter, stakeholder) and fail-closed on a thin base.
             Un-gated = a known emitter that never calls require_incorporation.

Usage: python3 scripts/universalize_report.py            (human)
       python3 scripts/universalize_report.py --json      (machine / CI)
Exit 0 always (a report, not a gate) unless --strict (exit 1 if any un-wired remain).
"""
import argparse
import json
import os
import re
import sys

REPO = "/root/landtek"
SCAN_DIRS = ["scripts", "leo_tools"]

# Infra / meta / test / migration files never "deliver" to a recipient — exclude from the
# A75 raw-reader census (they legitimately read facts to gate, test, or project them).
A75_EXCLUDE = re.compile(
    r"(recipient_projection|incorporation_gate|ontology_|agent_concept_map|timeline_coverage|"
    r"supervisor|calendar_sync|universalize_report|client_ontology|verify_worker|"
    r"^apply_deploy_|^test_|_harness|backup_workflow|deadline)", re.I)

# Known stakeholder-facing deliverable emitters (A70 lane). Extend as new emitters land.
EMITTERS = ["brief_drafter", "case_memo", "dossier_pipeline", "case_bundle",
            "ombudsman_hunter", "affidavit", "demand_letter", "case_forward"]
# Disposition: name-matches an emitter token but is NOT a per-matter stakeholder deliverable, so the
# A70 gate (require_incorporation(matter, stakeholder)) is a CATEGORY ERROR — never force it.
A70_NON_EMITTER = {
    "case_forward_digest": "internal cross-matter daily digest to the operator (no single matter base)",
}

FACT_READ = re.compile(r"\bFROM\s+matter_facts\b", re.I)
WIRED_A75 = re.compile(r"recipient_projection|project_fact_slice", re.I)
WIRED_A70 = re.compile(r"require_incorporation", re.I)


def py_files():
    out = []
    for d in SCAN_DIRS:
        base = os.path.join(REPO, d)
        for root, _, fns in os.walk(base):
            out += [os.path.join(root, fn) for fn in fns if fn.endswith(".py")]
    return sorted(out)


def scan():
    a75_wired, a75_raw = [], []
    a70_gated, a70_ungated = [], []
    for path in py_files():
        name = os.path.basename(path)[:-3]
        try:
            src = open(path, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        # A75 lane
        if FACT_READ.search(src) and not A75_EXCLUDE.search(name):
            (a75_wired if WIRED_A75.search(src) else a75_raw).append(name)
        # A70 lane (skip dispositioned non-emitters — category error to gate them)
        if any(e in name for e in EMITTERS) and name not in A70_NON_EMITTER:
            (a70_gated if WIRED_A70.search(src) else a70_ungated).append(name)
    return {
        "a75_wired": sorted(set(a75_wired)), "a75_raw": sorted(set(a75_raw)),
        "a70_gated": sorted(set(a70_gated)), "a70_ungated": sorted(set(a70_ungated)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="exit 1 if any un-wired path remains")
    args = ap.parse_args()
    r = scan()
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        print("=== A75 RECIPIENT-PROJECTION universalization (fact-ledger readers) ===")
        print(f"  🟢 wired through a profile ({len(r['a75_wired'])}): "
              + (", ".join(r["a75_wired"]) or "—"))
        print(f"  🟡 raw matter_facts readers — GRADUATE per-path ({len(r['a75_raw'])}): "
              + (", ".join(r["a75_raw"]) or "— none, universal!"))
        print()
        print("=== A70 INCORPORATION-GATE universalization (deliverable emitters) ===")
        print(f"  🟢 gated (calls require_incorporation) ({len(r['a70_gated'])}): "
              + (", ".join(r["a70_gated"]) or "—"))
        print(f"  🟡 emitters NOT gated — GRADUATE per-path ({len(r['a70_ungated'])}): "
              + (", ".join(r["a70_ungated"]) or "— none, universal!"))
        if A70_NON_EMITTER:
            print("  ⚪ dispositioned (NOT a stakeholder emitter — gating would be a category error): "
                  + ", ".join(f"{k} ({v})" for k, v in A70_NON_EMITTER.items()))
        print()
        total_open = len(r["a75_raw"]) + len(r["a70_ungated"])
        print(f"open universalization debt: {total_open} path(s). "
              "Each is a per-path graduation (A70 pattern), not a global flip.")
    if args.strict and (r["a75_raw"] or r["a70_ungated"]):
        sys.exit(1)


if __name__ == "__main__":
    main()
