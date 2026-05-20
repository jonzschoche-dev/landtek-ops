#!/usr/bin/env python3
"""forensic_agent — ELITE_FORENSIC_LAND_TITLE agent for MWK-001 case work.

Per Jonathan 2026-05-20: a specialized forensic agent that produces
partner-grade structured analysis (sections I-VII) for any matter,
with Opus 4.7, persistent Evidence_Corpus_Map.md, and citation hygiene.

System prompt: /root/landtek/prompts/forensic_land_title.md
Corpus pulled from: matters · documents · client_history · chat_notes ·
                    entities · case_deadlines · calendar_events · title_chain
Persistent state: /root/landtek/drafts/Evidence_Corpus_Map.md
Output: /root/landtek/drafts/forensic_<matter>_<date>.md  (+ PDF + ops send)

Cost: ~$2-3 per Opus 4.7 run with 1h prompt cache.

Usage:
  python3 forensic_agent.py --matter MWK-CV26360                 # full review
  python3 forensic_agent.py --matter MWK-CV26360 --new-doc 959   # incremental
  python3 forensic_agent.py --matter MWK-CV26360 --no-send       # local-only
  python3 forensic_agent.py --matter MWK-CV26360 --validate-citations  # post-process
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/root/landtek")

with open("/root/landtek/.env") as f:
    for line in f:
        if line.startswith("ANTHROPIC_API_KEY="):
            os.environ.setdefault("ANTHROPIC_API_KEY", line.strip().split("=", 1)[1])

import psycopg2
import psycopg2.extras
import anthropic
from llm_billing import anthropic_call

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
PROMPT_PATH = Path("/root/landtek/prompts/forensic_land_title.md")
ECM_PATH = Path("/root/landtek/drafts/Evidence_Corpus_Map.md")
DRAFTS_DIR = Path("/root/landtek/drafts")


def _load_token():
    with open("/root/landtek/.env") as f:
        for line in f:
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                return line.strip().split("=", 1)[1]


# ─── CORPUS LOADER ───────────────────────────────────────────────────────

def load_matter_corpus(cur, matter_code, related_matters=None):
    """Pull the full forensic context for the named matter."""
    related_matters = related_matters or []

    cur.execute("""
        SELECT * FROM matters WHERE matter_code = %s
    """, (matter_code,))
    matter = cur.fetchone()

    # Related matters (e.g., CV-26360 + GUARDIANSHIP + TCT4497)
    if related_matters:
        cur.execute("""
            SELECT matter_code, title, current_stage, next_event, court_or_agency,
                   docket_number, lead_counsel, stage_notes
              FROM matters WHERE matter_code = ANY(%s)
        """, (related_matters,))
        related = cur.fetchall()
    else:
        related = []

    # Documents tagged to this matter
    cur.execute("""
        SELECT id, doc_date_norm, classification, execution_status,
               COALESCE(smart_filename, document_title, original_filename) AS name,
               LEFT(COALESCE(extracted_text,''), 1500) AS excerpt
          FROM documents
         WHERE matter_code = %s
         ORDER BY doc_date_norm DESC NULLS LAST LIMIT 30
    """, (matter_code,))
    docs = cur.fetchall()

    # Title chain for the case_file
    case_file = matter["case_file"] if matter else "MWK-001"
    cur.execute("""
        SELECT parent_title, child_title, relationship, provenance_level
          FROM title_chain WHERE case_file = %s
         ORDER BY parent_title, child_title LIMIT 50
    """, (case_file,))
    chain = cur.fetchall()

    # Key instruments
    cur.execute("""
        SELECT parent_tct_number, instrument_type, entry_date,
               executor_full_name, authority_instrument_ref, authority_date
          FROM instruments_on_title
         WHERE parent_tct_number IN ('T-4497','T-32916','T-32917','T-52540','T-079-2021002126')
         ORDER BY entry_date NULLS LAST LIMIT 25
    """)
    instruments = cur.fetchall()

    # Client history events tagged to the matter
    cur.execute("""
        SELECT event_date, event_kind, LEFT(what_summary, 200) AS summary, citation_ref, provenance
          FROM client_history
         WHERE %s = ANY(matter_codes)
            OR matter_code = %s
         ORDER BY event_date DESC NULLS LAST LIMIT 25
    """, (matter_code, matter_code))
    history = cur.fetchall()

    # Recent chat_notes (past 30 days, matter or case)
    cur.execute("""
        SELECT id, created_at::date AS d, sender_name, LEFT(content, 300) AS content
          FROM chat_notes
         WHERE created_at > NOW() - INTERVAL '30 days'
           AND (content ILIKE %s OR related_case = %s)
         ORDER BY created_at DESC LIMIT 20
    """, (f"%{matter_code}%", case_file))
    notes = cur.fetchall()

    # Counsel / key entities for this case
    cur.execute("""
        SELECT id, canonical_name, role, affiliation
          FROM entities
         WHERE canonical_id IS NULL
           AND (role ILIKE '%counsel%' OR role ILIKE '%plaintiff%' OR role ILIKE '%administrator%'
                OR canonical_name ILIKE 'atty.%' OR canonical_name ILIKE '%municipal%'
                OR canonical_name ILIKE '%mayor%')
         ORDER BY mentions_count DESC LIMIT 15
    """)
    actors = cur.fetchall()

    # Deadlines + calendar
    cur.execute("""
        SELECT id, title, due_date, status, assigned_to FROM case_deadlines
         WHERE case_file = %s AND (status='pending' OR due_date >= CURRENT_DATE - 30)
         ORDER BY due_date LIMIT 10
    """, (case_file,))
    deadlines = cur.fetchall()

    cur.execute("""
        SELECT id, title, start_at, location FROM calendar_events
         WHERE related_case ILIKE %s AND start_at >= NOW() - INTERVAL '7 days'
         ORDER BY start_at LIMIT 10
    """, (f"%{case_file}%",))
    cal = cur.fetchall()

    return {
        "matter": dict(matter) if matter else None,
        "related_matters": [dict(r) for r in related],
        "documents": [dict(d) for d in docs],
        "title_chain": [dict(c) for c in chain],
        "instruments": [dict(i) for i in instruments],
        "history": [dict(h) for h in history],
        "chat_notes": [dict(n) for n in notes],
        "actors": [dict(a) for a in actors],
        "deadlines": [dict(d) for d in deadlines],
        "calendar": [dict(c) for c in cal],
    }


def render_corpus_for_opus(corpus, new_doc_ids=None):
    """Render the corpus as a human-readable text payload for Opus."""
    new_doc_ids = new_doc_ids or []
    parts = []

    m = corpus["matter"] or {}
    parts.append(f"━━ MATTER: {m.get('matter_code','?')} ━━")
    parts.append(f"Title: {m.get('title','?')}")
    parts.append(f"Status: {m.get('status','?')} · Current stage: {m.get('current_stage','?')}")
    parts.append(f"Court / agency: {m.get('court_or_agency','(unset)')}")
    parts.append(f"Docket: {m.get('docket_number','(unset)')}")
    parts.append(f"Lead counsel: {m.get('lead_counsel','(unset)')}")
    parts.append(f"Next event: {m.get('next_event','(unset)')}")
    parts.append(f"Stage notes: {(m.get('stage_notes') or '(none)')[:400]}")
    parts.append("")

    if corpus["related_matters"]:
        parts.append(f"━━ RELATED ACTIVE MATTERS (same case file) ━━")
        for r in corpus["related_matters"]:
            parts.append(f"  • {r['matter_code']}: {r['title']}")
            parts.append(f"      stage={r.get('current_stage')} · counsel={r.get('lead_counsel') or '(unset)'}")
            parts.append(f"      next={r.get('next_event','(unset)')[:120]}")
        parts.append("")

    parts.append(f"━━ TITLE CHAIN ({len(corpus['title_chain'])} edges) ━━")
    for c in corpus["title_chain"][:40]:
        parts.append(f"  {c['parent_title']} → {c['child_title']} [{c['provenance_level']}]")
    parts.append("")

    parts.append(f"━━ KEY INSTRUMENTS (Cesar dela Fuente + chain spine) ━━")
    for i in corpus["instruments"]:
        ex = (i.get("executor_full_name") or "").strip()
        parts.append(f"  [{i.get('entry_date','??')}] {i.get('parent_tct_number','?')} · {i.get('instrument_type','?')} · executor={ex or '(unknown)'}")
    parts.append("")

    parts.append(f"━━ DOCUMENTS TAGGED TO MATTER ({len(corpus['documents'])}) ━━")
    for d in corpus["documents"]:
        new_tag = " [NEW]" if d["id"] in new_doc_ids else ""
        parts.append(f"  [doc#{d['id']}{new_tag}] {d.get('doc_date_norm') or '(undated)'} · {d.get('classification') or 'Other'} · {(d.get('name') or '(unnamed)')[:60]}")
        if d.get("excerpt"):
            parts.append(f"      excerpt: { ' '.join(d['excerpt'].split())[:500] }")
    parts.append("")

    parts.append(f"━━ CLIENT HISTORY EVENTS ({len(corpus['history'])}) ━━")
    for h in corpus["history"]:
        parts.append(f"  [{h.get('event_date','??')}] {h.get('event_kind','?')} — {h.get('summary','')[:200]}")
    parts.append("")

    parts.append(f"━━ RECENT CHAT NOTES (past 30d, matter-related) ━━")
    for n in corpus["chat_notes"][:10]:
        parts.append(f"  [{n.get('d','?')}] {n.get('sender_name','?')}: {(n.get('content') or '')[:250]}")
    parts.append("")

    parts.append(f"━━ KEY ACTORS ━━")
    for a in corpus["actors"][:15]:
        parts.append(f"  • {a['canonical_name']} — role: {a.get('role') or '(unset)'} — affiliation: {(a.get('affiliation') or '(unset)')[:60]}")
    parts.append("")

    parts.append(f"━━ PENDING DEADLINES + CALENDAR ━━")
    for d in corpus["deadlines"]:
        parts.append(f"  [deadline #{d['id']}] {d['due_date']} ({d['status']}) — {d['title'][:90]}")
    for c in corpus["calendar"]:
        parts.append(f"  [event #{c['id']}] {c['start_at']} — {c['title']}")

    return "\n".join(parts)


# ─── EVIDENCE CORPUS MAP ──────────────────────────────────────────────────

def load_ecm():
    if ECM_PATH.exists():
        return ECM_PATH.read_text()
    return "# Evidence Corpus Map — MWK-001 / CV-26360\n\n*(empty — first run will populate)*\n"


def update_ecm_post_run(corpus, opus_output):
    """Extract or append a fresh Evidence Corpus Map after the agent runs.
    For v1: prepend a timestamped snippet derived from the agent's §IV table."""
    section_iv = ""
    m = re.search(r"#+\s*IV\..*?(?=\n#+\s*V\.)", opus_output, re.DOTALL)
    if m:
        section_iv = m.group(0)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    entry = (
        f"## Update {today}\n\n"
        f"Matter: {(corpus.get('matter') or {}).get('matter_code','?')}\n\n"
        f"{section_iv or '*(no §IV captured)*'}\n\n---\n\n"
    )
    existing = load_ecm()
    # Keep the header + insert update at top of body
    if existing.startswith("# "):
        header_end = existing.find("\n\n", 0)
        header, body = existing[:header_end+2], existing[header_end+2:]
    else:
        header, body = "# Evidence Corpus Map — MWK-001 / CV-26360\n\n", existing
    ECM_PATH.write_text(header + entry + body)


