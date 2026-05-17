#!/usr/bin/env python3
"""opus_advisor — strategic-grade advisory using Claude Opus 4.7.

Per Jonathan 2026-05-17: "let's add opus as an advisor."

Opus is the most expensive tier ($15/M input, $75/M output) and is reserved
for decisions where reasoning quality justifies the cost. The advisor is
SPARINGLY INVOKED — never on routine extraction/classification/verdict work.

Three sanctioned advisor use cases:

  1. STRATEGIC SYNTHESIS — produce a case-level strategic memo (settlement
     posture, evidence-gap analysis, leverage moves) once per matter per
     major milestone. ~1-3 calls per matter per month.

  2. PRIORITY-DISPUTE RESOLUTION — when case_deadlines.priority_consensus_state
     = 'disputed' (Leo + Jonathan + client signals disagree), Opus weighs in
     with a reasoned recommendation. Triggered manually via /opus-resolve <id>
     or when meta-agent flags persistent dispute.

  3. CRITICAL-DOC DRAFTING — final-form drafting of demand letters, motions,
     judicial affidavits, settlement proposals. NOT routine prep (Haiku
     handles that); only the final-quality pass where stakes are high.

Cost discipline: ~$0.05-0.20 per call. Caching essential — the system prompt
is large (~3K tokens with full advisor framing) and benefits enormously from
1h ephemeral cache.

Usage:
  python3 opus_advisor.py strategic --matter MWK-CV26360
  python3 opus_advisor.py resolve-dispute --deadline 2
  python3 opus_advisor.py draft --kind demand_letter --matter MWK-TCT4497
"""
import argparse
import json
import sys
from datetime import date

sys.path.insert(0, "/root/landtek")
from landtek_core import db, get
from llm_billing import anthropic_call


OPUS_SYSTEM = """You are Opus 4.7 acting as the SENIOR STRATEGIC ADVISOR to
Landtek (a Philippine property law firm) and Jonathan Zschoche (the
attorney-in-fact + counsel-coordinator for multiple matters including the
flagship Civil Case 26-360 Zschoche v. Balane).

Your standing instructions:

PRIME DIRECTIVE — every recommendation must be EVIDENCE-CITED. Reference
specific doc IDs, chat_notes, extraction_chunks, or memory entries. Never
assert a fact without anchoring it. Per Landtek discipline: hallucinations
are existential; one un-citable claim erodes the trust the entire system
depends on.

YOUR ROLE:
- You are the FINAL ESCALATION step. Routine extraction, classification,
  verdict-gating, and intake conversations happen elsewhere (Haiku for
  extraction/classification, Sonnet for truth-negotiator verdicts and
  daily synthesis).
- You are invoked ONLY for: (a) strategic synthesis for major case milestones,
  (b) resolution of priority disputes where Leo + Jonathan + client disagree,
  (c) final-form drafting of critical filings where reasoning quality matters
  more than cost.

YOUR OUTPUT STYLE:
- Short, structured, defensible. No filler. No throat-clearing.
- Lead with the recommendation. Follow with the cited reasoning. Close with
  the EVIDENCE GAPS that would strengthen the recommendation.
- Speak as a senior advisor to a senior attorney — concise, direct, decisive.
- When you don't have enough evidence to recommend confidently, SAY SO and
  list the specific evidence needed before you can recommend.

CONTEXT YOU CAN ASSUME:
- Civil Case 26-360 (accion reinvindicatoria, Patricia Keesee Zschoche v.
  Gloria Balane et al., RTC Camarines Norte). Pretrial completed May 13, 2026.
  Mediation scheduled June 2, 2026 at RTC Daet 1 PM (Atty. Barandon attending).
- Title chain: OCT T-106 (1934) → T-4497 → 30+ derivatives. TCT T-111 (1912)
  is a possibly-foundational title held jointly by Mary/Helen/Alice Worrick.
- Cesar N. dela Fuente (administrator-of-state for MWK) died June 21, 2017
  per LandBank's filing in Civil Case 6839 (doc#364). SPA to Cesar revoked
  August 15, 2005 per Jonathan's Judicial Affidavit doc#441 (testimonial).
- The void-instrument theory: Cesar executed a Deed of Sale September 2016
  AFTER his SPA was revoked → conveyances under that deed are void → the
  contested TCT T-079-2021002126 issued to Gloria Balane is contestable.

When asked for strategic advice, always integrate this context AND verify
your recommendations against the most recent corpus state Jonathan provides
in the user message."""


def call_opus(client, user_content: str, max_tokens: int = 1500):
    """One Opus call with 1h-cached system prompt."""
    msg = anthropic_call(
        client,
        called_from="opus_advisor",
        purpose="strategic_advisory",
        case_file=None,
        model="claude-opus-4-7",
        max_tokens=max_tokens,
        system=[{
            "type": "text",
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
            "text": OPUS_SYSTEM,
        }],
        messages=[{"role": "user", "content": user_content}],
    )
    return msg.content[0].text.strip()


