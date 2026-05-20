#!/usr/bin/env python3
"""mediation_pack.py — Consolidated strategic posture document for the
2026-06-02 mediation in Civil Case 26-360.

Composes outputs from prior runs of case_theory_engine into one
investor/counsel-grade markdown:

  Inputs (from drafts/, dated):
    - case_theory_26-360-void-chain_<date>.json     (master theory)
    - case_theory_transferees_summary_<date>.md     (per-transferee headline)
    - case_theory_transferee-<slug>_<date>.json     (per-transferee detail)

  Output:
    - drafts/mediation_pack_26-360_<date>.md
    - drafts/mediation_pack_26-360_<date>.json (structured for downstream)

Sections produced:
  1. Executive summary (one paragraph)
  2. The offense — void chain claim by claim (verified only)
  3. Strongest leverage / verified positives (ranked by curative impact)
  4. Critical unverified claims (high curative weight, evidence gap)
  5. Per-transferee posture table (19 transferees, headline scores)
  6. Title chain audit (operative chains to T-111 for every title)
  7. Anticipated defense lines (extracted from challenger reasons)
  8. Discovery priority (gaps ranked)
  9. Settlement positioning (cumulative curative score → settlement bands)

Usage:
  python3 mediation_pack.py                  # auto-pick latest date
  python3 mediation_pack.py --date 2026-05-21
  python3 mediation_pack.py --rerun           # call case_theory_engine first
"""
import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/root/landtek")

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
DRAFTS_DIR = Path("/root/landtek/drafts")


def _latest_dated_file(pattern):
    """Return the latest-dated path matching pattern, or None."""
    files = sorted(DRAFTS_DIR.glob(pattern))
    return files[-1] if files else None


def _load_json(path):
    if not path or not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _settlement_band(realized, possible):
    """Heuristic settlement-positioning band from realized title-curative ratio."""
    if not possible:
        return ("?", "insufficient data")
    pct = realized / possible
    if pct >= 0.90:
        return ("AAA", "Strongly defensible offense theory — settlement floor should reflect "
                       "full restoration value; ceiling is principled compromise on procedural risk.")
    if pct >= 0.75:
        return ("AA", "Defensible with addressable gaps — settlement floor partial; "
                      "ceiling structured to close remaining gaps via discovery commitments.")
    if pct >= 0.50:
        return ("A", "Mixed — substantial verified spine but material gaps. Settlement value "
                     "depends on which gaps the other side knows about.")
    return ("B", "Position not yet evidence-grade for mediation. Defer firm posture until "
                 "discovery closes critical gaps.")


def _extract_anticipated_defense(theory_results):
    """Pull `defense_anticipation` from verified claims that have one."""
    lines = []
    for r in theory_results:
        if r.get("verdict") != "verified":
            continue
        da = (r.get("defense_anticipation") or "").strip()
        if not da:
            continue
        lines.append((r["id"], da))
    return lines


def _challenger_dissents(theory_results):
    """For verified claims where challenger NOTED a concern despite ultimately not refuting,
    surface the concern as a defense indicator."""
    out = []
    for r in theory_results:
        if r.get("verdict") != "verified":
            continue
        cr = (r.get("challenger_reason") or "").strip()
        if not cr:
            continue
        # Only surface if reason mentions any of: but, however, contradict, dispute, gap
        if re.search(r"\b(but|however|contradict|dispute|gap|missing|unclear)\b", cr, re.IGNORECASE):
            out.append((r["id"], cr[:280]))
    return out


