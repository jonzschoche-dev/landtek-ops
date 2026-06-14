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
    derived = _gemini(text)
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
    else:
        print(__doc__)
