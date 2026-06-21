#!/usr/bin/env python3
"""agents.py — the LandTek resident-agent registry + health supervisor.

One canonical catalog of every autonomous ("resident") agent in the stack: its role, fuel tier,
cadence, systemd unit, and status. This is the production-readiness backbone for shipping a fully
ready Leo LandTek — it makes the fleet explicit, shows exactly what's still missing, and `--health`
checks each live agent is actually running (timer enabled + scheduled, last run not failed) so the
system can't silently stall. New resident agents get registered here as we build them.

Fuel tiers:  det = $0 deterministic (no LLM)  ·  local = in-house Ollama (sovereign, unlimited, $0)
             api = external API (quota/credits)  ·  human = needs operator adjudication

  python3 scripts/agents.py --list      # the roster
  python3 scripts/agents.py --health    # are the live ones alive? (run on the VPS)
"""
import argparse
import subprocess

# key, role, fuel, cadence, systemd timer unit (or ''), status, notes
AGENTS = [
    # ── LIVE — knowledge freshness ─────────────────────────────────────────────
    ("verify_loop",          "scout — find/rank/measure verification candidates", "det",
     "daily 03:00", "landtek-verify.timer", "live", "also regenerates case dossiers"),
    ("verify_worker",        "reader — docs → verified cited facts (local-first)", "local",
     "every 15 min", "landtek-verify-worker.timer", "live", "Ollama@MacStudio; Gemini fallback"),
    ("case_dossier",         "librarian — lay out each matter's corpus + evidence", "det",
     "daily (in verify svc)", "", "live", "case_dossiers/<MATTER>.md + INDEX.md"),
    ("cross_client_sentinel","separator — prevent cross-client entity conflation", "det",
     "daily", "landtek-cross-client.timer", "live", "MWK / Paracale / NIBDC isolation"),
    # ── LIVE — proactivity ─────────────────────────────────────────────────────
    ("deadlines",            "watchdog — never miss a date", "det",
     "daily (in digest)", "", "live", "forward-marker date engine"),
    ("build_digest",         "reporter — daily operator digest", "det",
     "daily 01:00", "landtek-digest.timer", "live", "Telegram-friendly"),
    ("supervisor",           "health — verify the fleet is alive (this script)", "det",
     "daily", "", "live", "agents.py --health"),
    # ── LIVE — gap-fillers (complete the corpus) ───────────────────────────────
    ("doc_discovery",        "find/link doc-less matters' papers from the unlinked pool", "det",
     "daily (in verify svc)", "", "live", "conservative; proposes + auto-links strong docket signals"),
    ("contradiction",        "cross-check verified facts for conflicts per matter", "det",
     "daily (in verify svc)", "", "live", "caught the Sept-2016-vs-2019 sale-date conflict"),
    # ── PLANNED — gap-fillers ──────────────────────────────────────────────────
    ("ocr_triage",           "re-OCR the OCR-garbage docs (local Tesseract)", "det",
     "daily", "", "planned", "unblocks OCR-blocked matters; no Gemini quota"),
    ("reconciler",           "adjudicate proposed_facts → verified/reject", "det+human",
     "on demand", "", "live", "human-in-the-loop; gate still checks on accept"),
    # ── LIVE — output / reasoning (in-house Ollama tier) ───────────────────────
    ("analyst",              "case theory / strategy from the verified corpus", "local",
     "on demand", "", "live", "derived reasoning, labeled; never a verified fact"),
    ("brief_drafter",        "draft work-product grounded in verified facts", "local",
     "on demand", "", "live", "[PENDING VERIFICATION] for gaps; draft for counsel"),
    # ── PLANNED ────────────────────────────────────────────────────────────────
    # ── THE FACE ───────────────────────────────────────────────────────────────
    ("leo",                  "Telegram interface — answers grounded in the corpus", "api",
     "realtime", "", "needs-wiring", "n8n AI-Agent; wire discernment protocol + answer gate"),
]


def _sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def list_roster():
    by = {}
    for a in AGENTS:
        by.setdefault(a[5], []).append(a)
    order = ["live", "planned", "needs-wiring"]
    print("=" * 78)
    print("LANDTEK RESIDENT-AGENT ROSTER")
    print("=" * 78)
    for st in order + [k for k in by if k not in order]:
        if st not in by:
            continue
        print(f"\n[{st.upper()}]  ({len(by[st])})")
        for key, role, fuel, cad, unit, status, notes in by[st]:
            print(f"  {key:22} {fuel:10} {cad:22} {role}")
    live = sum(1 for a in AGENTS if a[5] == "live")
    planned = sum(1 for a in AGENTS if a[5] == "planned")
    print(f"\n{live} live · {planned} planned · {len(AGENTS)} total. "
          f"Ship-readiness = build the planned gap-fillers + output agents, then wire Leo.")


def health():
    print("=" * 78)
    print("FLEET HEALTH (live agents with a systemd timer)")
    print("=" * 78)
    ok = True
    for key, role, fuel, cad, unit, status, notes in AGENTS:
        if status != "live" or not unit:
            continue
        enabled = _sh(f"systemctl is-enabled {unit} 2>/dev/null") or "?"
        active = _sh(f"systemctl is-active {unit} 2>/dev/null") or "?"
        svc = unit.replace(".timer", ".service")
        result = _sh(f"systemctl show {svc} -p Result --value 2>/dev/null") or "-"
        nxt = _sh(f"systemctl list-timers {unit} --no-pager 2>/dev/null | grep -i {unit.split('.')[0]} | awk '{{print $1, $2}}'")
        good = enabled == "enabled" and active == "active" and result in ("success", "-")
        ok = ok and good
        flag = "✓" if good else "✗"
        print(f"  {flag} {key:22} {unit:30} enabled={enabled} active={active} last={result} next={nxt or '?'}")
    print("\n" + ("✓ fleet healthy" if ok else "✗ one or more agents need attention"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--health", action="store_true")
    a = ap.parse_args()
    if a.health:
        health()
    else:
        list_roster()


if __name__ == "__main__":
    main()
