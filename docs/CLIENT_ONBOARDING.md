# Client Onboarding

How to onboard a new client to the LandTek property-intelligence system,
once the per-client registry (`case_theories/_clients.py`) is in place.

## Overview

The system is designed to support multiple clients in one database. Per-client
data — matters, titles, entities, documents, emails — is segregated by
`case_file` and `matter_code` fields. Generic scripts (chronicle, lookup,
backfills) consume `case_theories/_clients.py` to know which data belongs
to which client.

## Onboarding sequence

### 1. Register the client in `case_theories/_clients.py`

Add an entry to the `CLIENTS` dict with at minimum:
- `client_id` — short uppercase identifier (e.g., `PAR`, `XYZ`)
- `label` — human-readable client name
- `case_file` — the `documents.case_file` value (e.g., `Paracale-001`)
- `matter_prefix` — prefix all this client's matter_codes share (e.g., `PAR-`)

Populate as data arrives:
- `operative_root` — the operative root TCT for this client's title chain
- `ghost_titles` — titles referenced widely but not operative
- `civil_case_mappings` — `{ "CV number": "matter_code" }`
- `keystone_entities` — `{ "person_slug": entity_id }`
- `next_forcing_function` — upcoming hearing / deadline

### 2. Register the matters

For each distinct legal matter, add a row to `matters`:

```sql
INSERT INTO matters (matter_code, matter_type, ...) VALUES
  ('PAR-NEW-MATTER-1', 'civil_case', ...);
```

Matters can be ARTA cases, civil cases, regulatory, transactional, etc.

### 3. Add per-client memory rules

In `memory/`, add at least one file documenting the client's title-chain
origin story and load-bearing dates. Use existing MWK templates:
- `project_title_origins_mwk.md` → `project_title_origins_<client_id>.md`
- `project_civil_case_<docket>_load_bearing_dates.md` if appropriate

### 4. Run deterministic backfills (no LLM)

```bash
# Gmail ↔ matter linkage (uses civil_case_mappings + ARTA suffix rule)
python3 migrations/apply_deploy_226_gmail_matter_linkage.py --client <CLIENT_ID>

# Documents.matter_code backfill from extracted_text regex
python3 migrations/apply_deploy_234_documents_matter_backfill.py --client <CLIENT_ID>

# Resolutions table backfill (scans case_file's docs for Resolution-like patterns)
python3 migrations/apply_deploy_229_resolutions_table.py --client <CLIENT_ID>

# Document doc_date backfill
python3 migrations/apply_deploy_236_documents_doc_date_backfill.py --client <CLIENT_ID>
```

(Note: scripts currently default to MWK and would require small per-client
parameterization. Deploy_242 is the planned refactor that adds `--client`
arguments cleanly.)

### 5. Add per-client consolidation groups

In `scripts/consolidate_entities.py`, add `KEYSTONE_GROUPS` entries for
this client's known fragmented entities (per-transferee, key adversaries,
counsel, etc.). Run:

```bash
python3 scripts/consolidate_entities.py list                # see fragmentation
python3 scripts/consolidate_entities.py propose --auto      # generate proposals
python3 scripts/promote_proposals.py review --table entities  # interactive review
```

### 6. Add per-client case theories (optional but recommended)

For each significant matter, define a theory module in `case_theories/`:

```python
# case_theories/<client>_<matter_slug>.py
THEORY = {
    "theory_id": "<matter-code>-<theory-slug>",
    "matter_code": "<MATTER_CODE>",
    "case_caption": "...",
    "summary": "...",
    "claims": [...],
}
```

Then run:

```bash
python3 case_theory_engine.py case_theories.<client>_<matter_slug>
```

### 7. Add per-client truth tests

In `truth_tests/`, add a test module that asserts client-specific facts:
- The client's principals (plaintiff/heir) exist as canonical entities
- The operative root title is correctly registered
- Key chain edges have expected provenance
- Specific dates align with memory rules

### 8. Update the title chain canon (if needed)

In `title_chain_canon.py`, add the client's operative root, ghost titles,
and trunks to the respective dicts. Mirror what's in `_clients.py`.

### 9. Generate the chronicle

Once the above are in place:

```bash
python3 scripts/chronicle_mwk.py    # MWK
# python3 scripts/chronicle.py --client <id>   (after deploy_242 generalization)
```

Pulled to `drafts/chronicle_<CLIENT>_<date>.md`.

### 10. Verify with lookup queries

```bash
python3 scripts/lookup.py --matter <PREFIX>-NEW-MATTER-1
python3 scripts/lookup.py --entity "<plaintiff name>"
python3 scripts/lookup.py --title <TCT>
python3 scripts/show_client.py --client <CLIENT_ID>
```

## Verification checklist

Before declaring a client onboarded:

- [ ] `scripts/show_client.py --client <ID>` reports all keystone entities resolve
- [ ] `lookup.py --matter <MATTER>` returns ARTA/civil docs + emails + resolutions
- [ ] Chronicle exists with reasonable event count
- [ ] At least one truth_test assertion exists and passes
- [ ] Canonical matter dashboard shows the client's matters

## Current state

| Client | Status |
|---|---|
| MWK | Fully onboarded; chronicle 9,666 lines, 671 events, 277 audited entity changes |
| PAR | Skeleton only — `_clients.py` entry exists, matters registered, no backfills run |

## Generalization status of generic scripts

Some scripts currently hardcode MWK assumptions. Deploy_242 will refactor:

| Script | MWK-hardcoded today | After 242 |
|---|---|---|
| `migrations/apply_deploy_226_*` | CV_KNOWN_TO_MATTER dict | `--client` arg reads from registry |
| `migrations/apply_deploy_234_*` | case_file = 'MWK-001' | `--client` arg |
| `migrations/apply_deploy_229_*` | (filters all matters — already generic) | minor refactor |
| `scripts/chronicle_mwk.py` | filename + MEMORY_KEYSTONES | rename to `chronicle.py --client` |
| `scripts/consolidate_entities.py` | KEYSTONE_GROUPS includes all clients' groups | filter by client |

Until 242 lands, onboarding a new client requires editing the hardcoded
sections in each script. The registry (`_clients.py`) is the source of
truth that 242 will plumb through.
