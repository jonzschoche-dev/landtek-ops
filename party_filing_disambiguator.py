#!/usr/bin/env python3
"""Phase 1C — Haiku-disambiguate the 202 ambiguous party-filings.

For each row in case_party_filings tagged 'third_party' or 'ambiguous' with low confidence,
ask Haiku to decide plaintiff/respondent/court/agency/witness.
"""
import argparse, json, os, re, sys, time
import psycopg2, psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


def load_api_key():
    with open("/root/landtek/.env") as f:
        for line in f:
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.strip().split("=", 1)[1]
    return None


PROMPT = """You are a legal-doc party classifier for Philippine civil-procedure files.

Given a document's filename + first 8000 chars of text, decide who filed/issued it relative to the active case (Civil Case 26-360: Patricia Keesey Zschoche [plaintiff] vs Spouses Balane et al [respondents]).

Categories:
  • plaintiff — filed by Patricia Zschoche / Jonathan / Atty. Barandon (counsel for plaintiff)
  • respondent — filed by Balane / Pajarillo / Macale / Atty. Ronald Ramos (counsel for defendants) / their witnesses (Salvador, Princess, Erwin)
  • court — issued by RTC/MTC/CA/SC court (Orders, Notices, Decisions)
  • agency — issued by gov body (ARTA, DILG, RD, BIR, Treasurer, Assessor) — not court
  • witness — sworn affidavit by neutral third party
  • counsel — attorney correspondence between firms (NOT itself a filing)
  • third_party — none of above

Output JSON: {"party": str, "confidence": float (0..1), "reason": str (max 200 chars)}"""


def call_haiku(text, filename, api_key, retries=3):
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    backoff = 3
    for attempt in range(retries):
        try:
            import sys as _sys; _sys.path.insert(0, "/root/landtek")
            from llm_billing import anthropic_call
            msg = anthropic_call(
                client,
                called_from="party_filing_disambiguator",
                purpose="disambiguate_party",
                case_file="MWK-001",
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
                system=PROMPT,
                messages=[{"role": "user", "content": f"FILENAME: {filename or '(empty)'}\n\nTEXT:\n{text[:8000]}"}],
            )
            out = msg.content[0].text.strip()
            m = re.search(r"\{.*\}", out, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0)), None
                except: pass
            return None, "no_json"
        except anthropic.RateLimitError:
            if attempt < retries - 1: time.sleep(backoff); backoff *= 2; continue
            return None, "rate_limit"
        except anthropic.APIStatusError as e:
            if e.status_code in (429, 503, 529) and attempt < retries - 1:
                time.sleep(backoff); backoff *= 2; continue
            return None, f"api_err_{e.status_code}"
        except Exception as e:
            return None, f"err: {str(e)[:80]}"
    return None, "retries_exhausted"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()

    api_key = load_api_key()
    if not api_key:
        sys.exit("FATAL: ANTHROPIC_API_KEY missing")

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    # Pick up: (a) low-confidence third_party/ambiguous cases, AND
    # (b) high-confidence cases where filename strongly suggests a different party
    # (e.g., "Exhibit X" filed by complaint plaintiff but text-scored as agency/respondent;
    #        "ORDER Civil Case ..." should be court, not respondent)
    cur.execute("""
        SELECT cpf.id AS cpf_id, cpf.doc_id, cpf.filing_party, cpf.confidence,
               d.smart_filename, LEFT(d.extracted_text, 8000) AS text
          FROM case_party_filings cpf JOIN documents d ON d.id = cpf.doc_id
         WHERE d.extracted_text IS NOT NULL AND length(d.extracted_text) >= 300
           AND (
              (cpf.filing_party IN ('third_party','ambiguous') AND cpf.confidence < 0.6)
              OR (d.smart_filename ILIKE %s AND cpf.filing_party != 'plaintiff')
              OR (d.smart_filename ILIKE %s AND cpf.filing_party NOT IN ('court','plaintiff'))
           )
         ORDER BY cpf.id LIMIT %s
    """, ('%exhibit%', '%order%civil%case%', args.limit))
    rows = cur.fetchall()
    print(f"  {len(rows)} ambiguous filings to disambiguate")

    fixed = same = err = 0
    new_counts = {}
    for r in rows:
        result, e = call_haiku(r["text"], r["smart_filename"], api_key)
        if e or not result:
            err += 1; continue
        new_party = result.get("party", "third_party")
        new_conf = float(result.get("confidence", 0.5))
        if new_party not in ("plaintiff","respondent","court","agency","witness","counsel","third_party"):
            err += 1; continue
        if new_party == r["filing_party"]:
            same += 1
        else:
            # Resolve any existing collision: another row with same (doc_id, new_party)
            # from a prior haiku run or v1 leftover. Drop it before updating.
            cur.execute("""DELETE FROM case_party_filings
                            WHERE doc_id = %s AND filing_party = %s AND id != %s""",
                        (r["doc_id"], new_party, r["cpf_id"]))
            cur.execute("""UPDATE case_party_filings
                              SET filing_party = %s, confidence = %s,
                                  detection_method = 'haiku_disambig_v1',
                                  notes = COALESCE(notes,'') || ' | haiku: ' || %s
                            WHERE id = %s""",
                        (new_party, new_conf, result.get("reason","")[:300], r["cpf_id"]))
            fixed += 1
            new_counts[new_party] = new_counts.get(new_party, 0) + 1
        if (fixed + same) % 20 == 0:
            print(f"  ... {fixed + same}/{len(rows)} (fixed={fixed} same={same} err={err})")
        time.sleep(0.3)

    print(f"\n  fixed (changed party): {fixed}")
    print(f"  same: {same}")
    print(f"  err: {err}")
    if new_counts:
        print(f"  by new party:")
        for p, n in sorted(new_counts.items(), key=lambda x: -x[1]):
            print(f"    {p}: {n}")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
