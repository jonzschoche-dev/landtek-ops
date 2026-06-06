#!/usr/bin/env python3
"""leo_simulator.py — constantly-running Leo simulator (deploy_298c).

Long-running daemon: one synthetic Telegram webhook per cycle, grade reply.
For architecture regression bursts use rapid_fire_simulator.py instead.

Env:
  SIM_CYCLE_SECONDS  default 20 (set 5 for rapid mode)
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from simulator_core import (  # noqa: E402
    connect,
    health_ok,
    pick_probe,
    run_one_probe,
)

try:
    from tg_send import send as tg_send
except Exception:
    tg_send = None

JONATHAN = "6513067717"
CYCLE_SECONDS = int(os.environ.get("SIM_CYCLE_SECONDS", "20"))
HEALTH_PAUSE_SEC = int(os.environ.get("SIM_HEALTH_PAUSE_SEC", "90"))


def alert_critical(probe, scenario_def, fail_reason, reply_excerpt):
    if probe["severity"] != "critical" or tg_send is None:
        return
    text = (
        f"🚨 <b>SIM CRITICAL FAIL</b>\n\n"
        f"Probe: <code>{probe['name']}</code>\n"
        f"Prompt: <i>{(scenario_def['prompt_text'] or '')[:200]}</i>\n\n"
        f"Reason: {fail_reason}\n\n"
        f"Reply excerpt:\n  {(reply_excerpt or '(empty)')[:400]}"
    )
    try:
        tg_send(JONATHAN, text, source="watchdog", recipient_name="Jonathan", override_rate_limit=True)
    except Exception:
        pass


def main():
    print(f"[leo_simulator] cycle={CYCLE_SECONDS}s", flush=True)
    while True:
        cycle_start = time.time()
        try:
            conn, cur = connect()
            if not health_ok(cur):
                print(f"[leo_simulator] health bad — pause {HEALTH_PAUSE_SEC}s", flush=True)
                cur.close()
                conn.close()
                time.sleep(HEALTH_PAUSE_SEC)
                continue

            probe = pick_probe(cur)
            if not probe:
                cur.close()
                conn.close()
                time.sleep(CYCLE_SECONDS)
                continue

            result = run_one_probe(cur, probe)
            if not result["passed"]:
                alert_critical(
                    probe,
                    probe["definition"],
                    result["fail_reason"],
                    result["reply_excerpt"],
                )
            print(
                f"[leo_simulator] {result['probe']} pass={result['passed']} "
                f"fail={result['fail_reason'] or '—'}",
                flush=True,
            )
            cur.close()
            conn.close()
        except Exception as e:
            print(f"[leo_simulator] cycle error: {e}", flush=True)

        elapsed = time.time() - cycle_start
        time.sleep(max(CYCLE_SECONDS - elapsed, 1))


if __name__ == "__main__":
    main()