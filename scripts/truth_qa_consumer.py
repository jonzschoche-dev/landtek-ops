#!/usr/bin/env python3
"""truth_qa_consumer.py — the CONSUMER that closes the truth-QA loop.

`truth_qa.py` / `truth_qa_loop.py` PRODUCE per-probe results into `truth_qa_results`
(does the system still respect its own invariants — mmk≠mwk, T-4497 owner, client
isolation, hallucination resistance). Nothing read those results back, so a failing
invariant only ever fired a fire-and-forget Telegram — never a durable, digest-visible,
governance-tracked finding. This is that missing reader: it folds the LATEST result per
probe into `holes_findings` (the same ledger ontology_check writes; read by the daily
digest + sentinels), so a truth regression becomes a standing, resolvable finding.

It refuses to cry wolf. A probe that returned no reply (endpoint down / no_api_key /
HTTP error) is an INFRA failure of the harness, NOT evidence the system hallucinated —
those roll into ONE 'truth_harness_down' finding, never per-probe 'the system is wrong'
alarms. Only a probe that got a real answer and that answer broke an invariant becomes a
'truth_regression'. Staleness (no fresh run) also raises the harness-down finding.

Creditless: reads Postgres only, no LLM calls. Idempotent: dedups on the partial unique
index (finding_id_hash WHERE status='open'); resolves findings whose probe now passes.

  python3 truth_qa_consumer.py          # classify latest results, write/resolve findings
  python3 truth_qa_consumer.py --dry    # report only, write nothing
"""
import os
import sys
import json
import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
STALE_DAYS = 3   # no fresh run in this many days → the truth layer is effectively blind

# Probes that assert a NON-NEGOTIABLE invariant (CLAUDE.md "Critical do-nots") → critical if broken.
INVARIANTS = {"mmk_not_mwk", "hallucination_guard", "client_iso_labo", "client_iso_inocalla",
              "t30683_separate", "t4494_separate", "t4497_owner"}


def is_infra(fails, reply):
    """A no-answer (harness couldn't reach the model), NOT a wrong answer."""
    f = (fails or "").lower()
    rp = (reply or "").lower()
    return ("no_reply" in f or "no_api_key" in rp or rp.startswith("http_")
            or rp.startswith("call_failed") or rp.startswith("error") or "http error" in rp)


def main():
    dry = "--dry" in sys.argv
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # LATEST result per probe + freshness of the whole harness.
    cur.execute("""SELECT DISTINCT ON (case_id) case_id, passed, fails, reply, run_at
                   FROM truth_qa_results ORDER BY case_id, run_at DESC""")
    latest = cur.fetchall()
    cur.execute("SELECT max(run_at) AS m, EXTRACT(DAY FROM now()-max(run_at))::int AS age FROM truth_qa_results")
    fr = cur.fetchone()
    last_run, age = fr["m"], (fr["age"] if fr["age"] is not None else 9999)

    if not latest:
        print("[truth_qa_consumer] truth_qa_results is empty — producer has never run.")
        conn.close()
        return

    passed = [r["case_id"] for r in latest if r["passed"]]
    infra = [r for r in latest if not r["passed"] and is_infra(r["fails"], r["reply"])]
    defects = [r for r in latest if not r["passed"] and not is_infra(r["fails"], r["reply"])]
    # The harness is DOWN if results are stale, or half-or-more of the latest probes got no answer.
    harness_down = age > STALE_DAYS or len(infra) >= max(1, (len(latest) + 1) // 2)

    print(f"[truth_qa_consumer] {len(latest)} probes · last run {str(last_run)[:10]} ({age}d ago) · "
          f"{len(passed)} pass / {len(defects)} truth-defect / {len(infra)} infra-fail")

    findings = []   # (hash_key, severity, hole_type, description, metadata)
    if harness_down:
        why = []
        if age > STALE_DAYS:
            why.append(f"no fresh run in {age}d (last {str(last_run)[:10]})")
        if infra:
            why.append(f"{len(infra)}/{len(latest)} probes returned no answer (harness can't reach the model)")
        desc = ("Truth-QA harness DOWN: the invariant probes (mmk≠mwk, T-4497 owner, client isolation, "
                "hallucination guard) are not being evaluated — " + "; ".join(why)
                + ". The truth layer is currently blind. Fix: revive the producer via owned inference "
                "(route truth_qa through scripts/model_router.py instead of the unset Anthropic key), "
                "then re-enable landtek-truth-loop.service. Until then no truth regression can be detected.")
        findings.append(("truth_qa_harness_down", "high", "truth_harness_down", desc,
                         {"age_days": age, "infra": len(infra), "total": len(latest)}))

    for r in defects:
        cid = r["case_id"]
        sev = "critical" if cid in INVARIANTS else "high"
        desc = (f"Truth regression on probe '{cid}': the system answered but broke an invariant "
                f"[{r['fails']}]. Reply excerpt: {(r['reply'] or '')[:200]}. "
                f"This is a real correctness/isolation/hallucination failure, not an outage. "
                f"Triage: SELECT * FROM truth_qa_results WHERE case_id='{cid}' ORDER BY run_at DESC;")
        findings.append((f"truth_regression:{cid}", sev, "truth_regression", desc, {"case_id": cid}))

    if dry:
        for h, sev, ht, desc, meta in findings:
            print(f"  WOULD WRITE [{sev:8}] {ht:20} {h}")
        if not findings:
            print("  (clean — nothing to write)")
        conn.close()
        return

    # Write / refresh open findings (dedup on the partial unique index), then resolve recovered ones.
    for h, sev, ht, desc, meta in findings:
        cur.execute(
            """INSERT INTO holes_findings(routine_name, routine_version, finding_id_hash,
                 severity, hole_type, description, metadata, status)
               VALUES ('truth_qa_consumer','v1', md5(%s), %s, %s, %s, %s, 'open')
               ON CONFLICT (finding_id_hash) WHERE status='open'
               DO UPDATE SET description=EXCLUDED.description, severity=EXCLUDED.severity,
                             metadata=EXCLUDED.metadata""",
            (h, sev, ht, desc, json.dumps(meta)))

    # Resolve: probe now passes → close its open truth_regression; harness healthy → close harness_down.
    resolved = 0
    for cid in passed:
        cur.execute(
            """UPDATE holes_findings SET status='resolved', remediated_at=now(),
                 remediated_via='truth_qa_consumer', remediated_by='auto'
               WHERE finding_id_hash=md5(%s) AND status='open'""",
            (f"truth_regression:{cid}",))
        resolved += cur.rowcount
    if not harness_down:
        cur.execute(
            """UPDATE holes_findings SET status='resolved', remediated_at=now(),
                 remediated_via='truth_qa_consumer', remediated_by='auto'
               WHERE finding_id_hash=md5('truth_qa_harness_down') AND status='open'""")
        resolved += cur.rowcount

    print(f"[truth_qa_consumer] wrote/refreshed {len(findings)} open finding(s), resolved {resolved}.")
    conn.close()


if __name__ == "__main__":
    main()
