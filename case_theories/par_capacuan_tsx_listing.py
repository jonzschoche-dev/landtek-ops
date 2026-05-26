"""Case theory: Paracale Gold Corporation TSX Venture Exchange listing.

Allan V. Inocalla, President of Paracale Gold Corporation (PGC) — a company
registered in British Columbia, Canada — is positioning the family's
~240-hectare gold-bearing landholdings in Paracale / Jose Panganiban
(Camarines Norte, PH) for a public listing on the TSX Venture Exchange under
Canadian Securities law disclosure (NI 43-101, SEDAR).

Source documents (all under PAR-CAPACUAN):
  doc#478 (2026-03-28) — MGB Letter "Introduction of Paracale Gold Corporation —
    Request for Guidance on Tenure Clarity and Responsible Development of the
    Bicol Gold Project"
  doc#479 (2026-03-28) — PGC letter, same date, same content (duplicate / sent
    copy). Contains "NI 43-101 Technical Report (dated January 3, 2022, prepared
    by Jaime C. Zafra, P.Geo, FAUSIMM)"
  doc#485 (2020-06-18) — Green World Consultancy Inc. MOU (Burnaby BC). Shishir
    Allan Inocalla "of Green World Consultancy Inc". Pairs Shishir with Noel A.
    Zamora (Surrey BC) as consultant group.

Run via:
  python3 case_theory_engine.py case_theories.par_capacuan_tsx_listing
"""

