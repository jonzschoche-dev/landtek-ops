#!/usr/bin/env python3
"""case_theory_engine.py — Build a unified case theory + evidence gap report.

Composes:
  - truth_negotiator.negotiate() for per-claim verification (5/5 calibrated)
  - transfer_doc_status + doc_requirements_law for per-claim required-evidence gaps
  - Theory definition (claim chain with dependencies + development-impact fields)

For each claim it captures:
  - verdict (from truth-negotiator: verified/refuted/uncertain/unsourced/uncitable_draft)
  - top backing docs with citation tier (V·N / V·F / V·G / V·S)
  - challenger reason (anticipated defense extracted from negotiator's adversarial pass)
  - chain status (parents verified? structurally supported?)
  - transfer-linked evidence gap (which required docs are missing, if transfer_link set)
  - development_impact narrative + title_curative_score_delta (int -10..+10)

Outputs:
  - drafts/case_theory_<theory_id>_<date>.md — narrative posture document
  - drafts/case_theory_<theory_id>_<date>.json — structured for downstream consumers

Usage:
  python3 case_theory_engine.py case_theories.civil_case_26_360
  python3 case_theory_engine.py case_theories.civil_case_26_360 --no-report

Cost note: each claim triggers one truth-negotiator call (Sonnet 4.6, prompt-cached).
At ~$0.005-0.007 per claim, a 22-claim theory costs ~$0.11-0.15 per run.
"""
import argparse
import importlib
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras

sys.path.insert(0, "/root/landtek")

from title_chain_walker import render_chain_md, chain_integrity_audit  # noqa: E402

# Pattern for TCT/OCT title references in claim text.
TITLE_REF = re.compile(r"\b(?:OCT\s+)?T-\d{2,5}(?:-\d{3,15})?\b")

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
DRAFTS_DIR = Path("/root/landtek/drafts")

VERDICT_EMOJI = {
    "verified": "✓",
    "refuted": "✗",
    "uncertain": "?",
    "unsourced": "○",
    "uncitable_draft": "▽",
    "error": "!",
}


def _load_anthropic_key():
    env_path = "/root/landtek/.env"
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            if line.startswith("ANTHROPIC_API_KEY="):
                os.environ["ANTHROPIC_API_KEY"] = line.strip().split("=", 1)[1]


def evaluate_claim(cur, claim, matter_code):
    """Run truth_negotiator + cross-reference transfer evidence gaps."""
    from truth_negotiator import negotiate
    try:
        r = negotiate(claim["text"], case_file=matter_code, asked_by="case_theory_engine")
    except Exception as e:
        return {
            "id": claim["id"],
            "text": claim["text"],
            "section": claim.get("section", ""),
            "verdict": "error",
            "error": str(e)[:300],
            "depends_on": claim.get("depends_on", []),
            "title_curative_score_delta": int(claim.get("title_curative_score_delta") or 0),
            "development_impact": claim.get("development_impact", ""),
        }

    result = {
        "id": claim["id"],
        "text": claim["text"],
        "section": claim.get("section", ""),
        "depends_on": claim.get("depends_on", []),
        "transfer_link": claim.get("transfer_link"),
        "if_supported_implies": claim.get("if_supported_implies", ""),
        "defense_anticipation": claim.get("defense_anticipation", ""),
        "development_impact": claim.get("development_impact", ""),
        "title_curative_score_delta": int(claim.get("title_curative_score_delta") or 0),
        "verdict": r["verdict"],
        "citation_tag": r.get("citation_tag"),
        "evidence_doc_ids": r.get("fact_backers") or [],
        "challenger_reason": r.get("challenger_reason", "") or "",
        "evidence_count": r.get("evidence_count"),
    }

    if claim.get("transfer_link"):
        try:
            cur.execute("""
                SELECT tds.requirement_id, dr.required_doc_label, dr.legal_basis,
                       dr.weight, tds.status, tds.evidence_doc_id
                  FROM transfer_doc_status tds
                  JOIN doc_requirements_law dr ON dr.id = tds.requirement_id
                 WHERE tds.transfer_id = %s
                 ORDER BY dr.weight DESC, dr.required_doc_label
            """, (claim["transfer_link"],))
            result["transfer_evidence_status"] = [dict(row) for row in cur.fetchall()]
        except Exception as e:
            result["transfer_evidence_status_error"] = str(e)[:200]

    return result


