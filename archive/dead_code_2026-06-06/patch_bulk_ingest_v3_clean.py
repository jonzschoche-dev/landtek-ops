#!/usr/bin/env python3
"""
v3 Clean patch — no fancy multi-line strings (those broke v2).

Steps:
  1. RESTORE from backup first (the v2 patch left the file syntactically broken)
  2. Inject openai_call() — last-resort fallback only
  3. Inject llm_call() — Gemini primary, OpenAI fallback
  4. Swap classify + memo to use llm_call
  5. Add per-file 8s sleep + per-Gemini-model 6s sleep

Verification pass intentionally omitted from this patch — will be a
separate `audit_classifications.py` script that runs against Postgres
after ingestion completes (cheaper + safer).

Run on VPS:
    cd /root/landtek
    cp bulk_ingest_mwk.py.bak2 bulk_ingest_mwk.py    # restore broken v2
    python3 patch_bulk_ingest_v3_clean.py
"""
from pathlib import Path
import re

SRC = Path("/root/landtek/bulk_ingest_mwk.py")
text = SRC.read_text()

# --- 1. Add OPENAI_API_KEY load ---------------------------------------------
if "OPENAI_API_KEY" not in text:
    text = text.replace(
        'GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]',
        'GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]\n'
        'OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")',
        1,
    )

# --- 2. Inject openai_call + llm_call after gemini_call ---------------------
# Build INJECT line-by-line to avoid quote-escaping pitfalls.
inject_lines = [
    "",
    "",
    "# ---- openai (last-resort fallback only) ------------------------------------",
    "def openai_call(prompt, json_mode=True, max_tokens=4000):",
    "    if not OPENAI_API_KEY:",
    "        raise RuntimeError('OPENAI_API_KEY not set')",
    "    import requests, json as _json",
    "    body = {",
    "        'model': 'gpt-4o-mini',",
    "        'messages': [{'role': 'user', 'content': prompt}],",
    "        'max_tokens': max_tokens,",
    "        'temperature': 0.2,",
    "    }",
    "    if json_mode:",
    "        body['response_format'] = {'type': 'json_object'}",
    "    r = requests.post(",
    "        'https://api.openai.com/v1/chat/completions',",
    "        headers={'Authorization': 'Bearer ' + OPENAI_API_KEY,",
    "                 'Content-Type': 'application/json'},",
    "        json=body, timeout=60,",
    "    )",
    "    r.raise_for_status()",
    "    out = r.json()['choices'][0]['message']['content']",
    "    return _json.loads(out) if json_mode else out",
    "",
    "def llm_call(prompt, json_mode=True, max_tokens=4000):",
    "    try:",
    "        return gemini_call(prompt, json_mode=json_mode, max_tokens=max_tokens)",
    "    except Exception as e:",
    "        log('  all gemini failed, openai fallback: ' + str(e)[:80])",
    "        return openai_call(prompt, json_mode=json_mode, max_tokens=max_tokens)",
    "",
]
INJECT = "\n".join(inject_lines)

text = re.sub(
    r'(raise RuntimeError\(f"all gemini models failed; last=\{last_err\}"\)\n)',
    r'\1' + INJECT,
    text, count=1,
)

# --- 3. Swap classify + memo to llm_call ------------------------------------
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

# --- 4. Per-file pacing (8s) + per-Gemini-model pacing (6s) -----------------
text = text.replace(
    'cls = gemini_classify(text, f["name"])',
    'time.sleep(8)\n            cls = gemini_classify(text, f["name"])',
    1,
)
text = text.replace(
    "for model in GEMINI_MODELS:",
    "for model in GEMINI_MODELS:\n        time.sleep(6)",
    1,
)

# --- sanity check -----------------------------------------------------------
must_have = [
    "def openai_call(",
    "def llm_call(",
    "return llm_call(prompt, json_mode=True, max_tokens=2000)",
    "return llm_call(prompt, json_mode=True, max_tokens=3000)",
    "time.sleep(8)",
    "time.sleep(6)",
]
missing = [m for m in must_have if m not in text]
if missing:
    raise SystemExit("PATCH FAILED — missing: " + repr(missing))

# Validate the result actually compiles
import py_compile, tempfile
with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
    f.write(text)
    tmp = f.name
try:
    py_compile.compile(tmp, doraise=True)
except py_compile.PyCompileError as e:
    raise SystemExit("PATCH PRODUCED INVALID PYTHON:\n" + str(e))

SRC.write_text(text)
print("Patched bulk_ingest_mwk.py v3 (clean):")
print("  + openai_call() / llm_call() injected")
print("  + classify + memo route via llm_call")
print("  + per-file 8s pacing, per-Gemini-call 6s pacing")
print("  + py_compile validated — no syntax errors")
print()
print("Verify: grep -n 'def openai_call\\|def llm_call\\|time.sleep' bulk_ingest_mwk.py")
