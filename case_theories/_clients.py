"""_clients.py — Per-client configuration registry.

Single source of truth for the data that varies between clients. Generic scripts
(chronicle, gmail backfill, docs backfill, consolidate_entities) should read
from CLIENTS[<id>] rather than hardcoding MWK-specific values.

For COMPLEX per-client data (consolidation groups, case theory definitions,
memory keystones), the registry POINTS to where that data lives — it does not
copy it. This keeps each module responsible for its own content and avoids
multi-place edits.

Adding a new client:
  1. Add an entry below with case_file, matter_prefix, and any known scalars
  2. Add memory rule files per-client (memory/project_<...>_<client>.md)
  3. Create case_theory modules (case_theories/<...>.py) as needed
  4. Add per-client consolidation groups inside consolidate_entities.py
     KEYSTONE_GROUPS (or use a per-client filter)
  5. Add chronicle memory keystones inside the per-client chronicle module
  6. Run the backfill scripts with --client <id> (once they accept that arg)

See docs/CLIENT_ONBOARDING.md for the full sequence.
"""

CLIENTS = {
    # ─── MWK — Mary Worrick Keesey estate ─────────────────────────────────
    "MWK": {
        "client_id": "MWK",
        "label": "Mary Worrick Keesey",
        "owner_principal": "Patricia Keesey Zschoche (heir)",

        # Storage / namespace
        "case_file": "MWK-001",
        "matter_prefix": "MWK-",

        # Title chain canon (mirrored to title_chain_canon.py — keep in sync)
        "operative_root": "T-111",
        "ghost_titles": ["OCT T-106", "T-106", "1-106", "F-106"],
        "trunk_titles": ["T-111", "T-4497"],

        # Filing convention mappings (consumed by gmail + docs backfills)
        # CTN format: ARTA matters have suffix → matter_code lookup
        "arta_ctn_prefix_to_matter": "MWK-ARTA-",  # MWK-ARTA-<suffix>

        # Civil case + special case number → matter_code lookup
        "civil_case_mappings": {
            "26-360":  "MWK-CV26360",
            "26360":   "MWK-CV26360",
            "6839":    "MWK-CV6839",
            "6922":    "MWK-PARALLEL-CV6922",
            "9221":    "MWK-PARALLEL-CRIM9221",
        },

        # Keystone entity IDs — the canonical persons after consolidation
        # (used for adjudicator linkage, lookup short-circuits, truth tests)
        "keystone_entities": {
            "mary_worrick_keesey":         25,
            "patricia_keesey_zschoche":   400,
            "geraldine_keesey_hoppe":      16,
            "gloria_balane":               15,
            "efren_balane":              3057,
            "engr_erwin_balane":         3060,
            "loida_macale":                39,
            "cesar_de_la_fuente":        1348,
            "alexander_pajarillo":       1635,
            "atty_bonifacio_barandon":   3061,
            "atty_rodolfo_del_rosario":  8877,
            "atty_daisy_bragais":        8878,
            "usec_genes_abot":           8879,
            # Balane-family co-defendants in Civil Case 8563 (predecessor of
            # CA-G.R. SP No. 181607 / underlying CV26360). Surfaced via
            # deploy_251/255 Torralba-Donata-Balane lineage investigation.
            "donata_mabeza_king":        3155,
            "joel_i_mabeza":             8367,
            # 20 named transferees (post-consolidation)
            "alberto_victa":              856,
            "ananias_apor":               859,
            "arnel_mabeza":              1333,
            "aurora_bernardo":           1551,
            "cesar_ramirez":              621,
            "delfin_gaulit":             1295,
            "dolores_vela":              1274,
            "edgardo_santiago":          1229,
            "elsa_iligan":               1763,
            "erlinda_tychingco":         1241,
            "jose_pascual_jr":             72,
            "librada_onrubio":           1552,
            "maria_cereza":              1553,
            "mariquita_era":             1262,
            "pedro_valledor":            1268,
            "rosalina_hansol":           3411,  # canonical 'Rosalina M. Hansol' (filed under TCT T-50192)
            "roscoe_leano":              1209,  # canonical 'Roscoe Leaño' (with ñ); fragments: #425, #4695, #5682
            "ruben_ocan":                4474,  # canonical 'Ruben P. Ocan'; fragment: #1191
            "severino_tenorio_jr":       1554,  # canonical 'Severino Tenorio Jr.'; fragments: #1350, #5394
        },

        # Pointer: where this client's per-matter case theories live
        "case_theory_modules": [
            "case_theories.civil_case_26_360",
            "case_theories.transferees",  # generates 19 per-transferee theories
        ],

        # Pointer: which entries in consolidate_entities.KEYSTONE_GROUPS are MWK's
        "consolidation_groups_count": 22,  # informational; all current entries are MWK

        # Pointer: which memory rules belong to this client
        "memory_rules": [
            "feedback_multi_agent_git_routine",            # global
            "project_title_origins_mwk",                    # MWK-specific
            "project_civil_case_26_360_load_bearing_dates", # MWK-specific
            "feedback_legal_act_validity_scrutiny",         # global discipline
            "project_delia_macaso_transferee",              # MWK transferee detail
        ],

        # Generic chronicle script + per-client KEYSTONES list location
        "chronicle_script": "scripts/chronicle_mwk.py",
        "chronicle_keystones_var": "MEMORY_KEYSTONES",  # the constant in chronicle_mwk.py

        # Truth tests for this client (added per deploy)
        "truth_test_modules": [
            "test_titles_keystone",          # T-4497 facts
            "test_entities_keystone",        # Cesar #1348, Patricia exists
            "test_chain_canon_alignment",    # OPERATIVE_ROOTS["MWK-001"] = "T-111"
            "test_balane_chain_components",  # T-52540 → 079-2021002127 ↔ Psd-05-026197
        ],

        # Forcing function (currently active)
        "next_forcing_function": {
            "type": "mediation",
            "matter_code": "MWK-CV26360",
            "date": "2026-06-02",
            "venue": "RTC Camarines Norte (Daet)",
        },
    },

    # ─── PAR — Paracale (Allan V. Inocalla) ───────────────────────────────
    # Stub. Populate as data lands. The 7 PAR-* matters already exist in
    # the `matters` table; this entry tells the registry they belong to PAR.
    "PAR": {
        "client_id": "PAR",
        "label": "Paracale (Allan V. Inocalla)",
        "owner_principal": "Allan V. Inocalla",

        "case_file": "Paracale-001",
        "matter_prefix": "PAR-",

        "operative_root": None,           # TODO: when PAR title chain is mapped
        "ghost_titles": [],
        "trunk_titles": [],

        "arta_ctn_prefix_to_matter": None,  # Paracale matters aren't ARTA
        "civil_case_mappings": {},          # TODO: as PAR civil cases are documented

        "keystone_entities": {
            # Allan V. Inocalla — PAR principal. 19 mentions canonical.
            # Aliases #8091, #8147, #8320 consolidated → #7983 in deploy_258.
            "allan_inocalla":            7983,
            # Shishir Allan Inocalla — Datu/martial-arts persona (may be same
            # person as Allan; held separate canonical pending clarification).
            # Aliases #8062, #8776 → #8708.
            "shishir_allan_inocalla":    8708,
            # Jesus V. Inocalla — sibling/co-petitioner across Inocalla cases
            # (Civil Case 13-131220 etc). Alias #8158 → #8120.
            "jesus_v_inocalla":          8120,
        },

        "case_theory_modules": [
            "case_theories.par_capacuan_tsx_listing",
        ],
        "consolidation_groups_count": 0,   # nothing PAR-specific yet
        "memory_rules": [],                # TODO: project_title_origins_par.md
        "chronicle_script": None,          # TODO: chronicle_par.py or generic
        "chronicle_keystones_var": None,
        "truth_test_modules": [],

        "next_forcing_function": None,
    },

    # ─── NIBDC — Northern Island Builders and Development Corporation ─────
    # Third client (onboarded 2026-06-15). Mining-tenement services. Matters
    # NIBDC-EXPA-000250 + NIBDC-APSA-000322 already exist in `matters`. Note:
    # NIBDC has an adverse-interest history with the Paracale/Inocalla small-
    # scale miners over the APSA-000322 area — a business-awareness matter,
    # kept as separate clients (see memory client-separation-invariants).
    "NIBDC": {
        "client_id": "NIBDC",
        "label": "Northern Island Builders and Development Corporation",
        "owner_principal": "NIBDC (corporate)",

        "case_file": "NIBDC-001",
        "matter_prefix": "NIBDC-",

        "operative_root": None,
        "ghost_titles": [],
        "trunk_titles": [],

        "arta_ctn_prefix_to_matter": None,
        "civil_case_mappings": {},

        "keystone_entities": {},           # TODO: as NIBDC entities are canonicalized
        "case_theory_modules": [],
        "consolidation_groups_count": 0,
        "memory_rules": [],
        "chronicle_script": None,
        "chronicle_keystones_var": None,
        "truth_test_modules": [],
        "next_forcing_function": None,
    },

    # ─── OWNER — Jonathan Zschoche's personal/owner-bucket files ─────────
    # Not a legal client in the representation sense; it's the case_file used
    # for Jonathan's own documents (passport, birth records, family research,
    # archive certifications). Introduced in deploy_081. Some Owner docs may
    # also have matter_code values that cross-link to a real client matter
    # (e.g., a Patricia passport copy may be MWK-ESTATE evidence even though
    # the doc itself is filed under Owner).
    "OWNER": {
        "client_id": "OWNER",
        "label": "Owner (Jonathan Zschoche)",
        "owner_principal": "Jonathan Paul Zschoche",
        "case_file": "Owner",
        "matter_prefix": None,             # no matter_codes for Owner-only docs
        "operative_root": None,
        "ghost_titles": [],
        "trunk_titles": [],
        "arta_ctn_prefix_to_matter": None,
        "civil_case_mappings": {},
        "keystone_entities": {
            "jonathan_zschoche": None,     # populate when canonical entity id known
        },
        "case_theory_modules": [],
        "consolidation_groups_count": 0,
        "memory_rules": [],
        "chronicle_script": None,
        "chronicle_keystones_var": None,
        "truth_test_modules": [],
        "next_forcing_function": None,
    },
}


