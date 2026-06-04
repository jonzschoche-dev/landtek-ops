#!/usr/bin/env python3
"""sim_status.py — phone-friendly Leo simulator dashboard.

Run with no args for the standard view:
    python3 /root/landtek/scripts/sim_status.py

Optional positional arg: a probe-name substring to drill in:
    python3 /root/landtek/scripts/sim_status.py allan
    python3 /root/landtek/scripts/sim_status.py opus.sim

Prints:
  1. Daemon health           (simulator running? probe-gen timer armed? last sentinel run)
  2. Throughput              (runs this hour / today, pass rate)
  3. Library composition     (hand-authored vs Opus-generated, active vs disabled)
  4. Top failing probes      (24h)
  5. Last 3 actual replies   (so you can see what Leo is saying)
  6. Recent leak incidents   (should be empty)
  7. Drill-down              (if substring arg given: per-probe replies)
"""
from __future__ import annotations
import os
import subprocess
import sys
from datetime import datetime, timezone
import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
BOX_W = 78

def hr(ch="─", w=BOX_W):
    return ch * w

def title(t, w=BOX_W):
    return f"\n┌{'─' * (w-2)}┐\n│ {t:<{w-4}} │\n└{'─' * (w-2)}┘"

def section(t):
    print(f"\n━━━ {t} {'━' * max(0, BOX_W - len(t) - 5)}")