THEORY = {
    "theory_id": "par-capacuan-tsx-listing",
    "matter_code": "PAR-CAPACUAN",
    "client_id": "PAR",
    "case_caption": "Paracale Gold Corporation — TSX-V listing of Inocalla family gold properties",
    "summary": (
        "Allan V. Inocalla, President of Paracale Gold Corporation (a British "
        "Columbia, Canada-registered company), is positioning the Inocalla "
        "family's ~240-hectare landholdings in Paracale and Jose Panganiban, "
        "Camarines Norte for a public listing on the TSX Venture Exchange. "
        "A January 3 2022 NI 43-101 Technical Report by Jaime C. Zafra, P.Geo "
        "FAUSIMM exists. As of the March 28 2026 MGB letter, tenure clarity at "
        "the Philippine end (MGB / DENR) is still being established."
    ),
    "forcing_function": {
        "type": "tenure_clarity_followup",
        "date": None,  # No documented deadline yet; MGB response pending
        "venue": "MGB Compound, North Avenue, Diliman, Quezon City 1101",
    },
    # Scoring guide (Δ field): higher = stronger lever for TSX-V readiness.
    "claims": [
        # ─── Section 1: Corporate structure ─────────────────────────────────
        {
            "id": "pgc-bc-registered",
            "section": "Corporate structure",
            "text": "Paracale Gold Corporation (PGC) is a company registered in British Columbia, Canada",
            "depends_on": [],
            "transfer_link": None,
            "if_supported_implies": "PGC is the Canadian corporate vehicle for the planned TSX-V listing; "
                                    "subject to BC corporate law + Canadian Securities law disclosure.",
            "defense_anticipation": "Critics may probe whether BC registration is current / in good standing.",
            "development_impact": "Confirms the Canadian-side corporate entity. Pending: copy of BC Certificate "
                                  "of Incorporation + BC corporate registry search to verify status.",
            "title_curative_score_delta": 3,
        },
        {
            "id": "allan-is-pgc-president",
            "section": "Corporate structure",
            "text": "Allan V. Inocalla is the President of Paracale Gold Corporation",
            "depends_on": ["pgc-bc-registered"],
            "transfer_link": None,
            "if_supported_implies": "Allan is the signatory / public face for PGC's tenure-clarity engagement "
                                    "with MGB and (presumably) for any TSX-V listing application.",
            "defense_anticipation": None,
            "development_impact": "Establishes principal authority for all PGC correspondence. Quoted in doc#478, "
                                  "#479: 'I am Allan V. Inocalla, President of Paracale Gold Corporation.'",
            "title_curative_score_delta": 2,
        },
        {
            "id": "shishir-green-world",
            "section": "Corporate structure",
            "text": "Shishir Allan Inocalla operates Green World Consultancy Inc., a BC Canada corporation "
                    "(Burnaby BC, Suite 1105-9595 Erickson Dr.)",
            "depends_on": [],
            "transfer_link": None,
            "if_supported_implies": "Green World is the related Canadian entity through which Shishir engages "
                                    "BC business partners (e.g., Noel A. Zamora's consultancy group, doc#485). "
                                    "Likely advisor / channel-partner relationship to PGC; identity gap with "
                                    "Allan V. Inocalla pending clarification (same person? brother?).",
            "defense_anticipation": "Critics may scrutinize whether related-party transactions between PGC and "
                                    "Green World are arm's-length under TSX-V related-party rules.",
            "development_impact": "Surfaces the secondary Canadian-side vehicle. Gap: is Shishir Allan Inocalla "
                                  "the same person as Allan V. Inocalla (Datu/martial-arts persona vs legal name)? "
                                  "deploy_258 held them as separate canonicals pending clarification.",
            "title_curative_score_delta": 1,
        },

        # ─── Section 2: Underlying assets ───────────────────────────────────
        {
            "id": "inocalla-240-hectares",
            "section": "Underlying assets",
            "text": "The Inocalla family owns approximately 240 hectares of land in Paracale and Jose Panganiban, "
                    "Camarines Norte, held since 1931",
            "depends_on": [],
            "transfer_link": None,
            "if_supported_implies": "The 240-ha landholding is the asset base PGC plans to develop. Continuous "
                                    "family ownership since 1931 supports possession / tenure claims for the "
                                    "MGB tenure-clarity request.",
            "defense_anticipation": "Adverse parties (incl. Capacuan Small-Scale Miners Association per doc#660) "
                                    "may dispute boundaries or overlap with small-scale mining claims.",
            "development_impact": "Quoted from doc#478 #479: 'lands held since 1931. These lands, approximately "
                                  "240 hectares, host major gold-bearing quartz veins in the Paracale Gold District.' "
                                  "Gap: cite the specific TCT/OCT chain (probably traces to OCT P-1616 referenced "
                                  "elsewhere in corpus). Cross-reference PAR-TCT1616 matter.",
            "title_curative_score_delta": 4,
        },
        {
            "id": "paracale-gold-district",
            "section": "Underlying assets",
            "text": "The Inocalla holdings sit within the Paracale Gold District, a recognized gold-bearing "
                    "geological area in Camarines Norte, PH",
            "depends_on": ["inocalla-240-hectares"],
            "transfer_link": None,
            "if_supported_implies": "Geological precedent supports the resource-development thesis. The Paracale "
                                    "Gold District is a documented mining district under PH mining law.",
            "defense_anticipation": "Critics may demand specific assay grades / sample data, not just district-level claims.",
            "development_impact": "Establishes the geological backdrop. Specific quartz-vein characterization "
                                  "lives in the NI 43-101 report (see next claim).",
            "title_curative_score_delta": 2,
        },

        # ─── Section 3: Technical compliance ────────────────────────────────
        {
            "id": "ni43101-report-exists",
            "section": "Technical compliance",
            "text": "An NI 43-101 Technical Report dated January 3, 2022 exists for the Inocalla properties",
            "depends_on": ["pgc-bc-registered"],
            "transfer_link": None,
            "if_supported_implies": "PGC has the threshold technical disclosure document required for "
                                    "Canadian Securities Administrator (CSA) listing on TSX Venture Exchange. "
                                    "NI 43-101 is mandatory for any reporting issuer disclosing mineral "
                                    "projects in Canada.",
            "defense_anticipation": "Securities regulator (BCSC + TSX-V) will review the report's currency "
                                    "(a 2022-dated report may need refresh / update for a 2026 listing).",
            "development_impact": "Critical artifact. Quoted from doc#479: 'Our NI 43-101 Technical Report "
                                  "(dated January 3, 2022, prepared by Jaime C. Zafra, P.Geo FAUSIMM) identifies "
                                  "a significant exploration ta[rget].' Gap: get the full report into the document "
                                  "index (currently only excerpted). Verify currency requirements for 2026 listing.",
            "title_curative_score_delta": 5,
        },
        {
            "id": "zafra-qp",
            "section": "Technical compliance",
            "text": "Jaime C. Zafra, P.Geo, FAUSIMM, is the Qualified Person who prepared the NI 43-101 report",
            "depends_on": ["ni43101-report-exists"],
            "transfer_link": None,
            "if_supported_implies": "Zafra's credentials (Professional Geoscientist + Fellow of the Australasian "
                                    "Institute of Mining and Metallurgy) satisfy the QP requirement under "
                                    "NI 43-101 § 5.1. He must be independent of the issuer to sign certain "
                                    "technical disclosure.",
            "defense_anticipation": "Independence question: any prior relationship between Zafra and PGC / "
                                    "Inocalla family may require additional disclosure.",
            "development_impact": "Names the responsible QP. Already populated in entities (#8444 'Jaime C. Zafra'). "
                                  "Cross-reference his other engagements to assess independence.",
            "title_curative_score_delta": 2,
        },
        {
            "id": "balabag-comparable",
            "section": "Technical compliance",
            "text": "The PGC submission references the TVIP/TVIRD Balabag Gold-Silver Project as a SEDAR-disclosed "
                    "comparable",
            "depends_on": ["ni43101-report-exists"],
            "transfer_link": None,
            "if_supported_implies": "PGC is modeling its disclosure approach on an existing Canadian-listed "
                                    "Philippine gold-silver issuer's SEDAR filings. TVI Pacific Inc / TVI Resource "
                                    "Development Phils is the parent of the Balabag project.",
            "defense_anticipation": None,
            "development_impact": "Indicates sophistication in the listing strategy. Worth pulling Balabag's SEDAR "
                                  "history as a reference benchmark for PGC's expected disclosure cadence.",
            "title_curative_score_delta": 1,
        },

        # ─── Section 4: Listing path ────────────────────────────────────────
        {
            "id": "intent-tsx-v-listing",
            "section": "Listing path",
            "text": "PGC has documented intent to become a publicly traded Canadian resource company listed "
                    "on the TSX Venture Exchange",
            "depends_on": ["pgc-bc-registered", "ni43101-report-exists"],
            "transfer_link": None,
            "if_supported_implies": "TSX-V (the Canadian junior exchange) is the target market. Implies "
                                    "compliance posture for Canadian Securities Administrators (CSA) requirements: "
                                    "NI 43-101 technical disclosure, audited financials, Form 2A listing application, "
                                    "sponsorship by a TSX-V Member firm.",
            "defense_anticipation": "Listing application can be denied or deferred on tenure / title clarity (which "
                                    "is precisely why the March 28 2026 MGB letter exists).",
            "development_impact": "Headline claim. Quoted from doc#478 #479: 'PGC, in its plan to become a publicly "
                                  "traded Canadian resource company to be listed on the TSX Venture Exchange, in "
                                  "fulfillment of the disclosure requirements under Canadian Securities laws, "
                                  "including NI 43-101.' Gap: actual filing date, sponsor name, Form 2A version.",
            "title_curative_score_delta": 5,
        },
        {
            "id": "canadian-securities-disclosure",
            "section": "Listing path",
            "text": "PGC operates under the Canadian Securities laws disclosure framework (NI 43-101 + SEDAR+)",
            "depends_on": ["intent-tsx-v-listing"],
            "transfer_link": None,
            "if_supported_implies": "Once listed, PGC will be subject to continuous disclosure obligations: material "
                                    "change reports, annual MD&A, quarterly financials, all filed via SEDAR+.",
            "defense_anticipation": None,
            "development_impact": "Confirms the regulatory regime. SEDAR+ replaced SEDAR in 2023; verify PGC's "
                                  "filing system references are current.",
            "title_curative_score_delta": 2,
        },

        # ─── Section 5: Open gaps / risks ───────────────────────────────────
        {
            "id": "mgb-tenure-clarity-pending",
            "section": "Open gaps / risks",
            "text": "As of March 28 2026, MGB tenure clarity for the Inocalla properties is still being established",
            "depends_on": ["inocalla-240-hectares"],
            "transfer_link": None,
            "if_supported_implies": "The PH-side regulatory status is a gating item for the TSX-V listing. "
                                    "Tenure ambiguity at MGB is a material disclosure risk that BCSC reviewers "
                                    "would flag.",
            "defense_anticipation": "TSX-V will not sponsor a listing where the underlying asset's tenure is "
                                    "in dispute. The MGB tenure-clarity letter is essentially a pre-listing "
                                    "due-diligence remediation step.",
            "development_impact": "PRIMARY RISK. Until MGB issues a clarifying response, the listing thesis "
                                  "is incomplete. Doc#478/479 explicitly request 'Guidance on Tenure Clarity'. "
                                  "Next action: track for MGB response within 30-60 days of March 28 2026; "
                                  "if no response, escalate via DILG / DENR oversight channels.",
            "title_curative_score_delta": 5,
        },
        {
            "id": "capacuan-ssm-conflict",
            "section": "Open gaps / risks",
            "text": "The Capacuan Small-Scale Miners Association (doc#660) represents a potentially overlapping "
                    "claim on the same Inocalla properties area",
            "depends_on": ["inocalla-240-hectares"],
            "transfer_link": None,
            "if_supported_implies": "Small-scale mining claims under PH RA 7076 (People's Small-Scale Mining Act) "
                                    "must be reconciled before any large-scale MPSA or FTAA grant for PGC.",
            "defense_anticipation": "SSM associations may file opposition to PGC's tenure consolidation.",
            "development_impact": "Material risk to disclose to TSX-V. Need to identify which barangays / lots "
                                  "the Capacuan SSM operates on and whether they overlap with the Inocalla 240 ha.",
            "title_curative_score_delta": 3,
        },
        {
            "id": "ni43101-currency-risk",
            "section": "Open gaps / risks",
            "text": "The January 3 2022 NI 43-101 report may require update or supplement before 2026 listing",
            "depends_on": ["ni43101-report-exists", "intent-tsx-v-listing"],
            "transfer_link": None,
            "if_supported_implies": "NI 43-101 reports go stale; CSA staff typically expect material updates within "
                                    "24-36 months of last technical work. A 2022 report supporting a 2026 listing "
                                    "may need a refresh, especially if material exploration occurred after 2022.",
            "defense_anticipation": None,
            "development_impact": "Plan to commission an updated technical report if any drilling / sampling has "
                                  "occurred since January 2022, OR a current technical report confirmation letter "
                                  "from Zafra confirming the 2022 report's continued accuracy.",
            "title_curative_score_delta": 2,
        },
        {
            "id": "no-listing-application-filed-yet",
            "section": "Open gaps / risks",
            "text": "No filed TSX-V listing application or prospectus / Form 2A is documented in the corpus as of doc#479",
            "depends_on": ["intent-tsx-v-listing"],
            "transfer_link": None,
            "if_supported_implies": "PGC is at the pre-application phase. Listing remains an INTENT documented "
                                    "in a 2026-03-28 letter, not a filed application.",
            "defense_anticipation": None,
            "development_impact": "Gap to fill: ask Allan / Shishir for the latest TSX-V engagement status — "
                                  "sponsor firm engaged? Form 2A drafted? IPO underwriter? Target listing date?",
            "title_curative_score_delta": 2,
        },
    ],
}