# ─── Entity-consolidation canon (machine-readable; enforced, not just commented) ───
# survivor_entity_id -> [alias entity_ids that MUST fold into it].
# WHY this exists: extraction re-spawns name-variants ("Allan Inocalla", "Allan Inocalla
# y Villafria", "Datu Shishir Inocalla") as fresh entity rows, so a one-time manual merge
# silently DRIFTS back apart. The deploy_258 consolidation lived only in a code comment and
# had fully drifted by 2026-06-15 (8320/8062/8776/8158 all live again). This dict is the
# durable canon: `cross_client_sentinel.py --apply-canon` re-applies it idempotently and a
# truth test (test_cross_client_integrity) fails if any alias id is live — so it can't rot.
CANON_ALIAS_MERGES = {
    7983: [8091, 8147, 8320],   # Allan Villafria Inocalla — PAR principal (deploy_258)
    8708: [8062, 8776],         # Shishir Allan Inocalla — held SEPARATE from Allan (deploy_258)
    8120: [8158],               # Jesus V. Inocalla — PAR co-petitioner (deploy_258)
    1348: [9036],               # Cesar de la Fuente — MWK void-SPA executor (exact-name dup)
    15:   [3716],               # Gloria Balane — MWK defendant, "Gloria H. Balane" dup
}

