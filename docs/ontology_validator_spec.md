# Spec — `ontology_validator` (gate extension)

> **Status: APPLIED IN SHADOW (deploy_691, 2026-07-05).** V1/V3/V4 are live on the DB in `log` mode —
> they log to `holes_findings` and **block nothing**. Enforcement (`block` mode) still requires Jonathan's
> explicit go after a 72h clean shadow run (see §5, §7). The DDL sketch in §6 is superseded by the
> applied migration `migrations/apply_deploy_691_ontology_validator.py` (idempotent; `--rollback` reverts).
>
> **Origin.** Graded response to the "Agent-Native Ontology Enforcement" proposal (see `ARCHITECTURE.md`
> §8). We adopt its *intent* — reject non-conforming agent output at write time — but **keep enforcement
> in the database**, not in a Python/Pydantic layer, because the DB gate is the only layer that binds
> *every* writer including Leo's n8n LangChain.js path. Moving the gate into Python would silently exempt
> the most hallucination-prone writer. That is the whole point.

---

## 1. What problem this solves

Today the provenance gate answers *"is this fact grounded?"* (does it cite a real doc + excerpt).
It does **not** answer *"is this fact the right shape?"* — e.g. a fact written into a **legacy/drift
table** (`chain_of_title`, `cases`, `finance_transactions`), a matter row whose `client_code` doesn't
match its cited document's client (the A5 isolation gap), or an enum value outside the ontology
(`provenance_level = 'pretty_sure'`). The `ontology_validator` is the **shape gate** that sits beside the
existing **grounding gate**.

It is `ONTOLOGY.md` turned from documentation into a runtime guardrail — exactly the proposal's
"game-changer," done without a framework switch.

---

## 2. Design principles (non-negotiable)

1. **DB-resident.** Implemented as Postgres `CHECK` constraints + `BEFORE INSERT/UPDATE` triggers +
   validation views. No new Python framework. Mirrors the deploy_341 pattern.
2. **Fail to `holes/`, never crash.** A non-conforming write is **rejected with a reason** and routed to
   the existing `holes` quarantine — the degrade-don't-crash invariant
   (`memory/feedback-autonomous-stack-degrade-gracefully.md`). It must never take down a writer.
3. **Additive + idempotent.** `CREATE ... IF NOT EXISTS`, `ON CONFLICT DO NOTHING`. Reversible in one
   `DROP TRIGGER`. No existing row is mutated on install.
4. **Zero false positives before enforcement.** Ship in **shadow mode** first (log-only), measure, then
   flip to blocking. Same calibration bar as the dossier-verify gate.

---

## 3. The five checks (v1)

| # | Check | Rule | Action on fail |
|---|---|---|---|
| V1 | **No writes to drift tables** | INSERT into `chain_of_title` / `cases` / `finance_transactions` | reject → `holes`, reason `ONTOLOGY_DRIFT_TABLE` |
| V2 | **Enum conformance** | `provenance_level ∈ {verified,inferred_strong,inferred_weak}`; `accuracy_tier ∈ {rough,survey,ortho}`; etc. | reject, reason `ONTOLOGY_BAD_ENUM` |
| V3 | **Grounding shape** | `provenance_level='verified'` ⇒ `source_doc_id`/`source_id` NOT NULL **and** excerpt/quote NOT NULL | reject, reason `ONTOLOGY_UNGROUNDED_VERIFIED` |
| V4 | **Client isolation (A5)** | a `matter_facts`/`title_*` row whose cited doc's `matter_code` client ≠ the row's matter's `client_code` | **shadow-log** first (this will surface real contamination), reason `ONTOLOGY_CLIENT_CROSS` |
| V5 | **Lifespan (already live)** | delegate to `enforce_actor_lifespan_on_instruments` | (existing) |

V1–V3 are safe to enforce immediately (they only catch clearly-wrong writes). **V4 ships shadow-only**
until the contamination it finds is triaged — it is a detector before it is a gate.

---

## 4. Wire-protocol integration (agent outputs)