def main():
    drill = sys.argv[1].lower() if len(sys.argv) > 1 else None

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print(title(f"Leo Simulator Status — {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}"))

    # === Daemon health ===
    section("Daemon health")
    for unit in ("leo-simulator.service", "leo-qa-probe-generator.timer"):
        try:
            r = subprocess.run(["systemctl", "is-active", unit],
                               capture_output=True, text=True, timeout=5)
            status = r.stdout.strip()
        except Exception as e:
            status = f"err:{e}"
        glyph = "✓" if status == "active" else "✗"
        print(f"  {glyph} {unit:40s}  {status}")
    # Last sentinel cron exec — look at log mtime
    try:
        r = subprocess.run(["stat", "-c", "%y", "/var/log/sim_leak_sentinel.log"],
                           capture_output=True, text=True, timeout=5)
        print(f"  ▸ sentinel log last touched: {r.stdout.strip()}")
    except Exception:
        pass

    # === Throughput ===
    section("Throughput")
    cur.execute("""
        SELECT
          COUNT(*) FILTER (WHERE posted_at > now() - interval '1 hour')   AS h1,
          COUNT(*) FILTER (WHERE posted_at > now() - interval '24 hours') AS d1,
          COUNT(*) FILTER (WHERE posted_at > now() - interval '1 hour'   AND passed) AS h1_pass,
          COUNT(*) FILTER (WHERE posted_at > now() - interval '24 hours' AND passed) AS d1_pass
          FROM leo_qa_sim_payloads
    """)
    r = cur.fetchone()
    h1, d1 = r["h1"], r["d1"]
    h1p, d1p = r["h1_pass"], r["d1_pass"]
    print(f"  last hour:  {h1:5d} runs    {h1p:4d} pass  ({100*h1p/max(h1,1):4.1f}%)")
    print(f"  last 24h:   {d1:5d} runs    {d1p:4d} pass  ({100*d1p/max(d1,1):4.1f}%)")
    # Projected daily rate
    print(f"  projected/day at current cadence: {h1*24} runs")

    # === Library composition ===
    section("Probe library")
    cur.execute("""
        SELECT
          COUNT(*) FILTER (WHERE active)                                                AS active,
          COUNT(*) FILTER (WHERE active AND definition->>'origin' = 'opus_generated')   AS opus,
          COUNT(*) FILTER (WHERE active AND COALESCE(definition->>'origin','hand') != 'opus_generated') AS hand,
          COUNT(*) FILTER (WHERE NOT active)                                            AS retired
          FROM leo_qa_probes WHERE rail = 'sim'
    """)
    r = cur.fetchone()
    print(f"  active: {r['active']:4d}   ({r['hand']} hand-authored, {r['opus']} Opus-generated)")
    print(f"  retired: {r['retired']}")
    # When is next Opus batch?
    try:
        r2 = subprocess.run(
            ["systemctl", "list-timers", "leo-qa-probe-generator.timer", "--no-pager"],
            capture_output=True, text=True, timeout=5)
        for line in r2.stdout.splitlines():
            if "leo-qa-probe-generator" in line:
                # Extract first two fields = NEXT
                parts = line.split()
                if len(parts) >= 4:
                    print(f"  next Opus batch: {' '.join(parts[:4])}")
                break
    except Exception:
        pass

    # === Worst probes ===
    section("Worst-performing probes (24h)")
    cur.execute("""
        SELECT p.name, COUNT(*) AS runs,
               COUNT(*) FILTER (WHERE s.passed)     AS pass,
               COUNT(*) FILTER (WHERE NOT s.passed) AS fail,
               MAX(s.fail_reason) AS last_fail
          FROM leo_qa_sim_payloads s
          JOIN leo_qa_probes p ON p.id = s.probe_id
         WHERE s.posted_at > now() - interval '24 hours'
         GROUP BY p.name
        HAVING COUNT(*) FILTER (WHERE NOT s.passed) > 0
         ORDER BY fail DESC, runs DESC
         LIMIT 10
    """)
    for r in cur.fetchall():
        name = r["name"][:42]
        last_fail = (r["last_fail"] or "")[:30]
        print(f"  {name:42s}  {r['pass']}/{r['runs']:<3d} pass   last: {last_fail}")

    # === Recent replies ===
    section("Last 3 actual replies")
    cur.execute("""
        SELECT p.name, s.passed, s.prompt_text, s.leo_reply_text
          FROM leo_qa_sim_payloads s
          JOIN leo_qa_probes p ON p.id = s.probe_id
         ORDER BY s.id DESC LIMIT 3
    """)
    for r in cur.fetchall():
        glyph = "✓" if r["passed"] else "✗"
        prompt = (r["prompt_text"] or "")[:60]
        reply = (r["leo_reply_text"] or "(empty)")[:200].replace("\n", " ")
        print(f"  {glyph} {r['name']}")
        print(f"      Q: {prompt!r}")
        print(f"      A: {reply!r}")

    # === Leaks ===
    section("Sim leak incidents")
    cur.execute("""
        SELECT detected_at::timestamp(0) AS at, sim_sender_id, leaked_chat_id, acted
          FROM sim_leak_incidents
         WHERE detected_at > now() - interval '24 hours'
         ORDER BY detected_at DESC LIMIT 5
    """)
    rows = cur.fetchall()
    if not rows:
        print("  (clean — zero leaks in last 24h)")
    else:
        for r in rows:
            print(f"  {r['at']}  sim={r['sim_sender_id']}  →  leaked to {r['leaked_chat_id']}  acted={r['acted']}")

    # === Optional drill-down ===
    if drill:
        section(f"Drill-down: probes matching '{drill}'")
        cur.execute("""
            SELECT p.name, s.posted_at::timestamp(0) AS at, s.passed,
                   LEFT(s.prompt_text, 60) AS prompt,
                   LEFT(s.leo_reply_text, 240) AS reply,
                   LEFT(s.fail_reason, 80) AS fail_reason
              FROM leo_qa_sim_payloads s
              JOIN leo_qa_probes p ON p.id = s.probe_id
             WHERE LOWER(p.name) LIKE %s
             ORDER BY s.id DESC LIMIT 8
        """, (f"%{drill}%",))
        for r in cur.fetchall():
            glyph = "✓" if r["passed"] else "✗"
            print(f"  {glyph} {r['at']}  {r['name']}")
            print(f"      Q: {r['prompt']!r}")
            print(f"      A: {(r['reply'] or '(empty)')[:200]!r}")
            if not r["passed"]:
                print(f"      fail: {r['fail_reason']}")

    print()
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
