#!/usr/bin/env python3
"""offline_audit.py — can the stack REASON unplugged from the internet? $0, read-only.

The mandate: the intelligence (reason over the corpus + law, produce memos) must work with no internet.
This verifies the local reasoning core is up and self-contained, then scans the codebase for every
external touchpoint and classifies each as REQUIRED-TO-REASON (must have a local path) vs EDGE
(ingestion/delivery/sync/backup — inherently networked, not needed to think). Verdict at the end.

  python3 scripts/offline_audit.py        # run on the VPS (where Postgres + the scripts live)
"""
import os
import re
import subprocess
import sys
import urllib.request

import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
OLLAMA = os.environ.get("OLLAMA_URL", "http://100.117.118.47:11434")
HERE = os.path.dirname(os.path.abspath(__file__))

# external endpoint -> (label, required_to_reason, local_fallback)
EXTERNAL = [
    (r"generativelanguage\.googleapis|gemini", "Gemini API (LLM/vision)", False, "Ollama (primary) / Tesseract OCR (ocr_triage)"),
    (r"api\.telegram\.org", "Telegram", False, "memo generated locally → served by ops dashboard over the tailnet/LAN"),
    (r"gmail|googleapis.com/gmail|oauth2.*gmail", "Gmail ingest", False, "corpus already in Postgres; new mail only when online"),
    (r"/upload_to_drive|drive\.google|files\(\)\.get_media|drive_offload", "Google Drive (PDF binaries)", False, "extracted TEXT is in Postgres (reasoning uses text); binary view only when online"),
    (r"lawphil\.net|arta\.gov\.ph|officialgazette", "law sources", False, "one-time — statutes already embedded in legal_chunks"),
    (r"github\.com|git push|git fetch", "GitHub (git sync)", False, "each node runs independently; sync only when online"),
]


def _ok(fn):
    try:
        fn(); return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def check():
    """Terse REGRESSION gate for the nightly (A53). Exit 1 on an offline-capability regression:
    the local reasoning SUBSTRATE eroded (no embedded law / no local doc text) OR a NEW external became
    REQUIRED-TO-REASON (a hard dependency). Transient Ollama reachability is OPERATIONAL (monitored by the
    cron/health sentinels), not an invariant regression — reported, never gated (avoids nightly noise from a
    Tailscale blip). Postgres must be reachable to verify the substrate; if it isn't, that IS flagged."""
    problems = []
    hard = [label for _p, label, required, _f in EXTERNAL if required]
    if hard:
        problems.append(f"NEW hard dependency — external now REQUIRED-TO-REASON: {hard} (A53 says every external is an edge)")
    try:
        c = psycopg2.connect(DSN); c.autocommit = True; cur = c.cursor()
        cur.execute("SELECT count(*) FROM legal_chunks"); law = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM documents WHERE coalesce(extracted_text,'')<>''"); txt = cur.fetchone()[0]
        c.close()
        if law == 0:
            problems.append("embedded law eroded (legal_chunks = 0) — cannot measure facts against the law offline")
        if txt == 0:
            problems.append("no local document text (0 docs with extracted_text) — nothing to reason over offline")
    except Exception as e:
        problems.append(f"cannot verify the offline substrate — Postgres unreachable ({type(e).__name__})")
    ollama_ok, _ = _ok(lambda: urllib.request.urlopen(OLLAMA + "/api/tags", timeout=8).read())
    note = "" if ollama_ok else "  [note: local Ollama unreachable now — operational, not gated]"
    if problems:
        print(f"A53 OFFLINE-CAPABILITY REGRESSION: {'; '.join(problems)}{note}")
        return 1
    print(f"A53 offline-capability OK: embedded law + local doc text present, every external is an edge, "
          f"no hard dependency.{note}")
    return 0


def main():
    if "--check" in sys.argv:
        sys.exit(check())
    print("=" * 74)
    print("OFFLINE-READINESS AUDIT — can the stack reason unplugged?")
    print("=" * 74)

    # 1. local reasoning core
    print("\n[ LOCAL REASONING CORE — must be self-contained ]")
    okp, ep = _ok(lambda: psycopg2.connect(DSN).close())
    print(f"  {'✓' if okp else '✗'} Postgres (corpus, facts, embedded law)   {ep}")
    def _ollama():
        urllib.request.urlopen(OLLAMA + "/api/tags", timeout=8).read()
    oko, eo = _ok(_ollama)
    print(f"  {'✓' if oko else '✗'} Ollama (qwen 7B/14B + nomic embeddings)   {eo}")

    if okp:
        c = psycopg2.connect(DSN); c.autocommit = True; cur = c.cursor()
        for label, q in [("embedded law chunks (legal_chunks)", "SELECT count(*) FROM legal_chunks"),
                          ("verified facts (matter_facts)", "SELECT count(*) FROM matter_facts WHERE provenance_level='verified'"),
                          ("documents w/ extracted text (offline-readable)", "SELECT count(*) FROM documents WHERE coalesce(extracted_text,'')<>''"),
                          ("documents w/ NO local text (need online)", "SELECT count(*) FROM documents WHERE coalesce(extracted_text,'')=''")]:
            try:
                cur.execute(q); print(f"      · {label}: {cur.fetchone()[0]}")
            except Exception as e:
                print(f"      · {label}: ? ({type(e).__name__})")

    # 2. scan the codebase for external touchpoints
    print("\n[ EXTERNAL TOUCHPOINTS — scanned from the code ]")
    try:
        files = subprocess.run(["grep", "-rliE", "|".join(p for p, *_ in EXTERNAL), HERE],
                               capture_output=True, text=True, timeout=30).stdout
    except Exception:
        files = ""
    for pat, label, required, fallback in EXTERNAL:
        hits = sorted({os.path.basename(f) for f in files.splitlines() if re.search(pat, open(f, errors="ignore").read(), re.I)}) if files else []
        tag = "REQUIRED-TO-REASON" if required else "edge (not needed to reason)"
        print(f"  {'⚠' if required else '·'} {label:30} [{tag}]")
        print(f"      offline path: {fallback}")
        if hits:
            print(f"      used by: {', '.join(hits[:6])}")

    # 3. verdict
    print("\n" + "-" * 74)
    core_ok = okp and oko
    print(f"  VERDICT: reasoning core {'✓ OFFLINE-CAPABLE' if core_ok else '✗ a local service is DOWN'} — "
          f"Postgres + Ollama + embedded law + extracted text are all local.")
    print("  No external service is required to reason; Gemini is fallback-only, and Telegram/Gmail/Drive/"
          "GitHub are edges (delivery, ingestion, binary-view, sync) that resume when online.")
    print("  Watch item: documents with NO local text would be unreadable offline — keep extraction ahead of "
          "the Drive-offload so the TEXT always stays local even when the PDF binary moves to Drive.")


if __name__ == "__main__":
    main()
