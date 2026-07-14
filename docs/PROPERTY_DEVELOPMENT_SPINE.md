# Property Development Spine — Design (reconciled)

> **Status:** APPLIED — deploy_911–913 + **deploy_914 continuous profitability prep cycle**.
> Full portfolio ledger + unprompted prep loop (`profitability_prep_cycle` every 4h): every property
> gets prep moves for profitability **without requiring a controlling_matter**. Matter is optional
> schedule context only. V12 remains **log**.
> **Date:** 2026-07-14 (v2 — operator/engine write split + asset-owned-as-cache refinements)  
> **Supersedes:** the chat draft’s project-only / develop-only / `primary_project_code` shape.  
> **Authority:** `MASTER_PLAN.md` decides sequencing; this doc is the technical design for the
> Property Development + Revenue precondition graduation. Ontology minting (A81–A84) lands with the
> ontology desk on apply — provisional numbers confirmed free (highest minted = **A80**).
>
> **Respects (provisional):** A1, A5, A6, A9, A11, A67, A74, A78, **A81–A84** (below).  
> Graduates Future Domains (ONTOLOGY §9): **Revenue / Valuation / Portfolio** + **Construction /
> Project Delivery** in one spine — not two parallel products.
>
> **Sign-gate refinements (v2):** (1) `provenance_level='operator'` is an authenticated-operator
> write only — engine may never self-assign it; (2) asset-owned precondition rows are an
> **engine-derived cache** of title/geometry facts, never hand-set.

---

## 0. What stayed from the draft (directionally right)

| Principle | Keep |
|-----------|------|
| Hub-on-`property_assets` | Promote; never invent a second asset inventory |
| Promote-don’t-replace | Additive tables + ALTERs only |
| Preconditions-as-data | Durable, cited status — not read-time guesses |
| Evidence-gated `ok` | Fail-closed |
| Geometry only through link tables | No free-text coords on projects |
| `map_parcels.parcel_code` UNIQUE | `asset_map_parcels` FK valid as written |
| `clients(client_code)` | Real FK target (deploy_683 lineage) |
| A81–A84 free | A80 is highest minted (ONTOLOGY ~L864) |

---

## 1. Blocking conflicts — resolutions (must land in schema *and* narrative)

### 1.1 Population collision — `enroll_titles()` vs curated aggregates

**Conflict.** `revenue_engine.enroll_titles()` has a standing rule: *every title → one monetizable
asset* (`PA-<tct>`, `title_ref` 1:1). The draft also wanted *one curated asset → many titles via
`asset_titles`*. Shipping both without a discriminator makes T-52540 both an asset **and** a link
under another asset — two truths on the board.

**Resolution (uses existing column).** `property_assets.origin` already exists
(`'seed' | 'title'`, revenue_engine.py; extend with `'operator'`).

| `origin` | Role | Board role |
|----------|------|------------|
| **`title`** | **Title stub** — candidate inventory, 1:1 with a corpus title | **Fast-cash / inventory list only.** Never owns a develop project. Never is the parent of `asset_titles` components. |
| **`seed`** or **`operator`** | **Curated aggregate asset** — human- or seed-defined portfolio unit (building, resort site, estate package) | **Develop track + multi-title spine.** May own `asset_titles`, `asset_map_parcels`, and projects. |

**Rules (enforce in engine + truth_tests; document as law):**

1. `asset_titles` rows may only attach to assets with `origin IN ('seed','operator')`.
2. `development_projects.asset_code` may only reference curated assets (`origin IN ('seed','operator')`).
3. Title stubs (`origin='title'`) remain the `enroll_titles()` population; their monetization plan stays
   the ephemeral-or-ledger path for **sale/lease** readiness on that single title — they do **not**
   become components of each other.
4. When a curated asset claims a title via `asset_titles`, the stub `PA-<tct>` **may still exist**
   (inventory continuity) but is marked relationship-aware on the board:
   - board line for stub: `component_of: <curated_asset_code>` when a curated link exists
   - develop readiness is **only** computed on the curated parent
5. Do **not** auto-delete stubs when linking — deletion loses the 1:1 enroll surface; link + decorate.

**Say this out loud in every board UI header:**  
*“Inventory = all assets. Develop = curated only. Stubs = one-title cash candidates.”*

### 1.2 Two brains, one board — generalize the ledger to all four modes

**Conflict.** `_assess()` computes sale / lease / develop / mineral at **read time**. A develop-only
persisted ledger would make develop durable+cited while sale/lease/mineral stay guessed — two
epistemologies on one board.

**Resolution.** One table family: **`asset_preconditions`** (name chosen to signal “not develop-silo”),
keyed by **owner + mode + code**, covering all four modes. Develop is simply the **first mode lit
with real evidence**; other modes start as engine-backfilled rows (status may still be `unknown` /
`todo`) so the board has **one read path**.

This is the honest graduation of:

- ONTOLOGY **§8.8 Revenue / Valuation / Portfolio** (dormant business layer)
- ONTOLOGY **§9 Future Domains** — **Construction / Project Delivery** *and* **Revenue / Valuation**

`revenue_engine._assess()` becomes a **writer/reconciler** into the ledger, not a second truth source.
CLI `board` reads **only** the ledger (+ joins for display).

### 1.3 Precondition ownership — asset vs project (polymorphic owner)

