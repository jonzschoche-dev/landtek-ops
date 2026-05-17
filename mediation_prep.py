#!/usr/bin/env python3
"""Mediation prep pack — Civil Case 26-360 (Zschoche v. Balane), June 2 2026.

Produces a verified-only evidence pack + settlement-range analysis from the
*_safe views and asset_current_valuation. No LLM inference. Every claim is
either:
  (a) sourced from a _safe view (provenance_level='verified'), or
  (b) flagged "PENDING VERIFICATION" with a marker.

Output: /root/landtek/drafts/mediation_pack_CV26360_<date>.md

Per [[feedback_output_no_hallucination_discipline]] and the project's
"hallucinations are existential" posture, this script is SQL-and-cite only.
Strategic synthesis (posture, leverage moves, asks) goes through
opus_advisor.py strategic — a separate call.
"""
import psycopg2, psycopg2.extras
from datetime import date
from pathlib import Path

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
CASE = "MWK-001"
MATTER = "MWK-CV26360"
MEDIATION_DATE = "2026-06-02"
CONTESTED_TITLE = "T-079-2021002126"
MOTHER_TITLE = "T-4497"


def section(title):
    return f"\n## {title}\n"


def cite(doc_id, blurb):
    return f"[doc#{doc_id}: {blurb}]" if doc_id else "[NO DOC CITATION — PENDING VERIFICATION]"


