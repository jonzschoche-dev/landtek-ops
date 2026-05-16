#!/usr/bin/env python3
"""Self-research for pending_questions — Leo searches the corpus BEFORE asking.

Per feedback_leo_must_self_research: if the answer is derivable from existing
documents, Leo MUST propose an answer first, escalating to Jonathan only if
truly unknown.

For each pending_questions row where status='pending':
  1. Extract keywords from question text (entity names, case numbers, TCTs)
  2. Search documents.extracted_text for those keywords
  3. Pull top 5 docs with relevant excerpts
  4. Call Claude with question + excerpts → likely_answer + confidence
  5. If confidence >= 0.6: UPDATE pending_questions with proposed answer
     + DM Jonathan to confirm
     Note: status stays 'pending' until Jonathan confirms
  6. If confidence < 0.6: leave question for Jonathan to answer cold
"""
import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
import psycopg2
import psycopg2.extras

DSN = dict(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")
JONATHAN_TG_ID = "6513067717"

# Patterns that indicate corpus-derivable subjects
KEYWORD_PATTERNS = [
    re.compile(r"\bCivil Case (?:No\.? )?(\d{2,5}(?:[-/]\d+)?)", re.I),
    re.compile(r"\b(?:TCT|OCT)[-\s]?(?:T[-\s])?(\d{3,6})\b", re.I),
    re.compile(r"\bCTN SL-\d{4}-\d{4}-\d{4}", re.I),
    re.compile(r"\b(?:Atty\.?|Attorney)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", re.I),
    re.compile(r"\b([A-Z][a-z]+ [A-Z][a-z]+ ?[A-Z]?[a-z]*)\b"),  # proper names
]


def _token():
    for l in open("/root/landtek/.env"):
        if l.startswith("TELEGRAM_BOT_TOKEN="):
            return l.split("=", 1)[1].strip()


def tg_send(text, parse_mode=""):
    tok = _token()
    if not tok: return
    data = {"chat_id": JONATHAN_TG_ID, "text": text[:4090]}
    if parse_mode: data["parse_mode"] = parse_mode
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage",
                               data=urllib.parse.urlencode(data).encode(), timeout=10).read()
    except Exception as e:
        print(f"tg fail: {e}", file=sys.stderr)


def extract_search_terms(question_text):
    """Pull out probable search keywords from a question."""
    terms = set()
    for pat in KEYWORD_PATTERNS:
        for m in pat.finditer(question_text):
            term = m.group(0).strip()
            if len(term) >= 4:
                terms.add(term)
    return list(terms)


def search_corpus(cur, terms, case_file=None, limit_per_term=3):
    """Return docs matching any term in their extracted_text."""
    if not terms: return []
    seen = {}
    for t in terms:
        like = f"%{t}%"
        if case_file:
            cur.execute("""
                SELECT id, original_filename, case_file,
                       LEFT(extracted_text, 1500) AS excerpt
                  FROM documents
                 WHERE extracted_text ILIKE %s
                   AND (case_file = %s OR case_file IS NULL OR case_file = 'Unknown')
                 ORDER BY id DESC LIMIT %s
            """, (like, case_file, limit_per_term))
        else:
            cur.execute("""
                SELECT id, original_filename, case_file,
                       LEFT(extracted_text, 1500) AS excerpt
                  FROM documents
                 WHERE extracted_text ILIKE %s
                 ORDER BY id DESC LIMIT %s
            """, (like, limit_per_term))
        for r in cur.fetchall():
            seen[r["id"]] = r
    return list(seen.values())


def call_claude_research(question, doc_excerpts):
    import anthropic
    api_key = None
    for l in open("/root/landtek/.env"):
        if l.startswith("ANTHROPIC_API_KEY="):
            api_key = l.split("=", 1)[1].strip()
    client = anthropic.Anthropic(api_key=api_key, timeout=60)

    corpus = "\n\n".join(
        f"--- DOC {d['id']} ({d['original_filename'] or 'unnamed'}, case={d['case_file']}) ---\n{d['excerpt']}"
        for d in doc_excerpts[:8]
    )
    prompt = f"""You are a legal-research assistant. Below is a question and excerpts from documents in the corpus.

QUESTION: {question}

DOCUMENT EXCERPTS:
{corpus}

Based ONLY on these excerpts, can you answer the question? Return JSON:

{{
  "answer": "<your proposed answer, citing DOC ids — or empty string if you can't answer>",
  "confidence": <float 0..1>,
  "citations": ["DOC <id>", ...],
  "reasoning": "<one-sentence why you're confident or not>"
}}

If excerpts don't contain enough information, return confidence < 0.4 and empty answer.
Output ONLY the JSON. No prose."""

    resp = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = "".join(b.text for b in resp.content if hasattr(b, "text"))
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    try:
        return json.loads(raw)
    except Exception:
        return {"answer": "", "confidence": 0.0, "citations": [], "reasoning": "parse failure"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default=None, help="Limit to one case_file")
    ap.add_argument("--question-id", type=int, default=None, help="Process just one question")
    args = ap.parse_args()

    conn = psycopg2.connect(**DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    query = """
        SELECT id, case_file, question, context, source, asked_of_telegram_id
          FROM pending_questions
         WHERE status = 'pending'
    """
    params = []
    if args.case:
        query += " AND case_file = %s"
        params.append(args.case)
    if args.question_id:
        query += " AND id = %s"
        params.append(args.question_id)
    query += " ORDER BY id"
    cur.execute(query, params)
    questions = cur.fetchall()
    print(f"  {len(questions)} pending question(s) to research")

    for q in questions:
        print(f"\n  [Q#{q['id']}] {q['question'][:80]}...")
        terms = extract_search_terms(q["question"])
        if not terms:
            print(f"    no extractable keywords, skip")
            continue
        print(f"    terms: {terms[:8]}")

        docs = search_corpus(cur, terms, case_file=q["case_file"])
        print(f"    found {len(docs)} candidate docs")
        if not docs:
            continue

        result = call_claude_research(q["question"], docs)
        conf = result.get("confidence", 0.0)
        ans = result.get("answer", "")
        cit = result.get("citations", [])
        reason = result.get("reasoning", "")
        print(f"    confidence={conf:.2f}, citations={cit[:3]}")

        if conf >= 0.6 and ans:
            # Update the question with proposed answer (status remains 'pending'
            # until Jonathan confirms; reuse the 'answer' column as a 'proposed_answer')
            cur.execute("""
                UPDATE pending_questions
                   SET answer = %s,
                       source = source || ' + self_research_v1',
                       context = COALESCE(context || E'\\n', '') || %s
                 WHERE id = %s
            """, (ans, f"PROPOSED via self_research (conf={conf:.2f}): {ans[:300]}", q["id"]))
            citations_str = ", ".join(cit[:5])
            tg_send(
                f"🔎 Self-research on Q#{q['id']} (confidence {conf:.0%})\n\n"
                f"<b>Question</b>: {q['question'][:200]}\n\n"
                f"<b>Leo's proposed answer</b>: {ans[:1500]}\n\n"
                f"Citations: {citations_str}\n"
                f"Reasoning: {reason[:200]}\n\n"
                f"👉 Confirm 'yes' / correct / add detail.",
                parse_mode="HTML"
            )
        else:
            print(f"    not confident enough — left for Jonathan ({reason})")

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
