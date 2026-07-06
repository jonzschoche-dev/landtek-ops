# Spec — `ontology_validator` V7: Communications identity isolation (A25) · **SHADOW DRAFT, NOT APPLIED**

> **Status: DRAFT ONLY — no view, no config row, no trigger exists on the DB.** This is the enforcement-prep
> deliverable for **A25** (ONTOLOGY.md §2.14): *a `ChannelUser` resolves to at most one `client_code`; no
> channel identity is mapped across two clients.* It is written to fold into `docs/ontology_validator_spec.md`
> as **§10 (V7)**, continuing the V1–V6 family, once that file's in-flight edits land. It follows the **V6
> pattern exactly** (§8 of that spec): the comms analogue of V4 (client isolation on `matter_facts`) and V6
> (client isolation on geometry). Ships `log` (shadow) first; **zero false positives before any `block`.**

---

## 1. What A25 requires, and what is mechanically checkable today

A25 has two halves. They have very different readiness, and the spec is honest about the gap:

| Half of A25 | Statement | Checkable now? |
|---|---|---|
| **(a) Valid, single declared client** | a `channel_users` row's `mapped_client_code`, when set, must resolve to exactly **one real client** | 🟢 **Yes** — `_client_of()` resolves it; V7 Part 1 below |
| **(b) Cross-channel single client** | the *same human* reachable on ≥2 channels resolves to **one** `client_code`, never two | 🔴 **No** — `channel_users` has **no person-key** to join two rows to one human (see §4 blocker) |

`channel_users` is `UNIQUE(channel_id, channel_user_id)`, so a single (channel, id) pair cannot itself split
across clients. The leakage A25 really guards — *Gloria on WhatsApp tagged MWK, the same Gloria on Viber
tagged Paracale* — is **cross-row, cross-channel**, and cannot be detected without an identity key linking
those rows to one person. That key does not exist yet. This is the direct analogue of the A9/V6 situation,
where geometry isolation was blocked until `parcels.client_code` was added (deploy_733).

---

## 2. Design principles (inherited from the V1–V6 spec)

1. **Reuse `_client_of()`** — the same resolver V4/V6 use (matters→clients OR clients directly; handles
   `case_file ≠ matter_code`). No new resolution logic.
2. **Shadow first.** V7 ships `mode='log'` → logs to `holes_findings` via `ontology_reject()`, blocks
   nothing. Flip to `block` only after a ≥72h clean window + operator go.
3. **Zero false positives before enforcement.** Same calibration bar as V4/V6 and the dossier-verify gate.
4. **DB-resident.** A `BEFORE INSERT OR UPDATE` trigger binds *every* writer (Python workers, `psql`, the
   n8n LangChain path, and the channel adapters alike) — not one application path.

---

## 3. V7 Part 1 — declared-client validity (SHADOW-READY)

Enforceable the moment it is approved. Catches a `mapped_client_code` that is a typo, a stale code, or a
client that does not exist — the row-level slice of A25.

```sql
-- ===== V7 (communications identity isolation, A25) — SHADOW DRAFT, DO NOT APPLY =====
-- Config (mirrors V4/V6; ships 'log' first):
-- INSERT INTO ontology_validator_config(check_code,mode,note) VALUES
--   ('V7','log','channel identity client-isolation (A25) via v_ontology_channel_cross')
-- ON CONFLICT DO NOTHING;

-- Detector view — a channel identity's declared client must resolve to a real, single client.
CREATE OR REPLACE VIEW v_ontology_channel_cross AS
SELECT cu.id                                AS ref,
       cu.channel_id,
       cu.channel_user_id,
       cu.mapped_client_code                AS declared_client,
       _client_of(cu.mapped_client_code)    AS resolved_client
FROM   channel_users cu
WHERE  cu.mapped_client_code IS NOT NULL
  AND  _client_of(cu.mapped_client_code) IS NULL;   -- declared client resolves to NOTHING → invalid

-- Write-time trigger fn (same shape as ontvv_grounded_verified / ontvv_geometry_isolation).
CREATE OR REPLACE FUNCTION ontvv_channel_isolation() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE m text; BEGIN
  SELECT mode INTO m FROM ontology_validator_config WHERE check_code='V7';
  IF m IS NULL OR m='off' THEN RETURN NEW; END IF;
  IF NEW.mapped_client_code IS NOT NULL AND _client_of(NEW.mapped_client_code) IS NULL THEN
    PERFORM ontology_reject('ONTOLOGY_CHANNEL_BAD_CLIENT',
      'channel_users id='||coalesce(NEW.id::text,'?')||' mapped_client_code='||NEW.mapped_client_code
      ||' does not resolve to a known client');
    IF m='block' THEN
      RAISE EXCEPTION 'ontology_validator V7: channel_users.mapped_client_code (%) must resolve to exactly one known client — A25',
        NEW.mapped_client_code;
    END IF;
  END IF;
  RETURN NEW;
END $$;
-- attach in shadow ONLY on approval (uncomment then):
-- CREATE TRIGGER ontvv_v7_channel_users BEFORE INSERT OR UPDATE ON channel_users
--   FOR EACH ROW EXECUTE FUNCTION ontvv_channel_isolation();
```

