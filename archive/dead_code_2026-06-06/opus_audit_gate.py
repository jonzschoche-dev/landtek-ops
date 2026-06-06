#!/usr/bin/env python3
"""opus_audit_gate — comprehensive pre-delivery Opus validation (deploy_161).

Per Jonathan 2026-05-17 directive: STOP final PDF. Opus audits the architecture,
not rewrites it. Six audit areas:

  1. Post-Haiku tagging validation (distribution + 20 promoted samples + 20 questionable)
  2. Estate-first hierarchy check (no improper CV-26360 anchoring)
  3. Asset-separation check (CV-6839 ≠ TCT-4497 — strict title-set boundary)
  4. 2025 + 2026 narrative audit
  5. Cross-reference index spot-check on high-risk entries
  6. Forward-risk memo

Output:
  /root/landtek/drafts/Opus_Case_Bible_Audit_Gate_May2026.md (full audit)
  + terminal print of A/B/C/D summary
"""
import json
import random
import re
import sys
from pathlib import Path
sys.path.insert(0, "/root/landtek")
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
BIBLE_PATH = "/root/landtek/drafts/bible_OMNIBUS_MWK-001_2026-05-17.md"
AUDIT_OUT = "/root/landtek/drafts/Opus_Case_Bible_Audit_Gate_May2026.md"

# Asset separation: CV-6839 ⊃ {agrarian/CARP titles}; TCT-4497 ⊃ {separate chain}
CV6839_TITLE_SET = {"T-30681", "T-30682", "T-30683", "T-4494",
                    "T-4501", "T-4502", "T-4503", "T-14"}
T4497_CHAIN = {"T-4497", "T-32916", "T-32917", "T-31298",
               "T-38838", "T-47655", "T-47656", "T-47657",
               "T-48335", "T-48336", "T-49037", "T-49060", "T-49061", "T-49062",
               "T-52354", "T-52536", "T-52537", "T-52538", "T-52539", "T-52540",
               "T-079-2021002126", "T-079-2021002127"}
# Keywords that should ONLY appear with CV-6839 if asset-separation holds
CV6839_KEYWORDS = ["landbank", "land bank", "carp", "dar ", "just compensation",
                   "agrarian", "agrarian reform"]


def db_connect():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def get_distribution(cur):
    cur.execute("""
        WITH expanded AS (
          SELECT unnest(matter_codes) AS mc FROM client_history WHERE case_file='MWK-001'
        )
        SELECT mc, COUNT(*) AS n FROM expanded GROUP BY mc ORDER BY n DESC
    """)
    return cur.fetchall()


def sample_promotions(cur, n=20):
    """20 sample events that got promoted from MWK-ESTATE to specific matters
    (i.e., matter_codes != ['MWK-ESTATE'] in current state)."""
    cur.execute("""
        SELECT h.id, h.matter_codes, h.title_refs, h.event_kind, h.what_summary,
               COALESCE(h.event_date, h.date_executed, h.date_filed, h.date_received) AS dt,
               d.classification AS doc_classification,
               d.smart_filename AS doc_smart_filename,
               LEFT(d.extracted_text, 400) AS doc_snippet,
               t.amount AS tx_amount, t.category AS tx_category, t.counterparty AS tx_counterparty,
               g.subject AS gmail_subject
          FROM client_history h
          LEFT JOIN documents d ON h.source_table='documents' AND h.source_id=d.id::text
          LEFT JOIN transactions t ON h.source_table='transactions' AND h.source_id=t.id::text
          LEFT JOIN gmail_messages g ON h.source_table='gmail_messages' AND h.source_id=g.id::text
         WHERE h.case_file='MWK-001'
           AND NOT (h.matter_codes = ARRAY['MWK-ESTATE']::text[])
         ORDER BY random() LIMIT %s
    """, (n,))
    return cur.fetchall()