**Conflict.** `secure_tenure` and `survey_geometry` are **asset facts**. `capital_partner`,
`feasibility`, and most **permits** are **project facts**. Hanging everything on
`development_projects` duplicates tenure across two projects (sale + develop) and allows disagreement.

**Resolution — polymorphic owner on the ledger:**

```
owner_kind  ∈  {'asset','project'}
owner_code  =  asset_code | project_code
```

| Codes | Owner | Why |
|-------|--------|-----|
| `marketable_title` / `secure_tenure` | **asset** | Title state of the land unit |
| `survey_geometry` | **asset** | Plottable boundary of the land unit |
| `possession` (lease mode) | **asset** | Control of the unit |
| `seller_authority` | **asset** | Who may alienate |
| `usable` | **asset** | Habitability / buildability of the unit |
| `permits` (bundle status) + permit rows | **project** | Applications are for a *use*, not bare land |
| `capital_partner` | **project** | JV is per deal |
| `feasibility` | **project** | Return case is per deal |
| `buyer_price` / `tenant` / `operator` | **project** (or asset for pure lease-ops later) | Counterparty is deal-scoped |
| `tax_clearance` / `registrable` | **asset** or **project** — **Sprint-1 rule:** store on **asset** when title-bound; project may *reference* asset status in display, never copy a divergent `ok` |

**Forbid:** storing `secure_tenure` or `survey_geometry` with `owner_kind='project'`.  
CHECK or engine refuse-list + truth_test.

**Project board display:** joins project-level rows **plus** the parent asset’s asset-level rows
for the active mode (no duplicated storage).

### 1.4 Asset-owned rows are a derived cache (not a second SoR)

**Latent reopen.** Even after moving tenure off the project, the ledger keys asset-owned rows by
`(owner_kind, owner_code, mode, code)`. The single fact “title is clean” would otherwise be stored
as independent mode-scoped rows — e.g. `(asset, develop, secure_tenure)` and
`(asset, sale, marketable_title)` — both projections of the same `title_status`. If title clouds,
both must flip together; if they can be hand-edited, they **drift** — project-level duplication
reincarnated across modes on the asset.

**Resolution — declare by construction:**

| Layer | Role |
|-------|------|
| **Source of truth** | Asset real facts: worst-of `asset_titles.title_status` / `property_assets.title_status`; map geometry via `asset_map_parcels` → `map_parcels.accuracy_tier` + geom; possession / authority fields on the asset |
| **Ledger asset-owned rows** | **Engine-derived materialization** (cache) for board/join speed — **sole writer = engine recompute**, never hand-set, never operator-attested `ok` |
| **Recompute** | Atomic per asset: derive all mode-scoped asset-owned codes for that asset in one pass so they cannot disagree |

**Asset-owned codes (derived cache — engine sole writer):**  
`secure_tenure`, `marketable_title`, `survey_geometry`, `possession`, `seller_authority`,
`registrable`, `tax_clearance` (when title-bound), `usable`, `mineral_rights` (when derived from
asset/controlling matter).

**Project-owned / sourcing codes (may be operator-attested):**  
`capital_partner`, `feasibility`, `buyer_price`, `tenant`, `lease_instrument`, `collection`,
`permits` (bundle — or derived from `development_permits` by engine), `operator` (mineral
counterparty), and other deal-scoping inputs with **no** deterministic corpus origin.

Composes with §6 write-path rules: **operator `ok` is legal only for sourcing codes** that lack a
deterministic origin — **never** for the asset-owned cache codes above.

---

## 2. Corrections vs live schema (draft bugs fixed)

| Draft said | Live / correct |
|------------|----------------|
| Backfill `CASE case_file WHEN 'MWK-001' THEN 'MWK'` | Use **`_client_of(matter_or_bucket)`** (deploy_716 lineage; used in deploy_733, V6/V7). Confirm live codes only via `SELECT client_code FROM clients` before apply — never hardcode a map that will rot. |
| `matter_code = case_file` | **Illegal collapse.** `case_file` = client-corpus bucket (e.g. `MWK-001`). Legal matter = e.g. `MWK-CV26360` (already on `controlling_matter` for litigation gates). Keep axes separate: optional `case_file` (existing), optional `controlling_matter` (existing), optional soft `matter_code` only when it is a real matter code — **do not** copy case_file into matter_code. |
| Soft skip FK on `asset_survey_parcels` | **Hard FK** → `parcels(id)`. `parcels.client_code` exists (deploy_733); same-client enforcement available. |
| Provenance 4-value including silent `operator` | **`operator` is already in the ontology geometry/facts vocab** (ONTOLOGY lists operator-attested alongside verified / inferred_*). This spine **registers use deliberately** for A82: operator-attested ≠ inferred. Align CHECK lists with the stack’s active set: `verified \| operator \| inferred_strong \| inferred_weak` (and document that `asserted` on `matter_facts` is a facts-table synonym path — do not invent a fifth fork on these tables without ontology desk). |
| Canonical name `AssetParcelLink → asset_titles` | **Doc bug.** AssetParcelLink → **`asset_map_parcels`**. AssetTitleLink → **`asset_titles`**. |

---

## 3. Design step-ups (enforcement + governance)

### 3.1 A82 as DB CHECK (fail-closed) — and who may write `operator`

Doctrine: provenance gates live in the DB (A78), not only in Python.

