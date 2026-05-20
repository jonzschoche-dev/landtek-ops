"""transferees.py — Factory for per-transferee case theories under TCT T-4497.

Each of the 19 non-Balane named transferees gets a case theory that shares the
VOID_CHAIN_SPINE (15 claims) and adds transferee-specific leaf claim(s) sourced
from `title_transfers` table rows.

Usage:
  from case_theories.transferees import build_theory, list_transferees

  # All 19 with their parcel data:
  for name, parcels in list_transferees(cur):
      theory = build_theory(name, parcels)
      # → ready to pass into case_theory_engine.run_theory()
"""

import re

from case_theories._shared import VOID_CHAIN_SPINE, NON_BALANE_TRANSFEREES


def _slug(name):
    """Make a clean ID slug from a transferee name."""
    s = re.sub(r"[^A-Za-z0-9]+", "-", name.lower()).strip("-")
    return s


def list_transferees(cur):
    """Query title_transfers for parcels per named transferee.

    Returns list of (canonical_name, [parcel_dict, ...]). Names with no rows
    in title_transfers still produce a single entry with empty parcels list —
    those become "evidence-gap" theories.
    """
    out = []
    for canonical in NON_BALANE_TRANSFEREES:
        # Fuzzy match on last word of name (handles Illigan/Iligan etc.)
        last = canonical.split()[-1].rstrip(".")
        cur.execute("""
            SELECT id, transferee_name, parent_title, derivative_title,
                   transfer_date, area_hectares, instrument_type
              FROM title_transfers
             WHERE transferee_name ILIKE %s
                OR transferee_name ILIKE %s
             ORDER BY transfer_date NULLS LAST, id
        """, (f"%{last}%", f"%{canonical}%"))
        parcels = [dict(r) for r in cur.fetchall()]
        # De-dupe by transfer id
        seen_ids = set()
        deduped = []
        for p in parcels:
            if p["id"] in seen_ids:
                continue
            seen_ids.add(p["id"])
            deduped.append(p)
        out.append((canonical, deduped))
    return out


def build_theory(name, parcels):
    """Build a complete case theory dict for one transferee.

    Composes VOID_CHAIN_SPINE + per-transferee leaf claims derived from parcels.
    """
    slug = _slug(name)
    section = f"Per-transferee acquisition (`{name}`)"

    # Per-parcel leaf claims
    leaf_claims = []
    if not parcels:
        # No title_transfers row — gap-flagging claim
        leaf_claims.append({
            "id": f"{slug}-transferee-of-record",
            "section": section,
            "text": f"{name} is a named transferee of land under the TCT T-4497 estate",
            "depends_on": ["t4497-is-mother-title", "cesar-held-spa-from-heirs"],
            "transfer_link": None,
            "if_supported_implies": f"{name} acquired a parcel within the recoverable estate.",
            "defense_anticipation": "Good-faith-purchaser defense; possible registration estoppel.",
            "development_impact": (
                f"Per-parcel recoverable; **no title_transfers row found** for {name} — "
                f"specific derivative title, transfer date, and consideration pending corpus retrieval."
            ),
            "title_curative_score_delta": 1,
        })
    else:
        for i, p in enumerate(parcels):
            deriv = p.get("derivative_title") or "(derivative title unknown)"
            date = p.get("transfer_date")
            instrument = p.get("instrument_type") or "transfer"
            area = p.get("area_hectares")

            text_parts = [f"{name} acquired land under the TCT T-4497 estate"]
            if deriv != "(derivative title unknown)":
                text_parts.append(f"(derivative title `{deriv}`)")
            if date:
                text_parts.append(f"by {instrument} dated {date}")
            text = " ".join(text_parts)

            impact_parts = ["Per-parcel recoverable."]
            if date:
                # Post-2005 = void per spine; pre-2005 = pre-revocation, defensible
                # (heuristic — actual void determination requires SPA terms analysis)
                year = str(date)[:4]
                try:
                    if int(year) >= 2005:
                        impact_parts.append(
                            f"Transfer dated {date} is POST-revocation — void per spine "
                            f"if Cesar acted under the revoked SPA."
                        )
                    else:
                        impact_parts.append(
                            f"Transfer dated {date} is PRE-revocation — may be defensible "
                            f"if Cesar acted within unrevoked authority."
                        )
                except (ValueError, TypeError):
                    pass
            if area:
                impact_parts.append(f"Area: {area} ha.")

            leaf_claims.append({
                "id": f"{slug}-parcel-{i+1}-of-{len(parcels)}" if len(parcels) > 1
                      else f"{slug}-acquisition",
                "section": section,
                "text": text,
                "depends_on": ["t4497-is-mother-title", "cesar-held-spa-from-heirs"],
                "transfer_link": p["id"],
                "if_supported_implies": f"{name} acquired parcel {deriv}.",
                "defense_anticipation": "Good-faith-purchaser defense.",
                "development_impact": " ".join(impact_parts),
                "title_curative_score_delta": 1,
            })

    return {
        "theory_id": f"transferee-{slug}",
        "matter_code": "MWK-001",
        "case_caption": f"Per-transferee theory — {name} (under Civil Case 26-360 void-chain spine)",
        "summary": (
            f"Per-transferee posture for {name}, derived from the shared T-4497 "
            "void-chain spine (SPA revoked 2005 → 2016 deed void → 2021 cancellation void). "
            "Specific acquisition facts from `title_transfers`."
        ),
        "forcing_function": {
            "type": "mediation",
            "date": "2026-06-02",
            "venue": "RTC Camarines Norte (Daet)",
        },
        "claims": list(VOID_CHAIN_SPINE) + leaf_claims,
    }