# Entities that LEGITIMATELY hold defining roles across >1 client (so the integrity test
# must not flag them). The operator/agent is the canonical case: Jonathan acts as attorney-
# in-fact in MWK and is the principal of his own Owner bucket. Add a (id, reason) only after
# verifying the cross-appearance is real, not a mis-file.
CROSS_CLIENT_PRINCIPAL_ALLOWLIST = {
    1184: "Jonathan Paul Zschoche — operator / attorney-in-fact (MWK) + Owner principal",
}


def get(client_id):
    """Return client config dict. KeyError if not registered."""
    if client_id not in CLIENTS:
        raise KeyError(f"Unknown client {client_id!r}. Registered: {list(CLIENTS)}")
    return CLIENTS[client_id]


def all_ids():
    """Return list of registered client IDs."""
    return list(CLIENTS.keys())


def client_for_matter_code(matter_code):
    """Reverse lookup: which client does this matter_code belong to?"""
    if not matter_code:
        return None
    for cid, conf in CLIENTS.items():
        if matter_code.startswith(conf["matter_prefix"]):
            return cid
    return None


def client_for_case_file(case_file):
    """Reverse lookup: which client does this case_file belong to?"""
    for cid, conf in CLIENTS.items():
        if conf["case_file"] == case_file:
            return cid
    return None
