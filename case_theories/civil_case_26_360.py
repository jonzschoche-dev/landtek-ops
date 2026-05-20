"""Case theory definition for Civil Case No. 26-360 (Zschoche v. Balane).

Accion reinvindicatoria over TCT T-4497 (mother title, Heirs of Mary Worrick
Keesey). Plaintiff: Patricia Keesey Zschoche. Defendants: Gloria Balane et al.
holding contested TCT T-079-2021002126 (issued 2021 from cancelled T-52540 via
2016 Deed of Sale executed by Cesar de la Fuente under SPA revoked 2005).

This file defines the offense theory as a CHAIN of claims with dependencies,
plus per-claim development impact (narrative) and title_curative_score_delta
(int -10..+10).

Run via:
  python3 case_theory_engine.py case_theories.civil_case_26_360
"""

THEORY = {
    "theory_id": "26-360-void-chain",
    "matter_code": "MWK-001",
    "case_caption": "Civil Case No. 26-360 (Zschoche v. Balane)",
    "summary": (
        "Void chain: SPA to Cesar de la Fuente revoked 2005 → "
        "Cesar's 2016 Deed of Absolute Sale void at inception → "
        "2021 cancellation of TCT T-52540 (executed via that void deed) is itself void → "
        "TCT T-079-2021002126 issued 2021 to Gloria Balane derives from a void cancellation. "
        "Title restoration to the heirs of Mary Worrick Keesey is the remedy."
    ),
    "forcing_function": {
        "type": "mediation",
        "date": "2026-06-02",
        "venue": "RTC Camarines Norte (Daet)",
    },
    # Title curative scoring guide (Δ field):
    #   +10  Keystone — verifying this claim materially restores title marketability
    #   +5   High lever — clears a downstream block in the chain
    #   +2   Useful — establishes a predicate or named target
    #   0    Procedural / neutral
    #   -    Reserved for verified-claims that harm position (none currently expected)
    "claims": [
        # ─── Section 1: Title chain foundation ──────────────────────────────
        {
            "id": "mwk-deceased",
            "section": "Title chain foundation",
            "text": "Mary Worrick Keesey is deceased",
            "depends_on": [],
            "transfer_link": None,
            "if_supported_implies": "Estate is at issue; succession claims operative.",
            "defense_anticipation": None,
            "development_impact": "Establishes the succession baseline for every heirship and estate-derived act in the chain.",
            "title_curative_score_delta": 1,
        },
        {
            "id": "patricia-is-heir",
            "section": "Title chain foundation",
            "text": "Patricia Keesey Zschoche is an heir of Mary Worrick Keesey",
            "depends_on": ["mwk-deceased"],
            "transfer_link": None,
            "if_supported_implies": "Patricia has standing to bring accion reinvindicatoria over MWK estate assets.",
            "defense_anticipation": "Defendants may challenge heirship documentation (foreign domicile, lack of PSA records).",
            "development_impact": "Plaintiff standing established — required predicate for any title-curative action filed in her name.",
            "title_curative_score_delta": 2,
        },
        {
            "id": "t4497-is-mother-title",
            "section": "Title chain foundation",
            "text": "TCT T-4497 is the mother title of the contested Mercedes properties",
            "depends_on": [],
            "transfer_link": None,
            "if_supported_implies": "T-4497 is the root of the chain; all derivative titles trace back to it.",
            "defense_anticipation": "Defendants may dispute mother-title identity to break the chain.",
            "development_impact": "Defines the root parcel for Phase-1 master subdivision planning; chain integrity from T-4497 dictates which sub-parcels are clean.",
            "title_curative_score_delta": 3,
        },
        {
            "id": "t4497-registered-to-mwk-heirs",
            "section": "Title chain foundation",
            "text": "TCT T-4497 is registered in the names of the Heirs of Mary Worrick Keesey",
            "depends_on": ["t4497-is-mother-title", "patricia-is-heir"],
            "transfer_link": None,
            "if_supported_implies": "The legal owner of record is the MWK heirs (including Patricia), not Gloria Balane or her predecessors-in-interest.",
            "defense_anticipation": "Defendants may argue the registration was superseded by later cancellation events (which are the void chain's outputs).",
            "development_impact": "Confirms title-of-record for Patricia/heirs; baseline for valuation modeling at clean-title scenarios.",
            "title_curative_score_delta": 4,
        },
        {
            "id": "t32917-derives-from-t4497",
            "section": "Title chain foundation",
            "text": "TCT T-32917 derives from TCT T-4497",
            "depends_on": ["t4497-is-mother-title"],
            "transfer_link": None,
            "if_supported_implies": "T-32917's 17 sub-subdivisions are all under the MWK estate umbrella.",
            "defense_anticipation": "Title gap or break-in-chain claims.",
            "development_impact": "Confirms T-32917 sub-parcels are within the recoverable estate; relevant to per-transferee strategy on 19 of 20 named defendants.",
            "title_curative_score_delta": 3,
        },

        # ─── Section 2: Void instrument theory ──────────────────────────────
        {
            "id": "cesar-is-dead",
            "section": "Void instrument theory",
            "text": "Cesar M. de la Fuente is dead",
            "depends_on": [],
            "transfer_link": None,
            "if_supported_implies": "No post-death attribution; any post-2017 instrument purporting to be his act is automatically suspect.",
            "defense_anticipation": "Defendants may attempt to challenge the death date or attribute later acts via successor authority.",
            "development_impact": "Closes the timeline window — anything notarized 'by Cesar' after 2017-06-21 is automatically suspect.",
            "title_curative_score_delta": 1,
        },
        {
            "id": "cesar-died-pre-2019",
            "section": "Void instrument theory",
            "text": "Cesar de la Fuente died before September 2019",
            "depends_on": ["cesar-is-dead"],
            "transfer_link": None,
            "if_supported_implies": "September 2019 acts purportedly by Cesar are forgeries or improper-attribution.",
            "defense_anticipation": "Defendants may produce a 'corrected' notarial register.",
            "development_impact": "Targets specifically any 2019+ instruments in the chain — eliminates a wave of potential cleaning targets.",
            "title_curative_score_delta": 2,
        },
        {
            "id": "cesar-held-spa-from-heirs",
            "section": "Void instrument theory",
            "text": "Cesar M. de la Fuente held a Special Power of Attorney from the heirs of Mary Worrick Keesey",
            "depends_on": [],
            "transfer_link": None,
            "if_supported_implies": "Cesar was the attorney-in-fact; his authority is bounded by the SPA's terms and revocation.",
            "defense_anticipation": "Defendants may argue the SPA was broader than asserted or that revocation didn't extinguish the agency.",
            "development_impact": "Establishes the legal basis for ALL post-grant title actions through Cesar — and therefore the leverage of any revocation.",
            "title_curative_score_delta": 1,
        },
        {
            "id": "spa-revoked-2005",
            "section": "Void instrument theory",
            "text": "The Special Power of Attorney granted to Cesar de la Fuente was revoked in 2005",
            "depends_on": ["cesar-held-spa-from-heirs"],
            "transfer_link": None,
            "if_supported_implies": "Every post-2005 act by Cesar under that SPA is void at the instrument — including the 2016 Deed of Sale.",
            "defense_anticipation": "Defendants will argue the revocation wasn't served / not registered with the RD / Cesar lacked notice.",
            "development_impact": "KEYSTONE. Verifying revocation flips the entire 2016-2021 chain from 'colorable' to 'void.' Restores marketability across all affected sub-parcels.",
            "title_curative_score_delta": 10,
        },
        {
            "id": "cesar-2016-deed",
            "section": "Void instrument theory",
            "text": "Cesar de la Fuente executed a Deed of Absolute Sale in September 2016 affecting TCT T-52540",
            "depends_on": ["spa-revoked-2005"],
            "transfer_link": None,
            "if_supported_implies": "The cancellation instrument exists in record — and was executed under revoked authority.",
            "defense_anticipation": "Defendants will defend the deed as facially valid; may produce certified copy from RD.",
            "development_impact": "Identifies the specific instrument to nullify; targets restoration of T-52540's clean title for redevelopment.",
            "title_curative_score_delta": 6,
        },
        {
            "id": "t52540-cancelled-via-cesar-deed",
            "section": "Void instrument theory",
            "text": "T-52540 was cancelled in 2021 via a Deed of Sale executed by Cesar de la Fuente in September 2019",
            "depends_on": ["cesar-2016-deed", "spa-revoked-2005"],
            "transfer_link": None,
            "if_supported_implies": "The 2021 cancellation is downstream of a void instrument — itself void.",
            "defense_anticipation": "Defendants will say the RD did its job; cancellation is presumptively valid until set aside.",
            "development_impact": "Establishes the chain to reverse: void cancellation → void downstream title → restored upstream title.",
            "title_curative_score_delta": 5,
        },
        {
            "id": "balane-title-from-t52540",
            "section": "Void instrument theory",
            "text": "TCT T-079-2021002126 was issued in 2021 to Gloria Balane derived from the cancelled T-52540",
            "depends_on": ["t52540-cancelled-via-cesar-deed"],
            "transfer_link": None,
            "if_supported_implies": "The contested title's chain of authority traces back to the void 2016 deed.",
            "defense_anticipation": "Defendants will assert good-faith purchaser status (innocent-purchaser defense).",
            "development_impact": "Identifies the specific target title to cancel; clears the immediate adversary from the chain.",
            "title_curative_score_delta": 5,
        },

        # ─── Section 3: Procedural posture ──────────────────────────────────
        {
            "id": "26-360-at-pretrial",
            "section": "Procedural posture",
            "text": "Civil Case 26-360 is at the pretrial pending stage",
            "depends_on": [],
            "transfer_link": None,
            "if_supported_implies": "Mediation is procedurally appropriate; summary judgment motion is live.",
            "defense_anticipation": None,
            "development_impact": "Confirms the case timing for development decisions (delayed Phase 1 launch vs. risk of speculative pre-resolution moves).",
            "title_curative_score_delta": 0,
        },
        {
            "id": "barandon-counsel",
            "section": "Procedural posture",
            "text": "Atty. Bonifacio Jr. Barandon represents the plaintiff in Civil Case 26-360",
            "depends_on": [],
            "transfer_link": None,
            "if_supported_implies": "Service of process and pleading authority is settled on plaintiff side.",
            "defense_anticipation": None,
            "development_impact": "Establishes the counsel of record for ongoing case continuity.",
            "title_curative_score_delta": 0,
        },
        {
            "id": "notice-of-pretrial-issued",
            "section": "Procedural posture",
            "text": "A Notice of Pre-trial Conference was issued for Civil Case 26-360",
            "depends_on": [],
            "transfer_link": None,
            "if_supported_implies": "Court has formally moved the case to pretrial stage.",
            "defense_anticipation": None,
            "development_impact": "Procedural; relevant to mediation prep but not to title curative directly.",
            "title_curative_score_delta": 0,
        },
        {
            "id": "summary-judgment-motion-filed",
            "section": "Procedural posture",
            "text": "A Motion to Render Summary Judgment was filed by the plaintiff in Civil Case 26-360",
            "depends_on": [],
            "transfer_link": None,
            "if_supported_implies": "Plaintiff is seeking expedited resolution without full trial.",
            "defense_anticipation": "Defendants may oppose on the basis of disputed material facts.",
            "development_impact": "Faster resolution path = earlier title clearance = earlier development phase launch.",
            "title_curative_score_delta": 1,
        },

        # ─── Section 4: Defense claims to test (rebut-or-confirm) ───────────
        {
            "id": "balane-registered-owner",
            "section": "Defense claims to test",
            "text": "Gloria Balane is the registered owner of TCT T-079-2021002126",
            "depends_on": [],
            "transfer_link": None,
            "if_supported_implies": "Adversary identity is settled; targets the rescission of this specific title.",
            "defense_anticipation": "Trivially supported by RD records.",
            "development_impact": "Confirms the named target for the cancellation order.",
            "title_curative_score_delta": 1,
        },
        {
            "id": "erwin-balane-affidavit",
            "section": "Defense claims to test",
            "text": "Engr. Erwin H. Balane submitted a Judicial Affidavit in Civil Case 26-360",
            "depends_on": [],
            "transfer_link": None,
            "if_supported_implies": "Defendants have placed Erwin's testimony on the record.",
            "defense_anticipation": None,
            "development_impact": "Identifies a defense witness to prepare cross / impeachment for.",
            "title_curative_score_delta": 0,
        },
        {
            "id": "salvador-osum-affidavit",
            "section": "Defense claims to test",
            "text": "Salvador Osum Dela Fuente submitted a Judicial Affidavit in Civil Case 26-360",
            "depends_on": [],
            "transfer_link": None,
            "if_supported_implies": "A Tagalog-language witness with first-hand knowledge has testimony in record.",
            "defense_anticipation": "Defendants may challenge translation / authentication.",
            "development_impact": "Establishes a defense witness whose testimony 'Patay na po' could corroborate Cesar's death — potentially friendly evidence.",
            "title_curative_score_delta": 1,
        },

        # ─── Section 5: Named-transferee tests ──────────────────────────────
        {
            "id": "edgardo-santiago-transferee",
            "section": "Named transferees (under T-32917)",
            "text": "Edgardo Santiago acquired land under TCT T-32917 from Cesar de la Fuente as Attorney-in-Fact",
            "depends_on": ["cesar-held-spa-from-heirs"],
            "transfer_link": None,
            "if_supported_implies": "Edgardo's acquisition is one of the 19 non-Balane transferee positions to evaluate.",
            "defense_anticipation": "Edgardo may assert good-faith status.",
            "development_impact": "If transfer was post-revocation, recoverable; pre-revocation may be settled. Identifies which sub-parcel to evaluate next.",
            "title_curative_score_delta": 1,
        },
        {
            "id": "jose-pascual-transferee",
            "section": "Named transferees (under T-32917)",
            "text": "Jose Pascual Jr. acquired a 629 sqm parcel under TCT T-32917 for PHP 44,030",
            "depends_on": [],
            "transfer_link": None,
            "if_supported_implies": "Documented transfer to one of the 19 non-Balane named transferees.",
            "defense_anticipation": "Good-faith purchaser arguments.",
            "development_impact": "Per-parcel recoverable; PHP 44,030 / 629sqm ≈ PHP 70/sqm — historical price grounds future valuation deltas.",
            "title_curative_score_delta": 1,
        },
        {
            "id": "elsa-iligan-transferee",
            "section": "Named transferees (under T-32917)",
            "text": "Elsa O. Iligan acquired a 300 sqm parcel under TCT T-32917 for PHP 7,000",
            "depends_on": [],
            "transfer_link": None,
            "if_supported_implies": "Documented transfer to one of the 19 non-Balane named transferees.",
            "defense_anticipation": "Good-faith purchaser arguments.",
            "development_impact": "Per-parcel recoverable; PHP 7,000 / 300sqm ≈ PHP 23/sqm — bargain-price flag potentially relevant to good-faith analysis.",
            "title_curative_score_delta": 1,
        },
    ],
}