```sql
-- On asset_preconditions (and any twin):
CHECK (
  status <> 'ok'
  OR source_doc_id IS NOT NULL
  OR (evidence_ref IS NOT NULL AND evidence_ref <> '')
  OR provenance_level = 'operator'
)
```

**DB is the floor** on *shape* (`ok` needs evidence). It is **not** sufficient alone:  
`provenance_level='operator'` clears the CHECK **by itself**, so it is a **fail-closed bypass**
if any unauthenticated path can write that token. That is exactly the failure A78 legislates
against (“verified only via a traceable path, never by assertion or inference”).

**Therefore (law — enforced in engine + truth_test; optionally a write-path role later):**

| Writer | May set `status='ok'` when… | May set `provenance_level` |
|--------|----------------------------|----------------------------|
| **Engine / reconciler** | Only with `source_doc_id` **or** a **deterministic** `evidence_ref` (e.g. `title_status:clouded`, `map:PA-X:survey`) | **`inferred_*` only.** Must **never** self-assign `operator` or `verified` |
| **Operator-authenticated path** | Sourcing codes only (see §1.4); never asset-owned cache codes | **`operator` reserved for this path alone** |
| **Any machine write of `operator`** | — | **Bug, not a shortcut** — truth_test must fail the codebase if the engine upserts `operator`/`verified` |

See §6 for the contract row.

### 3.2 A81 isolation via ontology validator V12+ (not a bespoke trigger)

Cross-client link refusal follows the live pattern:

- `_client_of()` resolver  
- `ontology_reject` / holes logger  
- **V6/V7 shadow → block** (deploy_814, deploy_716; ALIGNMENT §9 flip protocol)

**V12 (provisional name):** shadow `log` triggers on:

- `asset_titles` — link `client_code` must match asset `client_code`; title’s resolved client (via
  titles → case_file / matter path as available) must not cross  
- `asset_map_parcels` — `client_code` = asset = `map_parcels.client_code`  
- `asset_survey_parcels` — same vs `parcels.client_code`  
- `development_projects` / `development_permits` / `asset_preconditions` — declared client matches
  owner’s client  
- **`asset_preconditions` owner existence** — polymorphic `owner_code` has **no FK** (unavoidable
  with `owner_kind`). V12 must check that the owner **exists**
  (`owner_kind='asset'` → row in `property_assets`; `owner_kind='project'` → row in
  `development_projects`), **not only** cross-client match. Orphan `owner_code` → finding.
  Pair with truth_test `test_precondition_owner_exists` (orphan insert / dangling after delete).

Graduation: shadow soak → pre-flight → rolled-back exception test → approval → `block`.

### 3.3 Kill `primary_project_code` (no circular FK)

**Do not** add `property_assets.primary_project_code`.

- `development_projects.asset_code` → `property_assets` (many projects per curated asset)  
- `development_projects.is_primary boolean` + **partial unique index**  
  (same pattern as `uq_asset_titles_one_primary`):

```sql
CREATE UNIQUE INDEX uq_dev_projects_one_primary
  ON development_projects (asset_code)
  WHERE is_primary AND status = 'active';
```

Open Decision **#4 resolved:** many concurrent projects (sale + develop); one primary flag; no cycle.

### 3.4 A67 — timeline on the project (not only permit expiry)

A67: every active lifecycle object carries a forward timeline (or explicit dateless class).

`development_projects` is a lifecycle object. Add:

| Column | Role |
|--------|------|
| `next_milestone_date` | Forward date for pulse / digest — **canonical A67 feed** (partial index) |
| `next_milestone_label` | Human short label |
| `stage_target_dates` | JSONB optional detail store `{ "permitting": "2026-09-01", ... }` — operator-set |
| `dateless_class` | `needs_date \| watch \| n/a` when no forward date (honest gap, never fabricate) |

**Pulse wiring rule:** the calendar / pulse layer must read the **indexed**
`next_milestone_date` (and label). **Never** parse `stage_target_dates` JSONB as the A67 feed —
otherwise the pulse goes dark on the dates that matter. JSONB is a detail/history store only;
promoting a stage target into the pulse = copy into `next_milestone_*`.

**Permit `expires_on`** remains on `development_permits` as a **fact about the instrument**.  
Any “renew by / file by” **nudge** is derived into the **calendar / pulse layer** (calendar-is-the-pulse),
never invented as a second deadline truth only on the permit row.

### 3.5 `survey_geometry` — tier-aware (the connect-subsystems win)

Precondition code lives on the **asset**. Engine rule:

| Geometry state | Status | Reason |
|----------------|--------|--------|
| Linked `map_parcels` with `geom_geojson` and `accuracy_tier IN ('survey','ortho')` | **`ok`** | Placed survey-grade (or better) boundary |
| Only `rough` plotted geometry | **`todo`** | “Upgrade plot (survey/ortho)” |
| Links exist, no geom | **`todo`** | “Plot boundary” |
| No links | **`unknown`** | “No map parcel linked” |

This wires **mapping** (`map_parcels.accuracy_tier`) into the **money board** — entitled-on-paper vs
unplottable-on-ground becomes visible without a second product.

---

## 4. Concept registry (corrected)