def cross_contamination(cur):
    """Find CV-6839-tagged events that touch T-4497 chain, or TCT4497-tagged
    events that mention CV6839 keywords (landbank/CARP/DAR/just compensation)."""
    findings = {"cv6839_touches_t4497": [], "tct4497_touches_cv6839": []}

    # CV-6839 events that mention T-4497 chain titles
    cur.execute("""
        SELECT h.id, h.title_refs, h.what_summary, h.matter_codes,
               COALESCE(h.event_date, h.date_executed) AS dt,
               d.classification, d.smart_filename
          FROM client_history h
          LEFT JOIN documents d ON h.source_table='documents' AND h.source_id=d.id::text
         WHERE 'MWK-CV6839' = ANY(h.matter_codes)
           AND h.title_refs && %s::text[]
         ORDER BY dt
    """, (list(T4497_CHAIN),))
    findings["cv6839_touches_t4497"] = cur.fetchall()

    # TCT-4497-tagged events that smell like CV-6839 (DAR / Landbank / etc.)
    cur.execute(f"""
        SELECT h.id, h.title_refs, h.what_summary, h.matter_codes,
               COALESCE(h.event_date, h.date_executed) AS dt,
               d.classification, d.smart_filename,
               LEFT(d.extracted_text, 200) AS doc_snippet
          FROM client_history h
          LEFT JOIN documents d ON h.source_table='documents' AND h.source_id=d.id::text
         WHERE 'MWK-TCT4497' = ANY(h.matter_codes)
           AND (
             {' OR '.join(f"d.extracted_text ILIKE '%%{k}%%'" for k in CV6839_KEYWORDS)}
             OR {' OR '.join(f"h.what_summary ILIKE '%%{k}%%'" for k in CV6839_KEYWORDS)}
           )
         ORDER BY dt
    """)
    findings["tct4497_touches_cv6839"] = cur.fetchall()

    # Also any event tagged TCT4497 whose title_refs include a CV-6839 title
    cur.execute("""
        SELECT h.id, h.title_refs, h.matter_codes, h.what_summary,
               COALESCE(h.event_date, h.date_executed) AS dt
          FROM client_history h
         WHERE 'MWK-TCT4497' = ANY(h.matter_codes)
           AND h.title_refs && %s::text[]
    """, (list(CV6839_TITLE_SET),))
    findings["tct4497_titlerefs_in_cv6839_set"] = cur.fetchall()
    return findings


def extract_section(md, start_pat, end_pat):
    s = re.search(start_pat, md, re.MULTILINE)
    if not s: return ""
    rest = md[s.start():]
    e = re.search(end_pat, rest, re.MULTILINE)
    return rest[:e.start()] if e else rest[:8000]


def build_audit_payload(cur):
    md = Path(BIBLE_PATH).read_text()
    dist = get_distribution(cur)
    promotions = sample_promotions(cur, 20)
    contam = cross_contamination(cur)
    n2025 = extract_section(md, r'^### 2025 — Annual Narrative Summary', r'\*\*Detailed Event Log:\*\*')
    n2026 = extract_section(md, r'^### 2026 — Annual Narrative Summary', r'\*\*Detailed Event Log:\*\*')
    proj = extract_section(md, r'^## Next Projected Events', r'^## Critical Open Deadlines')

    # Cross-ref entries to spot-check
    xref_entries = {}
    for label in ["T-4497", "T-30681", "T-30682", "T-30683", "T-4501", "T-4502", "T-4503",
                  "MWK-ARTA-0690", "MWK-ARTA-0747", "MWK-ARTA-0792",
                  "MWK-ARTA-1210", "MWK-ARTA-1321", "MWK-ARTA-1891"]:
        # By-Title section uses `### T-NNNN` headers; By-Matter section uses shorter tag
        if label.startswith("T-"):
            sec = extract_section(md, rf'^### {re.escape(label)} ', r'^### ')
        else:
            short = label.replace("MWK-", "")
            sec = extract_section(md, rf'^### {re.escape(short)} ', r'^### ')
        if sec:
            xref_entries[label] = sec[:1500]

    return dist, promotions, contam, n2025, n2026, proj, xref_entries


def format_event(e):
    """Compact one-line event repr for the prompt."""
    bits = [f"event#{e['id']}",
            f"date={e.get('dt') or '—'}",
            f"matter_codes={e['matter_codes']}"]
    if e.get("title_refs"):
        bits.append(f"titles={e['title_refs']}")
    if e.get("doc_classification"):
        bits.append(f"cls={e['doc_classification']!r}")
    if e.get("doc_smart_filename"):
        bits.append(f"file={e['doc_smart_filename'][:60]!r}")
    if e.get("doc_snippet"):
        s = e["doc_snippet"].strip()[:180].replace("\n", " ")
        bits.append(f"text={s!r}")
    if e.get("tx_amount") is not None:
        bits.append(f"tx=P{e['tx_amount']:,.0f} {e.get('tx_category','')} cp={e.get('tx_counterparty','')!r}")
    if e.get("gmail_subject"):
        bits.append(f"gmail_subj={e['gmail_subject'][:80]!r}")
    if e.get("what_summary"):
        bits.append(f"summary={e['what_summary'][:120]!r}")
    return "  - " + " | ".join(bits)


