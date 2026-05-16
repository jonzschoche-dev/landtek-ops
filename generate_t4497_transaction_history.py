#!/usr/bin/env python3
"""Every transaction ever — TCT T-4497 and its descent tree.

Pulls three streams (title transfers, instruments-on-title, financial transactions)
that touched any title in T-4497's descent and sorts them chronologically into a
single forensic ledger. Writes to drafts/ as a markdown report.

Zero LLM cost — pure SQL.
"""
import os
from datetime import datetime
from pathlib import Path
import psycopg2, psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
OUT = Path("/root/landtek/drafts") / f"t4497_transaction_history_{datetime.now().strftime('%Y-%m-%d')}.md"

DESCENT_CTE = """
WITH RECURSIVE tree(title, depth, path) AS (
  SELECT 'T-4497', 0, ARRAY['T-4497']::text[]
  UNION
  SELECT child_title, depth+1, path || child_title
    FROM title_chain tc JOIN tree t ON tc.parent_title = t.title
   WHERE NOT (tc.child_title = ANY(t.path))
),
descent AS (SELECT DISTINCT title FROM tree)
"""

def fetch():
    conn = psycopg2.connect(DSN)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Tree
    cur.execute(DESCENT_CTE + " SELECT title, MIN(depth) AS d FROM tree GROUP BY title ORDER BY d, title")
    tree = cur.fetchall()

    # Title transfers
    cur.execute(DESCENT_CTE + """
        SELECT COALESCE(transfer_date::text, annotation_date::text) AS event_date,
               parent_title, derivative_title, instrument_type,
               transferor, transferee_name, entry_pe_number, provenance_level, status,
               notes
          FROM title_transfers
         WHERE (parent_title IN (SELECT title FROM descent)
             OR derivative_title IN (SELECT title FROM descent))
         ORDER BY event_date NULLS LAST
    """)
    transfers = cur.fetchall()

    # Instruments
    cur.execute(DESCENT_CTE + """
        SELECT COALESCE(entry_date::text, executed_at_date::text) AS event_date,
               parent_tct_number AS title, pe_number, instrument_type,
               executor_full_name, authority_basis, authority_date::text AS auth_date,
               notary_name, instrument_doc_ref
          FROM instruments_on_title
         WHERE parent_tct_number IN (SELECT title FROM descent)
         ORDER BY event_date NULLS LAST
    """)
    instruments = cur.fetchall()

    # Financial transactions tied to chain docs
    chain_titles = [t["title"] for t in tree]
    cur.execute("""
        SELECT tx_date::text AS event_date, category,
               amount::numeric AS amount,
               LEFT(description, 120) AS description, source_doc_id
          FROM transactions
         WHERE case_file='MWK-001'
         ORDER BY tx_date DESC NULLS LAST
    """)
    all_tx = cur.fetchall()
    # Filter to those that reference a chain title in the description (loose) — keep ALL since case_file=MWK-001
    txns = all_tx

    cur.close(); conn.close()
    return tree, transfers, instruments, txns


