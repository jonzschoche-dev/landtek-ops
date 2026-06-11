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
import psycopg2, psycopg2.extras
from landtek_telegram.handlers import llm

PACE = 360          # seconds between probes (~10 probes/hr -> full bank ~hourly, ~240/day)
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
    cur.execute("""SELECT DISTINCT ON (case_id) case_id, passed FROM truth_qa_results
                   ORDER BY case_id, run_at DESC""")
    last_pass = {r["case_id"]: r["passed"] for r in cur.fetchall()}

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
            case = bank[i % len(bank)]
            try:
                reply, err = llm._call_anthropic(sysp, case["q"], [])
            except Exception as e:
                reply, err = None, f"{type(e).__name__}: {e}"
            fails = truth_qa.grade(case, reply)
            passed = not fails
            cur.execute("INSERT INTO truth_qa_results (case_id, passed, fails, reply) VALUES (%s,%s,%s,%s)",
                        (case["id"], passed, "; ".join(fails) or None, (reply or err or "")[:2000]))
            # regression: was passing, now fails -> one alert on the transition
            if last_pass.get(case["id"]) is True and not passed:
                log(f"REGRESSION {case['id']}: {'; '.join(fails)}")
                alert(f"Truth-layer regression: '{case['id']}' now failing ({'; '.join(fails)[:120]}). Check truth_qa_results.")
            last_pass[case["id"]] = passed
            log(f"{'PASS' if passed else 'FAIL'} {case['id']}" + (f" — {'; '.join(fails)}" if fails else ""))
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
