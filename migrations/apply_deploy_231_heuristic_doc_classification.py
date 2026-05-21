#!/usr/bin/env python3
"""Deploy 231 — Heuristic doc classification for the 282 unclassified docs.

Per May 21 audit: 282 of 953 docs (30%) have `classification IS NULL`.
This blocks the resolutions table backfill, per-matter dashboards, and bible
generation from finding the right docs by type.

Approach (deterministic, no LLM cost):
  1. Pattern-match smart_filename + first 800 chars of extracted_text against
     a ranked list of (regex → classification) rules.
  2. Most specific patterns win.
  3. If nothing matches, leave NULL (don't pollute with 'Other').

Classifications populated align with existing values in the documents table
(verified via SELECT DISTINCT classification FROM documents):
  Title (TCT/OCT), Affidavit, Judicial Affidavit, Complaint, Court Filing,
  Deed, Special Power of Attorney, Order, Resolution, Reply, Motion, Answer,
  Notice, Memorandum, Demand Letter, Letter, Correspondence,
  Government Submission, Transcript, Tax Document, Email, Other.

Idempotent (only touches NULL classification rows).
"""
import re
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


# Ordered: most-specific first. First match wins.
# Each entry: (compiled regex, classification, match_target)
#   match_target: "fn" = smart_filename only, "text" = first chars of body, "both" = either
def C(pat, cls, target="both", flags=re.IGNORECASE):
    return (re.compile(pat, flags), cls, target)


RULES = [
    # Highly specific filename markers
    C(r"judicial[\s_-]?affidavit", "Judicial Affidavit", "both"),
    C(r"\baffidavit[_\s]*of[_\s]+(?:loss|service|publication|merit|adverse[\s_]?claim|consolidation|confirmation|donation)", "Affidavit", "both"),
    C(r"\baffidavit\b", "Affidavit", "both"),
    C(r"\bdeed[_\s]+of[_\s]+(?:absolute[_\s]+)?sale\b", "Deed", "both"),
    C(r"\bdeed[_\s]+of[_\s]+donation\b", "Deed", "both"),
    C(r"\b(?:deed|sale)\b", "Deed", "fn"),
    C(r"\bspecial[_\s]+power[_\s]+of[_\s]+attorney\b", "Special Power of Attorney", "both"),
    C(r"\bSPA\b", "Special Power of Attorney", "fn"),
    C(r"\brevocation\b", "Special Power of Attorney", "both"),  # SPA revocations
    C(r"\bTCT[_\s]*[-]?\s*T?\s*-?\s*\d+", "Title (TCT/OCT)", "both"),
    C(r"\bOCT[_\s]*[-]?\s*T?\s*-?\s*\d+", "Title (TCT/OCT)", "both"),
    C(r"\b(?:property[_\s]+tree[_\s]+of[_\s]+titles?|title[_\s]+map)\b", "Title (TCT/OCT)", "fn"),
    C(r"\bcomplaint[\s_-]?(?:affidavit)?\b", "Complaint", "both"),
    C(r"\b(?:initial[_\s]+)?draft.*complaint\b", "Complaint", "fn"),
    C(r"\b(?:Hon\.?\s+)?Resolution\b(?!.*PETITION)", "Resolution", "both"),
    C(r"\bresolution\b", "Resolution", "fn"),
    C(r"\border\b", "Order", "fn"),
    C(r"\b(?:hereby\s+)?ordered\b", "Order", "text"),
    C(r"\bmotion[_\s]+(?:for|to)\b", "Motion", "both"),
    C(r"\bpetition\b", "Motion", "fn"),  # Petitions are filed as motions in PH practice
    C(r"\bnotice[_\s]+of[_\s]+(?:pre-?trial|hearing|appearance|filing)\b", "Notice", "both"),
    C(r"\bnotice\b", "Notice", "fn"),
    C(r"\breply\b", "Reply", "fn"),
    C(r"\brejoinder\b", "Reply", "fn"),
    C(r"\bcomment\b.*\bopposition\b", "Reply", "both"),
    C(r"\b(?:formal\s+)?answer\b", "Answer", "fn"),
    C(r"\bmemorandum\b", "Memorandum", "both"),
    C(r"\bmemorandum[_\s]+of[_\s]+agreement\b", "Memorandum", "both"),
    C(r"\b(?:demand|formal[_\s]+demand)[_\s]+letter\b", "Demand Letter", "both"),
    C(r"\bnotice[_\s]+to[_\s]+vacate\b", "Demand Letter", "both"),
    C(r"\btranscript\b", "Transcript", "both"),
    C(r"\b(?:tax\s+amnesty|RPT|real[_\s]+property[_\s]+tax|tax[_\s]+declaration|ARP\b|tax[_\s]+update)", "Tax Document", "both"),
    C(r"\b(?:CSC|DILG|PENRO|DAR|LRA|LMB|BARMM|ARTA|LGU)\b", "Government Submission", "fn"),
    C(r"\bendorsement\b", "Government Submission", "both"),
    C(r"\b(?:OSCA|SCA[\s_-]+)\b", "Government Submission", "fn"),
    C(r"^\s*(?:Fwd|Re|FW)\s*:\s*", "Email", "fn"),  # Forwarded/Reply mail
    C(r"\bletter\b", "Letter", "fn"),
    C(r"\b(?:dear|sincerely|respectfully\s+yours)\b", "Letter", "text"),
    C(r"\bCourt\s+(?:of\s+Appeals|filing|order|decision)\b", "Court Filing", "both"),
    C(r"\bCivil[\s_]+Case\s+No\.?\s*\d", "Court Filing", "both"),
    C(r"\bG\.R\.\s+No\.\s+\d+", "Court Filing", "both"),
]