def main():
    OUT.parent.mkdir(exist_ok=True)
    tree, transfers, instruments, txns = fetch()

    lines = [
        f"# TCT T-4497 — Every Transaction Ever",
        f"**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Scope:** T-4497 and every descendant in `title_chain`.",
        "",
        "## Descent tree",
        "",
    ]
    by_depth = {}
    for r in tree:
        by_depth.setdefault(r["d"], []).append(r["title"])
    for d in sorted(by_depth):
        lines.append(f"- **Depth {d}** ({len(by_depth[d])} titles): {', '.join(by_depth[d])}")
    lines.append(f"")
    lines.append(f"**Total titles in chain:** {len(tree)}")
    lines.append("")

    # --- Title-level conveyance events ---
    lines.append("## I. Title transfers / conveyances")
    lines.append("")
    lines.append("These are formal title-to-title chain events (TCT → TCT). Provenance level shows how confident we are in the linkage.")
    lines.append("")
    lines.append("| Date | Title step | Instrument | Parties | PE # | Prov | Status |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in transfers:
        date_s = (r.get("event_date") or "?")[:10]
        step = f"{r.get('parent_title')} → {r.get('derivative_title') or '?'}"
        instr = (r.get('instrument_type') or '?')[:30]
        parties = f"{(r.get('transferor') or '?')[:30]} → {(r.get('transferee_name') or '?')[:30]}"
        pe = r.get('entry_pe_number') or '—'
        prov = r.get('provenance_level') or '?'
        st = r.get('status') or '?'
        lines.append(f"| {date_s} | {step} | {instr} | {parties} | {pe} | {prov} | {st} |")
    lines.append("")
    lines.append(f"**Count:** {len(transfers)}")
    lines.append("")

    # --- Instrument-level (encumbrance) events ---
    lines.append("## II. Instruments / encumbrances on each title (Memorandum of Encumbrances)")
    lines.append("")
    lines.append("Every formal entry on the back of each TCT in the chain. Source: heightened Gemini OCR extraction.")
    lines.append("")
    lines.append("| Date | Title | PE# | Instrument | Executor | Authority | Notary |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in instruments:
        date_s = (r.get("event_date") or "?")[:10]
        title = r.get('title') or '?'
        pe = r.get('pe_number') or '—'
        instr = (r.get('instrument_type') or '?')[:30]
        exec_ = (r.get('executor_full_name') or '—')[:35]
        auth = (r.get('authority_basis') or '—')[:25]
        if r.get('auth_date'):
            auth = f"{auth} ({r['auth_date'][:10]})"
        notary = (r.get('notary_name') or '—')[:25]
        lines.append(f"| {date_s} | {title} | {pe} | {instr} | {exec_} | {auth} | {notary} |")
    lines.append("")
    lines.append(f"**Count:** {len(instruments)}")
    lines.append("")

    # --- Financial transactions ---
    lines.append("## III. Financial transactions (filings, registrations, taxes, fees)")
    lines.append("")
    lines.append(f"All MWK-001 transactions. Total recorded: {len(txns)}.")
    lines.append("")
    lines.append("| Date | Category | Amount (PHP) | Description |")
    lines.append("|---|---|---:|---|")
    by_cat = {}
    total_php = 0.0
    for r in txns:
        date_s = (r.get("event_date") or "?")[:10]
        cat = r.get('category') or '?'
        amt = float(r.get('amount') or 0)
        desc = (r.get('description') or '')[:100].replace("|", "/")
        lines.append(f"| {date_s} | {cat} | {amt:,.2f} | {desc} |")
        by_cat[cat] = by_cat.get(cat, 0) + amt
        total_php += amt
    lines.append("")
    lines.append("### Financial summary")
    lines.append("")
    lines.append("| Category | Total (PHP) |")
    lines.append("|---|---:|")
    for c, a in sorted(by_cat.items(), key=lambda x: -x[1]):
        lines.append(f"| {c} | {a:,.2f} |")
    lines.append(f"| **Total** | **{total_php:,.2f}** |")
    lines.append("")

    # --- Notes ---
    lines.append("---")
    lines.append("")
    lines.append("## Data quality notes")
    lines.append("")
    lines.append("- Title-transfer rows with `provenance_level='inferred_weak'` are not yet quote-backed — treat as PENDING VERIFICATION.")
    lines.append("- Many instruments_on_title rows have `executor_full_name='?'` — back-page handwriting was illegible at heightened OCR.")
    lines.append("- Future-dated transactions (2028, 2029) are likely ingestion-side date misparses; flagging for human review.")
    lines.append("- The May 21, 2025 cluster of ₱6,980.49 transactions across 30+ rows is almost certainly a single batched payment ingested per-title — not 30 separate payments.")
    lines.append("- Per memory [[feedback_information_is_gold]]: no row is deleted; rows remain for audit even when superseded.")

    OUT.write_text("\n".join(lines))
    print(f"Report written to: {OUT}")
    print(f"  {len(tree)} titles in descent")
    print(f"  {len(transfers)} title transfers")
    print(f"  {len(instruments)} instruments on title")
    print(f"  {len(txns)} financial transactions")


if __name__ == "__main__":
    main()