| Concept | Canonical table | Notes |
|---------|-----------------|-------|
| PropertyAsset | `property_assets` | Hub; **discriminate** by `origin` |
| TitleStub | `property_assets` where `origin='title'` | enroll_titles population |
| CuratedAsset | `property_assets` where `origin IN ('seed','operator')` | Aggregates + projects |
| AssetTitleLink | `asset_titles` | Curated → many titles |
| AssetParcelLink | **`asset_map_parcels`** | Curated → many map lots |
| AssetSurveyLink | `asset_survey_parcels` | Curated → `parcels.id` (hard FK) |
| DevelopmentProject | `development_projects` | Deal track; `is_primary`; A67 dates |
| Precondition | **`asset_preconditions`** | All modes; polymorphic owner |
| DevelopmentPermit | `development_permits` | Project-scoped instruments |
| MappedProperty | `map_parcels` | Existing; optional soft `asset_code` |
| SurveyGeometry | `parcels` | Existing |

---

## 5. Schema (reconciled DDL sketch)

### 5.1 `property_assets` — promote hub (no primary_project_code)

```sql
ALTER TABLE property_assets
  -- NULLABLE intentionally (degrade-don't-crash, same reasoning as parcels.client_code
  -- deploy_733): a stub whose client can't resolve must still insert; isolation stays
  -- dark for that row rather than blocking the write. Do NOT add NOT NULL in Sprint 1.
  ADD COLUMN IF NOT EXISTS client_code text,
  ADD COLUMN IF NOT EXISTS stage text
    DEFAULT 'inventory'
    CHECK (stage IN (
      'inventory','assessing','entitling','financing','permitting',
      'ready','under_construction','operating','exited','blocked'
    )),
  ADD COLUMN IF NOT EXISTS provenance_level text
    DEFAULT 'inferred_strong'
    CHECK (provenance_level IN (
      'verified','operator','inferred_strong','inferred_weak'
    )),
  ADD COLUMN IF NOT EXISTS source_doc_id int,
  ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now();

-- origin: ensure 'operator' is allowed (existing seed|title)
-- If a CHECK exists on origin, widen it; else document convention:
--   origin IN ('seed','title','operator')

CREATE INDEX IF NOT EXISTS idx_property_assets_client ON property_assets (client_code);
CREATE INDEX IF NOT EXISTS idx_property_assets_origin ON property_assets (origin);
CREATE INDEX IF NOT EXISTS idx_property_assets_stage  ON property_assets (stage);

-- Backfill only AFTER dry-run preflight (§11 step 1) proves resolution rates.
-- NO case_file→matter collapse, NO hardcoded MWK map:
--   UPDATE property_assets
--   SET client_code = COALESCE(
--         client_code,
--         _client_of(controlling_matter),
--         _client_of(case_file)
--       )
--   WHERE client_code IS NULL;
-- Report remaining NULLs; do not invent. NULL isolation = dark, not crash.
```

**Axes (do not collapse):**

| Column | Meaning |
|--------|---------|
| `case_file` | Corpus / client bucket (`MWK-001`, `Paracale-001`) |
| `controlling_matter` | Litigation / legal gate matter when title is clouded |
| `client_code` | Isolation wall via `_client_of` resolution — **nullable** until resolved |

### 5.2 `development_projects`

```sql
CREATE TABLE IF NOT EXISTS development_projects (
  project_code         text PRIMARY KEY,
  client_code          text NOT NULL REFERENCES clients(client_code),
  label                text NOT NULL,
  asset_code           text NOT NULL REFERENCES property_assets(asset_code),
  mode                 text NOT NULL DEFAULT 'develop'
    CHECK (mode IN ('develop','sale','lease','mineral')),
  stage                text NOT NULL DEFAULT 'assessing'
    CHECK (stage IN (
      'assessing','entitling','financing','permitting',
      'ready','under_construction','operating','exited','blocked'
    )),
  is_primary           boolean NOT NULL DEFAULT false,
  objective            text,
  target_use           text,
  gating_precondition  text,              -- denorm: first non-ok across joined chain
  readiness_ratio      numeric(5,4),
  -- A67 pulse fields
  next_milestone_date  date,
  next_milestone_label text,
  stage_target_dates   jsonb,
  dateless_class       text
    CHECK (dateless_class IS NULL OR dateless_class IN (
      'needs_date','watch','n/a'
    )),
  status               text NOT NULL DEFAULT 'active'
    CHECK (status IN ('active','paused','done','cancelled')),
  provenance_level     text NOT NULL DEFAULT 'operator'
    CHECK (provenance_level IN (
      'verified','operator','inferred_strong','inferred_weak'
    )),
  source_doc_id        int,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now()
);

-- Curated-asset-only: enforced in engine + truth_test
-- (optional DB trigger: reject if property_assets.origin = 'title')

CREATE UNIQUE INDEX IF NOT EXISTS uq_dev_projects_one_primary
  ON development_projects (asset_code)
  WHERE is_primary AND status = 'active';

CREATE INDEX IF NOT EXISTS idx_dev_projects_client ON development_projects (client_code);
CREATE INDEX IF NOT EXISTS idx_dev_projects_asset  ON development_projects (asset_code);
CREATE INDEX IF NOT EXISTS idx_dev_projects_stage  ON development_projects (stage);
CREATE INDEX IF NOT EXISTS idx_dev_projects_milestone
  ON development_projects (next_milestone_date)
  WHERE status = 'active' AND next_milestone_date IS NOT NULL;
```

### 5.3 Link tables

