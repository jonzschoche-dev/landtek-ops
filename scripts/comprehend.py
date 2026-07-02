#!/usr/bin/env python3
"""comprehend.py — the recognition layer: teach the system to READ its own documents and
derive the facts it would otherwise have to ask the operator for.

The deterministic engine can only pattern-match; this layer comprehends. For an asset/matter it
reads the linked documents and extracts grounded facts — title status (clean vs clouded, from
cancellation stamps / adverse-claim / lis-pendens / encumbrance annotations), assessed value,
possession indicators — each with a VERBATIM excerpt + a confidence score. High-confidence facts
overwrite the coarse defaults; only low-confidence / contradictory ones are flagged for the
operator (the human as exception-handler, not director). Runs on Gemini free-tier (key×model
ladder) = creditless re: Anthropic. Quality scales with OCR (the re-OCR sweep feeds this).

  python3 comprehend.py --title T-32917            # dry: show what it derives
  python3 comprehend.py --title T-32917 --go       # derive + write (updates property_assets)
  python3 comprehend.py --sweep --limit 20 --go    # comprehend the title backlog, rate-limited
  python3 comprehend.py --reconcile-chain          # dry: face-reads that the verified chain contradicts
  python3 comprehend.py --reconcile-chain --go     # self-heal: verified chain overrides the face-read
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
GEMINI_KEYS = [k for k in (os.environ.get("GEMINI_API_KEY", ""), os.environ.get("GEMINI_API_KEY_FALLBACK", "")) if k]
MODELS = [os.environ.get("GEMINI_VISION_MODEL", "gemini-2.5-flash"), os.environ.get("GEMINI_VISION_FALLBACK", "gemini-2.0-flash")]
CONF_WRITE = float(os.environ.get("COMPREHEND_MIN_CONF", "0.6"))   # write threshold
# Local backend (offline-sovereignty): reason from extracted text with no cloud dependency.
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct")
LLM_BACKEND = os.environ.get("LLM_BACKEND", "auto")   # auto | gemini | ollama
_RPM = 0
_LAST = [0.0]

PROMPT = """You are reading text extracted from a Philippine land title (TCT/OCT) document.
From the TEXT ONLY (do not speculate), determine:
1. title_status: one of "clean" | "clouded" | "cancelled" | "unverified".
   - "clouded" if there is an adverse claim, lis pendens, pending litigation, notice, encumbrance,
     mortgage, or any annotation casting doubt on ownership.
   - "cancelled" if the title is stamped cancelled / superseded / "cancelled by".
   - "clean" if it is an active title with no such annotation.
   - "unverified" if the text is too garbled/incomplete to tell.
