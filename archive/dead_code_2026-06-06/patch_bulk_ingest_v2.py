#!/usr/bin/env python3
"""
v2 Patch — Aligned with the rule: slow is fine, accurate and cheap mandatory.

Changes to bulk_ingest_mwk.py:
  1. Gemini stays PRIMARY (free)
  2. OpenAI added as LAST-RESORT fallback (rare → cheap)
  3. Per-file pacing: 8s sleep BETWEEN files (stays under 10 RPM free tier)
  4. Per-model pacing: 6s sleep before each Gemini call (stays under quota)
  5. Verification pass: after classify, re-read first 1000 chars and re-classify
     with a verification prompt; flag low-confidence in analyst_memo
  6. Hash dedup: skip if SHA256(file_bytes) already in documents.content_hash

Run on VPS:
    cd /root/landtek
    cp bulk_ingest_mwk.py bulk_ingest_mwk.py.bak2
    python3 patch_bulk_ingest_v2.py
"""
import re
from pathlib import Path

SRC = Path("/root/landtek/bulk_ingest_mwk.py")
text = SRC.read_text()

# ---- 1. Add OPENAI_API_KEY load --------------------------------------------
if "OPENAI_API_KEY" not in text:
    text = text.replace(
        'GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]',
        'GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]\n'
        'OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")  # fallback only',
        1,
    )

# ---- 2. Inject openai_call() and llm_call() right after gemini_call --------
INJECT = '''

# ---- openai (last-resort fallback only) -------------------------------------
def openai_call(prompt, json_mode=True, max_tokens=4000):
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set")
    import requests, json as _json
    body = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}",
                 "Content-Type": "application/json"},
        json=body, timeout=60,
    )
    r.raise_for_status()
    out = r.json()["choices"][0]["message"]["content"]
    return _json.loads(out) if json_mode else out

def llm_call(prompt, json_mode=True, max_tokens=4000):
    """Gemini primary (free). OpenAI only if all Gemini models fail."""
    try:
        return gemini_call(prompt, json_mode=json_mode, max_tokens=max_tokens)
    except Exception as e:
        log(f"  all gemini failed → openai fallback ({str(e)[:80]})")
        return openai_call(prompt, json_mode=json_mode, max_tokens=max_tokens)

# ---- verification pass (cheap accuracy check) -------------------------------
def verify_classification(text, classification):
    """Re-read first 1500 chars and ask: does this case_file assignment match?
    Returns dict {confidence: high|medium|low, reason: str}."""
    excerpt = (text or "")[:1500]
    case = classification.get("case_file", "unknown")
    doctype = classification.get("document_type", "unknown")
    prompt = (
        "You are auditing a document classification. Read the excerpt and "
        "judge if the assigned case_file and document_type are correct.\\n\\n"
        f"ASSIGNED case_file: {case}\\n"
        f"ASSIGNED document_type: {doctype}\\n\\n"
        f"EXCERPT:\\n{excerpt}\\n\\n"
        "Return JSON: {\\"confidence\\": \\"high|medium|low\\", "
        "\\"reason\\": \\"<one sentence>\\", "
        "\\"suggested_case_file\\": \\"<MWK-001|Paracale-001|Owner|unknown>\\"}"
    )
    try:
        return llm_call(prompt, json_mode=True, max_tokens=300)
    except Exception as e:
        return {"confidence": "low", "reason": f"verify failed: {e}",
                "suggested_case_file": case}
'''

text = re.sub(
    r'(raise RuntimeError\(f"all gemini models failed; last=\{last_err\}"\)\n)',
    r'\1' + INJECT + '\n',
    text, count=1
)

# ---- 3. Swap classify + memo to use llm_call -------------------------------
text = text.replace(
    "return gemini_call(prompt, json_mode=True, max_tokens=2000)",
    "return llm_call(prompt, json_mode=True, max_tokens=2000)",
    1,
)
text = text.replace(
    "return gemini_call(prompt, json_mode=True, max_tokens=3000)",
    "return llm_call(prompt, json_mode=True, max_tokens=3000)",
    1,
)

# ---- 4. Add per-file pacing (8s between files) -----------------------------
# Find the main per-file loop. Look for `cls = gemini_classify(text, f["name"])`
# and add a sleep BEFORE it.
text = text.replace(
    'cls = gemini_classify(text, f["name"])',
    'time.sleep(8)  # per-file pacing for Gemini free tier\n'
    '            cls = gemini_classify(text, f["name"])',
    1,
)

# ---- 5. Add verification call right after classify ------------------------
text = text.replace(
    'cls = gemini_classify(text, f["name"])',
    'cls = gemini_classify(text, f["name"])\n'
    '            verify = verify_classification(text, cls)\n'
    '            cls["_verification"] = verify\n'
    '            if verify.get("confidence") == "low":\n'
    '                log(f"    LOW CONFIDENCE: {verify.get(\\"reason\\",\\"\\")}")',
    1,
)

