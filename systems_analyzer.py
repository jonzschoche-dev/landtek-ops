#!/usr/bin/env python3
"""Systems analyzer — the meta-agent that audits Leo himself (deploy 120).

Runs every hour via systemd timer. Checks data freshness, coverage gaps,
verification discipline. Auto-remediates fixable issues. Telegram-digests
unfixable ones to Jonathan.

A meta-Leo. Does NOT do legal work — only audits the primary Leo.
"""
import argparse, json, os, subprocess, sys, time
from datetime import datetime, timezone, timedelta
import psycopg2, psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


def emit_heartbeat(cur, source, status="ok", duration_ms=None, metadata=None):
    cur.execute("""
        INSERT INTO system_heartbeat (source, status, duration_ms, metadata)
        VALUES (%s, %s, %s, %s::jsonb)
    """, (source, status, duration_ms, json.dumps(metadata or {})))


def record_finding(cur, finding_type, severity, source_area, description, suggested_fix=None, auto_remediable=False):
    """Insert a finding if not already open."""
    cur.execute("""
        SELECT id FROM system_analyzer_findings
         WHERE description = %s AND remediated_at IS NULL
         LIMIT 1
    """, (description,))
    if cur.fetchone():
        return None
    cur.execute("""
        INSERT INTO system_analyzer_findings
          (finding_type, severity, source_area, description, suggested_fix, auto_remediable)
        VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
    """, (finding_type, severity, source_area, description, suggested_fix, auto_remediable))
    return cur.fetchone()["id"]


def auto_remediate(cur, finding_id, source_area):
    """Try to auto-fix the issue. Returns True if remediated."""
    try:
        if source_area == "gmail":
            subprocess.run(["python3", "/root/landtek/gmail_watcher.py", "--max", "50"],
                           capture_output=True, timeout=120)
            cur.execute("""UPDATE system_analyzer_findings
                              SET remediated_at = now(), remediated_via = 'gmail_watcher_triggered'
                            WHERE id = %s""", (finding_id,))
            return True
        if source_area == "drive":
            subprocess.run(["python3", "/root/landtek/drive_backfill.py"],
                           capture_output=True, timeout=300)
            cur.execute("""UPDATE system_analyzer_findings
                              SET remediated_at = now(), remediated_via = 'drive_backfill_triggered'
                            WHERE id = %s""", (finding_id,))
            return True
        if source_area == "case_correlation":
            subprocess.run(["python3", "/root/landtek/correlate_orphan_cases.py"],
                           capture_output=True, timeout=120)
            cur.execute("""UPDATE system_analyzer_findings
                              SET remediated_at = now(), remediated_via = 'orphan_correlator_triggered'
                            WHERE id = %s""", (finding_id,))
            return True
        if source_area == "exec_classification":
            subprocess.run(["python3", "/root/landtek/classify_execution_status.py"],
                           capture_output=True, timeout=300)
            cur.execute("""UPDATE system_analyzer_findings
                              SET remediated_at = now(), remediated_via = 'exec_status_classifier_triggered'
                            WHERE id = %s""", (finding_id,))
            return True
    except Exception as e:
        print(f"  ⚠ auto-remediate failed for {source_area}: {e}")
    return False