```sql
CREATE TABLE IF NOT EXISTS asset_titles (
  id               bigserial PRIMARY KEY,
  asset_code       text NOT NULL REFERENCES property_assets(asset_code) ON DELETE CASCADE,
  client_code      text NOT NULL REFERENCES clients(client_code),
  title_no         text NOT NULL,
  role             text NOT NULL DEFAULT 'component'
    CHECK (role IN ('primary','component','adjacent','claim','encumbering')),
  title_status     text,
  is_primary       boolean NOT NULL DEFAULT false,
  provenance_level text NOT NULL DEFAULT 'inferred_strong'
    CHECK (provenance_level IN (
      'verified','operator','inferred_strong','inferred_weak'
    )),
  source_doc_id    int,
  note             text,
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (asset_code, title_no)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_asset_titles_one_primary
  ON asset_titles (asset_code) WHERE is_primary;

-- asset_titles.asset_code must be curated: engine + truth_test
-- (optional trigger refuse origin='title' parents)

CREATE TABLE IF NOT EXISTS asset_map_parcels (
  id               bigserial PRIMARY KEY,
  asset_code       text NOT NULL REFERENCES property_assets(asset_code) ON DELETE CASCADE,
  client_code      text NOT NULL REFERENCES clients(client_code),
  parcel_code      text NOT NULL REFERENCES map_parcels(parcel_code),
  role             text NOT NULL DEFAULT 'site'
    CHECK (role IN ('site','access','buffer','claim','exclude')),
  provenance_level text NOT NULL DEFAULT 'operator'
    CHECK (provenance_level IN (
      'verified','operator','inferred_strong','inferred_weak'
    )),
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (asset_code, parcel_code)
);

CREATE TABLE IF NOT EXISTS asset_survey_parcels (
  id               bigserial PRIMARY KEY,
  asset_code       text NOT NULL REFERENCES property_assets(asset_code) ON DELETE CASCADE,
  client_code      text NOT NULL REFERENCES clients(client_code),
  survey_parcel_id int NOT NULL REFERENCES parcels(id),  -- HARD FK
  role             text NOT NULL DEFAULT 'boundary',
  provenance_level text NOT NULL DEFAULT 'inferred_strong'
    CHECK (provenance_level IN (
      'verified','operator','inferred_strong','inferred_weak'
    )),
  source_doc_id    int,
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (asset_code, survey_parcel_id)
);

-- Soft denorm on map layer (Open Decision #3):
ALTER TABLE map_parcels
  ADD COLUMN IF NOT EXISTS asset_code text;  -- NO hard FK in Sprint 1
CREATE INDEX IF NOT EXISTS idx_map_parcels_asset ON map_parcels (asset_code);
```

### 5.4 Generalized precondition ledger

> **Law on this table (read before writing rows):**
>
> 1. **Asset-owned codes** (`secure_tenure`, `marketable_title`, `survey_geometry`, `possession`,
>    `seller_authority`, `registrable`, and other §1.4 cache codes) are an **engine-derived
>    materialization** of the asset’s real facts (`title_status` / geometry / possession fields).
>    **Sole writer = engine recompute** (atomic per asset across all modes). **Never hand-edited.
>    Never operator-attested `ok`.** Source of truth is the asset/title/geometry layer; these rows
>    are a **cache** so the board has one join path.
> 2. **Project-owned sourcing codes** (`capital_partner`, `feasibility`, `buyer_price`, `tenant`,
>    …) may be operator-attested; A82 `operator` token is legal **only** for these, via an
>    operator-authenticated write path (§3.1 / §6).
> 3. Mode-scoped asset-owned rows for the same underlying fact (e.g. develop/`secure_tenure` vs
>    sale/`marketable_title`) are **projections of one recompute** — they must not be independently
>    editable or they re-open cross-mode drift.

```sql
CREATE TABLE IF NOT EXISTS asset_preconditions (
  id                 bigserial PRIMARY KEY,
  -- Nullable only if we ever need dark isolation; prefer NOT NULL when owner has client_code.
  -- For asset rows, copy from property_assets.client_code (may be NULL → row client_code NULL
  -- only if we drop NOT NULL; Sprint 1: require client when owner has one; allow NULL only
  -- when asset.client_code IS NULL — implement as trigger or app rule; keep FK when non-null.
  client_code        text REFERENCES clients(client_code),

  -- Polymorphic owner (NO FK — V12 + truth_test enforce existence; see §3.2)
  owner_kind         text NOT NULL CHECK (owner_kind IN ('asset','project')),
  owner_code         text NOT NULL,   -- asset_code | project_code

  mode               text NOT NULL
    CHECK (mode IN ('develop','sale','lease','mineral')),
  code               text NOT NULL,   -- secure_tenure | survey_geometry | permits | ...
  label              text NOT NULL,
  sort_order         int NOT NULL DEFAULT 0,

  status             text NOT NULL DEFAULT 'unknown'
    CHECK (status IN ('ok','blocked','todo','unknown')),
  reason             text,
  next_move          text,

  evidence_kind      text
    CHECK (evidence_kind IS NULL OR evidence_kind IN (
      'title_status','matter','permit','doc','operator',
      'geometry','finance','external'
    )),
  evidence_ref       text,
  source_doc_id      int,
  provenance_level   text NOT NULL DEFAULT 'inferred_weak'
    CHECK (provenance_level IN (
      'verified','operator','inferred_strong','inferred_weak'
    )),

  recheck_condition  text,            -- A74
  last_assessed_at   timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),

  UNIQUE (owner_kind, owner_code, mode, code),

  -- A82 fail-closed (shape only — who may write 'operator' is engine/path law, §3.1)
  CONSTRAINT asset_preconditions_ok_requires_evidence CHECK (
    status <> 'ok'
    OR source_doc_id IS NOT NULL
    OR (evidence_ref IS NOT NULL AND btrim(evidence_ref) <> '')
    OR provenance_level = 'operator'
  )
);

CREATE INDEX IF NOT EXISTS idx_asset_pre_owner
  ON asset_preconditions (owner_kind, owner_code);
CREATE INDEX IF NOT EXISTS idx_asset_pre_status
  ON asset_preconditions (status);
CREATE INDEX IF NOT EXISTS idx_asset_pre_client
  ON asset_preconditions (client_code);

-- Ownership placement guard (codes that MUST be asset-owned)
-- Prefer a small trigger or engine refuse-list; example CHECK is incomplete for freeform codes.
-- Truth_test hard-fails if secure_tenure|survey_geometry|possession stored under project.
-- Truth_test hard-fails if engine path assigns provenance_level IN ('operator','verified').
-- Truth_test hard-fails orphan owner_code (V12 companion).
```