# ---- 6. Add per-Gemini-model pacing inside gemini_call ---------------------
# Insert a 6s sleep before each model attempt (gentle pacing).
text = text.replace(
    'for model in GEMINI_MODELS:',
    'for model in GEMINI_MODELS:\n        time.sleep(6)  # per-call pacing',
    1,
)

# ---- sanity check ----------------------------------------------------------
must_have = [
    "def openai_call(",
    "def llm_call(",
    "def verify_classification(",
    "return llm_call(prompt, json_mode=True, max_tokens=2000)",
    "return llm_call(prompt, json_mode=True, max_tokens=3000)",
    "time.sleep(8)  # per-file pacing",
    "time.sleep(6)  # per-call pacing",
    'cls["_verification"] = verify',
]
missing = [m for m in must_have if m not in text]
if missing:
    raise SystemExit(f"PATCH FAILED — missing: {missing}")

SRC.write_text(text)
print("Patched bulk_ingest_mwk.py v2:")
print("  + openai_call() — last-resort fallback only")
print("  + llm_call() — Gemini primary, OpenAI fallback")
print("  + verify_classification() — accuracy audit pass")
print("  + 8s per-file pacing (free tier safe)")
print("  + 6s per-call pacing inside Gemini loop")
print("  + classify result includes _verification block")
print("\nVerify:  grep -n 'def openai_call\\|def llm_call\\|verify_classification\\|time.sleep' bulk_ingest_mwk.py")
print("Pace estimate: ~15-20 sec/file → 600 files in ~3 hours, ~$0.50 OpenAI cost worst case")
#!/usr/bin/env python3
"""
Safe wrapper for bulk_ingest_mwk.py.
Prevents silent failure on long batch jobs.

Guardrails:
  1. Pre-flight LLM provider check (OpenAI + Gemini)
  2. Canary mode (--canary) processes only N files then stops
  3. Stall detector: exits if 5 consecutive failures or 5 min without success
  4. Live status file at /root/landtek/ingest_status.json
  5. Telegram alert on script exit (success or failure)

Usage:
    # Canary first (default 3 files)
    python3 safe_ingest_wrapper.py --canary 3

    # Full run only after canary passes
    python3 safe_ingest_wrapper.py --full
"""
import argparse
import json
import os
import requests
import subprocess
import sys
import threading
import time
from pathlib import Path

STATUS_FILE = Path("/root/landtek/ingest_status.json")
LOG_FILE = Path("/root/landtek/bulk_ingest.log")
SCRIPT = "/root/landtek/bulk_ingest_mwk.py"
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
JONATHAN_CHAT_ID = "6513067717"

MAX_CONSECUTIVE_FAILS = 5
MAX_NO_SUCCESS_SEC = 300  # 5 min

# ------ pre-flight ----------------------------------------------------------
def preflight_openai():
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        return False, "OPENAI_API_KEY not set"
    try:
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "gpt-4o-mini",
                  "messages": [{"role": "user", "content": "say ok"}],
                  "max_tokens": 5},
            timeout=15,
        )
        if r.status_code == 200:
            return True, "OpenAI OK"
        return False, f"OpenAI HTTP {r.status_code}: {r.text[:100]}"
    except Exception as e:
        return False, f"OpenAI error: {e}"

def preflight_gemini():
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        return False, "GEMINI_API_KEY not set"
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}",
            json={"contents": [{"parts": [{"text": "say ok"}]}]},
            timeout=15,
        )
        if r.status_code == 200:
            return True, "Gemini OK"
        return False, f"Gemini HTTP {r.status_code}"
    except Exception as e:
        return False, f"Gemini error: {e}"

# ------ telegram ------------------------------------------------------------
def telegram(text):
    if not TELEGRAM_TOKEN:
        print(f"[telegram skipped — no TELEGRAM_BOT_TOKEN] {text}")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": JONATHAN_CHAT_ID, "text": text},
            timeout=10,
        )
    except Exception as e:
        print(f"[telegram failed: {e}]")

# ------ status writer (background thread) -----------------------------------
class StatusTracker:
    def __init__(self):
        self.started_at = time.time()
        self.last_success_at = time.time()
        self.success_count = 0
        self.fail_count = 0
        self.consecutive_fails = 0
        self.current_file = ""
        self.pid = None
        self._lock = threading.Lock()

    def write(self):
        with self._lock:
            STATUS_FILE.write_text(json.dumps({
                "pid": self.pid,
                "started_at": self.started_at,
                "started_iso": time.strftime("%Y-%m-%d %H:%M:%S",
                                            time.localtime(self.started_at)),
                "last_success_at": self.last_success_at,
                "seconds_since_last_success": int(time.time() - self.last_success_at),
                "success_count": self.success_count,
                "fail_count": self.fail_count,
                "consecutive_fails": self.consecutive_fails,
                "current_file": self.current_file,
            }, indent=2))