def classify_doc(filename, text):
    """Apply rules in order; return classification or None."""
    fn = (filename or "")
    body = (text or "")[:800]
    combined = fn + "\n" + body
    for regex, cls, target in RULES:
        if target == "fn":
            if regex.search(fn):
                return cls
        elif target == "text":
            if regex.search(body):
                return cls
        else:  # both
            if regex.search(combined):
                return cls
    return None


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print("Deploy 231 — Heuristic doc classification")
    print("=" * 60)

    cur.execute("""
        SELECT id, smart_filename, COALESCE(extracted_text, '') AS extracted_text
          FROM documents
         WHERE classification IS NULL
         ORDER BY id
    """)
    rows = cur.fetchall()
    print(f"\nScanning {len(rows)} unclassified documents…")

    classified = 0
    by_cls = {}
    still_null = 0

    for r in rows:
        cls = classify_doc(r["smart_filename"], r["extracted_text"])
        if cls:
            cur.execute(
                "UPDATE documents SET classification = %s WHERE id = %s AND classification IS NULL",
                (cls, r["id"]),
            )
            if cur.rowcount > 0:
                classified += 1
                by_cls[cls] = by_cls.get(cls, 0) + 1
        else:
            still_null += 1

    print(f"\n  ✓ {classified} docs classified")
    print(f"  ○ {still_null} docs still NULL — no heuristic matched")
    print()
    print("  Newly-classified counts:")
    for c, n in sorted(by_cls.items(), key=lambda x: -x[1]):
        print(f"    {c:<28s} {n}")

    # Final audit
    print()
    print("=" * 60)
    cur.execute("SELECT COUNT(*) AS n FROM documents WHERE classification IS NULL")
    still_null_final = cur.fetchone()["n"]
    cur.execute("SELECT COUNT(*) AS n FROM documents")
    total = cur.fetchone()["n"]
    pct = 100 * (total - still_null_final) / max(1, total)
    print(f"Final coverage: {total - still_null_final}/{total} documents classified ({pct:.1f}%)")
    print(f"Remaining unclassified: {still_null_final}")
    print()
    print("Residual unclassified docs can be reviewed manually or handled by a")
    print("future Haiku/Gemini classification pass (proposed_changes flow).")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
