#!/usr/bin/env python3
"""inference_tier_sentinel.py — is the sovereign local inference tier actually up?

Runs on the VPS. Probes the Mac Studio's Ollama (Tier 1 in model_router.py). If the Mac is
asleep / off Tailscale / Ollama down, inference silently degrades to the quota-capped API tiers
(or, since those are stubs, fails outright) — and nobody notices until legal work stalls. This
catches that within the timer cadence and writes a HIGH-severity holes_findings row.

Also summarizes the last-24h inference_audit so the log shows whether the local tier is really
carrying load or the system has been quietly falling back.

Read-only except the best-effort holes_findings write on an outage. Never blocks anything, no LLM, $0.

Usage:
  python3 scripts/inference_tier_sentinel.py            # probe + 24h summary
  python3 scripts/inference_tier_sentinel.py --json     # machine-readable

Exit: 0 = tier reachable, 1 = tier down (holes row written).
"""
from __future__ import annotations
import os
import sys
import json
import time
import requests

OLLAMA_URL = os.environ.get("LANDTEK_OLLAMA_URL", "http://100.117.118.47:11434")
DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
RETRIES = 3
RETRY_GAP_SEC = 12  # ~30s total — rides out a brief blip, still catches a real outage


def probe() -> tuple[bool, str]:
    """Probe Ollama /api/tags with retries. Returns (up, detail)."""
    last = ""
    for i in range(RETRIES):
        try:
            r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=6)
            if r.status_code == 200:
                models = [m.get("name") for m in r.json().get("models", [])]
                return True, f"{len(models)} models: {', '.join(models[:6])}"
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = type(e).__name__
        if i < RETRIES - 1:
            time.sleep(RETRY_GAP_SEC)
    return False, last


def audit_24h(conn) -> dict:
    """Last-24h inference_audit rollup — is the local tier carrying load?"""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT count(*) total,
                       count(*) FILTER (WHERE model_tier='tier1') tier1,
                       count(*) FILTER (WHERE success) ok,
                       count(*) FILTER (WHERE fallback_reason IS NOT NULL) fallbacks,
                       max(timestamp) FILTER (WHERE success AND model_tier='tier1') last_local_ok
                FROM inference_audit WHERE timestamp > now() - interval '24 hours'""")
            total, tier1, ok, fb, last_ok = cur.fetchone()
        return {"calls_24h": total, "tier1": tier1,
                "tier1_pct": round(100 * tier1 / total) if total else None,
                "success": ok, "fallbacks": fb,
                "last_local_ok": last_ok.isoformat() if last_ok else None}
    except Exception as e:
        return {"error": str(e)}


def write_hole(conn, detail: str) -> None:
    """Best-effort HIGH-severity holes row on outage. Never raises."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO holes_findings(routine_name, routine_version, finding_id_hash,
                     severity, hole_type, description, metadata, status)
                   VALUES ('inference_tier_sentinel','v1', md5(%s), 'high', 'inference_tier_down',
                     %s, jsonb_build_object('url',%s), 'open')""",
                (f"tier_down|{OLLAMA_URL}",
                 f"Sovereign local inference tier unreachable ({detail}) at {OLLAMA_URL}. "
                 f"Inference has degraded to the quota-capped API tiers. Wake the Mac / check "
                 f"Tailscale + the com.landtek.ollama-host launchd agent.",
                 OLLAMA_URL))
        conn.commit()
    except Exception:
        pass


def main():
    as_json = "--json" in sys.argv
    up, detail = probe()
    audit = {}
    conn = None
    try:
        import psycopg2
        conn = psycopg2.connect(DSN, connect_timeout=4)
        conn.autocommit = False
        audit = audit_24h(conn)
        if not up:
            write_hole(conn, detail)
        conn.close()
    except Exception:
        pass

    report = {"tier1_reachable": up, "detail": detail, "url": OLLAMA_URL, "inference_24h": audit}
    if as_json:
        print(json.dumps(report, indent=2))
    else:
        print(f"=== inference_tier_sentinel ===")
        print(f"  Tier 1 (Mac Ollama): {'UP' if up else 'DOWN'} — {detail}")
        print(f"  24h: {audit}")
        print(f"=== {'OK' if up else 'TIER DOWN (holes row written)'} ===")
    sys.exit(0 if up else 1)


if __name__ == "__main__":
    main()