# ─── CITATION VALIDATOR (Phase 3 integration) ─────────────────────────────

KNOWN_CASES_PATH = Path("/root/landtek/prompts/known_ph_sc_cases.md")

def load_known_cases() -> set[str]:
    """Read prompts/known_ph_sc_cases.md — list of verified real PH SC cases.
    Each line ":  ─ Case Name v. Other (citation) — doctrine notes".
    Returns the lowercase case-name set."""
    if not KNOWN_CASES_PATH.exists():
        return set()
    text = KNOWN_CASES_PATH.read_text().lower()
    # Crude — pull out "X v. Y" patterns
    pat = re.compile(r"([a-z][\w\.'\-]+(?:\s+(?:de\s+la\s+|de\s+|del\s+|of\s+|and\s+)?[\w\.'\-]+){0,5})\s+v\.\s+([a-z][\w\.'\-]+(?:\s+(?:de\s+la\s+|de\s+|del\s+|of\s+|and\s+)?[\w\.'\-]+){0,5})", re.IGNORECASE)
    return {m.group(0).strip().lower() for m in pat.finditer(text)}


def validate_citations_in_text(text: str) -> tuple[str, list[str]]:
    """Find every 'X v. Y' citation in `text`, validate against the known list,
    annotate unknowns with [Citation pending verification by counsel] inline.
    Returns (annotated_text, list_of_unverified)."""
    known = load_known_cases()
    if not known:
        return text, []  # no list — pass through

    # Match italicized or plain "X v. Y" / "X vs. Y" patterns
    pat = re.compile(
        r"(\b[A-Z][\w\.'\-]+(?:\s+(?:de\s+la|de|del|of|and|y)?\s*[A-Z\w\.'\-]+){0,5})\s+(?:v\.|vs\.|v )\s+([A-Z][\w\.'\-]+(?:\s+(?:de\s+la|de|del|of|and|y)?\s*[A-Z\w\.'\-]+){0,5})"
    )
    unverified = []
    def _annot(m):
        full = m.group(0)
        if full.lower() in known:
            return full
        # Already-flagged? skip
        if "[Citation pending verification" in text[max(0, m.start()-30):m.end()+30]:
            return full
        unverified.append(full)
        return f"{full} *[Citation pending verification by counsel — Atty. Barandon to confirm]*"
    annotated = pat.sub(_annot, text)
    return annotated, list(dict.fromkeys(unverified))