def compute_chain_health(results):
    """For each claim, mark structural support — verified AND all deps verified."""
    by_id = {r["id"]: r for r in results}
    for r in results:
        weakest = []
        for parent_id in r.get("depends_on", []):
            p = by_id.get(parent_id)
            if not p or p.get("verdict") != "verified":
                weakest.append(parent_id)
        r["chain_broken_at"] = weakest
        r["structurally_supported"] = (r.get("verdict") == "verified" and not weakest)
    return results


def _doc_meta(cur, doc_ids):
    if not doc_ids:
        return {}
    cur.execute("""
        SELECT id, smart_filename, classification, execution_status
          FROM documents WHERE id = ANY(%s)
    """, (list(doc_ids),))
    return {r["id"]: dict(r) for r in cur.fetchall()}


def render_markdown(theory, results, run_meta, cur):
    """Build the unified posture markdown."""
    lines = []
    lines.append(f"# {theory.get('case_caption', 'Case Theory')} — Strategic Posture")
    lines.append("")
    lines.append(f"**Theory ID:** `{theory['theory_id']}`")
    lines.append(f"**Generated:** {run_meta['generated_at']}")
    lines.append(f"**Method:** Calibrated truth-negotiator (5/5 back-tests) + transfer_doc_status cross-reference + theory-chain dependency analysis.")
    lines.append("")
    lines.append(f"> {theory['summary']}")
    lines.append("")

    ff = theory.get("forcing_function") or {}
    if ff:
        fields = []
        if ff.get("type"):
            fields.append(ff["type"].title())
        if ff.get("date"):
            fields.append(ff["date"])
        if ff.get("venue"):
            fields.append(ff["venue"])
        lines.append(f"**Forcing function:** {' · '.join(fields)}")
        lines.append("")

    # At-a-glance
    by_verdict = defaultdict(int)
    score_total_possible = 0
    score_realized = 0
    for r in results:
        by_verdict[r.get("verdict", "?")] += 1
        delta = r.get("title_curative_score_delta", 0) or 0
        score_total_possible += max(0, delta)
        if r.get("verdict") == "verified":
            score_realized += max(0, delta)

    structurally_supported = sum(1 for r in results if r.get("structurally_supported"))

    lines.append("## At a glance")
    lines.append("")
    for v, n in sorted(by_verdict.items(), key=lambda x: -x[1]):
        emoji = VERDICT_EMOJI.get(v, "·")
        lines.append(f"- {emoji} `{v}`: **{n}**")
    lines.append("")
    lines.append(f"**Title curative score:** **{score_realized} / {score_total_possible}** "
                 f"({(100 * score_realized / max(1, score_total_possible)):.0f}% of attainable upside currently realized)")
    lines.append(f"**Structurally supported claims** (verified + all dependencies verified): **{structurally_supported} / {len(results)}**")
    lines.append("")

    # Section-grouped detail
    by_section = defaultdict(list)
    section_order = []
    for r in results:
        s = r.get("section") or "—"
        if s not in by_section:
            section_order.append(s)
        by_section[s].append(r)

    # Pre-fetch metadata for all referenced docs at once (efficiency)
    all_doc_ids = set()
    for r in results:
        for d in (r.get("evidence_doc_ids") or [])[:3]:
            all_doc_ids.add(d)
    doc_meta = _doc_meta(cur, all_doc_ids)

    for section in section_order:
        lines.append(f"## {section}")
        lines.append("")
        for c in by_section[section]:
            verdict = c.get("verdict", "?")
            emoji = VERDICT_EMOJI.get(verdict, "·")
            structural = " 🔗" if c.get("structurally_supported") else ""
            lines.append(f"### {emoji} `{c['id']}`{structural}")
            lines.append("")
            lines.append(f"**Claim:** {c['text']}")
            lines.append("")
            lines.append(f"- **Verdict:** `{verdict}` · **Citation tier:** {c.get('citation_tag') or '—'}")
            if c.get("title_curative_score_delta"):
                lines.append(f"- **Title curative Δ:** `{c['title_curative_score_delta']:+d}`")
            if c.get("depends_on"):
                deps_str = " · ".join(f"`{d}`" for d in c["depends_on"])
                if c.get("chain_broken_at"):
                    broken = " · ".join(f"`{d}`" for d in c["chain_broken_at"])
                    lines.append(f"- **Depends on:** {deps_str} — ⚠ chain unsupported at: {broken}")
                else:
                    lines.append(f"- **Depends on:** {deps_str} (all verified)")
            if c.get("evidence_doc_ids"):
                top = c["evidence_doc_ids"][:3]
                top_str = ", ".join(
                    f"doc#{d} ({doc_meta.get(d, {}).get('classification', '?')})"
                    for d in top
                )
                lines.append(f"- **Top backing docs:** {top_str}")
            if c.get("if_supported_implies"):
                lines.append(f"- **If supported implies:** {c['if_supported_implies']}")
            if c.get("development_impact"):
                lines.append(f"- **Development impact:** {c['development_impact']}")
            if c.get("defense_anticipation"):
                lines.append(f"- **Anticipated defense:** {c['defense_anticipation']}")
            if c.get("challenger_reason"):
                reason = c["challenger_reason"][:400].replace("\n", " ")
                lines.append("")
                lines.append(f"> **Negotiator's adversarial pass:** {reason}")

            tev = c.get("transfer_evidence_status")
            if tev:
                lines.append("")
                lines.append("**Transfer evidence gap:**")
                lines.append("")
                lines.append("| Required doc | Weight | Status | Backing doc |")
                lines.append("|---|---|---|---|")
                for row in tev:
                    backing = f"doc#{row['evidence_doc_id']}" if row.get("evidence_doc_id") else "—"
                    lines.append(
                        f"| {row['required_doc_label']} | {row['weight']} | "
                        f"`{row['status']}` | {backing} |"
                    )
            lines.append("")

    # Discovery priority
    lines.append("## Discovery priority")
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
        lines.append("Gaps ranked by `weight × curative-impact`. Most leverage first.")
        lines.append("")
        lines.append("| # | Claim | Required doc | Weight | Curative Δ | Priority |")
        lines.append("|---|---|---|---|---|---|")
        for i, d in enumerate(discovery[:15], 1):
            lines.append(
                f"| {i} | `{d['claim_id']}` | {d['required_doc']} | "
                f"{d['weight']} | {d['curative_impact']} | {d['score']} |"
            )
    else:
        lines.append("_No transfer-linked gaps surfaced in current theory definition. "
                     "Wire `transfer_link` field on relevant claims to activate this section._")
    lines.append("")

    # Mediation positioning
    if ff.get("type") == "mediation":
        lines.append("## Mediation positioning")
        lines.append("")
        verified_positive = [
            r for r in results
            if r.get("verdict") == "verified" and (r.get("title_curative_score_delta") or 0) > 0
        ]
        verified_positive.sort(key=lambda x: -(x.get("title_curative_score_delta") or 0))
        if verified_positive:
            lines.append("**Strongest leverage (verified + high curative impact):**")
            lines.append("")
            for c in verified_positive[:5]:
                delta = c.get("title_curative_score_delta", 0)
                impact = c.get("development_impact") or c.get("if_supported_implies", "")
                lines.append(f"- **`{delta:+d}`** — `{c['id']}` — {impact}")
            lines.append("")

        unverified_critical = [
            r for r in results
            if r.get("verdict") not in ("verified", "error")
            and (r.get("title_curative_score_delta") or 0) >= 5
        ]
        unverified_critical.sort(key=lambda x: -(x.get("title_curative_score_delta") or 0))
        if unverified_critical:
            lines.append("**Critical claims not yet verified (high curative weight, evidence-gap):**")
            lines.append("")
            for c in unverified_critical:
                delta = c.get("title_curative_score_delta", 0)
                impl = c.get("if_supported_implies", "")
                lines.append(
                    f"- **`{delta:+d}`** — `{c['id']}` "
                    f"(verdict: `{c.get('verdict')}`) — {impl}"
                )
            lines.append("")

    # Chain integrity overview
    lines.append("## Claim-dependency chain integrity")
    lines.append("")
    broken_chains = [r for r in results if r.get("chain_broken_at")]
    if broken_chains:
        lines.append("Claims whose dependency chains are not yet fully verified:")
        lines.append("")
        for c in broken_chains:
            broken = " · ".join(f"`{d}`" for d in c["chain_broken_at"])
            lines.append(f"- `{c['id']}` — broken at: {broken}")
    else:
        lines.append("All claims with dependencies have those dependencies verified.")
    lines.append("")

    # Title chain audit — for every title referenced anywhere in the theory,
    # walk its ancestry, surface ghost-title refs, flag missing/weak edges.
    matter = theory.get("matter_code", "MWK-001")
    titles_seen = set()
    for r in results:
        for m in TITLE_REF.findall(r.get("text") or ""):
            titles_seen.add(m.strip())
    if titles_seen:
        lines.append("## Title chain audit")
        lines.append("")
        lines.append(f"Every TCT/OCT referenced in the theory's claims is walked up to operative root via "
                     f"`title_chain_walker`. Canon (`title_chain_canon.py`) trumps DB ambiguity — ghost titles "
                     f"(e.g. OCT T-106) are flagged, not presented as roots.")
        lines.append("")

        # Integrity summary first (compact)
        audit = chain_integrity_audit(cur, sorted(titles_seen), matter)
        lines.append("### Integrity summary")
        lines.append("")
        lines.append("| Title | Chain length | Issues |")
        lines.append("|---|---|---|")
        for a in audit:
            issues_str = "; ".join(a["issues"]) if a["issues"] else "_(clean)_"
            issues_disp = issues_str[:140].replace("|", "/")
            lines.append(f"| `{a['title']}` | {a['chain_length']} | {issues_disp} |")
        lines.append("")

        # Full per-title rendering (collapsible-ish — just sectioned)
        lines.append("### Per-title ancestral chains")
        lines.append("")
        for t in sorted(titles_seen):
            lines.append(f"#### `{t}`")
            lines.append("")
            try:
                lines.append(render_chain_md(cur, t, matter))
            except Exception as e:
                lines.append(f"_chain walk failed: {e}_")
            lines.append("")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("theory", help="Python module path, e.g. case_theories.civil_case_26_360")
    ap.add_argument("--no-report", action="store_true",
                    help="Run + print summary but don't write markdown/json")
    args = ap.parse_args()

    _load_anthropic_key()
    mod = importlib.import_module(args.theory)
    theory = mod.THEORY

    print(f"Theory: {theory['theory_id']} ({len(theory['claims'])} claims)")
    print(f"Matter: {theory.get('matter_code')}")
    print(f"Summary: {theory.get('summary', '')[:120]}…")
    print()

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    results = []
    for claim in theory["claims"]:
        print(f"  → {claim['id']:42s} ", end="", flush=True)
        r = evaluate_claim(cur, claim, theory.get("matter_code"))
        results.append(r)
        emoji = VERDICT_EMOJI.get(r.get("verdict", "?"), "·")
        delta = r.get("title_curative_score_delta", 0)
        cite = r.get("citation_tag") or "—"
        print(f"{emoji} {r.get('verdict', '?'):14s} Δ{delta:+d}  cite={cite}")

    results = compute_chain_health(results)

    n_verified = sum(1 for r in results if r.get("verdict") == "verified")
    n_struct = sum(1 for r in results if r.get("structurally_supported"))
    realized = sum(max(0, r.get("title_curative_score_delta", 0) or 0)
                   for r in results if r.get("verdict") == "verified")
    possible = sum(max(0, r.get("title_curative_score_delta", 0) or 0)
                   for r in results)
    print()
    print(f"→ {n_verified}/{len(results)} verified · "
          f"{n_struct}/{len(results)} structurally supported · "
          f"title curative {realized}/{possible}")

    run_meta = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "theory_id": theory["theory_id"],
        "n_claims": len(results),
    }

    if not args.no_report:
        DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        md_path = DRAFTS_DIR / f"case_theory_{theory['theory_id']}_{date}.md"
        json_path = DRAFTS_DIR / f"case_theory_{theory['theory_id']}_{date}.json"
        md_path.write_text(render_markdown(theory, results, run_meta, cur))
        json_path.write_text(json.dumps(
            {"theory": theory, "results": results, "run_meta": run_meta},
            indent=2, default=str,
        ))
        print()
        print(f"Markdown: {md_path}")
        print(f"JSON:     {json_path}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
