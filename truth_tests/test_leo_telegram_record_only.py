#!/usr/bin/env python3
"""test_leo_telegram_record_only.py — Leo's answers to Jonathan come from the record or say they are not there.
Locks the four defects in the 4 Nov 2026 review (side-session-notes LEO_REVIEW_2026-11-04.md, Jonathan's go
"Yes, fix Telegram"):

  J1  "open and read those two SPAs, quote the exact language ..." was not an inquiry, so it reached the free
      model, which invented "Document: PA-T-4765".
  J2  "Not possible" got a free-model status: "the Balane matter is still pending ... relocation survey".
  J3  "What Balane matter ?", "status of the guardianship", "status of CV6839" had no record answer.
  J4  Every stack miss also pushed a "Needs your call" ping past the S14 hold, even when Jonathan asked.

Data-relative (matter titles read from the DB). Probes run in rolled-back transactions; the model and Telegram
are stubbed (nothing is generated or sent).
"""
import os
import re
import sys
import types

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "leo_tools"))
from _harness import run, TruthFailure, DSN
import leo_service as LS
import inquiry_stack as IST

JONATHAN_TG = "6513067717"
SPA_ASK = ("open and read those two SPAs, quote the exact language defining Cesar's authority, with dates and "
           "principals, and cite document plus page")
INVENTED = ("Jonathan, I reviewed the SPAs. Cesar M. de la Fuente's authority is defined as acting on behalf of the "
            "principal in property transactions, effective from the date of the agreement. Document: PA-T-4765",
            "Jonathan, the status of the Balane matter is still pending. We need to follow up with the counsel "
            "regarding the relocation survey.")
SOCIAL = "Okay Jonathan, noted. Talk soon."


def _rb():
    conn = psycopg2.connect(DSN); conn.autocommit = False
    return conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _generate(message, model_text):
    calls = []
    real = LS._llm
    LS._llm = lambda *a, **k: (calls.append(a) or model_text)
    conn, tc = _rb()
    try:
        out = LS.generate_reply(tc, "telegram", JONATHAN_TG, message, "MWK-001", dry_run=True)
    finally:
        conn.rollback(); conn.close()
        LS._llm = real
    return out or {}, calls


def read_document_ask_never_reaches_free_model(cur):
    if not LS.is_inquiry(SPA_ASK):
        raise TruthFailure(f"a read/quote-the-document ask is not treated as a record question: {SPA_ASK!r}")
    out, calls = _generate(SPA_ASK, INVENTED[0])
    if calls or "PA-T-4765" in (out.get("text") or ""):
        raise TruthFailure(f"read/quote ask reached the free model: {out.get('text')!r}")


def free_model_record_claims_withheld(cur):
    for t in INVENTED:
        out, _ = _generate("Not possible", t)
        if (out.get("text") or "") == t or "PA-T-4765" in (out.get("text") or "") or \
                "relocation survey" in (out.get("text") or ""):
            raise TruthFailure(f"free-model record claim was sent: {out.get('text')!r}")
    out, _ = _generate("ok thanks", SOCIAL)
    if out.get("via") == "free_fact_withheld":
        raise TruthFailure(f"plain social reply was withheld as a record claim: {SOCIAL!r}")


def _route(client, q):
    conn, tc = _rb()
    try:
        return LS.try_purpose_route(tc, client, q, channel="telegram", channel_user_id=JONATHAN_TG,
                                    dry_run=True) or {}
    finally:
        conn.rollback(); conn.close()


def matter_named_by_party_is_answered(cur):
    cur.execute("""SELECT matter_code, title FROM matters WHERE client_code='MWK-001'
                     AND matter_code IN ('MWK-CV26360','MWK-GUARDIANSHIP','MWK-CV6839')""")
    titles = {r["matter_code"]: r["title"] for r in cur.fetchall()}
    asks = {"MWK-CV26360": "What Balane matter ?", "MWK-GUARDIANSHIP": "What is the status of the guardianship?",
            "MWK-CV6839": "status of CV6839"}
    for mc, q in asks.items():
        if mc not in titles:
            continue
        r = _route("MWK-001", q)
        head = titles[mc][:25]
        if r.get("via") != "composer:matter_status" or head not in (r.get("text") or ""):
            raise TruthFailure(f"{q!r} was not answered with {mc} from the record: via={r.get('via')} "
                               f"text={(r.get('text') or '')[:160]!r}")
    # A5: another client never gets this client's matter by party name
    r = _route("Paracale-001", "What Balane matter ?")
    if "Balane" in (r.get("text") or ""):
        raise TruthFailure(f"CROSS-CLIENT LEAK: Paracale-001 was told about Balane: {r.get('text')!r}")


def no_per_miss_ping_to_jonathan(cur):
    seen = {}
    real = IST.try_inquiry_stack
    IST.try_inquiry_stack = lambda *a, **k: (seen.update(k) or None)
    try:
        _route("MWK-001", "blorp quux zibble status?")
    finally:
        IST.try_inquiry_stack = real
    if seen.get("notify", True) is not False:
        raise TruthFailure(f"Jonathan's own unanswered question still pings him: notify={seen.get('notify')!r}")
    calls = []
    fake = types.ModuleType("tg_send")
    fake.send = lambda **kw: (calls.append(kw) or (True, "stub"))
    real_tg = sys.modules.get("tg_send")
    sys.modules["tg_send"] = fake
    conn, tc = _rb()
    try:
        IST._enqueue_human_review(tc, 0, "truth test question", {"text": "x"}, notify=False)
        if calls:
            raise TruthFailure("notify=False still sent a Telegram ping")
        IST._enqueue_human_review(tc, 0, "truth test question", {"text": "x"}, notify=True)
        if calls and calls[0].get("override_pacing"):
            raise TruthFailure("the per-miss ping skips the S14 hold (override_pacing=True)")
    finally:
        conn.rollback(); conn.close()
        if real_tg is not None:
            sys.modules["tg_send"] = real_tg
        else:
            sys.modules.pop("tg_send", None)


TESTS = [
    ("leo_tg.read_document_never_free_model", read_document_ask_never_reaches_free_model),
    ("leo_tg.free_model_claims_withheld", free_model_record_claims_withheld),
    ("leo_tg.matter_by_party_answered", matter_named_by_party_is_answered),
    ("leo_tg.no_per_miss_ping", no_per_miss_ping_to_jonathan),
]

if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