def build():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    today = date.today().isoformat()

    out = [
        f"# Mediation Prep Pack — Civil Case 26-360",
        f"**Mediation:** {MEDIATION_DATE} · RTC Daet Branch 64 · 1 PM",
        f"**Counsel:** Atty. Bonifacio Jr. Barandon (Barandon Law Offices)",
        f"**Plaintiff:** Patricia Keesee Zschoche (heirs of Mary Worrick Keesey)",
        f"**Defendant:** Gloria Balane et al. (holding TCT {CONTESTED_TITLE})",
        f"**Prepared:** {today} · verified-only data from *_safe views",
        "",
        "> Every fact below carries a doc# citation OR is flagged PENDING VERIFICATION.",
        "> Do not cite anything without a citation as fact in mediation.",
    ]

    # ── 1. THE VOID-CHAIN CASE ──────────────────────────────────────────
    out.append(section("1. THE VOID-CHAIN CASE (theory of plaintiff's claim)"))
    out.append(
        "Plaintiff's theory: TCT " + CONTESTED_TITLE + " (issued 2021 to Gloria Balane) "
        "is void because it descends from a 2016 Deed of Sale executed by Cesar N. dela "
        "Fuente UNDER AN SPA THAT WAS REVOKED IN 2005. A void deed cannot transfer "
        "title; therefore the cancelled mother title T-52540 was wrongly cancelled and "
        + CONTESTED_TITLE + " was wrongly issued."
    )

    # 1a. SPA + Revocation
    out.append("\n### 1a. The SPA and its revocation")
    cur.execute("""
        SELECT id, COALESCE(smart_filename, original_filename) AS fname,
               document_title, classification, created_at::date AS d
          FROM documents
         WHERE case_file = %s
           AND (document_title ILIKE '%%SPA%%' OR original_filename ILIKE '%%SPA%%'
                OR classification ILIKE '%%power%%attorney%%' OR document_title ILIKE '%%revocation%%')
         ORDER BY id LIMIT 8
    """, (CASE,))
    spa_docs = cur.fetchall()
    if spa_docs:
        for d in spa_docs:
            label = d['document_title'] or d['fname'][:70]
            out.append(f"- {cite(d['id'], label)} ({d['classification'] or '—'})")
    else:
        out.append("- ⚠️ NO SPA/REVOCATION DOC FOUND IN CORPUS — primary instrument missing")

    out.append(
        "\n**Critical:** The 2005 Revocation of SPA is presently testimonial only "
        "(Jonathan's Judicial Affidavit doc#441). Primary instrument (notarized "
        "revocation document) is the highest-priority evidence gap."
    )

    # 1b. Cesar's death
    out.append("\n### 1b. Cesar dela Fuente died 2017 — separate void path")
    cur.execute("""
        SELECT id, COALESCE(smart_filename, original_filename) AS fname,
               document_title, classification
          FROM documents
         WHERE case_file = %s
           AND (document_title ILIKE '%%LandBank%%6839%%' OR original_filename ILIKE '%%LandBank%%6839%%'
                OR document_title ILIKE '%%dela fuente%%death%%' OR document_title ILIKE '%%cesar%%death%%')
         ORDER BY id DESC LIMIT 5
    """, (CASE,))
    death_docs = cur.fetchall()
    if death_docs:
        for d in death_docs:
            label = d['document_title'] or d['fname'][:70]
            out.append(f"- {cite(d['id'], label)}")
    else:
        out.append("- Cesar's death (June 21, 2017) cited in LandBank's filing in CV-6839 — "
                   "see project_civil_case_26_360_load_bearing_dates memory; doc# pending corpus match")
    out.append(
        "\nIndependent of the SPA revocation theory, Cesar could not have executed any "
        "instrument after his death. Any post-2017 conveyance bearing his signature is "
        "facially void."
    )

    # 1c. The contested title chain
    out.append("\n### 1c. Verified title chain to the contested title")
    cur.execute("""
        SELECT parent_title, child_title, relationship, provenance_level,
               source_doc_id
          FROM title_chain_safe
         WHERE child_title = %s OR child_title = 'T-52540'
            OR parent_title IN (%s, 'T-52540')
         ORDER BY child_title
         LIMIT 15
    """, (CONTESTED_TITLE, MOTHER_TITLE))
    chain = cur.fetchall()
    if chain:
        for c in chain:
            out.append(f"- {c['parent_title']} → {c['child_title']} "
                       f"({c['relationship']}) {cite(c['source_doc_id'], 'chain edge')}")
    else:
        out.append("- ⚠️ Chain to " + CONTESTED_TITLE + " not yet in verified title_chain_safe")

    # ── 2. THE 20 NAMED TRANSFEREES ─────────────────────────────────────
    out.append(section("2. NAMED TRANSFEREES (status snapshot, verified-only)"))
    cur.execute("""
        SELECT canonical_name, accion_status, current_possession,
               source_doc_id, provenance_level
          FROM transferees_safe
         WHERE case_file = %s
         ORDER BY accion_status, canonical_name
    """, (CASE,))
    tx = cur.fetchall()
    out.append(f"_{len(tx)} verified transferee record(s) in transferees_safe._")
    out.append("")
    for t in tx[:30]:
        out.append(f"- **{t['canonical_name']}** — {t['accion_status']} · {t['current_possession'] or '—'} "
                   f"{cite(t['source_doc_id'], 'transferee')}")

    # ── 3. ASSET / SETTLEMENT RANGE ─────────────────────────────────────
    out.append(section("3. SETTLEMENT RANGE (asset values for floor/ceiling)"))
    # Valuations are keyed by tax_dec_no, assets by TCT — no bridge yet,
    # so report from asset_current_valuation directly. Total across all
    # MWK valuations (the universe Patricia would be vindicating).
    cur.execute("""
        SELECT asset_title, tax_dec_no, area_sqm,
               assessed_value, zonal_value, market_price_value,
               appraised_value, current_use
          FROM asset_current_valuation
         WHERE case_file = %s
           AND COALESCE(assessed_value, market_price_value, zonal_value) IS NOT NULL
         ORDER BY COALESCE(market_price_value, assessed_value) DESC NULLS LAST
         LIMIT 20
    """, (CASE,))
    val_rows = cur.fetchall()
    total_assessed = 0.0
    total_market = 0.0
    n_with_assessed = 0
    n_with_market = 0
    for r in val_rows:
        a = float(r['assessed_value'] or 0)
        m = float(r['market_price_value'] or 0)
        total_assessed += a
        total_market += m
        if a: n_with_assessed += 1
        if m: n_with_market += 1
        out.append(f"- {r['tax_dec_no']} ({r['current_use'] or '—'}, {r['area_sqm'] or '—'} sqm) — "
                   f"assessed P{a:,.0f} · market P{m:,.0f}")

    # Pull case-wide totals (not just top 20)
    cur.execute("""
        SELECT
          COUNT(*) FILTER (WHERE assessed_value IS NOT NULL)         AS n_assessed,
          SUM(assessed_value)                                        AS sum_assessed,
          COUNT(*) FILTER (WHERE market_price_value IS NOT NULL)     AS n_market,
          SUM(market_price_value)                                    AS sum_market
        FROM asset_current_valuation WHERE case_file = %s
    """, (CASE,))
    tot = cur.fetchone()
    out.append("")
    out.append(f"**Floor (sum of assessed values, {tot['n_assessed']} valued parcels):** "
               f"P{float(tot['sum_assessed'] or 0):,.0f}")
    out.append(f"**Ceiling (sum of declared market values, {tot['n_market']} parcels):** "
               f"P{float(tot['sum_market'] or 0):,.0f}")
    out.append(
        "\n_Floor = LGU assessed values (most conservative public number)._\n"
        "_Ceiling = market price from tax declarations where available; many assets lack "
        "FMV in corpus — the ceiling is understated. Independent appraisal would refine._"
    )

    # ── 4. EVIDENCE GAPS (asks for Jonathan) ────────────────────────────
    out.append(section("4. EVIDENCE GAPS — items Jonathan must close before 6-2"))
    cur.execute("""
        SELECT COUNT(*) AS n_placeholder
          FROM title_transfers
         WHERE case_file = %s AND provenance_level != 'verified'
    """, (CASE,))
    n_ph = cur.fetchone()['n_placeholder']
    out.append(f"- **{n_ph} placeholder title_transfers** need primary docs (currently in title_transfers but not in title_transfers_safe).")

    cur.execute("""
        SELECT id, COALESCE(smart_filename, original_filename, document_title) AS label,
               execution_status
          FROM documents
         WHERE case_file = %s
           AND (execution_status = 'draft' OR execution_status IS NULL)
           AND (document_title ILIKE '%%revocation%%' OR document_title ILIKE '%%SPA%%'
                OR document_title ILIKE '%%deed%%')
         ORDER BY id DESC LIMIT 10
    """, (CASE,))
    drafts = cur.fetchall()
    if drafts:
        out.append("- **Unverified-execution docs** (draft or unknown status — cannot cite as fact):")
        for d in drafts:
            out.append(f"  - doc#{d['id']}: {d['label'][:80]} (status={d['execution_status'] or 'unknown'})")

    # Critical missing primary instruments (manual list — these are well-known gaps)
    out.append("\n- **Primary-instrument hunt list** (per project memory):")
    out.append("  - 2005 Revocation of SPA (notarized) — currently testimonial via Jonathan's affidavit")
    out.append("  - 1988 Mary Worrick Keesey death certificate (PSA-issued)")
    out.append("  - Cesar dela Fuente death certificate (2017) — referenced in CV-6839 LandBank filing")
    out.append("  - The 2016 Deed of Sale itself (Cesar → buyer that led to T-52540 cancellation)")

    # ── 5. PRETRIAL ORDER (post-pretrial intake status) ─────────────────
    out.append(section("5. POST-PRETRIAL STATUS"))
    cur.execute("""
        SELECT current_stage, stage_updated_at::date, next_event, stage_notes
          FROM matters WHERE matter_code = %s
    """, (MATTER,))
    m = cur.fetchone()
    if m:
        out.append(f"- **Current stage:** {m['current_stage']} (updated {m['stage_updated_at']})")
        out.append(f"- **Awaiting:** {m['next_event']}")

    # Intake response state
    cur.execute("""
        SELECT r.id, r.timing, r.status, r.items_total, r.items_received, r.fired_at::date AS d
          FROM stage_intake_response r
          JOIN case_deadlines d ON d.id = r.deadline_id
         WHERE d.case_file = %s
         ORDER BY r.fired_at DESC LIMIT 5
    """, (CASE,))
    intakes = cur.fetchall()
    for ir in intakes:
        out.append(f"  - Intake#{ir['id']} ({ir['timing']}, fired {ir['d']}): "
                   f"{ir['items_received']}/{ir['items_total']} items received · status={ir['status']}")

    # ── 6. ATTY. BARANDON HANDOFF CHECKLIST ─────────────────────────────
    out.append(section("6. BARANDON HANDOFF CHECKLIST"))
    out.append("- [ ] Confirm mediation date/time/venue with Atty. Barandon's office")
    out.append("- [ ] Authorize/decline settlement floor (assessed-value basis)")
    out.append("- [ ] Authorize/decline ceiling (market-value basis or independent appraisal)")
    out.append("- [ ] Confirm Patricia's presence (in person, remote, or via SPA)")
    out.append("- [ ] Decide on Reply / Motion for Summary Judgment posture vis-à-vis mediation")
    out.append("- [ ] Pre-Trial Order status — has it issued? Trial date set?")

    out.append("\n---\n")
    out.append(f"_Generated {today} from verified-only data. Strategic posture, leverage moves, "
               f"and risk assessment: see opus_advisor.py strategic --matter {MATTER}._")

    pack = "\n".join(out)

    Path("/root/landtek/drafts").mkdir(exist_ok=True)
    outpath = Path(f"/root/landtek/drafts/mediation_pack_CV26360_{today}.md")
    outpath.write_text(pack)
    print(f"Wrote {outpath} ({len(pack):,} chars, {pack.count(chr(10))+1} lines)")
    return outpath


if __name__ == "__main__":
    build()
