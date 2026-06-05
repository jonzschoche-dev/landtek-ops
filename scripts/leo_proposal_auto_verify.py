#!/usr/bin/env python3
"""leo_proposal_auto_verify.py — autonomous verifier (deploy_327 perpetual).

Hardened from original deploy_309 version:
  - Tolerates retired target probes (skips them, verifies on remaining ≥2 active)
  - Tolerates partial data (verifies if ≥2 target probes have ≥3 runs each)
  - Marks proposals 'verified' with notes flagging which targets were skipped
  - Alerts Jonathan on verify with delta + skipped count
"""
from __future__ import annotations
import json, os, subprocess, sys
import psycopg2, psycopg2.extras

sys.path.insert(0, "/root/landtek/scripts")
try:
    from tg_send import send as tg_send
except Exception:
    tg_send = None

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
JONATHAN = "6513067717"
MIN_RUNS_PER_PROBE = 3
MIN_ACTIVE_PROBES_FOR_VERIFY = 2


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id, target_probes, applied_at, failure_pattern, baseline_pass_rate
          FROM leo_improvement_proposals
         WHERE status = 'applied'
           AND applied_at < now() - interval '30 minutes'
         ORDER BY applied_at ASC
    """)
    ready = cur.fetchall()
    if not ready:
        print("[auto-verify] no proposals due")
        return

    for p in ready:
        targets = p["target_probes"] or []
        # Filter to ACTIVE target probes only
        cur.execute("""
            SELECT name, id FROM leo_qa_probes
             WHERE name = ANY(%s) AND active = true
        """, (targets,))
        active = {r["name"]: r["id"] for r in cur.fetchall()}
        retired = [n for n in targets if n not in active]

        if len(active) < MIN_ACTIVE_PROBES_FOR_VERIFY:
            print(f"[auto-verify] proposal {p['id']}: only {len(active)} of {len(targets)} "
                  f"target probes still active (need ≥{MIN_ACTIVE_PROBES_FOR_VERIFY})")
            continue

        # Check runs per active probe since apply
        cur.execute("""
            SELECT p.name, COUNT(s.id) AS runs,
                   COUNT(s.id) FILTER (WHERE s.passed) AS passes
              FROM leo_qa_probes p
              LEFT JOIN leo_qa_sim_payloads s
                ON s.probe_id = p.id AND s.posted_at > %s
             WHERE p.name = ANY(%s)
             GROUP BY p.name
        """, (p["applied_at"], list(active.keys())))
        per_probe = cur.fetchall()
        qualified = [r for r in per_probe if r["runs"] >= MIN_RUNS_PER_PROBE]

        if len(qualified) < MIN_ACTIVE_PROBES_FOR_VERIFY:
            print(f"[auto-verify] proposal {p['id']}: {len(qualified)}/{len(active)} active "
                  f"probes hit ≥{MIN_RUNS_PER_PROBE} runs; waiting")
            continue

        # Run verify on the qualified subset
        print(f"[auto-verify] verifying proposal {p['id']} on {len(qualified)} of "
              f"{len(targets)} probes ({len(retired)} retired)")
        total_runs = sum(r["runs"] for r in qualified)
        total_pass = sum(r["passes"] for r in qualified)
        new_rate = round(total_pass / max(total_runs, 1), 4)
        delta = new_rate - (p["baseline_pass_rate"] or 0)

        notes_addn = (f"\n[auto-verify] runs={total_runs} passes={total_pass} "
                      f"delta={delta:+.3f} verified_on={len(qualified)} retired={len(retired)}")
        if retired:
            notes_addn += f" skipped_probes={retired}"

        cur.execute("""
            UPDATE leo_improvement_proposals
               SET status = 'verified',
                   verified_at = now(),
                   post_apply_pass_rate = %s,
                   notes = COALESCE(notes,'') || %s
             WHERE id = %s
        """, (new_rate, notes_addn, p["id"]))

        glyph = "✅" if delta > 0.05 else ("➖" if abs(delta) <= 0.05 else "❌")
        msg = (f"{glyph} <b>Proposal #{p['id']} auto-verified</b>\n"
               f"<i>{p['failure_pattern'][:120]}</i>\n"
               f"pass rate {p['baseline_pass_rate']} → {new_rate}  ({delta:+.3f})\n"
               f"verified on {len(qualified)} of {len(targets)} probes "
               f"({len(retired)} retired, skipped)\n"
               f"total runs: {total_runs}  passes: {total_pass}")
        if tg_send is not None:
            try:
                tg_send(JONATHAN, msg, source="watchdog",
                        recipient_name="Jonathan", override_rate_limit=True)
            except Exception:
                pass
        print(f"  verified: delta {delta:+.3f}")


if __name__ == "__main__":
    main()