Structured agent output (Leo tool-calls, `verify_worker`, Workflow `schema:` agents) already lands via
SQL INSERT. The validator binds at the **table**, so *no agent code changes are required* — a
non-conforming tool-call fails its INSERT and the caller sees the rejection, exactly like a provenance
violation today. For the n8n path, the failing node uses the existing `onError=continueRegularOutput`
pattern so the exec continues and logs (never a hard stop reaching Jonathan's phone).

Optional (v2): a thin read-only `ontology_lint(json)` SQL function agents *may* call pre-write to
self-check — but the binding guarantee stays at the table, so a forgetful agent still can't slip past.

---

## 5. Rollout (wartime-safe)

1. **Shadow (day 1):** install triggers in `mode='log'` → write rejections to `holes_findings` with
   reason codes; block nothing. Run ≥72h.
2. **Measure:** `SELECT reason, count(*) FROM holes_findings WHERE finding_kind='ontology' GROUP BY 1`.
   Confirm V1–V3 false-positive rate = 0.
3. **Enforce V1–V3:** flip to `mode='block'`. Leave **V4 in shadow** and triage contamination separately.
4. **Post-Aug-12:** enforce V4 once the corpus `case_file`/`matter_code` isolation (A5) is FK-hardened.

---

## 6. DDL — ready to apply, NOT YET APPLIED

```sql
-- migrations/apply_deploy_NNN_ontology_validator.sql   (SHADOW MODE)
-- Idempotent. Reversible: DROP the triggers. Applies nothing destructive.

CREATE TABLE IF NOT EXISTS ontology_validator_config (
  check_code text PRIMARY KEY,     -- V1..V5
  mode       text NOT NULL DEFAULT 'log' CHECK (mode IN ('log','block','off'))
);
INSERT INTO ontology_validator_config(check_code,mode) VALUES
  ('V1','log'),('V2','log'),('V3','log'),('V4','log')
ON CONFLICT DO NOTHING;

-- reason-logging helper → routes to existing holes quarantine
CREATE OR REPLACE FUNCTION ontology_reject(_reason text, _detail text)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO holes_findings(finding_kind, reason, detail, created_at)
  VALUES ('ontology', _reason, _detail, now());
END $$;

-- V1: block writes to drift tables (example: chain_of_title)
CREATE OR REPLACE FUNCTION ontvv_no_drift() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE m text; BEGIN
  SELECT mode INTO m FROM ontology_validator_config WHERE check_code='V1';
  PERFORM ontology_reject('ONTOLOGY_DRIFT_TABLE', TG_TABLE_NAME);
  IF m = 'block' THEN
    RAISE EXCEPTION 'ontology_validator V1: % is a drift table; write to the canonical table (see ONTOLOGY.md §3)', TG_TABLE_NAME;
  END IF;
  RETURN NEW;
END $$;
-- attach in shadow (uncomment per table when ready):
-- CREATE TRIGGER ontvv_v1_chain_of_title BEFORE INSERT ON chain_of_title
--   FOR EACH ROW EXECUTE FUNCTION ontvv_no_drift();

-- V3: verified ⇒ grounded (example on matter_facts)
CREATE OR REPLACE FUNCTION ontvv_grounded_verified() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE m text; BEGIN
  SELECT mode INTO m FROM ontology_validator_config WHERE check_code='V3';
  IF NEW.provenance_level='verified'
     AND (NEW.source_id IS NULL OR COALESCE(NEW.excerpt,'')='') THEN
    PERFORM ontology_reject('ONTOLOGY_UNGROUNDED_VERIFIED',
      TG_TABLE_NAME||' id='||COALESCE(NEW.id::text,'?'));
    IF m='block' THEN
      RAISE EXCEPTION 'ontology_validator V3: verified fact needs source_id + excerpt (ONTOLOGY.md A2)';
    END IF;
  END IF;
  RETURN NEW;
END $$;
-- CREATE TRIGGER ontvv_v3_matter_facts BEFORE INSERT OR UPDATE ON matter_facts
--   FOR EACH ROW EXECUTE FUNCTION ontvv_grounded_verified();
```

*(V2 enum + V4 isolation triggers follow the same shape; omitted here for brevity — implement alongside
V1/V3 when the shadow migration is authored.)*

---

## 7. Definition of done (v1)

- [x] Shadow migration authored + **applied** (`migrations/apply_deploy_691_ontology_validator.py`) — V1/V3/V4 in `log` mode; crash-proof logger self-tested on apply. *(deploy_691, 2026-07-05)*
- [x] `scripts/ontology_check.py` whole-corpus linter built + running (V3 grounding, V4 isolation, drift-table watch, provenance-vocab audit, unregistered-table review). Closes the loop.
- [x] **V4 fired on first run** — caught 6 verified facts (Allan Inocalla / OCT P-1616, Paracale) mis-filed under `MWK-TCT4497`; **re-homed to `PAR-TCT1616`**; `v_ontology_client_cross` now returns 0.
- [x] V3 confirmed 0 false positives at apply time (0 ungrounded verified facts).
- [ ] 72h shadow run; V1 false-positive rate = 0 confirmed in `holes_findings` (V1 drift-writes should be 0; `chain_of_title`/`cases` hold *pre-existing* rows, not new writes).
- [ ] V1/V3 flipped to `block` (`UPDATE ontology_validator_config SET mode='block' WHERE check_code IN ('V1','V3');`); one rollback drill (`--rollback`) executed.
- [x] `knowledge_graph_triples.provenance_level` overload reconciled (deploy_693: split to `extraction_method` col; vocab now clean).
- [ ] V4 kept as detector; enforce post-Aug-12 once A5 (`case_file`/`matter_code`) is FK-hardened.

---

## 8. V6 — Geometry client isolation (A9) · **SHADOW DRAFT, NOT APPLIED** (deploy_732 prep)

Extends the §3 family with a sixth check for the Mapping domain (ONTOLOGY.md §2.4, axiom A9): a parcel's
geometry belongs to exactly one client. The geometry analogue of V4. **Drafted only — no view, no config
row, no trigger has been created on the DB.** It ships `log` first (like V4).

**Blocker RESOLVED (deploy_733 — operator decision 7.1 = option (a)):** `parcels.client_code` was added
(nullable, FK→`clients`, forward-filled by `_client_of(matter_code)` at write). **Both** geometry layers
now carry a declared `client_code`, so V6 covers **both arms uniformly** — the draft below is updated
accordingly. Applying it (even in `log`) is the separate **7.2** approval and has NOT been done.

```sql
-- ===== V6 (geometry client isolation, A9) — SHADOW DRAFT, DO NOT APPLY =====
-- Config (mirrors V4; ships 'log' first):
-- INSERT INTO ontology_validator_config(check_code,mode,note) VALUES
--   ('V6','log','geometry client-isolation (A9) via v_ontology_geometry_cross')
-- ON CONFLICT DO NOTHING;

-- Detector view — BOTH arms now (each has a DECLARED client_code). Reuses _client_of()
-- (the same resolver V4 uses: matters->clients OR clients directly).
CREATE OR REPLACE VIEW v_ontology_geometry_cross AS
SELECT 'map_parcels' AS layer, mp.parcel_code::text AS ref, mp.matter_code,
       mp.client_code AS declared_client, _client_of(mp.matter_code) AS resolved_client
FROM   map_parcels mp
WHERE  mp.matter_code IS NOT NULL AND mp.client_code IS NOT NULL
  AND  _client_of(mp.matter_code) IS NOT NULL
  AND  mp.client_code IS DISTINCT FROM _client_of(mp.matter_code)
UNION ALL
SELECT 'parcels' AS layer, p.id::text AS ref, p.matter_code,
       p.client_code AS declared_client, _client_of(p.matter_code) AS resolved_client
FROM   parcels p
WHERE  p.matter_code IS NOT NULL AND p.client_code IS NOT NULL
  AND  _client_of(p.matter_code) IS NOT NULL
  AND  p.client_code IS DISTINCT FROM _client_of(p.matter_code);

-- Write-time trigger fn. Generic over the ref column (map_parcels PK=parcel_code, parcels PK=id).
-- Same shape as ontvv_grounded_verified.
CREATE OR REPLACE FUNCTION ontvv_geometry_isolation() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE m text; resolved text; BEGIN
  SELECT mode INTO m FROM ontology_validator_config WHERE check_code='V6';
  IF m IS NULL OR m='off' THEN RETURN NEW; END IF;
  IF NEW.matter_code IS NOT NULL AND NEW.client_code IS NOT NULL THEN
    resolved := _client_of(NEW.matter_code);
    IF resolved IS NOT NULL AND NEW.client_code <> resolved THEN
      -- generic over both tables: reference only matter_code/client_code (present on each).
      PERFORM ontology_reject('ONTOLOGY_GEOMETRY_CLIENT_CROSS',
        TG_TABLE_NAME||' matter_code='||NEW.matter_code||' client_code='||NEW.client_code
        ||' but matter resolves to '||resolved);
      IF m='block' THEN
        RAISE EXCEPTION 'ontology_validator V6: %.client_code (%) must match the client of matter_code % (%) — A9',
          TG_TABLE_NAME, NEW.client_code, NEW.matter_code, resolved;
      END IF;
    END IF;
  END IF;
  RETURN NEW;
END $$;
-- attach in shadow ONLY on 7.2 approval (uncomment then) — BOTH arms, same fn:
-- CREATE TRIGGER ontvv_v6_map_parcels BEFORE INSERT OR UPDATE ON map_parcels
--   FOR EACH ROW EXECUTE FUNCTION ontvv_geometry_isolation();
-- CREATE TRIGGER ontvv_v6_parcels BEFORE INSERT OR UPDATE ON parcels
--   FOR EACH ROW EXECUTE FUNCTION ontvv_geometry_isolation();   -- UNBLOCKED by deploy_733
```

**Definition of done (V6):**
- [x] `parcels.client_code` decision made → **option (a), added deploy_733** (writer forward-fills via `_client_of`).
- [ ] `v_ontology_geometry_cross` created; returns 0 on the live seed (MWK-BALANE) — expected clean. *(7.2)*
- [ ] V6 config row inserted `mode='log'`; both triggers attached; ≥72h shadow, 0 false positives. *(7.2)*
- [ ] Flip both arms to `block` after a clean shadow window. *(post-7.2)*

---

## 9. Mapping high-risk-surface governance boundaries (prep — **NOT built**)

Two Mapping concepts touch surfaces the evidence core never does: a **third party** (external map services)
and **personal data** (a user's real-time location). Both are ○ planned in ONTOLOGY.md §2.4 and axiom-guarded
(A11, A10). **Neither may be built until the governance below exists.**

### 9.1 ExternalMapReference (A11) — publishing geometry off-platform
Boundary: creating or serving a Google Earth/Maps deep-link, KML/KMZ, embed, or tile-set is an **outward
action** that exports one client's survey geometry beyond LandTek. Required before any build:
1. A per-reference audit row: `client_code` + `created_by` + `audience` + `created_at`.
2. **Client isolation enforced** (not asserted): a reference may expose ONLY its own client's geometry (A9/A5).
3. **Outward-guard integration** (`outward_guard_config`, ONTOLOGY.md §8.11): a publish is a governed, logged,
   human-authorized flip — the same discipline as an outbound message (S14).
4. An explicit **publish gate** wired to `map_parcels.status='published'` + `no-external-exposure-until-ready`.

> Do **not** create an `external_map_references` table or any publish path until 1–4 are signed off.

### 9.2 UserLocationContext (A10) — storing device location
Boundary: today device GPS is **ephemeral + client-side** (point-in-polygon runs in the browser; nothing
leaves the device, nothing is stored) — **safe**. The moment location is **persisted** it becomes personal
data. Required before any storage:
1. A **consent record** (who consented, when, to what) — no location row may exist without one.
2. A **retention/erasure policy** (how long; deletion on request).
3. Purpose limitation + client isolation (a client's location tied to their own map only).

> Recommended default: **keep it ephemeral.** Do not add a location table; A10 is the guardrail.
