#!/usr/bin/env python3
"""legacy_probe_sample.py — slow sample of non-architecture sim probes.

Fires N legacy probes with webhook health gates and spacing for 1GB VPS.
Usage: python3 scripts/legacy_probe_sample.py --count 10 --interval 18
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time

ROOT = __file__.rsplit("/", 1)[0] + "/.."
sys.path.insert(0, ROOT)
sys.path.insert(0, ROOT + "/scripts")

from simulator_core import connect, pick_probe, run_one_probe  # noqa: E402

DEFAULT_SAMPLE = [
    "client.mwk_current_phase",
    "client.obligations_at_risk",
    "client.what_we_owe_allan",
    "filing.honest_about_zero_exhibits",
    "filing.cite_by_lt_when_asked_evidence",
    "filing.knows_doc_inventory_shape",
    "workflow.barandon_correspondence_recent",
    "client.brief_patricia",
    "filing.distinguishes_primary_vs_corroborating",
    "client.needs_paracale_001",
]


def webhook_ready() -> bool:
    if subprocess.run(
        ["curl", "-sf", "--max-time", "5", "http://localhost:5678/healthz"],
        capture_output=True,
    ).returncode != 0:
        return False
    r = subprocess.run(
        [
            "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
            "--max-time", "20", "-X", "POST",
            "https://leo.hayuma.org/webhook/2fe01d2f-680c-47bd-86c6-7bb24893afb9/webhook",
            "-H", "Content-Type: application/json",
            "-H", "X-Telegram-Bot-Api-Secret-Token: vSDQv1vfn6627bnA_fc7b5df9-2d73-48d4-92e8-c5fc21dee837",
            "-d", '{"update_id":1,"message":{"message_id":1,"from":{"id":999000001},'
                  '"chat":{"id":999000001},"date":1,"text":"ping"}}',
        ],
        capture_output=True,
        text=True,
    )
    return r.stdout.strip() in ("200", "204")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--interval", type=float, default=18.0)
    ap.add_argument("--probe", action="append", dest="probes", help="specific probe(s)")
    args = ap.parse_args()

    names = args.probes or DEFAULT_SAMPLE[: args.count]
    conn, cur = connect()
    passed = failed = skipped = 0
    results = []

    print(f"# legacy sample n={len(names)} interval={args.interval}s")
    for i, name in enumerate(names, 1):
        if not webhook_ready():
            print(f"  [{i}/{len(names)}] SKIP {name} — n8n/webhook not ready")
            skipped += 1
            time.sleep(args.interval)
            continue
        probe = pick_probe(cur, name=name)
        if not probe:
            print(f"  [{i}/{len(names)}] SKIP {name} — not in leo_qa_probes")
            skipped += 1
            continue
        try:
            r = run_one_probe(cur, probe)
        except Exception as e:
            r = {"probe": name, "passed": False, "fail_reason": str(e), "reply_excerpt": ""}
        results.append(r)
        if r.get("passed"):
            passed += 1
            mark = "PASS"
        else:
            failed += 1
            mark = "FAIL"
        reason = r.get("fail_reason") or ""
        print(f"  [{i}/{len(names)}] {mark}  {name}  {reason[:80]}")
        if i < len(names):
            time.sleep(args.interval)

    print(f"\n# done: {passed} pass, {failed} fail, {skipped} skip")
    conn.close()
    sys.exit(0 if failed == 0 and skipped == 0 else 1)


if __name__ == "__main__":
    main()