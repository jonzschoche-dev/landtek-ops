#!/usr/bin/env python3
"""improvement_agent — every-other-day strategic code + system audit.

Per Jonathan 2026-05-17: schedule an every-other-day agent whose sole job is
ensuring Landtek/Leo trends toward becoming "the Philippines' greatest land
executive assistant." Sole purpose: efficiency, accuracy, tech-forward.

Workflow per run:
  1. Scan /root/landtek/*.py (excluding migrations/, backups/) for:
     - Redundancy (DSN hard-coded; .env reimplementations; helper duplication)
     - Efficiency (large files; missing prompt caching on Sonnet calls;
                   Sonnet used where Haiku would work)
     - Accuracy (validity-audit coverage gap; truth-negotiator pass rate;
                 inferred-weak ratio; recent hallucinations)
     - Tech-forward gaps (no async; no batching; missing prompt cache on
                          long static prompts)
  2. Pull current system KPIs from DB.
  3. Synthesize a top-5 leverage-move list via Sonnet (one cached call).
  4. Output: markdown report + Telegram document.

Cost: ~1 Sonnet call per run with prompt caching = ~$0.02-0.05.
Schedule: every 48h via systemd timer.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, date, timezone
from pathlib import Path

sys.path.insert(0, "/root/landtek")
from landtek_core import db, get, tg_send_raw

ROOT = Path("/root/landtek")
EXCLUDE_DIRS = {"migrations", "backups", "heightened_ocr", "uploads", "drafts",
                "n8n_code_nodes", "snapshots", "autonomous", "scripts",
                "leo_tools", "staging", "worker", ".git", "logs"}


def list_active_scripts():
    """Return list of (path, line_count, mtime) for .py files in root only."""
    out = []
    for p in ROOT.glob("*.py"):
        if not p.is_file():
            continue
        try:
            n = sum(1 for _ in p.open())
            out.append((p, n, p.stat().st_mtime))
        except Exception:
            pass
    return out


def static_code_scan(scripts):
    """Pattern-match each script for known anti-patterns and consolidation opportunities."""
    findings = {
        "hard_coded_dsn": [],
        "reimpl_env_loader": [],
        "hard_coded_jonathan_tg_id": [],
        "tg_send_direct_bypass_queue": [],
        "anthropic_no_cache_control": [],
        "sonnet_used_where_haiku_might_do": [],
        "large_files": [],
        "missing_landtek_core_import": [],
    }
    for path, n_lines, _ in scripts:
        try:
            text = path.read_text(errors="ignore")
        except Exception:
            continue
        fname = path.name
        if fname in ("landtek_core.py", "llm_billing.py"):
            continue  # these are the canonical sources; exempt
        if 'postgresql://n8n:n8npassword@172.18.0.3' in text and "from landtek_core import" not in text:
            findings["hard_coded_dsn"].append(fname)
        if re.search(r'def\s+load_env|def\s+load_token|def\s+load_api_key|with open\("/root/landtek/\.env"\)', text):
            findings["reimpl_env_loader"].append(fname)
        if '6513067717' in text and fname != "tg_dispatcher.py" and fname != "daily_strategic_digest.py":
            findings["hard_coded_jonathan_tg_id"].append(fname)
        if re.search(r'api\.telegram\.org/bot.*?/sendMessage', text):
            if "tg_send_raw" not in text and fname != "tg_dispatcher.py":
                findings["tg_send_direct_bypass_queue"].append(fname)
        if "claude-sonnet" in text and "cache_control" not in text:
            findings["anthropic_no_cache_control"].append(fname)
        if "claude-sonnet" in text:
            # Heuristic: if a sonnet call's prompt is short (<300 chars in system=) Haiku might work
            sys_match = re.search(r'system=\s*[\(\[]([^,]{0,400})[,\]\)]', text)
            # (very rough; flag for inspection)
            if sys_match and len(sys_match.group(1)) < 250:
                findings["sonnet_used_where_haiku_might_do"].append(fname)
        if n_lines > 500:
            findings["large_files"].append(f"{fname} ({n_lines} lines)")
        if "DSN = " in text and "from landtek_core" not in text:
            findings["missing_landtek_core_import"].append(fname)
    return findings


def fetch_kpis(cur):
    """KPIs that quantify trajectory toward greatest-PH-land-EA."""
    kpis = {}

    cur.execute("SELECT COUNT(*) AS n FROM matters WHERE status='active'")
    kpis["active_matters"] = cur.fetchone()["n"]
    cur.execute("SELECT COUNT(DISTINCT client_code) AS n FROM matters WHERE status='active' AND client_code NOT IN ('PENDING_TRIAGE','Owner')")
    kpis["active_clients"] = cur.fetchone()["n"]

    cur.execute("""
        SELECT ROUND(AVG(cost_usd)::numeric, 4) AS avg
          FROM llm_calls
         WHERE called_at >= NOW() - INTERVAL '7 days'
    """)
    kpis["avg_call_cost_7d"] = float(cur.fetchone()["avg"] or 0)

    cur.execute("""
        SELECT date_trunc('day', called_at)::date AS day,
               ROUND(SUM(cost_usd)::numeric, 4) AS cost
          FROM llm_calls WHERE called_at >= NOW() - INTERVAL '7 days'
         GROUP BY 1 ORDER BY 1
    """)
    kpis["spend_last_7d"] = [(r["day"].isoformat(), float(r["cost"])) for r in cur.fetchall()]

    cur.execute("""
        SELECT
          (SELECT COUNT(*) FROM extraction_chunks WHERE chunk_type='validity_audit') AS audited,
          (SELECT COUNT(*) FROM documents WHERE execution_status IN ('executed_filed','executed_notarized','government_issued')) AS auditable
    """)
    r = cur.fetchone()
    kpis["validity_audit_coverage_pct"] = round(100 * (r["audited"] or 0) / max(1, r["auditable"] or 1), 1)
    kpis["audits_done"] = r["audited"]
    kpis["audits_auditable"] = r["auditable"]

    cur.execute("""
        SELECT
          ROUND(100.0 * SUM(CASE WHEN provenance_level='verified' THEN 1 ELSE 0 END) / NULLIF(COUNT(*),0), 1) AS pct
          FROM extraction_chunks
    """)
    kpis["chunks_verified_pct"] = float(cur.fetchone()["pct"] or 0)

    cur.execute("""
        SELECT COUNT(*) FILTER (WHERE passed) AS passed, COUNT(*) AS total
          FROM back_test_runs WHERE run_at >= NOW() - INTERVAL '7 days'
    """)
    r = cur.fetchone()
    kpis["backtest_pass_rate_7d_pct"] = round(100 * (r["passed"] or 0) / max(1, r["total"] or 1), 1) if r["total"] else None

    cur.execute("SELECT COUNT(*) FROM hallucination_log WHERE occurred_at >= NOW() - INTERVAL '30 days'")
    kpis["hallucinations_logged_30d"] = cur.fetchone()["count"]

    cur.execute("SELECT COUNT(*) FROM client_history")
    kpis["client_history_events"] = cur.fetchone()["count"]

    return kpis


def synthesize_recommendations(scan_findings, kpis):
    """Call Sonnet 4.6 with cached system prompt to produce top-5 leverage moves."""
    import anthropic
    from llm_billing import anthropic_call
    client = anthropic.Anthropic(api_key=get("ANTHROPIC_API_KEY"))

    system_prompt = (
        "You are the Landtek Improvement Agent. Sole job: every other day, "
        "audit Leo/Landtek's codebase + system KPIs and produce 5 concrete "
        "leverage moves that push trajectory toward 'the Philippines' greatest "
        "land executive assistant'. Format each as WHAT (verb-first action), "
        "WHY (which pillar it advances), HOW (concrete steps), COST (LLM/dev "
        "estimate). Be ruthless about redundancy and tech-forward gaps. "
        "Output AS JSON ONLY (no prose, no markdown fences): "
        '{"moves": [{"what": str, "why": str, "how": str, "cost": str, "leverage_score": 0-10}], '
        '"trajectory_score": 0-100, "trajectory_commentary": "<140 chars on where we are vs the goal>"}'
    )
    user_input = json.dumps({
        "static_code_scan": scan_findings,
        "system_kpis": kpis,
        "trajectory_pillars": [
            "Evidence-grade discipline (verified chunk %)",
            "Multi-client scalability (clients > 1; ARR > 0; cost/client trend)",
            "PH-property domain depth (title_chain edges; ARTA/RD coverage)",
            "Proactive autonomy (intakes auto-fire; gaps surface; deadlines auto-complete)",
            "Cost-discipline (<$5/day; Sonnet only for verdicts; caching used)",
            "Reliability (zero hallucinations; meta-agent green; <1 false alert/month)",
            "Bilingual / cultural fluency (Filipino source-quotes; PH Civil Code rubrics)",
            "Multi-channel reach (Telegram + Web + Email + WhatsApp + Voice)",
        ]
    })

    msg = anthropic_call(
        client,
        called_from="improvement_agent",
        purpose="strategic_audit",
        case_file=None,
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=[{
            "type": "text",
            "cache_control": {"type": "ephemeral"},
            "text": system_prompt,
        }],
        messages=[{"role": "user", "content": user_input}],
    )
    out = msg.content[0].text.strip()
    out = re.sub(r"^```(?:json)?\s*|\s*```$", "", out)
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:
        return {"error": f"json_parse_fail: {e}", "raw": out[:1000]}


def render_md(scan, kpis, recs):
    today = date.today().isoformat()
    lines = [
        f"# Landtek Improvement Audit — {today}",
        f"_Generated {datetime.now(timezone.utc).strftime('%H:%M UTC')} · improvement_agent.py_",
        "",
        "## Trajectory snapshot",
        "",
    ]
    if isinstance(recs, dict) and "trajectory_score" in recs:
        lines.append(f"- **Trajectory score:** {recs['trajectory_score']} / 100")
        lines.append(f"- **Commentary:** {recs.get('trajectory_commentary','—')}")
    lines.append("")
    lines.append("## System KPIs")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    for k, v in kpis.items():
        if isinstance(v, list):
            v = ", ".join(f"{a}=${b:.4f}" for a, b in v)
        lines.append(f"| `{k}` | {v} |")
    lines.append("")

    lines.append("## Static-code scan findings")
    lines.append("")
    for cat, files in scan.items():
        n = len(files)
        if n == 0:
            lines.append(f"- ✓ `{cat}` — clean")
        else:
            lines.append(f"- ⚠️ `{cat}` ({n}): {', '.join(files[:8])}{' …' if n > 8 else ''}")
    lines.append("")

    lines.append("## Top leverage moves")
    lines.append("")
    if isinstance(recs, dict) and "moves" in recs:
        for i, m in enumerate(recs["moves"], 1):
            score = m.get("leverage_score", "?")
            lines.append(f"### {i}. {m.get('what','?')}  _(leverage {score}/10)_")
            lines.append(f"- **WHY:** {m.get('why','?')}")
            lines.append(f"- **HOW:** {m.get('how','?')}")
            lines.append(f"- **COST:** {m.get('cost','?')}")
            lines.append("")
    else:
        lines.append(f"_(no moves — {recs.get('error', 'unknown error')})_")
        if "raw" in recs:
            lines.append(f"\n```\n{recs['raw'][:500]}\n```")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="markdown output path")
    ap.add_argument("--tg", action="store_true")
    ap.add_argument("--no-llm", action="store_true",
                    help="skip Sonnet synthesis (cheap dry run)")
    args = ap.parse_args()

    scripts = list_active_scripts()
    scan = static_code_scan(scripts)
    with db() as cur:
        kpis = fetch_kpis(cur)
    if args.no_llm:
        recs = {"moves": [], "trajectory_score": None,
                "trajectory_commentary": "(--no-llm — synthesis skipped)"}
    else:
        try:
            recs = synthesize_recommendations(scan, kpis)
        except Exception as e:
            # Degrade gracefully: a depleted balance / unreachable model must NOT crash the
            # self-improvement loop. Still emit the deterministic audit; LLM synthesis resumes
            # automatically once the model is reachable again (offline-sovereignty principle).
            print(f"  LLM synthesis unavailable ({type(e).__name__}: {str(e)[:90]}) — "
                  f"emitting deterministic audit only")
            recs = {"moves": [], "trajectory_score": None,
                    "trajectory_commentary": f"(LLM unavailable — deterministic audit only: {type(e).__name__})"}

    md = render_md(scan, kpis, recs)
    out_path = Path(args.out or
        f"/root/landtek/drafts/improvement_audit_{date.today().isoformat()}.md")
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(md)
    print(f"  Wrote: {out_path} ({len(md):,} chars)")

    if args.tg:
        from output_audit import audit_text
        passed, findings = audit_text(md, strict=True)
        if not passed:
            print(f"  ✗ TG send BLOCKED — {sum(1 for f in findings if f['severity']=='high')} hallucination-risk lines")
            for f in [f for f in findings if f["severity"] == "high"][:5]:
                print(f"     line {f['line']}: {f['issue']} — {f['snippet'][:80]}")
        else:
            import requests
            token = get("TELEGRAM_BOT_TOKEN")
            with open(out_path, "rb") as fh:
                r = requests.post(
                    f"https://api.telegram.org/bot{token}/sendDocument",
                    data={"chat_id": "6513067717",
                          "caption": f"🔧 Improvement audit — {date.today().isoformat()}"},
                    files={"document": fh}, timeout=30)
            print(f"  TG: {r.status_code}")


if __name__ == "__main__":
    main()
