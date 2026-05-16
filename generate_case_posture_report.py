#!/usr/bin/env python3
"""Generate Civil Case 26-360 strategic posture report.

Runs the calibrated truth-negotiator on every load-bearing claim of the case
(plaintiff offense, defendant predictable defense, evidentiary gaps).
Groups by verdict, outputs a verified-only strategic posture markdown.

Cost: ~20 claims × Sonnet w/ prompt-cache = ~$0.10 total.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/root/landtek")

# Load env
with open("/root/landtek/.env") as f:
    for line in f:
        if line.startswith(("ANTHROPIC_API_KEY=", "GEMINI_API_KEY=")):
            k, v = line.strip().split("=", 1)
            os.environ.setdefault(k, v)

from truth_negotiator import negotiate

# ─── CASE CLAIMS LIBRARY ─────────────────────────────────────────────────────

CLAIMS = {
    "Offense — title chain": [
        "Mary Worrick Keesey is deceased",
        "Patricia Keesey Zschoche is an heir of Mary Worrick Keesey",
        "TCT T-4497 is the mother title of the contested Mercedes properties",
        "TCT T-4497 is registered in the names of the Heirs of Mary Worrick Keesey",
        "TCT T-32917 derives from TCT T-4497",
    ],
    "Offense — void instrument theory": [
        "Cesar M. de la Fuente is dead",
        "Cesar M. de la Fuente held a Special Power of Attorney from the heirs of Mary Worrick Keesey",
        "The Special Power of Attorney granted to Cesar de la Fuente was revoked in 2005",
        "Cesar de la Fuente executed a Deed of Absolute Sale in September 2016 affecting TCT T-52540",
        "TCT T-52540 was cancelled in 2021 via the 2016 Deed of Sale",
        "TCT T-079-2021002126 was issued in 2021 to Gloria Balane derived from the cancelled T-52540",
    ],
    "Procedural posture": [
        "Civil Case 26-360 is at the pretrial pending stage",
        "Atty. Bonifacio Jr. Barandon represents the plaintiff in Civil Case 26-360",
        "A Notice of Pre-trial Conference was issued for Civil Case 26-360",
        "A Motion to Render Summary Judgment was filed by the plaintiff in Civil Case 26-360",
    ],
    "Adjacent matters": [
        "ARTA Case CTN SL-2025-1021-0747 charges Mayor Pajarillo with violations of R.A. 11032 Sections 21(b), 21(d), and 21(e)",
        "A separate ARTA case CTN SL-2025-1104-0792 exists relating to the Mercedes Municipal Engineer's Office",
    ],
    "Predictable defense claims to test": [
        "Gloria Balane is the registered owner of TCT T-079-2021002126",
        "Engr. Erwin H. Balane submitted a Judicial Affidavit in Civil Case 26-360",
        "Salvador Osum Dela Fuente submitted a Judicial Affidavit in Civil Case 26-360",
    ],
    "Named transferees (under T-32917)": [
        "Edgardo Santiago acquired land under TCT T-32917 from Cesar de la Fuente as Attorney-in-Fact",
        "Jose Pascual Jr. acquired a 629 sqm parcel under TCT T-32917 for PHP 44,030",
        "Elsa O. Iligan acquired a 300 sqm parcel under TCT T-32917 for PHP 7,000",
    ],
}


def verdict_emoji(v):
    return {
        "verified": "✓",
        "refuted": "✗",
        "uncertain": "?",
        "unsourced": "○",
        "uncitable_draft": "▽",
    }.get(v, "·")


def main():
    out_dir = Path("/root/landtek/drafts")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"case_posture_26_360_{datetime.now().strftime('%Y-%m-%d')}.md"

    lines = [
        f"# Civil Case 26-360 — Strategic Posture Report",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Method:** Truth-negotiator (Sonnet 4.6, calibrated, prompt-cached) on load-bearing claims.",
        f"**Citation tier:** Only `verified` (V·N / V·F / V·G) claims are quotable in court output.",
        "",
    ]

    all_results = []
    for section, claims in CLAIMS.items():
        lines.append(f"## {section}")
        lines.append("")
        lines.append("| | Claim | Verdict | Citation | Top backer |")
        lines.append("|---|---|---|---|---|")
        for claim in claims:
            try:
                r = negotiate(claim, case_file="MWK-001", asked_by="posture_report")
                verdict = r["verdict"]
                cite = r.get("citation_tag", "—")
                backers = r.get("fact_backers") or []
                top_doc = f"doc#{backers[0]}" if backers else "—"
                reason = (r.get("challenger_reason") or "")[:130].replace("|", "/")
                emoji = verdict_emoji(verdict)
                lines.append(f"| {emoji} | {claim} | `{verdict}` | {cite} | {top_doc} |")
                all_results.append({
                    "section": section, "claim": claim, "verdict": verdict,
                    "citation": cite, "top_doc": top_doc, "reason": reason,
                })
                print(f"  {emoji} {verdict:14s} | {claim[:75]}")
            except Exception as e:
                lines.append(f"| ! | {claim} | `error` | — | — |")
                print(f"  ! ERROR | {claim[:75]} — {str(e)[:80]}")
                all_results.append({
                    "section": section, "claim": claim, "verdict": "error",
                    "error": str(e)[:200],
                })
        lines.append("")

    # Summary
    by_verdict = {}
    for r in all_results:
        by_verdict[r["verdict"]] = by_verdict.get(r["verdict"], 0) + 1

    lines.insert(4, "## At-a-glance")
    lines.insert(5, "")
    lines.insert(6, f"Total claims tested: **{len(all_results)}**")
    lines.insert(7, "")
    for v, n in sorted(by_verdict.items(), key=lambda x: -x[1]):
        emoji = verdict_emoji(v)
        lines.insert(8, f"- {emoji} `{v}`: **{n}**")
    lines.insert(8 + len(by_verdict), "")

    lines.append("---")
    lines.append("")
    lines.append("## Cost-aware notes")
    lines.append("- Truth-negotiator uses Sonnet 4.6 with 5-min prompt caching.")
    lines.append("- Per-claim cost ≈ $0.005-0.007 (cache hit) / $0.01 (cache write).")
    lines.append("- All calls logged to `llm_calls` table.")

    out_path.write_text("\n".join(lines))
    print(f"\nReport written to: {out_path}")

    # Cost
    import psycopg2
    conn = psycopg2.connect("postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*), SUM(cost_usd), SUM(input_tokens), SUM(cached_input_tokens), SUM(output_tokens)
          FROM llm_calls
         WHERE called_from='truth_negotiator' AND purpose='challenger'
           AND called_at >= NOW() - INTERVAL '5 min'
    """)
    n, cost, in_t, cached, out_t = cur.fetchone()
    cur.close(); conn.close()
    if n:
        print(f"\n  Run cost: {n} challenger calls = ${float(cost or 0):.4f}")
        print(f"  Tokens: input={in_t} cached={cached} output={out_t}")
        print(f"  Cache hit ratio: {100*float(cached or 0)/max(1,float(cached or 0)+float(in_t or 0)):.0f}%")


if __name__ == "__main__":
    main()