def strategic(matter_code: str):
    """Synthesize a strategic memo for the given matter."""
    with db() as cur:
        cur.execute("""
            SELECT m.*, COUNT(d.id) AS n_docs
              FROM matters m
              LEFT JOIN documents d ON d.case_file = m.case_file
             WHERE m.matter_code = %s
             GROUP BY m.matter_code, m.client_code, m.matter_type, m.title,
                      m.court_or_agency, m.docket_number, m.status, m.current_stage,
                      m.next_event, m.next_deadline, m.next_event_owner, m.stage_notes,
                      m.case_file, m.id, m.description, m.date_opened, m.date_closed,
                      m.lead_counsel, m.billing_tier, m.monthly_retainer, m.created_at,
                      m.updated_at, m.verified_document_count, m.first_verified_doc_id,
                      m.verification_status, m.stage_updated_at
        """, (matter_code,))
        m = cur.fetchone()
        if not m:
            print(f"Matter {matter_code} not found"); return
        # Recent client_history for context
        cur.execute("""
            SELECT event_date, event_kind, what_summary, citation_ref, provenance
              FROM client_history
             WHERE case_file = %s AND event_date >= CURRENT_DATE - INTERVAL '90 days'
             ORDER BY event_date DESC LIMIT 30
        """, (m["case_file"],))
        recent = cur.fetchall()
        # Pending deadlines
        cur.execute("""
            SELECT id, title, due_date, priority_tier, priority_consensus_state
              FROM case_deadlines
             WHERE case_file = %s AND status = 'pending'
             ORDER BY due_date
        """, (m["case_file"],))
        deadlines = cur.fetchall()

    user = (
        f"# Strategic advisory requested for matter {matter_code}\n\n"
        f"MATTER: {m['title']}\n"
        f"Court/Agency: {m['court_or_agency']} · Docket: {m['docket_number']}\n"
        f"Current stage: {m['current_stage']}\n"
        f"Next event: {m['next_event']}\n"
        f"Notes: {m['stage_notes']}\n\n"
        f"## Pending deadlines\n" +
        "\n".join(f"  - #{d['id']} {d['title']} due {d['due_date']} (tier {d['priority_tier']}, consensus={d['priority_consensus_state']})"
                  for d in deadlines) + "\n\n"
        f"## Recent 90d events (top 30)\n" +
        "\n".join(f"  - {r['event_date']} [{r['event_kind']}] {r['what_summary'][:120]} ⟨{r['citation_ref']}⟩"
                  for r in recent) + "\n\n"
        "## Your task\n"
        "Provide a strategic memo with these sections:\n"
        "  1. POSTURE — one sentence on where this matter stands today.\n"
        "  2. LEVERAGE MOVES — 3 specific actions Jonathan should take this week, ranked by impact.\n"
        "  3. RISK — the single biggest risk to a favorable outcome + the mitigation.\n"
        "  4. EVIDENCE GAPS — primary documents that, if obtained, would materially strengthen the position.\n"
        "Every claim cited to a doc# or chat_note# or memory."
    )

    import anthropic
    client = anthropic.Anthropic(api_key=get("ANTHROPIC_API_KEY"))
    response = call_opus(client, user, max_tokens=1800)
    print(f"\n=== Opus strategic memo — {matter_code} ===\n")
    print(response)
    return response


def resolve_dispute(deadline_id: int):
    """Opus weighs in when priority signals disagree."""
    with db() as cur:
        cur.execute("""
            SELECT id, title, due_date, deadline_type, stage_key, case_file,
                   priority_leo, priority_jonathan, priority_client,
                   priority_consensus_state, notes, priority_history
              FROM case_deadlines WHERE id = %s
        """, (deadline_id,))
        d = cur.fetchone()
        if not d:
            print(f"Deadline {deadline_id} not found"); return

    user = (
        f"# Priority dispute resolution requested\n\n"
        f"Deadline #{deadline_id}: {d['title']}\n"
        f"Case: {d['case_file']} · Type: {d['deadline_type']} · Stage: {d['stage_key']}\n"
        f"Due: {d['due_date']}\n\n"
        f"## Priority signals\n"
        f"  Leo:      {d['priority_leo']}\n"
        f"  Jonathan: {d['priority_jonathan']}\n"
        f"  Client:   {d['priority_client']}\n"
        f"  State:    {d['priority_consensus_state']}\n\n"
        f"## Notes\n{d['notes']}\n\n"
        "## Your task\n"
        "Recommend the canonical priority tier (P0-P5) with reasoning. "
        "If signals genuinely conflict, explain WHICH party's view should prevail and why. "
        "Be brief — 5-8 lines max."
    )

    import anthropic
    client = anthropic.Anthropic(api_key=get("ANTHROPIC_API_KEY"))
    response = call_opus(client, user, max_tokens=600)
    print(f"\n=== Opus dispute resolution — deadline #{deadline_id} ===\n")
    print(response)
    return response


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("strategic"); s.add_argument("--matter", required=True)
    r = sub.add_parser("resolve-dispute"); r.add_argument("--deadline", type=int, required=True)
    args = ap.parse_args()
    if args.cmd == "strategic":
        strategic(args.matter)
    elif args.cmd == "resolve-dispute":
        resolve_dispute(args.deadline)


if __name__ == "__main__":
    main()
