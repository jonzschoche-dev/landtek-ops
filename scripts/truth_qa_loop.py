#!/usr/bin/env python3
"""truth_qa_loop.py — CONTINUOUS truth-layer testing daemon. Always on: cycles the
probe bank through Leo's real pipeline one probe at a time, grades each, stores it
in truth_qa_results, and alerts the instant a probe that used to pass starts
failing (data/answer drift). Like the Leo Simulator, but for factual correctness,
provenance, separate-matter discipline, client isolation, and hallucination.

Reuses the bank + grader from truth_qa.py so the suite is defined once.
Run as systemd service landtek-truth-loop.
"""
import os, sys, time
sys.path.insert(0, "/root/landtek/scripts")
import truth_qa  # loads .env, llm, BANK, grade
import truth_judge  # senior-litigator grader (lawyer-grade)
import cost_governor  # daily spend cap — QA throttles itself, never burns the balance
import psycopg2, psycopg2.extras
from landtek_telegram.handlers import llm

PACE = 1800         # 30 min between probes (cost-tuned: ~48/day, full bank every ~5h)
PROMPT_TTL = 3600   # rebuild the system prompt hourly (matters/vault state change)
DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def alert(text):
    try:
        sys.path.insert(0, "/root/landtek/scripts")
        import tg_send
        tg_send.send("6513067717", text, "watchdog", recipient_name="Jonathan")
    except Exception as e:
        log(f"alert send failed: {e}")


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""CREATE TABLE IF NOT EXISTS truth_qa_results (
        id serial PRIMARY KEY, case_id text, passed bool, fails text, reply text,
        run_at timestamptz DEFAULT now())""")
    for col, typ in (("grade", "text"), ("legal_pass", "bool"), ("defects", "text"), ("one_line", "text")):
        cur.execute(f"ALTER TABLE truth_qa_results ADD COLUMN IF NOT EXISTS {col} {typ}")
    cur.execute("""SELECT DISTINCT ON (case_id) case_id, coalesce(legal_pass, passed) lp
                     FROM truth_qa_results ORDER BY case_id, run_at DESC""")
    last_pass = {r["case_id"]: r["lp"] for r in cur.fetchall()}

    sysp, built = None, 0.0
    bank = truth_qa.BANK
    i = 0
    log(f"truth_qa_loop started — {len(bank)} probes, pace {PACE}s")
    while True:
        try:
            if time.time() - built > PROMPT_TTL:
                sysp = llm.SYSTEM_PROMPT_PRIVATE_JONATHAN_TEMPLATE.format(
                    matters_block=llm._live_matters_block(), vault_state_block=llm._live_vault_state())
                built = time.time()
            if not cost_governor.can_afford("qa"):
                log(f"over daily LLM cap (${cost_governor.today_spend():.2f}) — holding probes")
                time.sleep(PACE); continue
            case = bank[i % len(bank)]
            try:
                reply, err = llm._call_anthropic(sysp, case["q"], [])
            except Exception as e:
                reply, err = None, f"{type(e).__name__}: {e}"
            fails = truth_qa.grade(case, reply)              # fast substring tripwire
            jg = truth_judge.judge(case["q"], reply or "", conn)  # lawyer-grade verdict
            grade = jg.get("grade", "?")
            legal_pass = bool(jg.get("pass"))
            defects = "; ".join(jg.get("defects", []))[:600]
            one_line = (jg.get("one_line") or "")[:300]
            cur.execute("""INSERT INTO truth_qa_results
                (case_id, passed, fails, reply, grade, legal_pass, defects, one_line)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (case["id"], not fails, "; ".join(fails) or None, (reply or err or "")[:2000],
                 grade, legal_pass, defects or None, one_line or None))
            # regression: was court-ready (A/B), now isn't -> one alert on the transition
            if last_pass.get(case["id"]) is True and not legal_pass:
                log(f"REGRESSION {case['id']} -> grade {grade}: {one_line}")
                alert(f"Truth-layer regression: '{case['id']}' dropped to grade {grade}. "
                      f"{one_line[:140]} Check truth_qa_results.")
            last_pass[case["id"]] = legal_pass
            log(f"{grade} {'PASS' if legal_pass else 'FAIL'} {case['id']}: {one_line[:90]}")
            i += 1
            if i % len(bank) == 0:
                npass = sum(1 for v in last_pass.values() if v)
                log(f"--- bank cycle complete: {npass}/{len(bank)} currently passing ---")
            time.sleep(PACE)
        except Exception as e:
            log(f"loop error: {type(e).__name__}: {str(e)[:120]}")
            time.sleep(60)


if __name__ == "__main__":
    main()
