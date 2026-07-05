# Spec — `ontology_validator` (gate extension)

> **Status: SPEC ONLY (2026-07-05). Nothing here is applied to the live DB.** Applying a new
> trigger/gate during the Aug-12 litigation window requires Jonathan's explicit go. This document
> is the design; the DDL at the end is ready-to-apply but **unapplied**.
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

- [ ] Shadow migration authored (`migrations/apply_deploy_NNN_ontology_validator.sql`) — V1–V4 in `log` mode.
- [ ] 72h shadow run; V1–V3 false-positive rate = 0 confirmed in `holes_findings`.
- [ ] V1–V3 flipped to `block`; one rollback drill executed.
- [ ] `scripts/ontology_check.py` regenerates `ONTOLOGY.md` §2–§3 from live schema (closes the loop).
- [ ] V4 contamination triaged; deferred to post-Aug-12 A5 hardening.