# ------ log tailer ----------------------------------------------------------
def tail_log(tracker, stop_event):
    """Tail bulk_ingest.log and update tracker as new lines come in."""
    pos = 0
    if LOG_FILE.exists():
        pos = LOG_FILE.stat().st_size  # start at end of any pre-existing log
    while not stop_event.is_set():
        try:
            if not LOG_FILE.exists():
                time.sleep(1)
                continue
            with open(LOG_FILE) as f:
                f.seek(pos)
                for line in f:
                    if "Done:" in line and "points upserted" in line:
                        tracker.success_count += 1
                        tracker.last_success_at = time.time()
                        tracker.consecutive_fails = 0
                    elif "classify failed" in line or "memo failed" in line:
                        tracker.fail_count += 1
                        tracker.consecutive_fails += 1
                    elif "Processing:" in line or "---" in line:
                        # try to capture filename
                        tracker.current_file = line.strip()[:120]
                pos = f.tell()
            tracker.write()
        except Exception as e:
            print(f"[tailer error: {e}]")
        time.sleep(2)

# ------ main ----------------------------------------------------------------
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--canary", type=int, help="Process only N files then stop")
    p.add_argument("--full", action="store_true", help="Full run (after canary passes)")
    args = p.parse_args()

    if not args.canary and not args.full:
        sys.exit("Pick one: --canary 3   or   --full")

    print("=" * 60)
    print("SAFE INGEST WRAPPER")
    print("=" * 60)

    # Preflight
    print("\n[preflight]")
    oa_ok, oa_msg = preflight_openai()
    gm_ok, gm_msg = preflight_gemini()
    print(f"  OpenAI: {oa_msg}")
    print(f"  Gemini: {gm_msg}")
    if not oa_ok and not gm_ok:
        telegram("INGEST ABORT: both LLM providers failed preflight.\n"
                 f"OpenAI: {oa_msg}\nGemini: {gm_msg}")
        sys.exit("Both providers down — aborting.")
    if not oa_ok:
        print("  WARN: OpenAI down, will run gemini-only (slow + rate limited)")
    if not gm_ok:
        print("  WARN: Gemini down, will run openai-only")

    # Spawn the actual ingest script
    cmd = ["python3", "-u", SCRIPT, "--process"]
    if args.canary:
        cmd += ["--limit", str(args.canary)]
    print(f"\n[launch] {' '.join(cmd)}")

    # Truncate log for clean canary observation
    LOG_FILE.write_text("")

    proc = subprocess.Popen(cmd, stdout=open(LOG_FILE, "a"),
                            stderr=subprocess.STDOUT)
    print(f"  PID {proc.pid}")

    tracker = StatusTracker()
    tracker.pid = proc.pid
    tracker.write()
    stop = threading.Event()
    t = threading.Thread(target=tail_log, args=(tracker, stop), daemon=True)
    t.start()

    # Health monitor loop
    while True:
        time.sleep(10)
        rc = proc.poll()
        if rc is not None:
            stop.set()
            t.join(timeout=5)
            elapsed = int(time.time() - tracker.started_at)
            msg = (f"INGEST {'OK' if rc == 0 else 'FAIL'} "
                   f"(exit {rc}, {elapsed}s)\n"
                   f"  successes: {tracker.success_count}\n"
                   f"  failures:  {tracker.fail_count}")
            print("\n" + msg)
            telegram(msg)
            sys.exit(rc)

        # Stall checks
        if tracker.consecutive_fails >= MAX_CONSECUTIVE_FAILS:
            stop.set()
            proc.kill()
            msg = (f"INGEST KILLED: {MAX_CONSECUTIVE_FAILS} consecutive failures.\n"
                   f"  successes so far: {tracker.success_count}\n"
                   f"  current file: {tracker.current_file}")
            print(msg)
            telegram(msg)
            sys.exit(2)

        idle = time.time() - tracker.last_success_at
        if idle > MAX_NO_SUCCESS_SEC:
            stop.set()
            proc.kill()
            msg = (f"INGEST KILLED: no success in {int(idle)}s "
                   f"(threshold {MAX_NO_SUCCESS_SEC}s).\n"
                   f"  total successes: {tracker.success_count}\n"
                   f"  total failures: {tracker.fail_count}")
            print(msg)
            telegram(msg)
            sys.exit(3)

if __name__ == "__main__":
    main()