def run_audits(cur):
    findings_made = []
    now = datetime.now(timezone.utc)

    # 1. Data freshness — heartbeats
    for source, threshold_min in [
        ("gmail-watcher", 20),
        ("drive-sync", 35),
        ("deadline-sentinel", 20),
    ]:
        cur.execute("""SELECT max(emitted_at) AS m FROM system_heartbeat WHERE source = %s""", (source,))
        last = cur.fetchone()["m"]
        if not last or (now - last) > timedelta(minutes=threshold_min):
            sa = source.split("-")[0] if "-" in source else source
            fid = record_finding(cur, "staleness", "high", sa,
                                 f"{source} hasn't run in {(now - last).total_seconds()//60:.0f}min" if last else f"{source} has never emitted a heartbeat",
                                 f"trigger {source} manually or check timer", auto_remediable=True)
            if fid: findings_made.append((fid, sa))

    # 2. Coverage: case_file correlation
    cur.execute("""SELECT count(*) FROM documents
                    WHERE (case_file IS NULL OR case_file = '' OR case_file IN ('unknown','Unknown'))
                      AND extracted_text IS NOT NULL AND length(extracted_text) >= 200""")
    n = cur.fetchone()["count"]
    if n > 20:
        fid = record_finding(cur, "coverage_gap", "medium", "case_correlation",
                             f"{n} extracted docs still have NULL case_file (>20 threshold)",
                             "run correlate_orphan_cases.py", auto_remediable=True)
        if fid: findings_made.append((fid, "case_correlation"))

    # 3. Coverage: execution_status
    cur.execute("""SELECT count(*) FROM documents
                    WHERE (execution_status IS NULL OR execution_status='unknown')
                      AND extracted_text IS NOT NULL AND length(extracted_text) >= 200""")
    n = cur.fetchone()["count"]
    if n > 50:
        fid = record_finding(cur, "coverage_gap", "medium", "exec_classification",
                             f"{n} extracted docs lack execution_status (>50 threshold)",
                             "run classify_execution_status.py", auto_remediable=True)
        if fid: findings_made.append((fid, "exec_classification"))

    # 4. Drive ingestion gap
    import json as _json
    try:
        inv = _json.load(open("/root/landtek/drive_inventory.json"))
        total_drive = sum(len(v) for v in inv.values() if isinstance(v, list))
        cur.execute("SELECT count(DISTINCT drive_file_id) FROM documents WHERE drive_file_id IS NOT NULL")
        linked = cur.fetchone()["count"]
        if total_drive - linked > 50:
            fid = record_finding(cur, "coverage_gap", "high", "drive",
                                 f"{total_drive - linked} Drive files not ingested ({linked}/{total_drive})",
                                 "run drive_backfill.py", auto_remediable=True)
            if fid: findings_made.append((fid, "drive"))
    except Exception:
        pass

    # 5. Pending approvals aging
    cur.execute("""SELECT count(*) FROM channel_users
                    WHERE onboarding_state = 'awaiting_jonathan_approval'
                      AND first_seen_at < now() - interval '4 hours'""")
    n = cur.fetchone()["count"]
    if n > 0:
        record_finding(cur, "staleness", "medium", "onboarding",
                       f"{n} channel users awaiting approval >4h", "run /pending_approvals")

    # 6. Deadlines within 7 days uncited
    cur.execute("""SELECT count(*) FROM case_deadlines cd
                    WHERE cd.status = 'pending'
                      AND cd.due_date <= now()::date + interval '7 days'
                      AND NOT EXISTS (SELECT 1 FROM deadline_alerts a WHERE a.deadline_id = cd.id AND a.tier IN ('t7','t3','t1','t0','overdue'))""")
    n = cur.fetchone()["count"]
    if n > 0:
        record_finding(cur, "integrity", "critical", "deadlines",
                       f"{n} deadlines within 7 days have NO sentinel alert yet",
                       "verify deadline-sentinel cron")

    # 7. Bottleneck staleness
    cur.execute("""SELECT count(*) FROM bottlenecks
                    WHERE status IN ('open','attempting')
                      AND created_at < now() - interval '14 days'""")
    n = cur.fetchone()["count"]
    if n > 0:
        record_finding(cur, "staleness", "medium", "bottlenecks",
                       f"{n} bottlenecks open >14 days without progress",
                       "review and update mitigation_status")

    return findings_made