2. assessed_or_market_value_php: a number if any peso value/assessed value appears, else null.
3. possession_note: short note on any possession/occupancy indicator, else null.
4. evidence: a SHORT verbatim quote from the text supporting title_status.
5. confidence: 0.0-1.0 — how sure you are, lower if the text is garbled.
Return ONLY a JSON object with exactly these keys."""


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True; return c


def _throttle():
    if _RPM > 0:
        wait = 60.0 / _RPM - (time.time() - _LAST[0])
        if wait > 0:
            time.sleep(wait)
    _LAST[0] = time.time()


class QuotaExhausted(Exception):
    pass


def _gemini(text):
    """Key×model ladder; returns parsed JSON dict or raises QuotaExhausted."""
    body = {"contents": [{"parts": [{"text": PROMPT + "\n\nTEXT:\n" + text[:12000]}]}],
            "generationConfig": {"temperature": 0, "response_mime_type": "application/json"}}
    _throttle()
    for key in GEMINI_KEYS:
        for model in MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                         headers={"content-type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=90) as r:
                    out = json.loads(r.read())
                raw = "".join(p.get("text", "") for p in out["candidates"][0]["content"]["parts"])
                return json.loads(raw)
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(1); continue
                raise
            except (json.JSONDecodeError, KeyError, IndexError):
                return None
    raise QuotaExhausted("all gemini key/model combos 429")


def _ollama(text):
    """Local Ollama backend — reads the title text with no cloud dependency. Returns dict or None."""
    body = {"model": OLLAMA_MODEL, "prompt": PROMPT + "\n\nTEXT:\n" + text[:12000],
            "format": "json", "stream": False, "options": {"temperature": 0}}
    req = urllib.request.Request(OLLAMA_URL + "/api/generate", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=240) as r:
            out = json.loads(r.read())
        return json.loads(out.get("response", "") or "{}")
    except (json.JSONDecodeError, KeyError, urllib.error.URLError, TimeoutError):
        return None


def _derive(text):
    """Backend selector. 'auto' tries Gemini, then DEGRADES to local Ollama (offline-sovereignty)."""
    if LLM_BACKEND == "ollama":
        return _ollama(text)
    if LLM_BACKEND == "gemini":
        return _gemini(text)
    try:
        return _gemini(text)
    except QuotaExhausted:
        return _ollama(text)


def _doc_text(cur, tct):
    cur.execute("""SELECT d.extracted_text FROM titles t JOIN documents d ON d.id = t.source_doc_id
                   WHERE t.tct_number=%s AND length(coalesce(d.extracted_text,'')) > 50""", (tct,))
    row = cur.fetchone()
    return row["extracted_text"] if row else None


def comprehend_title(tct, go=False):
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    text = _doc_text(cur, tct)
    if not text:
        cur.close(); c.close(); return {"tct": tct, "error": "no readable source doc"}
    derived = _derive(text)
    if not derived:
        cur.close(); c.close(); return {"tct": tct, "error": "no parse"}
    res = {"tct": tct, "derived": derived}
    conf = float(derived.get("confidence") or 0)
    if go and conf >= CONF_WRITE and derived.get("title_status") in ("clean", "clouded", "cancelled"):
        note = f"comprehended {derived['title_status']} (conf {conf:.2f}): {str(derived.get('evidence',''))[:160]}"
        cur.execute("""UPDATE property_assets SET title_status=%s,
                       tier = CASE WHEN %s IN ('clouded','cancelled') THEN 'recover_then'
                                   WHEN coalesce(area_sqm,0) > 20000 THEN 'develop' ELSE 'earn_now' END,
                       note = left(coalesce(note,'') || ' | ' || %s, 400),
                       est_value = COALESCE(%s, est_value), updated_at = now()
                       WHERE title_ref=%s""",
                    (derived["title_status"], derived["title_status"], note,
                     derived.get("assessed_or_market_value_php"), tct))
        res["written"] = cur.rowcount > 0
        # promote titles.status out of 'unknown' (inferred_strong; guard keeps keystone-'active' titles untouched)
        try:
            st_map = {"clean": "active", "clouded": "clouded", "cancelled": "cancelled"}
            cur.execute("""UPDATE titles SET status=%s, provenance_level='inferred_strong',
                           provenance_notes=left(%s, 400), updated_at=now()
                           WHERE tct_number=%s AND coalesce(status,'unknown')='unknown'""",
                        (st_map[derived["title_status"]], "comprehend: " + note, tct))
            res["title_promoted"] = cur.rowcount > 0
        except Exception as e:
            res["title_promote_err"] = str(e)[:120]
    elif conf < CONF_WRITE:
        res["flagged_for_human"] = f"low confidence ({conf:.2f}) — needs operator confirmation"
    cur.close(); c.close()
    return res


def sweep(limit=None, rpm=8, go=False):
    global _RPM
    _RPM = rpm
    c = _conn(); cur = c.cursor()
    # titles with a readable source doc, not yet comprehended (note lacks the marker)
    cur.execute("""SELECT t.tct_number FROM titles t JOIN documents d ON d.id=t.source_doc_id
                   LEFT JOIN property_assets p ON p.title_ref=t.tct_number
                   WHERE length(coalesce(d.extracted_text,'')) > 50
                     AND coalesce(p.note,'') NOT LIKE '%comprehended%'
                   ORDER BY t.tct_number""")
    tcts = [r[0] for r in cur.fetchall()]
    cur.close(); c.close()
    if limit:
        tcts = tcts[:limit]
    print(f"[comprehend] queue={len(tcts)} rpm={rpm}", flush=True)
    done = wrote = flagged = 0
    for tct in tcts:
        try:
            r = comprehend_title(tct, go=go)
        except QuotaExhausted:
            print(f"[comprehend] Gemini quota exhausted after {done} — resume after reset", flush=True)
            break
        done += 1
        if r.get("written"):
            wrote += 1
            d = r["derived"]
            print(f"  {tct}: {d.get('title_status')} (conf {d.get('confidence')})", flush=True)
        elif r.get("flagged_for_human"):
            flagged += 1
            print(f"  {tct}: FLAGGED — {r['flagged_for_human']}", flush=True)
        else:
            print(f"  {tct}: {r.get('error','-')}", flush=True)
    print(f"[comprehend] processed={done} wrote={wrote} flagged_for_human={flagged}", flush=True)


def reconcile_chain(go=False):
    """Self-heal against the VERIFIED title_chain (which OUTRANKS the LLM face-read).

    comprehend reads the FACE of a title doc, so a title later cancelled by a derivative (its
    cancellation living on a different doc) can read 'clean/active'. This pass corrects that:
    a title that a verified 'cancelled_and_replaced' edge shows cancelled — but that is NOT marked
    cancelled — is set to cancelled (verified, sourced to the chain quote). Subdivision parents
    ('derivative' edges) that read active/clouded are AMBIGUOUS (mother-title status is
    case-dependent) and only FLAGGED as an operator-review matter_fact, never auto-changed.
    Hard-locked titles are skipped. Idempotent."""
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""SELECT DISTINCT ON (tc.parent_title) tc.parent_title AS tct,
                          tc.provenance_quote AS q, t.status, coalesce(t.verification_lock,'') AS lock
                   FROM title_chain tc JOIN titles t ON t.tct_number=tc.parent_title
                   WHERE tc.relationship='cancelled_and_replaced' AND tc.provenance_level='verified'
                     AND coalesce(tc.provenance_quote,'')<>'' AND t.status<>'cancelled'
                   ORDER BY tc.parent_title, tc.verified_at DESC""")
    corrected = []
    for r in cur.fetchall():
        if r["lock"] == "hard":
            print(f"  SKIP {r['tct']}: hard-locked — surfacing for manual review", flush=True); continue
        if go:
            cur.execute("""UPDATE titles SET status='cancelled', provenance_level='verified',
                           provenance_notes=left(%s,400), updated_at=now()
                           WHERE tct_number=%s AND coalesce(verification_lock,'')<>'hard'""",
                        ("chain-verified cancelled (supersedes face-read): " + (r["q"] or ""), r["tct"]))
            cur.execute("""UPDATE property_assets SET title_status='cancelled',
                           note=left(coalesce(note,'')||' | CHAIN-CORRECTED->cancelled (verified title_chain edge)',400),
                           updated_at=now() WHERE title_ref=%s""", (r["tct"],))
        corrected.append(r["tct"])
        print(f"  {'CORRECT' if go else 'WOULD-CORRECT'} {r['tct']}: {r['status']} -> cancelled (verified)", flush=True)
    cur.execute("""SELECT DISTINCT tc.parent_title AS tct, t.status FROM title_chain tc
                   JOIN titles t ON t.tct_number=tc.parent_title
                   WHERE tc.relationship='derivative' AND tc.provenance_level='verified'
                     AND t.status IN ('active','clouded')
                     AND tc.parent_title NOT IN (SELECT parent_title FROM title_chain
                        WHERE relationship='cancelled_and_replaced' AND provenance_level='verified')
                   ORDER BY tc.parent_title""")
    flags = cur.fetchall()
    for f in flags:
        print(f"  FLAG {f['tct']}: {f['status']} (subdivision parent — mother-title status case-dependent)", flush=True)
    if go and flags:
        stmt = ("Title chain-reconcile: subdivision-parent titles read active/clouded but spawned verified "
                "derivatives (" + ", ".join(f["tct"] for f in flags) + "). Mother-title status on subdivision "
                "is case-dependent (retained vs cancelled) — operator confirmation needed before treated as fact.")
        cur.execute("""INSERT INTO matter_facts (matter_code, statement, fact_kind, source_kind,
                       provenance_level, confidence, created_by)
                       SELECT 'MWK-001', %s, 'issue', 'operator', 'inferred_strong', 0.8, 'comprehend-reconcile-chain'
                       WHERE NOT EXISTS (SELECT 1 FROM matter_facts
                          WHERE created_by='comprehend-reconcile-chain' AND statement=%s)""",
                    (stmt, stmt))
    print(f"[reconcile] corrections={len(corrected)} subdivision_flags={len(flags)} go={go}", flush=True)
    cur.close(); c.close()
    return {"corrected": corrected, "flagged": [f["tct"] for f in flags], "go": go}


if __name__ == "__main__":
    a = sys.argv
    if "--sweep" in a:
        lim = int(a[a.index("--limit") + 1]) if "--limit" in a else None
        sweep(limit=lim, rpm=int(a[a.index("--rpm") + 1]) if "--rpm" in a else 8, go="--go" in a)
    elif "--title" in a:
        try:
            print(json.dumps(comprehend_title(a[a.index("--title") + 1], go="--go" in a), indent=2))
        except QuotaExhausted:
            print(json.dumps({"error": "gemini quota exhausted — comprehension runs as quota resets "
                              "(shares the re-OCR sweep's budget), or instantly with Anthropic credits"}, indent=2))
    elif "--reconcile-chain" in a:
        reconcile_chain(go="--go" in a)
    else:
        print(__doc__)
