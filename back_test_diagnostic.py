#!/usr/bin/env python3
"""back_test_diagnostic.py — verbose truth-negotiator back-test runner.

Why this exists:
  systems_analyzer.run_backtests() runs the 5-case suite hourly and logs pass/fail
  + challenger_reason to back_test_runs. That tells you something failed but NOT WHY.
  Per Phase 1.1 of LEO_MASTER_PLAN.md the negotiator is at 1/5 pass rate. To calibrate
  we need to SEE, for each failing test: (a) was the expected smoking-gun doc in the
  ranked top-10? (b) what did the challenger actually say? (c) where did the verdict
  diverge from expectation?

What it does:
  For each row in back_test_suite WHERE active:
    1. Call truth_negotiator.negotiate() with full result captured.
    2. Compute pass/fail using the same logic as systems_analyzer.run_backtests().
    3. For FAILED tests, dump:
       - Ranked fact_backers (top 10) with execution_status + classification
       - Whether each expected_doc_id appeared in top-10 (RANKING HEALTH)
       - Whether the expected_contains_quote appeared in challenger_reason
       - Full challenger reason
       - Atom decomposition
    4. Write a markdown report to /root/landtek/drafts/tn_diagnostic_<DATE>.md

Usage:
  python3 back_test_diagnostic.py                   # run all active tests
  python3 back_test_diagnostic.py --test NAME       # one test
  python3 back_test_diagnostic.py --no-report       # stdout only

Read-only against documents corpus. WRITES to truth_negotiations (audit table)
because every negotiate() call inserts an audit row — that's expected behavior.
Does NOT write to back_test_runs (so it doesn't pollute the production suite history).
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
DRAFTS_DIR = Path("/root/landtek/drafts")


def _load_anthropic_key():
    """Same env-loading pattern as systems_analyzer.run_backtests()."""
    env_path = "/root/landtek/.env"
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            if line.startswith("ANTHROPIC_API_KEY="):
                os.environ["ANTHROPIC_API_KEY"] = line.strip().split("=", 1)[1]


def _doc_meta(cur, doc_ids):
    """Look up smart_filename + classification + execution_status for a list of docs."""
    if not doc_ids:
        return {}
    cur.execute("""
        SELECT id, smart_filename, classification, execution_status
          FROM documents WHERE id = ANY(%s)
    """, (list(doc_ids),))
    return {r["id"]: dict(r) for r in cur.fetchall()}


def run_one(cur, test, negotiate_fn):
    """Run one back-test and capture diagnostic detail."""
    claim = test["claim"]
    case_file = test["case_file"]
    expected = test["expected_verdict"]
    expected_docs = list(test.get("expected_doc_ids") or [])
    expected_quote = test.get("expected_contains_quote") or ""

    try:
        r = negotiate_fn(claim, case_file=case_file, asked_by="diagnostic")
    except Exception as e:
        return {
            "test_name": test["test_name"],
            "passed": False,
            "error": f"negotiate() raised: {e}",
            "claim": claim,
            "expected": expected,
        }

    actual = r["verdict"]
    fact_backers = list(r.get("fact_backers") or [])
    comm_backers = list(r.get("comm_backers") or [])
    drafts = list(r.get("drafts") or [])

    # Mirror systems_analyzer pass logic
    verdict_match = actual == expected
    doc_match = True
    if verdict_match and expected_docs:
        if not set(expected_docs) & set(fact_backers[:10]):
            doc_match = False
    passed = verdict_match and doc_match

    # Diagnostic: which expected docs ARE / AREN'T in top-10?
    top10 = fact_backers[:10]
    docs_meta = _doc_meta(cur, set(top10) | set(expected_docs))
    expected_doc_status = []
    for did in expected_docs:
        in_top10 = did in top10
        rank = top10.index(did) + 1 if in_top10 else None
        m = docs_meta.get(did, {})
        expected_doc_status.append({
            "doc_id": did,
            "in_top10": in_top10,
            "rank": rank,
            "smart_filename": m.get("smart_filename"),
            "classification": m.get("classification"),
            "execution_status": m.get("execution_status"),
        })

    # Challenger quote check
    challenger_reason = r.get("challenger_reason") or ""
    quote_in_reason = expected_quote.lower() in challenger_reason.lower() if expected_quote else None

    # Why did it fail?
    failure_reasons = []
    if not verdict_match:
        failure_reasons.append(f"verdict mismatch: expected={expected} actual={actual}")
        if actual == "refuted":
            failure_reasons.append(f"challenger refuted; reason: {challenger_reason[:200]}")
        elif actual == "unsourced":
            failure_reasons.append("no evidence retrieved — probe miss (anchors/concepts didn't hit corpus)")
        elif actual == "uncitable_draft":
            failure_reasons.append("only draft_unsigned docs surfaced — ranking pushed primary docs out of top hits")
        elif actual == "uncertain":
            failure_reasons.append("evidence inconclusive — challenger neither confirmed nor refuted, or <2 fact_backers")
    if verdict_match and not doc_match:
        missing = [d for d in expected_docs if d not in top10]
        failure_reasons.append(f"verdict OK but expected docs {missing} not in top-10 fact_backers — ranking issue")

    return {
        "test_name": test["test_name"],
        "claim": claim,
        "case_file": case_file,
        "expected_verdict": expected,
        "actual_verdict": actual,
        "expected_docs": expected_docs,
        "expected_doc_status": expected_doc_status,
        "top10_fact_backers": top10,
        "top10_meta": [docs_meta.get(d, {"id": d}) for d in top10],
        "comm_backers": comm_backers,
        "drafts": drafts,
        "challenger_disagrees": r.get("challenger_disagrees"),
        "challenger_reason": challenger_reason,
        "expected_quote": expected_quote,
        "quote_in_challenger_reason": quote_in_reason,
        "atoms": r.get("atoms") or [],
        "evidence_count": r.get("evidence_count"),
        "duration_ms": r.get("duration_ms"),
        "passed": passed,
        "failure_reasons": failure_reasons,
    }


def render_markdown(results):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    passed_n = sum(1 for r in results if r.get("passed"))
    total_n = len(results)

    lines = [
        f"# Truth-Negotiator back-test diagnostic — {now}",
        "",
        f"**Pass rate: {passed_n}/{total_n}** "
        f"({'🟢 above 4/5 target' if passed_n >= 4 else '🔴 below 4/5 target'})",
        "",
        f"Source: `back_test_diagnostic.py` against `back_test_suite` rows WHERE active. "
        f"Mirrors systems_analyzer pass logic. Does not write to back_test_runs.",
        "",
        "## Summary",
        "",
        "| Test | Expected | Actual | Pass | Top-10 has expected? | Notes |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        if "error" in r:
            lines.append(f"| `{r['test_name']}` | {r['expected']} | ERROR | ❌ | — | {r['error'][:80]} |")
            continue
        has = "yes" if all(s["in_top10"] for s in r["expected_doc_status"]) else (
            "partial" if any(s["in_top10"] for s in r["expected_doc_status"]) else "no"
        )
        if not r["expected_docs"]:
            has = "n/a"
        mark = "✓" if r["passed"] else "✗"
        first_reason = (r["failure_reasons"][0] if r["failure_reasons"] else "")[:80]
        lines.append(f"| `{r['test_name']}` | {r['expected_verdict']} | {r['actual_verdict']} | "
                     f"{mark} | {has} | {first_reason} |")

    lines.append("")
    lines.append("## Per-test detail")

    for r in results:
        lines.append("")
        lines.append(f"### `{r['test_name']}` — {'PASS' if r.get('passed') else 'FAIL'}")
        lines.append("")
        if "error" in r:
            lines.append(f"**ERROR:** {r['error']}")
            continue

        lines.append(f"**Claim:** {r['claim']}")
        lines.append(f"**Expected verdict:** `{r['expected_verdict']}` · "
                     f"**Actual:** `{r['actual_verdict']}`")
        lines.append(f"**Atoms ({len(r['atoms'])}):** " + " | ".join(f"`{a}`" for a in r["atoms"]))
        lines.append(f"**Evidence found:** {r['evidence_count']} docs · "
                     f"**Duration:** {r['duration_ms']}ms")
        lines.append("")

        # Expected doc status
        if r["expected_doc_status"]:
            lines.append("**Expected-doc ranking health:**")
            lines.append("")
            lines.append("| doc# | in top-10? | rank | classification | execution_status | filename |")
            lines.append("|---|---|---|---|---|---|")
            for s in r["expected_doc_status"]:
                lines.append(
                    f"| {s['doc_id']} | {'✓' if s['in_top10'] else '✗ MISSING'} | "
                    f"{s['rank'] or '—'} | {s.get('classification') or '?'} | "
                    f"{s.get('execution_status') or '?'} | "
                    f"`{(s.get('smart_filename') or '?')[:60]}` |"
                )
            lines.append("")

        # Top-10 fact_backers
        lines.append("**Top-10 fact_backers (ranking output):**")
        lines.append("")
        lines.append("| rank | doc# | classification | execution_status | filename |")
        lines.append("|---|---|---|---|---|")
        for i, m in enumerate(r["top10_meta"], 1):
            lines.append(
                f"| {i} | {m.get('id', '?')} | {m.get('classification') or '?'} | "
                f"{m.get('execution_status') or '?'} | "
                f"`{(m.get('smart_filename') or '?')[:60]}` |"
            )
        lines.append("")

        # Challenger
        lines.append(f"**Challenger disagrees:** `{r['challenger_disagrees']}`")
        lines.append("")
        lines.append("**Challenger reason:**")
        lines.append("")
        lines.append(f"> {r['challenger_reason'] or '_(empty)_'}")
        lines.append("")

        if r["expected_quote"]:
            lines.append(f"**Expected quote in reason:** `{r['expected_quote']}` — "
                         f"{'✓ present' if r['quote_in_challenger_reason'] else '✗ missing'}")
            lines.append("")

        # Failure reasons
        if r["failure_reasons"]:
            lines.append("**Why this failed:**")
            for fr in r["failure_reasons"]:
                lines.append(f"- {fr}")
            lines.append("")

    lines.append("")
    lines.append("## Suggested fix vectors (by failure pattern observed)")
    lines.append("")
    lines.append("- **`verdict=refuted` with the expected smoking-gun doc IN top-10**: "
                 "challenger prompt over-refuting despite seeing the evidence. "
                 "Tune the challenger prompt examples or evidence-summary format in `call_challenger()`.")
    lines.append("- **`verdict=refuted` with smoking-gun doc NOT in top-10**: "
                 "ranking issue. Adjust `_rank()` in `truth_negotiator.negotiate()` — likely "
                 "CLASS_RANK weights need bumping for the missing classification, or precision boost "
                 "for direct-quote hits needs to outweigh structural classification rank.")
    lines.append("- **`verdict=unsourced`**: probe miss. Check `extract_atoms()` anchor patterns + "
                 "`bilingual_search.expand()` synonym list for the relevant concepts. "
                 "Maybe the claim's key term has no concept mapping yet.")
    lines.append("- **`verdict=uncitable_draft`**: a draft doc outranked the executed doc. "
                 "EXEC_RANK draft_unsigned=0 should already prevent this — check whether the "
                 "executed copy is in the corpus at all (could be missing from heightened OCR queue).")
    lines.append("- **`verdict=verified` but expected_docs missing from top-10**: "
                 "ranking is finding OTHER supporting docs (good) but not the canonical ones the "
                 "test expects. May indicate the expected_doc_ids fixture is over-specific — "
                 "consider broadening it OR tightening the ranking to elevate the canonical doc.")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", help="run only this test_name")
    ap.add_argument("--no-report", action="store_true", help="don't write markdown report")
    args = ap.parse_args()

    _load_anthropic_key()
    sys.path.insert(0, "/root/landtek")
    from truth_negotiator import negotiate

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if args.test:
        cur.execute("SELECT * FROM back_test_suite WHERE test_name = %s", (args.test,))
    else:
        cur.execute("SELECT * FROM back_test_suite WHERE active ORDER BY id")
    tests = cur.fetchall()
    if not tests:
        print("✗ no tests matched")
        return

    print(f"Running {len(tests)} test(s) against truth_negotiator.negotiate()…\n")
    results = []
    for t in tests:
        print(f"  → {t['test_name']:35s} ", end="", flush=True)
        r = run_one(cur, t, negotiate)
        results.append(r)
        if "error" in r:
            print(f"ERROR ({r['error'][:50]})")
        else:
            mark = "✓" if r["passed"] else "✗"
            print(f"{mark} expected={r['expected_verdict']:10s} actual={r['actual_verdict']:10s} "
                  f"(evidence={r['evidence_count']}, {r['duration_ms']}ms)")

    passed_n = sum(1 for r in results if r.get("passed"))
    print(f"\n→ {passed_n}/{len(results)} passed.")

    if not args.no_report:
        DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = DRAFTS_DIR / f"tn_diagnostic_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.md"
        report_path.write_text(render_markdown(results))
        print(f"\n→ Report written: {report_path}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
