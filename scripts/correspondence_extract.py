#!/usr/bin/env python3
"""correspondence_extract.py — auto-populate the correspondence ledger with DELIVERY-GAP events.

Deterministic (no LLM in the extraction path → no fabrication): scans the matter's documents for
delivery-failure / late-receipt language and records each as a ledger event whose proof quote is lifted
VERBATIM from the document (so it passes the substring gate by construction). The gaps are the §21
findings — non-deliveries, phantom responses, late receipts. Dedups against quotes already in the ledger.

Runs ON THE VPS (psycopg2). Pairs with correspondence_ledger.py.
  python3 correspondence_extract.py --matter 'MWK-ARTA%' --dry
  python3 correspondence_extract.py --matter 'MWK-ARTA%'
"""
import argparse
import re
import psycopg2
import correspondence_ledger as L

GAP = [
    ("phantom", r"phantom response|never (?:received|delivered)|undelivered|no notice at all|"
                r"address not found|non-existent[^.]{0,25}address|bounced|did not (?:actually )?(?:deliver|arrive)|"
                r"was not delivered|misplac\w+ the|misspell"),
    ("late",    r"only received[^.]{0,45}(?:later|month|afternoon|underway|belated)|belatedly|"
                r"months later|received[^.]{0,20}months (?:later|after)"),
]
PARTIES = ["Balane", "Pajarillo", "Macale", "Abla", "Teope", "Ong", "Fortuno", "PENRO", "CART",
           "Sangguniang", "Municipal Engineer", "Assessor", "Treasurer", "Mayor"]
# sentences that ARGUE ABOUT delivery (legal commentary) rather than assert a delivery event — skip them
META_RX = re.compile(r"resolution|whether arta|legal standard|if allowed ?to ?stand|signal ?to ?government|"
                     r"basic principle|fails on both|cannot stand|appears to|evidence on record|"
                     r"benefit of the doubt|annex|attachment \d", re.IGNORECASE)
PER_DOC_CAP = 2


def sentence_around(text, pos, width=170):
    a = text.rfind(".", max(0, pos - width), pos)
    b = text.find(".", pos, pos + width)
    a = a + 1 if a != -1 else max(0, pos - width)
    b = b if b != -1 else min(len(text), pos + width)
    return text[a:b].strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matter", required=True)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    conn = psycopg2.connect(L.DSN); conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT id, coalesce(left(doc_date::text,10),''), "
                "regexp_replace(coalesce(extracted_text,''),'[[:space:]]+',' ','g') "
                "FROM documents WHERE id IN (SELECT doc_id FROM document_matter_links WHERE matter_code ILIKE %s) "
                "AND extracted_text IS NOT NULL", (a.matter,))
    docs = cur.fetchall()
    cur.execute("SELECT proofs FROM correspondence_events")
    seen = set()
    for (pf,) in cur.fetchall():
        for p in (pf or []):
            seen.add(L._norm(p.get("quote", ""))[:55])

    cand = added = 0
    for did, ddate, txt in docs:
        per_doc = 0
        for status, pat in GAP:
            for m in re.finditer(pat, txt, re.I):
                if per_doc >= PER_DOC_CAP:
                    break
                q = sentence_around(txt, m.start())
                if len(q) < 30 or META_RX.search(q):
                    continue
                key = L._norm(q)[:55]
                if key in seen:
                    continue
                seen.add(key); cand += 1; per_doc += 1
                party = next((p for p in PARTIES if re.search(p, q, re.I)), None)
                ev = {"matter_code": a.matter.strip("%"), "author": party, "addressee": None,
                      "subject": f"Delivery gap ({status}) in the record", "claimed_date": ddate or None,
                      "channel": None, "sent_to": None, "delivery_status": status, "received_date": None,
                      "gap_flag": q[:280], "proofs": [{"doc_id": did, "quote": q[:240]}]}
                if a.dry:
                    print(f"  [{status:7}] doc {did} ({party or '—'}): {q[:88]}")
                else:
                    L.add_event(cur, ev); added += 1
    print(f"\n  candidates: {cand}" + ("  (dry — no writes)" if a.dry else f"  ·  added: {added}"))
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
