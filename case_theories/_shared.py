"""_shared.py — Shared spine claims for any MWK-001 transferee theory.

The void chain (SPA revoked 2005 → 2016 deed void → T-52540 cancellation void)
is shared by every named transferee under T-4497. Only the transferee-specific
leaf claims (which parcel they acquired, when, from whom) vary.

Used by:
  - case_theories/civil_case_26_360.py (Balane-specific theory)
  - case_theories/transferees.py (factory for other 19 transferees)
"""

# Shared spine: 15 claims that apply to ANY transferee under the T-4497 estate.
# These cover: title chain foundation + void instrument theory + procedural posture
# of Civil Case 26-360 (which all named transferees are tied to).
#
# Note: per-transferee theories add their OWN leaf claim(s) downstream — the
# transferee's specific acquisition + per-parcel facts.
VOID_CHAIN_SPINE = [
    # Title chain foundation
    {
        "id": "mwk-deceased",
        "section": "Title chain foundation",
        "text": "Mary Worrick Keesey is deceased",
        "depends_on": [],
        "transfer_link": None,
        "if_supported_implies": "Estate is at issue; succession claims operative.",
        "defense_anticipation": None,
        "development_impact": "Succession baseline for every heirship-derived act in the chain.",
        "title_curative_score_delta": 1,
    },
    {
        "id": "patricia-is-heir",
        "section": "Title chain foundation",
        "text": "Patricia Keesey Zschoche is an heir of Mary Worrick Keesey",
        "depends_on": ["mwk-deceased"],
        "transfer_link": None,
        "if_supported_implies": "Patricia has standing for accion reinvindicatoria over MWK assets.",
        "defense_anticipation": "Defendants may challenge heirship documentation.",
        "development_impact": "Plaintiff standing established — predicate for title-curative action.",
        "title_curative_score_delta": 2,
    },
    {
        "id": "t4497-is-mother-title",
        "section": "Title chain foundation",
        "text": "TCT T-4497 is the mother title of the contested Mercedes properties",
        "depends_on": [],
        "transfer_link": None,
        "if_supported_implies": "T-4497 is root; all derivatives trace back to it.",
        "defense_anticipation": "Defendants may dispute mother-title identity.",
        "development_impact": "Root parcel for master subdivision planning.",
        "title_curative_score_delta": 3,
    },
    {
        "id": "t4497-registered-to-mwk-heirs",
        "section": "Title chain foundation",
        "text": "TCT T-4497 is registered in the names of the Heirs of Mary Worrick Keesey",
        "depends_on": ["t4497-is-mother-title", "patricia-is-heir"],
        "transfer_link": None,
        "if_supported_implies": "Legal owner of record is MWK heirs (incl. Patricia).",
        "defense_anticipation": "Defendants may argue registration superseded by later cancellation.",
        "development_impact": "Confirms title-of-record; baseline for clean-title valuation.",
        "title_curative_score_delta": 4,
    },
    {
        "id": "t32917-listed-as-mwk-property",
        "section": "Title chain foundation",
        "text": "TCT T-32917 is listed in the heirs' records as part of the Mary Worrick Keesey estate properties",
        "depends_on": ["t4497-is-mother-title"],
        "transfer_link": None,
        "if_supported_implies": "T-32917's 17 sub-subdivisions are within the MWK estate umbrella.",
        "defense_anticipation": "Title gap / break-in-chain claims.",
        "development_impact": "T-32917 sub-parcels are within recoverable estate.",
        "title_curative_score_delta": 3,
    },

    # Void instrument theory (Cesar de la Fuente / SPA / 2016 deed)
    {
        "id": "cesar-is-dead",
        "section": "Void instrument theory",
        "text": "Cesar M. de la Fuente is dead",
        "depends_on": [],
        "transfer_link": None,
        "if_supported_implies": "No post-death attribution; post-2017 acts as Cesar are suspect.",
        "defense_anticipation": "Defendants may challenge death date or attribute via successor.",
        "development_impact": "Closes timeline window — post-2017-06-21 'Cesar' notarizations suspect.",
        "title_curative_score_delta": 1,
    },
    {
        "id": "cesar-died-pre-2019",
        "section": "Void instrument theory",
        "text": "Cesar de la Fuente died before September 2019",
        "depends_on": ["cesar-is-dead"],
        "transfer_link": None,
        "if_supported_implies": "September 2019 acts purportedly by Cesar are forgeries.",
        "defense_anticipation": "Defendants may produce a 'corrected' notarial register.",
        "development_impact": "Eliminates any 2019+ instruments purportedly executed by Cesar.",
        "title_curative_score_delta": 2,
    },
    {
        "id": "cesar-held-spa-from-heirs",
        "section": "Void instrument theory",
        "text": "Cesar M. de la Fuente held a Special Power of Attorney from the heirs of Mary Worrick Keesey",
        "depends_on": [],
        "transfer_link": None,
        "if_supported_implies": "Cesar was attorney-in-fact; authority bounded by SPA terms + revocation.",
        "defense_anticipation": "Defendants may argue SPA was broader or revocation didn't extinguish.",
        "development_impact": "Legal basis for ALL post-grant Cesar-executed title actions.",
        "title_curative_score_delta": 1,
    },
    {
        "id": "spa-revoked-2005",
        "section": "Void instrument theory",
        "text": "The Special Power of Attorney granted to Cesar de la Fuente was revoked in 2005",
        "depends_on": ["cesar-held-spa-from-heirs"],
        "transfer_link": None,
        "if_supported_implies": "Every post-2005 Cesar-executed act under that SPA is VOID at the instrument.",
        "defense_anticipation": "Defendants will argue revocation wasn't served / registered / Cesar lacked notice.",
        "development_impact": "KEYSTONE. Verifying revocation flips the entire 2016-2021 chain to void.",
        "title_curative_score_delta": 10,
    },
    {
        "id": "cesar-2016-deed",
        "section": "Void instrument theory",
        "text": "Cesar de la Fuente executed a Deed of Absolute Sale in September 2016 affecting TCT T-52540",
        "depends_on": ["spa-revoked-2005"],
        "transfer_link": None,
        "if_supported_implies": "The cancellation instrument exists and was executed under revoked authority.",
        "defense_anticipation": "Defendants will defend the deed as facially valid.",
        "development_impact": "Identifies specific instrument to nullify for T-52540 restoration.",
        "title_curative_score_delta": 6,
    },
    {
        "id": "t52540-cancelled-via-cesar-deed",
        "section": "Void instrument theory",
        "text": "T-52540 was cancelled in 2021 via a Deed of Sale executed by Cesar de la Fuente in September 2019",
        "depends_on": ["cesar-2016-deed", "spa-revoked-2005"],
        "transfer_link": None,
        "if_supported_implies": "2021 cancellation is downstream of a void instrument — itself void.",
        "defense_anticipation": "Defendants will assert RD presumptive validity until set aside.",
        "development_impact": "Establishes the chain to reverse for restoration of upstream title.",
        "title_curative_score_delta": 5,
    },

    # Procedural posture (Civil Case 26-360 — all named transferees are parties)
    {
        "id": "26-360-at-pretrial",
        "section": "Procedural posture",
        "text": "Civil Case 26-360 is at the pretrial pending stage",
        "depends_on": [],
        "transfer_link": None,
        "if_supported_implies": "Mediation procedurally appropriate; summary judgment motion live.",
        "defense_anticipation": None,
        "development_impact": "Confirms case timing for development phasing decisions.",
        "title_curative_score_delta": 0,
    },
    {
        "id": "barandon-counsel",
        "section": "Procedural posture",
        "text": "Atty. Bonifacio Jr. Barandon represents the plaintiff in Civil Case 26-360",
        "depends_on": [],
        "transfer_link": None,
        "if_supported_implies": "Plaintiff counsel of record settled.",
        "defense_anticipation": None,
        "development_impact": "Continuity of representation.",
        "title_curative_score_delta": 0,
    },
    {
        "id": "notice-of-pretrial-issued",
        "section": "Procedural posture",
        "text": "A Notice of Pre-trial Conference was issued for Civil Case 26-360",
        "depends_on": [],
        "transfer_link": None,
        "if_supported_implies": "Court formally moved the case to pretrial.",
        "defense_anticipation": None,
        "development_impact": "Procedural; mediation prep relevant.",
        "title_curative_score_delta": 0,
    },
    {
        "id": "summary-judgment-motion-filed",
        "section": "Procedural posture",
        "text": "A Motion to Render Summary Judgment was filed by the plaintiff in Civil Case 26-360",
        "depends_on": [],
        "transfer_link": None,
        "if_supported_implies": "Plaintiff seeking expedited resolution without full trial.",
        "defense_anticipation": "Defendants may oppose on disputed material facts.",
        "development_impact": "Faster resolution = earlier title clearance = earlier development.",
        "title_curative_score_delta": 1,
    },
]


# The 19 named non-Balane transferees per CLAUDE.md. Spellings as currently
# canonicalized; the engine's entity-alias expansion handles variants.
NON_BALANE_TRANSFEREES = [
    "Alberto Victa",
    "Ananias Apor",
    "Arnel Mabeza",
    "Aurora Bernardo",
    "Cesar Ramirez",
    "Delfin Gaulit",
    "Dolores Vela",
    "Edgardo Santiago",
    "Elsa Illigan",
    "Erlinda Tychingco",
    "Jose Pascual Jr.",
    "Librada B. Onrubio",
    "Maria V. Cereza",
    "Mariquita Era",
    "Pedro Valledor",
    "Rosalina Hansol",
    "Roscoe Leaño",
    "Ruben Ocan",
    "Severino Tenorio Jr.",
]