**Mode seed catalogs** (engine `--ensure-catalog`):

| Mode | Asset-owned codes (**derived cache**) | Project-owned codes (**sourcing**; operator ok allowed) |
|------|----------------------------------------|---------------------------------------------------------|
| **develop** | `secure_tenure`, `survey_geometry` | `permits`, `capital_partner`, `feasibility` |
| **sale** | `marketable_title`, `seller_authority`, `registrable`, `tax_clearance` | `buyer_price` |
| **lease** | `possession`, `usable` | `tenant`, `lease_instrument`, `collection` |
| **mineral** | `mineral_rights` | `permit`, `operator` (counterparty code — not provenance tier) |

(Align labels with existing `revenue_engine.PRECONDS` / `NEXT_MOVE`; add `survey_geometry` only on develop.)

**Engine `ok` evidence for derived cache rows:** use deterministic `evidence_ref` strings
(e.g. `title_status:clean`, `title_status:clouded@MWK-CV26360`, `map:MWK-BALANE:survey`) and/or
`source_doc_id` when a doc backs the fact — **not** `provenance_level='operator'`.

### 5.5 `development_permits`

```sql
CREATE TABLE IF NOT EXISTS development_permits (
  permit_code      text PRIMARY KEY,
  project_code     text NOT NULL REFERENCES development_projects(project_code) ON DELETE CASCADE,
  client_code      text NOT NULL REFERENCES clients(client_code),
  asset_code       text REFERENCES property_assets(asset_code),
  authority        text NOT NULL,
  permit_type      text NOT NULL,
  status           text NOT NULL DEFAULT 'not_started'
    CHECK (status IN (
      'not_started','preparing','filed','under_review',
      'granted','denied','expired','waived','not_required'
    )),
  filed_on         date,
  decided_on       date,
  expires_on       date,              -- instrument fact; pulse derives via calendar layer
  reference_no     text,
  source_doc_id    int,
  provenance_level text NOT NULL DEFAULT 'operator'
    CHECK (provenance_level IN (
      'verified','operator','inferred_strong','inferred_weak'
    )),
  note             text,
  recheck_condition text,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);
```

---

## 6. Engine contract (`development_engine.py` / graduated `revenue_engine`)