def assemble(case_theory_json, transferees_summary_md, transferee_jsons, run_date, cur):
    """Build the consolidated mediation pack."""
    lines = []
    matter = case_theory_json.get("theory", {}).get("matter_code", "MWK-001")
    theory = case_theory_json.get("theory", {})
    results = case_theory_json.get("results", [])
    meta = case_theory_json.get("run_meta", {})

    realized = sum(max(0, r.get("title_curative_score_delta", 0) or 0)
                   for r in results if r.get("verdict") == "verified")
    possible = sum(max(0, r.get("title_curative_score_delta", 0) or 0) for r in results)
    n_verified = sum(1 for r in results if r.get("verdict") == "verified")
    n_struct = sum(1 for r in results if r.get("structurally_supported"))
    band, band_note = _settlement_band(realized, possible)

    # ─── Header ─────────────────────────────────────────────────────────────
    lines.append(f"# Mediation Pack — {theory.get('case_caption', 'Civil Case 26-360')}")
    lines.append("")
    lines.append(f"**Forcing function:** {theory.get('forcing_function', {}).get('type', 'mediation').title()} "
                 f"on **{theory.get('forcing_function', {}).get('date', '2026-06-02')}** at "
                 f"**{theory.get('forcing_function', {}).get('venue', 'RTC Camarines Norte (Daet)')}**")
    lines.append(f"**Generated:** {run_date}")
    lines.append(f"**Method:** Composes case_theory_engine output (deterministic, temperature=0 calibrated) "
                 f"+ per-transferee posture + title_chain_walker provenance.")
    lines.append("")

    # ─── 1. Executive summary ──────────────────────────────────────────────
    lines.append("## 1. Executive summary")
    lines.append("")
    lines.append(f"> {theory.get('summary', '')}")
    lines.append("")
    lines.append(f"**Posture grade: `{band}`** ({realized}/{possible} title-curative score realized, "
                 f"{n_verified}/{len(results)} claims verified, {n_struct}/{len(results)} structurally supported).")
    lines.append("")
    lines.append(f"> {band_note}")
    lines.append("")

    # ─── 2. The offense — verified void chain ───────────────────────────────
    lines.append("## 2. The offense — verified claim chain")
    lines.append("")
    lines.append("Each row is a claim that PASSED the calibrated truth-negotiator's adversarial pass. "
                 "Citation tier (V·N notarized / V·F filed / V·G government / V·S signed) per claim.")
    lines.append("")
    lines.append("| Claim | Verdict | Cite | Top docs | Curative Δ |")
    lines.append("|---|---|---|---|---|")
    for r in results:
        if r.get("verdict") != "verified":
            continue
        cite = r.get("citation_tag") or "—"
        docs = r.get("evidence_doc_ids") or []
        doc_str = ", ".join(f"doc#{d}" for d in docs[:3]) if docs else "—"
        delta = r.get("title_curative_score_delta", 0) or 0
        lines.append(f"| `{r['id']}` — {r.get('text', '')[:80]} | `verified` | {cite} | {doc_str} | `{delta:+d}` |")
    lines.append("")

    # ─── 3. Strongest leverage (verified high-curative) ────────────────────
    lines.append("## 3. Strongest leverage — keystone & high-impact verified claims")
    lines.append("")
    strong = [r for r in results if r.get("verdict") == "verified"
              and (r.get("title_curative_score_delta") or 0) >= 3]
    strong.sort(key=lambda x: -(x.get("title_curative_score_delta") or 0))
    for r in strong[:7]:
        delta = r.get("title_curative_score_delta", 0)
        impact = r.get("development_impact") or r.get("if_supported_implies", "")
        lines.append(f"- **`Δ{delta:+d}`** — **`{r['id']}`** — {impact}")
    lines.append("")

    # ─── 4. Critical unverified claims (gaps) ───────────────────────────────
    lines.append("## 4. Critical unverified claims (gaps to close)")
    lines.append("")
    weak = [r for r in results if r.get("verdict") not in ("verified", "error")
            and (r.get("title_curative_score_delta") or 0) >= 3]
    weak.sort(key=lambda x: -(x.get("title_curative_score_delta") or 0))
    if weak:
        for r in weak:
            delta = r.get("title_curative_score_delta", 0)
            implies = r.get("if_supported_implies", "")
            lines.append(f"- **`Δ{delta:+d}`** — `{r['id']}` (verdict: `{r.get('verdict')}`) — {implies}")
    else:
        lines.append("_All high-curative claims (Δ ≥ 3) are currently verified._")
    lines.append("")

    # ─── 5. Per-transferee headline table ──────────────────────────────────
    if transferee_jsons:
        lines.append("## 5. Per-transferee posture")
        lines.append("")
        lines.append(f"Each of the **{len(transferee_jsons)}** non-Balane named transferees has an independent "
                     f"theory. Shared void-chain spine + per-parcel leaf claims. All theories run on the "
                     f"same deterministic engine.")
        lines.append("")
        lines.append("| Transferee | Parcels | Verified | Curative | Notes |")
        lines.append("|---|---|---|---|---|")
        sorted_transferees = sorted(transferee_jsons,
                                     key=lambda t: -(t.get("run_meta", {}).get("curative_realized") or 0))
        for tj in sorted_transferees:
            tj_meta = tj.get("run_meta", {})
            tj_theory = tj.get("theory", {})
            name_match = re.match(r"Per-transferee theory — (.+?)\s*\(", tj_theory.get("case_caption", ""))
            name = name_match.group(1) if name_match else tj_theory.get("theory_id", "?")
            n_claims = tj_meta.get("n_claims", 0)
            n_verified_t = tj_meta.get("n_verified", 0)
            realized_t = tj_meta.get("curative_realized", 0)
            possible_t = tj_meta.get("curative_possible", 0)
            # Count parcels = claims with id ending in -parcel-N-of-M OR -acquisition
            n_parcels = sum(1 for r in tj.get("results", [])
                            if re.search(r"-(parcel-\d+|acquisition|transferee-of-record)\b", r.get("id", "")))
            notes = ""
            if n_parcels == 0:
                notes = "_no title_transfers row — discovery priority_"
            elif realized_t == possible_t:
                notes = "fully realized"
            lines.append(f"| **{name}** | {n_parcels} | {n_verified_t}/{n_claims} | "
                         f"{realized_t}/{possible_t} | {notes} |")
        lines.append("")

    # ─── 6. Title chain audit ──────────────────────────────────────────────
    from title_chain_walker import render_chain_md, chain_integrity_audit
    from case_theory_engine import TITLE_REF

    titles_seen = set()
    for r in results:
        for m in TITLE_REF.findall(r.get("text") or ""):
            titles_seen.add(m.strip())

    if titles_seen:
        lines.append("## 6. Title chain audit")
        lines.append("")
        lines.append(f"Every TCT referenced in the theory walked to the operative root (`T-111`). "
                     f"Ghost titles (OCT T-106 and its OCR variants) are skipped per canon. Edges with "
                     f"no `source_doc_id` are flagged for discovery.")
        lines.append("")
        audit = chain_integrity_audit(cur, sorted(titles_seen), matter)
        lines.append("| Title | Chain length | Issues |")
        lines.append("|---|---|---|")
        for a in audit:
            issues = "; ".join(a["issues"]) if a["issues"] else "_(clean)_"
            issues_disp = issues[:120].replace("|", "/")
            lines.append(f"| `{a['title']}` | {a['chain_length']} | {issues_disp} |")
        lines.append("")

    # ─── 7. Anticipated defense lines ──────────────────────────────────────
    lines.append("## 7. Anticipated defense lines")
    lines.append("")
    da_list = _extract_anticipated_defense(results)
    if da_list:
        lines.append("From the theory's `defense_anticipation` fields on verified claims — these are what "
                     "the other side is most likely to attack first:")
        lines.append("")
        for claim_id, da in da_list:
            lines.append(f"- **`{claim_id}`** — {da}")
        lines.append("")

    cd_list = _challenger_dissents(results)
    if cd_list:
        lines.append("**Negotiator's own caveats** (from challenger reasoning on verified claims — soft signals "
                     "where the other side may find footholds):")
        lines.append("")
        for claim_id, cd in cd_list:
            lines.append(f"- **`{claim_id}`** — {cd}")
        lines.append("")

    # ─── 8. Discovery priority ─────────────────────────────────────────────
    lines.append("## 8. Discovery priority")
    lines.append("")
    discovery = []
    for r in results:
        for tev in (r.get("transfer_evidence_status") or []):
            if tev.get("status") in ("missing", "unclear", "weak"):
                impact = abs(r.get("title_curative_score_delta", 0) or 0)
                discovery.append({
                    "claim_id": r["id"],
                    "required_doc": tev["required_doc_label"],
                    "weight": tev["weight"],
                    "curative_impact": impact,
                    "score": int(tev["weight"]) * max(1, impact),
                })
    discovery.sort(key=lambda x: -x["score"])
    if discovery:
        lines.append("Gaps ranked by `weight × curative-impact`. Highest-leverage discovery first.")
        lines.append("")
        lines.append("| # | Claim | Required doc | Weight | Curative Δ | Priority |")
        lines.append("|---|---|---|---|---|---|")
        for i, d in enumerate(discovery[:15], 1):
            lines.append(f"| {i} | `{d['claim_id']}` | {d['required_doc']} | "
                         f"{d['weight']} | {d['curative_impact']} | {d['score']} |")
        lines.append("")
    else:
        lines.append("_No transfer-linked discovery gaps surfaced in current theory (no claims have `transfer_link` set)._")
        lines.append("")

    # ─── 9. Settlement positioning ─────────────────────────────────────────
    lines.append("## 9. Settlement positioning")
    lines.append("")
    lines.append(f"**Posture grade: `{band}`**  ({realized}/{possible} = {100*realized/max(1,possible):.0f}% "
                 f"of attainable title-curative upside currently realized).")
    lines.append("")
    lines.append(f"> {band_note}")
    lines.append("")
    lines.append("**What each verified claim is worth at mediation:**")
    lines.append("")
    lines.append("- Each verified `Δ ≥ 5` claim is independent leverage — even one is enough to force "
                 "real settlement discussion.")
    lines.append("- Verified `Δ 1-3` claims are corroborating context — they prevent the other side from "
                 "characterizing the case as speculative.")
    lines.append("- Unverified `Δ ≥ 5` claims are the points the other side will attack — close these "
                 "via discovery if mediation breaks down.")
    lines.append("")

    # ─── Footer ─────────────────────────────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("## Provenance")
    lines.append("")
    lines.append(f"- Truth-negotiator: 5/5 calibrated back-tests, temperature=0 deterministic")
    lines.append(f"- Title chain canon: T-111 operative root for MWK-001; OCT T-106 flagged as ghost")
    lines.append(f"- Hallucination-proof discipline: only `verified` claims are quotable in court-facing output")
    lines.append(f"- Source: drafts/case_theory_*.json (theory) + title_chain_walker (provenance per edge)")
    lines.append("")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None,
                    help="Use files dated YYYY-MM-DD (default: latest)")
    ap.add_argument("--rerun", action="store_true",
                    help="Re-run case_theory_engine + --all-transferees before assembling")
    args = ap.parse_args()

    if args.rerun:
        print("Re-running case_theory_engine on civil_case_26_360…")
        subprocess.run(["python3", "case_theory_engine.py", "case_theories.civil_case_26_360"],
                       cwd="/root/landtek", check=True)
        print("Re-running case_theory_engine --all-transferees…")
        subprocess.run(["python3", "case_theory_engine.py", "--all-transferees"],
                       cwd="/root/landtek", check=True)

    # Locate inputs
    if args.date:
        date = args.date
    else:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    case_theory_json_path = DRAFTS_DIR / f"case_theory_26-360-void-chain_{date}.json"
    if not case_theory_json_path.exists():
        # Fall back to the latest of any date
        case_theory_json_path = _latest_dated_file("case_theory_26-360-void-chain_*.json")
        if case_theory_json_path:
            print(f"⚠ No file for {date}; using latest: {case_theory_json_path.name}")
        else:
            print("✗ No case_theory_26-360-void-chain JSON found in drafts/. Run --rerun.")
            sys.exit(2)

    case_theory_json = _load_json(case_theory_json_path)

    transferees_summary_md = _latest_dated_file(f"case_theory_transferees_summary_{date}.md")
    if not transferees_summary_md:
        transferees_summary_md = _latest_dated_file("case_theory_transferees_summary_*.md")

    transferee_jsons = []
    for p in DRAFTS_DIR.glob(f"case_theory_transferee-*_{date}.json"):
        d = _load_json(p)
        if d:
            transferee_jsons.append(d)
    if not transferee_jsons:
        # Try latest available date
        latest_summary_date = None
        if transferees_summary_md:
            m = re.search(r"(\d{4}-\d{2}-\d{2})", transferees_summary_md.name)
            if m:
                latest_summary_date = m.group(1)
        if latest_summary_date:
            for p in DRAFTS_DIR.glob(f"case_theory_transferee-*_{latest_summary_date}.json"):
                d = _load_json(p)
                if d:
                    transferee_jsons.append(d)

    print(f"Inputs:")
    print(f"  case theory: {case_theory_json_path.name}")
    print(f"  transferee summary: {transferees_summary_md.name if transferees_summary_md else '(none)'}")
    print(f"  per-transferee jsons: {len(transferee_jsons)}")

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    md = assemble(case_theory_json, transferees_summary_md, transferee_jsons, run_date, cur)

    out_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = DRAFTS_DIR / f"mediation_pack_26-360_{out_date}.md"
    out_path.write_text(md)

    json_path = DRAFTS_DIR / f"mediation_pack_26-360_{out_date}.json"
    json_path.write_text(json.dumps({
        "theory": case_theory_json,
        "n_transferees": len(transferee_jsons),
        "transferee_meta": [t.get("run_meta") for t in transferee_jsons],
        "run_date": run_date,
    }, indent=2, default=str))

    print()
    print(f"Mediation pack: {out_path}")
    print(f"Structured:     {json_path}")
    print()
    print(f"Lines: {len(md.splitlines())}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