# ─── MAIN ────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matter", required=True, help="matter_code, e.g. MWK-CV26360")
    ap.add_argument("--new-doc", type=int, nargs="*", default=None,
                    help="Doc id(s) to flag as NEW in the corpus payload")
    ap.add_argument("--related", nargs="*", default=None,
                    help="Other matter_codes to include in the context")
    ap.add_argument("--no-send", action="store_true",
                    help="Don't render PDF or send to ops")
    ap.add_argument("--max-output-tokens", type=int, default=4500)
    ap.add_argument("--skip-citation-validate", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Default related matters for MWK
    related = args.related
    if related is None and args.matter.startswith("MWK"):
        related = ["MWK-CV26360", "MWK-GUARDIANSHIP", "MWK-TCT4497", "MWK-ESTATE"]
        related = [r for r in related if r != args.matter]

    corpus = load_matter_corpus(cur, args.matter, related_matters=related)
    if not corpus["matter"]:
        sys.exit(f"matter {args.matter} not found")

    corpus_text = render_corpus_for_opus(corpus, new_doc_ids=args.new_doc or [])
    ecm = load_ecm()
    system_prompt = PROMPT_PATH.read_text()

    new_doc_count = len(args.new_doc) if args.new_doc else 0
    user_msg = (
        f"━━ EVIDENCE CORPUS MAP (current state, persistent across runs) ━━\n\n"
        f"{ecm}\n\n"
        f"━━ CURRENT CASE CORPUS (live database state) ━━\n\n"
        f"{corpus_text}\n\n"
        f"━━ INVOCATION ━━\n\n"
        f"New documents in this run: {new_doc_count}\n"
        f"Mode: {'full-corpus review' if new_doc_count == 0 else 'incremental forensic integration'}\n\n"
        f"Per your system prompt, begin with the session-opening line, then produce sections I-VII."
    )

    print(f"forensic_agent: matter={args.matter} · corpus_chars={len(corpus_text):,}")
    print(f"  → calling Opus 4.7 with 1h-cached system prompt (~$2-3 expected)")

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = anthropic_call(
        client,
        called_from="forensic_agent",
        purpose=f"forensic_analysis_{args.matter}",
        case_file=corpus["matter"].get("case_file","MWK-001"),
        model="claude-opus-4-7",
        max_tokens=args.max_output_tokens,
        system=[{
            "type": "text",
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
            "text": system_prompt,
        }],
        messages=[{"role": "user", "content": user_msg}],
    )
    output = msg.content[0].text.strip()

    # Citation validation
    unverified = []
    if not args.skip_citation_validate:
        output, unverified = validate_citations_in_text(output)
        if unverified:
            output += (
                f"\n\n---\n\n## Citation Verification Notes (auto-generated post-process)\n\n"
                f"{len(unverified)} case citation(s) could not be verified against the firm's "
                f"known-cases list. Atty. Barandon should confirm before any of these is relied on:\n\n"
                + "\n".join(f"  • {c}" for c in unverified)
            )

    # Save
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_md = DRAFTS_DIR / f"forensic_{args.matter}_{today}.md"
    out_md.write_text(
        f"# Forensic Analysis — {args.matter}\n\n"
        f"*Generated {today} by ELITE_FORENSIC_LAND_TITLE (Opus 4.7) · "
        f"Tokens: {msg.usage.input_tokens:,}in / {msg.usage.output_tokens:,}out · "
        f"Cost: ${(msg.usage.input_tokens*15 + msg.usage.output_tokens*75)/1_000_000:.4f}*\n\n---\n\n"
        f"{output}\n"
    )
    print(f"  ✓ saved: {out_md}")

    # Update ECM
    update_ecm_post_run(corpus, output)
    print(f"  ✓ Evidence_Corpus_Map.md updated")

    # PDF + send
    if not args.no_send:
        try:
            import markdown as md_lib, weasyprint
            html_body = md_lib.markdown(out_md.read_text(),
                extensions=["tables","fenced_code","toc","sane_lists","nl2br"])
            html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 20mm 16mm 18mm 16mm;
         @bottom-left {{ content: "PRIVILEGED & CONFIDENTIAL · FORENSIC ANALYSIS · ATTORNEY WORK PRODUCT";
                         font-size: 8pt; color: #888; font-family: Georgia,serif; }}
         @bottom-right {{ content: "Page " counter(page) " / " counter(pages);
                          font-size: 9pt; color: #888; font-family: Georgia,serif; }} }}
body {{ font-family: Georgia, "Times New Roman", serif; font-size: 11pt;
       line-height: 1.5; color: #1a1a1a; }}
h1 {{ font-size: 16pt; color: #4a0d0d; border-bottom: 2px solid #4a0d0d;
     padding-bottom: 4px; margin-top: 0; }}
h2 {{ font-size: 13pt; color: #2a3a5c; border-bottom: 1px solid #b8b8b8;
     padding-bottom: 3px; margin-top: 22px; }}
h3 {{ font-size: 11.5pt; color: #2a3a5c; margin-top: 16px; font-weight: 700; }}
table {{ border-collapse: collapse; margin: 8px 0; font-size: 9.5pt; width: 100%; }}
th, td {{ border: 1px solid #c8c8c8; padding: 5px 7px; vertical-align: top; }}
th {{ background: #e8e8e8; font-weight: 700; }}
em {{ color: #555; font-style: italic; }}
blockquote {{ border-left: 3px solid #b8860b; background: #fdf8ee;
              padding: 8px 14px; color: #444; margin: 10px 0; font-size: 10pt; }}
code {{ font-family: "Menlo",monospace; font-size: 9.5pt; background: #f4f4f4;
       padding: 1px 4px; border-radius: 2px; color: #4a0d0d; }}
strong {{ color: #1a1a1a; }}
hr {{ border: 0; border-top: 1px solid #c8c8c8; margin: 16px 0; }}
</style></head><body>{html_body}</body></html>"""
            out_pdf = out_md.with_suffix(".pdf")
            weasyprint.HTML(string=html, base_url="/root/landtek").write_pdf(str(out_pdf))
            print(f"  ✓ PDF: {out_pdf} ({out_pdf.stat().st_size/1024:.1f} KB)")

            from comms import _orig_post
            from comms_recipients import OPS_RECIPIENTS
            token = _load_token()
            caption = (
                f"🔬 <b>Forensic Analysis — {args.matter}</b>\n"
                f"<i>{today} · audience=ops · Opus 4.7 · "
                f"${(msg.usage.input_tokens*15 + msg.usage.output_tokens*75)/1_000_000:.2f}</i>\n\n"
                f"Sections: I exec summary · II theory of case · III defendant taxonomy · "
                f"IV evidence inventory · V gaps + risks · VI next moves · VII strategic recommendation"
                + (f"\n\n⚠ <b>{len(unverified)} unverified citation(s)</b> — see post-process notes." if unverified else "")
            )
            for name, cid in OPS_RECIPIENTS:
                with open(out_pdf, "rb") as fh:
                    r = _orig_post(f"https://api.telegram.org/bot{token}/sendDocument",
                                   data={"chat_id": cid, "caption": caption, "parse_mode": "HTML"},
                                   files={"document": (out_pdf.name, fh, "application/pdf")},
                                   timeout=60)
                j = r.json() if r.content else {}
                ok = r.status_code == 200 and j.get("ok")
                print(f"  {'✓' if ok else '✗'} {name} ({cid}) — HTTP {r.status_code}  msg_id={j.get('result',{}).get('message_id')}")
        except Exception as e:
            print(f"  ⚠ PDF/send failed: {e}")

    cost = (msg.usage.input_tokens*15 + msg.usage.output_tokens*75) / 1_000_000
    print(f"\nTokens: {msg.usage.input_tokens:,}in / {msg.usage.output_tokens:,}out · cost: ${cost:.4f}")
    if unverified:
        print(f"Unverified citations: {len(unverified)} — flagged in output")


if __name__ == "__main__":
    main()
