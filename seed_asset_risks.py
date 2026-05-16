#!/usr/bin/env python3
"""Seed asset_risks from known corpus facts (deploy_113-D).

Each risk derives from a specific document or established case fact. Risks are
versioned (append-only) per the [[feedback-evolving-assessments]] rule.

After seeding, also computes intrinsic_value = market - sum(risk-weighted losses).
"""
from datetime import date, timedelta
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# Real risks for MWK-001 assets, derived from corpus docs:
#   - doc #401, #402 (Plaintiff's Reply): SPA-authority risk for any title transferred by Cesar/Salvador
#   - doc #407 (Salvador's Judicial Affidavit, "Patay na po"): Cesar's death → forgery exposure
#   - doc #76, #79 (2005 SPA revocation): SPA-revoked-but-Cesar-continued risk
#   - doc #384 (ARTA complaint): LGU intransigence risk (Mayor Pajarillo)
#   - doc #392 (Pretrial notice): Pretrial-procedural risk on 26-360
RISKS = [
    # ── T-52540 / its derivative T-079-2021002126 (Gloria Balane's title — contested) ──
    {
        "asset_title": "T-52540",
        "case_file": "MWK-001",
        "risk_type": "title_defect",
        "severity": "critical",
        "likelihood_pct": 95,
        "expected_loss_php": 7000000,
        "mitigation_strategy": "Win Civil Case 26-360 (accion reinvindicatoria) — declare deed null, cancel TCT 079-2021002126",
        "mitigation_status": "in_progress",
        "mitigation_cost": 350000,
        "learned_from_case": "MWK-001",
        "evidence_doc_ids": [233, 240, 401, 402, 405, 441, 444, 445],
        "notes": "Mother title T-52540 cancelled in 2021 via 2016 Deed of Sale executed by Cesar de la Fuente under revoked SPA. Plaintiff's Reply (doc #401) and Jonathan's Judicial Affidavit (doc #441, #445) anchor the void-conveyance claim. Currently at pretrial_pending stage.",
    },
    {
        "asset_title": "T-079-2021002126",  # Gloria Balane's TCT
        "case_file": "MWK-001",
        "risk_type": "adverse_claim",
        "severity": "critical",
        "likelihood_pct": 95,
        "expected_loss_php": 7000000,
        "mitigation_strategy": "Cancel as derivative of void T-52540 deed in Civil Case 26-360",
        "mitigation_status": "in_progress",
        "mitigation_cost": 0,  # part of same case
        "learned_from_case": "MWK-001",
        "evidence_doc_ids": [368, 410, 413, 415, 441, 445],
        "notes": "Defendants' TCT 079-2021002126 was issued from cancelled T-52540 via 2016 Deed of Sale. Sale was executed by Cesar de la Fuente under a 1992 SPA that was revoked on 2005-08-15 (per docs #76, #79, #441 ¶f-g). Subject of 26-360.",
    },

    # ── Estate-wide: Cesar-De-La-Fuente authority exposure ──
    # Apply to T-32917 as the major derivative
    {
        "asset_title": "T-32917",
        "case_file": "MWK-001",
        "risk_type": "spa_authority",
        "severity": "high",
        "likelihood_pct": 60,
        "expected_loss_php": 2000000,
        "mitigation_strategy": "(a) Procure PSA death certificate for Cesar de la Fuente to anchor forgery exposure on 2019-09-26 sale. (b) Pursue criminal falsification charges against Salvador Dela Fuente for continuing to sign in deceased father's name. (c) File adverse claims on any title showing post-2005-08-15 transactions executed under the revoked 1992 SPA.",
        "mitigation_status": "planning",
        "mitigation_cost": 50000,
        "learned_from_case": "MWK-001",
        "evidence_doc_ids": [35, 38, 72, 76, 79, 82, 329, 369, 407, 441],
        "notes": "Cesar held 1992 SPA, revoked 2005-08-15 (docs #76, #79). Per Salvador's Judicial Affidavit (doc #407), Cesar is DECEASED. Yet 2019-09-26 sale to Balane bears his signature → if death predates 2019, signature is forged. Salvador continuing to sign as 'Von' Dela Fuente in his stead may extend forgery exposure to other titles.",
    },
    {
        "asset_title": "T-4497",  # mother title
        "case_file": "MWK-001",
        "risk_type": "spa_authority",
        "severity": "high",
        "likelihood_pct": 50,
        "expected_loss_php": 5000000,
        "mitigation_strategy": "Audit ALL derivative titles for transactions executed under revoked 1992 SPA. Map who Cesar (or Salvador in his name) conveyed to. File adverse claims pre-emptively.",
        "mitigation_status": "planning",
        "mitigation_cost": 100000,
        "learned_from_case": "MWK-001",
        "evidence_doc_ids": [21, 35, 38, 39, 76, 79, 82, 329, 369, 407, 441],
        "notes": "Mother title T-4497 (Heirs of Mary Worrick Keesey). 17+ derivative TCTs. Risk: any post-2005 conveyance executed under the revoked SPA potentially attackable.",
    },

    # ── Estate-administration risk ──
    {
        "asset_title": "T-4497",
        "case_file": "MWK-001",
        "risk_type": "heir_dispute",
        "severity": "medium",
        "likelihood_pct": 30,
        "expected_loss_php": 1500000,
        "mitigation_strategy": "Complete intestate estate proceedings (doc #165, #298). Ensure all heirs sign acknowledgment + waiver where needed.",
        "mitigation_status": "in_progress",
        "mitigation_cost": 75000,
        "learned_from_case": "MWK-001",
        "evidence_doc_ids": [165, 183, 294, 298],
        "notes": "Mary Worrick Keesey is deceased. Multiple heirs (Patricia, Geraldine, Marcia, Ellen). Patricia is plaintiff via SPA to Jonathan. Other heirs' positions unknown — risk of intra-heir conflict on settlement strategy.",
    },

    # ── LGU intransigence risk (ARTA pending) ──
    {
        "asset_title": "T-4497",
        "case_file": "MWK-001",
        "risk_type": "political",
        "severity": "medium",
        "likelihood_pct": 70,
        "expected_loss_php": 500000,
        "mitigation_strategy": "Escalate from ARTA → DILG (already done — matter MWK-ARTA-DILG opened 2026-04-23). If admin sanctions insufficient, parallel civil action vs LGU for occupation.",
        "mitigation_status": "in_progress",
        "mitigation_cost": 30000,
        "learned_from_case": "MWK-001",
        "evidence_doc_ids": [302, 304, 339, 344, 384],
        "notes": "Mayor Pajarillo's office charged in ARTA Complaint-Affidavit doc #384 with R.A. 11032 violations (failure to issue written disapproval, delays). Underlies the 1979 donation deed implementation dispute.",
    },

    # ── Tax delinquency exposure for older ARPs ──
    {
        "asset_title": "GR-2014-HH-07-001-00229",
        "case_file": "MWK-001",
        "risk_type": "tax_delinquency",
        "severity": "low",
        "likelihood_pct": 100,
        "expected_loss_php": 5000,  # documented in Statement of Account
        "mitigation_strategy": "Pay accrued RPT + penalty under tax amnesty (see doc #277). Document via OR.",
        "mitigation_status": "unaddressed",
        "mitigation_cost": 5000,
        "learned_from_case": "MWK-001",
        "evidence_doc_ids": [59, 277],
        "notes": "Statement of Account doc #59 shows RPT delinquency accumulated 2014-2023 = ₱1,367.64 with discount = ₱852.80. Pattern likely repeats across many ARPs.",
    },
]


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    new = updated = 0
    for r in RISKS:
        # Append-only — check if same risk_type exists for same asset
        cur.execute("""
            SELECT id, severity, expected_loss_php, mitigation_status
              FROM asset_risks
             WHERE asset_title=%s AND risk_type=%s
             ORDER BY assessed_at DESC LIMIT 1
        """, (r["asset_title"], r["risk_type"]))
        existing = cur.fetchone()
        if existing:
            # Insert new row only if material change
            material_change = (
                existing["severity"] != r["severity"] or
                float(existing["expected_loss_php"] or 0) != float(r["expected_loss_php"]) or
                existing["mitigation_status"] != r["mitigation_status"]
            )
            if not material_change:
                continue

        next_review = date.today() + timedelta(days=30 if r["severity"] in ("critical", "high") else 90)
        cur.execute("""
            INSERT INTO asset_risks
              (asset_title, case_file, risk_type, severity, likelihood_pct,
               expected_loss_php, mitigation_strategy, mitigation_status, mitigation_cost,
               learned_from_case, evidence_doc_ids, internal_only, next_review_due, notes,
               provenance_level)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true,%s,%s,'inferred_strong')
            RETURNING id
        """, (r["asset_title"], r["case_file"], r["risk_type"], r["severity"], r["likelihood_pct"],
              r["expected_loss_php"], r["mitigation_strategy"], r["mitigation_status"], r["mitigation_cost"],
              r["learned_from_case"], r["evidence_doc_ids"], next_review, r["notes"]))
        rid = cur.fetchone()["id"]
        if existing:
            updated += 1
            # log the change event
            cur.execute("""
                INSERT INTO risk_change_events
                  (asset_title, case_file, risk_type, event_type,
                   old_severity, new_severity, old_expected_loss, new_expected_loss,
                   delta_php, triggered_at, notes)
                VALUES (%s,%s,%s,'manual_seed_update',%s,%s,%s,%s,%s,now(),%s)
            """, (r["asset_title"], r["case_file"], r["risk_type"],
                  existing["severity"], r["severity"],
                  existing["expected_loss_php"], r["expected_loss_php"],
                  float(r["expected_loss_php"]) - float(existing["expected_loss_php"] or 0),
                  f"Updated by seed_asset_risks.py — risk #{rid}"))
        else:
            new += 1
        print(f"  + #{rid} {r['asset_title']:35s} {r['risk_type']:18s} sev={r['severity']:8s} loss={r['expected_loss_php']:,}")

    print(f"\n  asset_risks: {new} new / {updated} updated")

    # Recompute intrinsic_value for each tracked asset
    cur.execute("""
        WITH risk_loss AS (
          SELECT asset_title,
                 sum(CASE
                       WHEN mitigation_status = 'eliminated' THEN 0
                       WHEN mitigation_status = 'in_progress' THEN expected_loss_php * (likelihood_pct/100.0) * 0.5
                       WHEN mitigation_status = 'partial'     THEN expected_loss_php * (likelihood_pct/100.0) * 0.7
                       ELSE expected_loss_php * (likelihood_pct/100.0)
                     END) AS expected_loss
            FROM asset_current_risks
           GROUP BY asset_title
        )
        UPDATE asset_valuations av
           SET intrinsic_value = COALESCE(av.market_price_value, 0) - COALESCE(rl.expected_loss, 0),
               opportunity_score = CASE
                 WHEN av.market_price_value IS NULL OR av.market_price_value <= 0 THEN NULL
                 WHEN rl.expected_loss IS NULL OR rl.expected_loss <= 0 THEN 0
                 ELSE LEAST(1.0,
                   GREATEST(0,
                     (COALESCE(av.market_price_value,0) - COALESCE(rl.expected_loss,0))
                     / NULLIF(av.market_price_value,0)
                   )
                 )::real
               END
          FROM risk_loss rl
         WHERE av.asset_title = rl.asset_title
        RETURNING av.asset_title, av.market_price_value, av.intrinsic_value, av.opportunity_score
    """)
    intrinsic = cur.fetchall()
    print(f"\n  intrinsic_value updated for {len(intrinsic)} assets:")
    for r in intrinsic:
        print(f"    {r['asset_title']:35s} market={r['market_price_value']:>14,.0f}  intrinsic={r['intrinsic_value']:>14,.0f}  score={r['opportunity_score']:.2f}")

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