| Concern | Rule |
|---------|------|
| Single epistemology | Board reads **`asset_preconditions` only** |
| `_assess` / recompute role | **Sole writer** of asset-owned (cache) rows; upserts project-owned when deriving from permits/docs; never a parallel read-time truth |
| **A82 write split (critical)** | Engine may set `status='ok'` **only** with `source_doc_id` **or** a **deterministic** `evidence_ref`. Engine may **never** self-assign `provenance_level IN ('operator','verified')`. **`operator` is reserved for an operator-authenticated write path.** A machine write that sets `operator` is a **bug**, not a shortcut (A78). |
| **Operator `ok` scope** | Legal **only** on project-owned **sourcing** codes (`capital_partner`, `feasibility`, `buyer_price`, `tenant`, …). **Forbidden** on asset-owned cache codes (`secure_tenure`, `survey_geometry`, `possession`, `marketable_title`, `seller_authority`, `registrable`, …). |
| Asset-owned cache | Derived from title_status / geometry / asset fields; **atomic recompute per asset** across all modes so mode-scoped projections cannot drift; **never hand-edited** |
| Develop projects | Only curated assets (`origin IN ('seed','operator')`) |
| Title stubs | Fast-cash board; if linked under curated, show `component_of` |
| Stage changes | **Engine suggests**; operator commits (Open Decision #2) |
| A84 `ready` | Suggested only when all required codes for the project’s mode are `ok` (asset-owned ∪ project-owned) |
| Recompute | Idempotent; sets `gating_precondition`, `readiness_ratio`, `last_assessed_at`; refreshes all asset-owned mode rows for the asset together |
| Geometry | Tier-aware rule §3.5; `ok` via deterministic `evidence_ref` + `inferred_*` |
| Tenure | Worst-of linked `asset_titles.title_status` else `property_assets.title_status`; same sole-writer rule |
| Client | Always `_client_of` / declared `client_code`; never CASE maps; NULL client on asset = dark isolation, not invent |
| Pulse | Feed A67 from `next_milestone_date` only — never JSONB `stage_target_dates` |

**CLI sketch:**

```
python3 scripts/development_engine.py --ensure-schema
python3 scripts/development_engine.py --ensure-catalog
python3 scripts/development_engine.py --recompute [--asset X | --project Y]
python3 scripts/development_engine.py --board [--curated | --stubs | --all]
python3 scripts/development_engine.py --seed-project DEV-... --asset PA-... --mode develop
# Operator-authenticated path (separate entry — not the reconciler):
#   --operator-set --project Y --code capital_partner --status ok --by <principal>
```

`revenue_engine.board` either becomes a thin wrapper over this or is retired for the money board path
(operator pick at implement time — prefer **one** CLI entrypoint).

---

## 7. Views

### 7.1 Develop / deal board (curated projects)

Joins project-level preconditions **plus** parent asset’s asset-level preconditions for `p.mode`.

```sql
CREATE OR REPLACE VIEW v_development_board AS
SELECT
  p.project_code,
  p.client_code,
  p.label,
  p.asset_code,
  a.label AS asset_label,
  a.origin AS asset_origin,
  a.title_ref,
  a.title_status,
  p.mode,
  p.stage,
  p.is_primary,
  p.gating_precondition,
  p.readiness_ratio,
  p.next_milestone_date,
  p.next_milestone_label,
  p.dateless_class,
  p.status,
  (SELECT count(*) FROM asset_preconditions x
    WHERE x.owner_kind='project' AND x.owner_code=p.project_code
      AND x.mode=p.mode AND x.status='ok') AS project_pre_ok,
  (SELECT count(*) FROM asset_preconditions x
    WHERE x.owner_kind='asset' AND x.owner_code=p.asset_code
      AND x.mode=p.mode AND x.status='ok') AS asset_pre_ok,
  (SELECT bool_or(mp.geom_geojson IS NOT NULL AND mp.accuracy_tier IN ('survey','ortho'))
     FROM asset_map_parcels amp
     JOIN map_parcels mp ON mp.parcel_code = amp.parcel_code
    WHERE amp.asset_code = p.asset_code) AS has_survey_grade_geom,
  p.updated_at
FROM development_projects p
JOIN property_assets a ON a.asset_code = p.asset_code
WHERE p.status = 'active'
  AND a.origin IN ('seed','operator');
```

### 7.2 Inventory / fast-cash (includes stubs)

```sql
CREATE OR REPLACE VIEW v_asset_inventory AS
SELECT
  a.*,
  (SELECT at.asset_code FROM asset_titles at
    WHERE at.title_no = a.title_ref
      AND at.asset_code <> a.asset_code
    LIMIT 1) AS component_of_curated,
  (SELECT status FROM asset_preconditions ap
    WHERE ap.owner_kind='asset' AND ap.owner_code=a.asset_code
      AND ap.mode = COALESCE(a.modes[1],'sale')
      AND ap.code IN ('marketable_title','secure_tenure')
    ORDER BY ap.updated_at DESC LIMIT 1) AS tenure_status
FROM property_assets a;
```

---

## 8. Provisional invariants A81–A84

| ID | Statement | Enforcement |
|----|-----------|-------------|
| **A81** | Asset / project / precondition / permit / link rows carry declared `client_code`; cross-client title or parcel links are refused. | V12 shadow→block via ontology_validator + `_client_of` |
| **A82** | Precondition `status='ok'` requires evidence: `source_doc_id` OR non-empty `evidence_ref` OR `provenance_level='operator'`. **`operator`/`verified` may only be written by an operator-authenticated path; engine may only `ok` via doc or deterministic `evidence_ref` + `inferred_*`.** Asset-owned cache codes never receive operator `ok`. | **DB CHECK** + engine write-path law + truth_tests |
| **A83** | Geometry for an asset only via `asset_map_parcels` / `asset_survey_parcels` (and optional soft `map_parcels.asset_code`); no free-text coordinates on projects. | truth_test + no columns for free coords |
| **A84** | Project stage `ready` only when all required preconditions for its mode (asset-owned ∪ project-owned) are `ok`. | Engine-suggest + truth_test (Sprint 1); DB trigger optional later |

**MASTER_PLAN line (when executing):**  
`Property Development / Revenue spine. Respects: A5, A9, A11, A67, A74, A78, A81–A84`

---

## 9. Open decisions — closed from repo + review

| # | Question | Answer |
|---|----------|--------|
| 1 | Client codes for MWK/Paracale | **Do not hardcode.** Use `_client_of()`. Confirm live values with `ssh landtek` → `psql` → `SELECT client_code FROM clients` before apply. |
| 2 | Stage owner | **Engine suggests; operator commits.** Matches shadow-first + A84-in-engine. |
| 3 | `map_parcels.asset_code` FK | **Soft first.** Consistent with soft `matter_code` / `title_no` on that table. |
| 4 | Project cardinality | **Many projects; `is_primary` partial unique; no `primary_project_code`.** |
| 5 | A81–A84 numbers | **Free** (A80 max minted). Desk ratifies on land. |

---

## 10. Explicit non-goals (Sprint 1)

- Tenants / rent rolls / maintenance (Property Mgmt v2.0 still later)  
- CAPEX / full finance product (scaffold `finance_transactions` may link later)  
- Client-facing map publish (A11 held)  
- Auto stage transitions without operator  
- LLM “development agent” loop  
- Deleting title stubs when curated links form  
- Collapsing `case_file` and `matter_code`  

---

## 11. Implementation sequence (when operator says go)

1. **Preflight live (mandatory before any DDL)** — this is the only place the design still touches
   facts not fully knowable from the repo:
   - `SELECT client_code FROM clients ORDER BY 1;`
   - `SELECT origin, count(*) FROM property_assets GROUP BY 1;`
   - **Dry-run the backfill** (do not apply yet). `_client_of()` takes a matter/code string;
     whether it resolves a **bucket** like `MWK-001` depends on its lookup tables — do not assume:
     ```sql
     SELECT case_file, controlling_matter,
            _client_of(controlling_matter) AS via_matter,
            _client_of(case_file)          AS via_bucket
       FROM property_assets;
     -- Then count NULLs:
     SELECT count(*) AS total,
            count(*) FILTER (WHERE _client_of(controlling_matter) IS NULL
                               AND _client_of(case_file) IS NULL) AS unresolved
       FROM property_assets;
     ```
   - Only after seeing resolution rates decide COALESCE order / whether orphan stubs stay
     `client_code NULL` (allowed — degrade-don’t-crash).
2. Migration: ALTERs + tables + CHECKs + views (no V12 block yet).  
   Keep `property_assets.client_code` **nullable**.  
3. `development_engine.py`: ensure-catalog, **atomic asset recompute** (cache rows), board (single
   epistemology), operator-set path separate from reconciler.  
4. Wire `revenue_engine` board → ledger writer / thin wrapper.  
5. Truth tests: population discriminator; A82 CHECK; **engine never writes operator/verified**;
   **asset-owned never hand/operator ok**; ownership placement; **orphan owner_code**;
   curated-only projects; geometry tier rule; atomic multi-mode tenure flip.  
6. Ontology desk: mint A81–A84 + V12 shadow spec (isolation **+ owner existence**); Future Domain
   graduation notes §8.8 / §9.  
7. Ops surface later: `/ops/development` + digest slice + A67 pulse feed from
   **`next_milestone_date` only**.  

**Do not** ship project-only develop-only ledger first — that hardens the split this doc exists to prevent.

---

## 12. ER (reconciled)

```
clients
  │
  ├─ property_assets ──── origin=title  → title stubs (fast-cash)
  │       │
  │       └─ origin∈{seed,operator} → curated
  │              │
  │              ├─ asset_titles ──────────► titles (soft title_no)
  │              ├─ asset_map_parcels ─────► map_parcels (FK parcel_code)
  │              ├─ asset_survey_parcels ──► parcels (FK id)
  │              │
  │              └─ development_projects (many; is_primary)
  │                     │
  │                     └─ development_permits
  │
  └─ asset_preconditions
         owner_kind=asset   → DERIVED CACHE (engine sole writer)
                              tenure / geometry / possession / …
         owner_kind=project → SOURCING (operator ok allowed)
                              permits bundle / capital / feasibility / …
         modes: develop | sale | lease | mineral
         (asset-owned multi-mode rows = one atomic recompute, not independent facts)
```

---

## 13. Changelog vs prior chat draft

| Topic | Was | Now |
|-------|-----|-----|
| Populations | Unstated dual mint | **`origin` discriminator** stubs vs curated |
| Ledger | develop-only on project | **All four modes; polymorphic owner** |
| Tenure storage | On project | **Asset-owned derived cache** (engine sole writer) |
| Client backfill | Hardcoded CASE | **`_client_of()`** + dry-run preflight |
| matter vs case_file | Collapsed | **Axes kept separate** |
| Survey link FK | Soft optional | **Hard FK to parcels** |
| Provenance | Silent operator | **Deliberate stack vocab** |
| AssetParcelLink | Wrong table name | **`asset_map_parcels`** |
| A82 | Engine only | **DB CHECK** + **write-path split** (engine ≠ operator) |
| A81 | Bespoke trigger later | **V12** isolation **+ owner existence** |
| primary_project_code | Circular FK | **`is_primary` on project** |
| A67 | Permit expiry only | **Project `next_milestone_*`** (pulse never JSONB) |
| survey_geometry | New code, thin rule | **Tier-aware mapping join** |

### v2 (sign-gate) vs v1 reconciled doc

| Topic | v1 risk | v2 law |
|-------|---------|--------|
| `provenance_level='operator'` | Engine could self-assign → A82 bypass | Engine never writes `operator`/`verified`; operator path only |
| Asset-owned multi-mode rows | Independent hand-set → cross-mode drift | Derived cache; atomic recompute; no hand/operator ok |
| Polymorphic owner | Client match only | V12 + truth_test: **owner must exist** |
| `client_code` | Implied strict | **NULLABLE** on assets; degrade-don’t-crash |
| Preflight | `SELECT clients` only | **Dry-run** `_client_of` on case_file + controlling_matter; count NULLs |
| Pulse | Unspecified feed | **`next_milestone_date` only**, not `stage_target_dates` JSONB |

---

*End of design (v2). Ready for operator sign → §11 step 1 preflight (dry-run) → migration PR.*