def main():
    cur = db_connect()
    dist, promotions, contam, n2025, n2026, proj, xref_entries = build_audit_payload(cur)

    # Build prompt
    parts = []
    parts.append("# OPUS AUDIT GATE — Master Case Bible (Heirs of MWK)\n")
    parts.append("## STRICT MANDATE\n")
    parts.append("Audit the architecture. DO NOT rewrite anything. Flag errors, "
                  "misclassifications, over-anchoring, unsafe conclusions. Lead with "
                  "the highest-risk findings.\n\n")
    parts.append("## CRITICAL DOMAIN RULES YOU MUST ENFORCE\n")
    parts.append("- **MWK-001 / MWK-ESTATE is the TOP-LEVEL parent.** CV-26360, CV-6839, "
                  "TCT-4497, ARTA matters, guardianship, and tax/title administration are "
                  "SIBLING subtracks of the estate — NOT subparts of the Balane case (CV-26360).\n")
    parts.append("- **CV-6839 is the LandBank/DAR/CARP just-compensation track** and applies "
                  "ONLY to this title set:\n"
                  "  {T-30681, T-30682, T-30683, T-4494, T-4501, T-4502, T-4503, T-14}\n")
    parts.append("- **TCT-4497 is a SEPARATE asset chain** — the contested-Balane chain "
                  "(T-4497 → 32916/32917/31298 → derivatives → T-079-2021002126).\n")
    parts.append("- **Any cross-contamination** (CV-6839 tag on T-4497-chain event, or "
                  "TCT-4497 tag on CARP/Landbank-related event) is a defect.\n")
    parts.append("- **Cesar dela Fuente died 21 June 2017** (doc#364, LandBank filing in "
                  "CV-6839). Any post-2017 attribution to him is impossible.\n")
    parts.append("- **Patricia Keesee Zschoche** (caption spelling — note 'Keesee' not 'Keesey').\n")
    parts.append("- **CV-26360 venue: RTC Camarines Norte Branch 64** (not MTC Mercedes).\n\n")

    parts.append("## SECTION 1 — POST-HAIKU TAG DISTRIBUTION\n")
    for r in dist:
        parts.append(f"  {r['mc']:30s}  {r['n']:>5d} events")
    parts.append("\n")

    parts.append("## SECTION 2 — 20 RANDOMLY-SAMPLED PROMOTED EVENTS\n")
    parts.append("(For each, judge whether the promotion is supported by the text signal.)\n")
    for e in promotions:
        parts.append(format_event(e))
    parts.append("\n")

    parts.append("## SECTION 3 — CROSS-CONTAMINATION FINDINGS\n")
    parts.append(f"### 3a. Events tagged MWK-CV6839 whose title_refs include T-4497 chain "
                  f"({len(contam['cv6839_touches_t4497'])} events)\n")
    for e in contam["cv6839_touches_t4497"][:30]:
        parts.append(f"  - event#{e['id']} {e.get('dt') or '?'} title_refs={e['title_refs']} "
                      f"summary={(e.get('what_summary') or '')[:120]!r}")
    parts.append(f"\n### 3b. Events tagged MWK-TCT4497 whose text mentions LandBank/CARP/DAR "
                  f"({len(contam['tct4497_touches_cv6839'])} events)\n")
    for e in contam["tct4497_touches_cv6839"][:30]:
        parts.append(f"  - event#{e['id']} {e.get('dt') or '?'} "
                      f"cls={e.get('classification')!r} file={(e.get('smart_filename') or '')[:50]!r} "
                      f"snippet={(e.get('doc_snippet') or '')[:120]!r}")
    parts.append(f"\n### 3c. Events tagged MWK-TCT4497 whose title_refs include CV-6839 set "
                  f"({len(contam['tct4497_titlerefs_in_cv6839_set'])} events)\n")
    for e in contam["tct4497_titlerefs_in_cv6839_set"][:30]:
        parts.append(f"  - event#{e['id']} {e.get('dt') or '?'} title_refs={e['title_refs']}")
    parts.append("\n")

    parts.append("## SECTION 4 — 2025 NARRATIVE\n")
    parts.append(n2025[:4000])
    parts.append("\n\n## SECTION 5 — 2026 NARRATIVE\n")
    parts.append(n2026[:4000])
    parts.append("\n\n## SECTION 6 — FORWARD PROJECTED EVENTS\n")
    parts.append(proj[:2500])
    parts.append("\n\n## SECTION 7 — CROSS-REF INDEX SPOT-CHECK\n")
    for label, content in xref_entries.items():
        parts.append(f"\n### {label}\n{content[:1500]}")
    parts.append("\n\n## DELIVERABLE\n")
    parts.append("Produce a structured audit. Use these EXACT headings:\n"
                  "  A. POST-HAIKU TAG VALIDATION — soundness + 20-sample assessment + "
                  "20 lowest-confidence promotions you'd second-guess\n"
                  "  B. ESTATE-FIRST HIERARCHY CHECK — flag every place a non-CV26360 event "
                  "is improperly narrated through the lens of the Balane case\n"
                  "  C. ASSET-SEPARATION FINDINGS — verdict on each cross-contamination row\n"
                  "  D. 2025 NARRATIVE AUDIT — statements to remove / soften / cite / "
                  "decouple / verify\n"
                  "  E. 2026 NARRATIVE AUDIT — same\n"
                  "  F. CROSS-REF INDEX SPOT-CHECK — anomalies + verification asks\n"
                  "  G. FORWARD-RISK MEMO — safe-now / verify-first / do-not-rely / "
                  "top-5-corrections-before-PDF\n"
                  "  H. GO/NO-GO VERDICT — one line\n")

    user_msg = "\n".join(parts)
    print(f"Audit payload: {len(user_msg):,} chars")

    import anthropic
    from landtek_core import get
    from llm_billing import anthropic_call
    api_key = get("ANTHROPIC_API_KEY") or open("/root/landtek/.env").read().split("ANTHROPIC_API_KEY=")[1].split("\n")[0].strip()
    client = anthropic.Anthropic(api_key=api_key)
    from opus_advisor import OPUS_SYSTEM

    msg = anthropic_call(
        client,
        called_from="opus_audit_gate",
        purpose="pre_delivery_full_audit",
        case_file="MWK-001",
        model="claude-opus-4-7",
        max_tokens=4096,
        system=[{"type":"text", "cache_control":{"type":"ephemeral","ttl":"1h"}, "text": OPUS_SYSTEM}],
        messages=[{"role":"user", "content": user_msg}],
    )
    response = msg.content[0].text.strip()

    # Save full audit
    Path(AUDIT_OUT).write_text(
        f"# Opus Case Bible Audit Gate — May 2026\n\n"
        f"_Generated 2026-05-17 from bible v3 (post-Haiku tagger pass)._\n\n"
        f"## Source\n  - Bible: {BIBLE_PATH}\n"
        f"  - Audit payload size: {len(user_msg):,} chars\n"
        f"  - Tokens: {msg.usage.input_tokens}in / {msg.usage.output_tokens}out\n"
        f"  - Cost: ${(msg.usage.input_tokens * 15 + msg.usage.output_tokens * 75) / 1_000_000:.3f}\n\n"
        f"---\n\n{response}\n"
    )

    # Parse sections for terminal summary
    print("\n" + "═"*80)
    print("A. POST-HAIKU TAG DISTRIBUTION")
    print("═"*80)
    for r in dist:
        print(f"  {r['mc']:30s}  {r['n']:>5d} events")
    print(f"\n  Cross-contamination counts:")
    print(f"    CV-6839 → T-4497 chain: {len(contam['cv6839_touches_t4497'])} events")
    print(f"    TCT-4497 → CARP/Landbank text: {len(contam['tct4497_touches_cv6839'])} events")
    print(f"    TCT-4497 → CV-6839 title set: {len(contam['tct4497_titlerefs_in_cv6839_set'])} events")

    # Extract Section C (asset-separation) and G/H (top-5 + verdict) for terminal
    def extract_audit_section(resp, header):
        m = re.search(rf'^\s*##?\s*{re.escape(header)}', resp, re.MULTILINE | re.IGNORECASE)
        if not m: return ""
        rest = resp[m.start():]
        n = re.search(r'^\s*##?\s*[A-Z]\.\s', rest[len(header)+5:], re.MULTILINE)
        return rest[:n.start() + len(header) + 5] if n else rest[:3000]

    sec_c = extract_audit_section(response, "C.")
    sec_g = extract_audit_section(response, "G.")
    sec_h = extract_audit_section(response, "H.")

    print("\n" + "═"*80)
    print("B. ASSET CROSS-CONTAMINATION FINDINGS (Opus verdict)")
    print("═"*80)
    print(sec_c if sec_c else "(verdict text not extractable — see full audit)")

    print("\n" + "═"*80)
    print("C. TOP-5 'DO NOT TRUST YET' ISSUES + FORWARD-RISK")
    print("═"*80)
    print(sec_g if sec_g else "(verdict text not extractable — see full audit)")

    print("\n" + "═"*80)
    print("D. GO/NO-GO VERDICT")
    print("═"*80)
    print(sec_h if sec_h else "(verdict text not extractable — see full audit)")

    print(f"\n→ Full audit saved to {AUDIT_OUT}")
    print(f"  Cost: ${(msg.usage.input_tokens * 15 + msg.usage.output_tokens * 75) / 1_000_000:.3f}")


if __name__ == "__main__":
    main()