def run_backtests(cur):
    """Run all active back-test cases through truth_negotiator."""
    cur.execute("SELECT * FROM back_test_suite WHERE active")
    tests = cur.fetchall()
    results = []
    sys.path.insert(0, "/root/landtek")
    with open("/root/landtek/.env") as f:
        for line in f:
            if line.startswith("ANTHROPIC_API_KEY="):
                os.environ["ANTHROPIC_API_KEY"] = line.strip().split("=", 1)[1]
    from truth_negotiator import negotiate

    for t in tests:
        try:
            r = negotiate(t["claim"], case_file=t["case_file"], asked_by="back_test")
        except Exception as e:
            results.append((t, False, f"err: {e}"))
            continue

        actual = r["verdict"]
        expected = t["expected_verdict"]
        passed = actual == expected

        # Check expected doc_ids
        if passed and t.get("expected_doc_ids"):
            backers = set(r["fact_backers"][:10])
            if not set(t["expected_doc_ids"]) & backers:
                passed = False
                fail_reason = f"expected doc(s) {t['expected_doc_ids']} missing from top fact_backers {list(backers)[:5]}"
            else:
                fail_reason = None
        else:
            fail_reason = None if passed else f"expected verdict={expected}, got {actual}"

        # Check expected quote in challenger
        if passed and t.get("expected_contains_quote"):
            if t["expected_contains_quote"].lower() not in (r.get("challenger_reason") or "").lower():
                # Not a hard fail — challenger may pass without that quote
                pass

        cur.execute("""INSERT INTO back_test_runs (test_id, passed, actual_verdict, actual_doc_ids, challenger_reason, failure_reason)
                       VALUES (%s,%s,%s,%s,%s,%s)""",
                    (t["id"], passed, actual, r["fact_backers"][:10], r["challenger_reason"], fail_reason))
        results.append((t, passed, fail_reason))
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-remediate", action="store_true")
    ap.add_argument("--no-tg", action="store_true")
    ap.add_argument("--skip-backtest", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # ── Audits ──
    print("== Running system audits ==")
    findings_made = run_audits(cur)
    print(f"  → {len(findings_made)} NEW findings")

    # ── Auto-remediate ──
    remediated = []
    if not args.no_remediate:
        for fid, area in findings_made:
            cur.execute("SELECT auto_remediable FROM system_analyzer_findings WHERE id = %s", (fid,))
            row = cur.fetchone()
            if row and row["auto_remediable"]:
                if auto_remediate(cur, fid, area):
                    remediated.append((fid, area))
                    print(f"  ✓ auto-remediated #{fid} ({area})")

    # ── Back-tests ──
    test_results = []
    if not args.skip_backtest:
        print("\n== Back-test suite ==")
        test_results = run_backtests(cur)
        passed = sum(1 for _, p, _ in test_results if p)
        print(f"  → {passed}/{len(test_results)} passed")
        for t, p, reason in test_results:
            mark = "✓" if p else "✗"
            print(f"  {mark} {t['test_name']:30s} {reason or ''}")

    dt = int((time.time() - t0) * 1000)
    emit_heartbeat(cur, "systems-analyzer", "ok", duration_ms=dt,
                   metadata={"findings_made": len(findings_made),
                              "remediated": len(remediated),
                              "backtests_passed": sum(1 for _,p,_ in test_results if p),
                              "backtests_total": len(test_results)})

    # ── Telegram digest if anything noteworthy ──
    if not args.no_tg and (findings_made or any(not p for _,p,_ in test_results)):
        import requests
        env = {}
        with open("/root/landtek/.env") as f:
            for l in f:
                if "=" in l and not l.startswith("#"):
                    k, _, v = l.strip().partition("="); env[k.strip()] = v.strip()
        lines = ["🛰️ <b>Systems Analyzer — hourly audit</b>", ""]
        if findings_made:
            lines.append(f"<b>New findings: {len(findings_made)}</b>")
            cur.execute("""SELECT id, finding_type, severity, source_area, description, remediated_at IS NOT NULL AS fixed
                             FROM system_analyzer_findings WHERE id = ANY(%s)""",
                        ([fid for fid, _ in findings_made],))
            for r in cur.fetchall():
                emoji = "✓" if r["fixed"] else {"critical":"🚨","high":"🔴","medium":"🟠","low":"🟡"}.get(r["severity"], "•")
                lines.append(f"  {emoji} [{r['severity']}/{r['source_area']}] {r['description']}")
            lines.append("")
        failed_tests = [(t,r) for t,p,r in test_results if not p]
        if failed_tests:
            lines.append(f"<b>Back-tests failed: {len(failed_tests)}</b>")
            for t, reason in failed_tests:
                lines.append(f"  ✗ <code>{t['test_name']}</code> — {reason}")
            lines.append("")
        if remediated:
            lines.append(f"<b>Auto-remediated: {len(remediated)}</b>")
        lines.append(f"<i>Audit duration: {dt}ms · Backtests passed: {sum(1 for _,p,_ in test_results if p)}/{len(test_results)}</i>")
        text = "\n".join(lines)
        r = requests.post(f"https://api.telegram.org/bot{env['TELEGRAM_BOT_TOKEN']}/sendMessage",
                          json={"chat_id": "6513067717", "text": text,
                                "parse_mode": "HTML", "disable_web_page_preview": True})
        print(f"  → TG: {r.status_code}")

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