---

## 4. V7 Part 2 — cross-channel single client (BLOCKED — schema decision required)

A25(b) is the load-bearing half, and it is **blocked on a schema decision**, exactly as A9/V6 was blocked on
`parcels.client_code`. The minimal unblock is a **person-key** on `channel_users` linking rows that are the
same human — the natural candidate is the existing `entities` node (the canonical person/org, §2.9).

```sql
-- ===== V7 Part 2 (cross-channel single-client) — BLOCKED, DO NOT APPLY =====
-- Proposed minimal unblock (NOT built — operator decision, the A25 analogue of the deploy_733 / 7.1 call):
--   ALTER TABLE channel_users ADD COLUMN entity_id integer REFERENCES entities(id);   -- canonical person
--   -- forward-fill at write via the same entity-resolution path used elsewhere.
--
-- With entity_id populated, the cross-channel detector becomes trivial and mechanical:
-- CREATE OR REPLACE VIEW v_ontology_channel_person_cross AS
-- SELECT entity_id,
--        count(DISTINCT mapped_client_code)      AS n_clients,
--        array_agg(DISTINCT mapped_client_code)  AS codes
-- FROM   channel_users
-- WHERE  entity_id IS NOT NULL AND mapped_client_code IS NOT NULL
-- GROUP BY entity_id
-- HAVING count(DISTINCT mapped_client_code) > 1;   -- one human, >1 client = A25 violation
--
-- The trigger analogue rejects an INSERT/UPDATE that would give an entity a 2nd distinct client_code.
```

Until this key exists, **A25(b) is a discipline, not a guarantee** — the exact wording ONTOLOGY.md §5 uses
for the corpus, and the honest state of the A25 row today.

---

## 5. Definition of done (V7)

- [ ] `v_ontology_channel_cross` (Part 1) created; returns **0** on live `channel_users` (expected clean —
      few rows today). *(shadow prep — re-ground on the VPS; this Mac session cannot reach the DB)*
- [ ] V7 config row inserted `mode='log'`; `ontvv_v7_channel_users` trigger attached; ≥72h shadow;
      `ONTOLOGY_CHANNEL_BAD_CLIENT` false-positive rate = 0 in `holes_findings`.
- [ ] Flip V7 Part 1 to `block` after the clean window + operator go
      (`UPDATE ontology_validator_config SET mode='block' WHERE check_code='V7';`).
- [ ] **Part 2 blocker — operator decision** on `channel_users.entity_id` (the cross-channel person key).
      Until then, A25(b) stays discipline-only and this doc records why.
- [ ] On apply, update the ONTOLOGY.md **A25** enforcement marker from *"resolver + block-guard not built"*
      → *"V7 Part 1 shadow-applied; Part 2 blocked on `entity_id` decision"* (a marker update, not a prose
      refinement of §2.14).

---

## 6. How this folds into `docs/ontology_validator_spec.md`

Paste §1–§5 above as a new **§10 (V7)** after that spec's §9, and add a `('V7','log',…)` line to the config
list in §6. No change to V1–V6. `ontology_check.py --coverage` is unaffected (no new *domain* tables; the
new *view* is validator infrastructure, not a concept store). Deferred here only to avoid a merge collision
with the file's in-flight edits — **content is complete and ready.**

---

*Enforcement-prep deliverable. Nothing here changes schema, code, or enforcement — it is a shadow-mode
**draft**. Part 1 is ready to apply in `log` on approval; Part 2 is a flagged schema decision for Jonathan.*
