#!/usr/bin/env python3
"""corpus_onboarding_digest.py — once-a-day onboarding line to Jonathan.

One plain sentence: how searchable the corpus is, how many docs still await OCR,
and the verdict. Sends a one-time congratulations the day it crosses bullet-proof.
Respects tg_send pacing (Rule S14) — never overrides, never chains.
"""
import json, os, sys
import psycopg2

sys.path.insert(0, "/root/landtek/scripts")
import tg_send

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
JONATHAN = "6513067717"
STATE = "/root/landtek/logs/onboarding_digest_state.json"
CANON = ("master_form='digital' AND coalesce(ingest_status,'') NOT IN "
         "('quarantined_dup','quarantined_ghost','quarantined_nobytes')")


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"SELECT count(*) FROM documents WHERE {CANON}")
    total = cur.fetchone()[0] or 1
    cur.execute("SELECT count(*) FROM corpus_backfill_state WHERE embedded")
    embedded = cur.fetchone()[0]
    cur.execute(f"SELECT count(*) FROM documents WHERE {CANON} AND coalesce(length(extracted_text),0) < 50")
    no_text = cur.fetchone()[0]
    cur.close(); conn.close()

    pct = round(100 * min(embedded, total) / total)
    bulletproof = (no_text == 0 and pct >= 99)

    prev = {}
    try:
        prev = json.load(open(STATE))
    except Exception:
        pass

    if bulletproof and not prev.get("bulletproof"):
        text = ("Corpus onboarding complete — every document is now reachable, read, "
                "and searchable. The corpus is bullet-proof.")
    elif bulletproof:
        return  # already announced; stay quiet
    else:
        text = (f"Corpus onboarding: {pct}% searchable, {no_text} documents still "
                f"awaiting OCR on the free tier. Grinding.")

    try:
        tg_send.send(JONATHAN, text, "briefer", recipient_name="Jonathan")
    except Exception as e:
        print(f"digest send failed: {e}")

    json.dump({"bulletproof": bulletproof, "pct": pct, "no_text": no_text},
              open(STATE, "w"))
    print(f"digest: pct={pct} no_text={no_text} bulletproof={bulletproof}")


if __name__ == "__main__":
    main()
