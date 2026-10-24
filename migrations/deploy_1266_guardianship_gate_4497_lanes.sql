-- deploy_1266_guardianship_gate_4497_lanes.sql
-- Magnate engine, step 3: put the guardianship GATE (with its date) on the board, and
-- finesse the T-4497 estate into its true lanes.
--
-- Guardianship SP2680 (RTC Br.41 Daet, Judge Dating) is the gate in front of the Keesey cash.
--   Next hearing: Wed 11 Nov 2026 (AM) — reset from 19 Oct (judge ill); 8 Sep opened & continued.
--   Petition is property-only over T-32911 (8,706 sqm, pleaded ₱5M); ground absence+peril; Botor
--   carves out Gerry Hoppe's 1/3. Operator (2026-10-24): the CV6839 writ path waits on this grant.
--   (Scope nuance: the petition is pleaded over T-32911; the estate-wide unlock is operator-stated,
--    not asserted here as fact.)
--
-- Finesse of T-4497: it is NOT one lump. Three lanes —
--   (1) GATE   : guardianship SP2680 (dated milestone that unblocks the rest)
--   (2) NOW-MONEY : occupant compensation on Patricia's 1/3 via Art. 487 — does NOT wait on
--                   guardianship; gated only on the T-32917 census + serving pay-to-stay. Value
--                   unquantified until the census, so it is carried as a visible now-money lane,
--                   not a fabricated number.
--   (3) LONG-RUN : recovery of the derivative parcels (26-360 Balane + the 20 transferees), the
--                   ₱50M held value — gated on litigation (and the indispensable-party cure that
--                   loops back to guardianship). Left as PA-T4497-ESTATE (held; 0 near-term cash).
--
-- Internal/reversible. Running readiness engine untouched.

-- ── gate/timeline columns on money_fronts ────────────────────────────────────────────────────────
ALTER TABLE money_fronts ADD COLUMN IF NOT EXISTS gate      text;  -- what blocks this front
ALTER TABLE money_fronts ADD COLUMN IF NOT EXISTS gate_date date;  -- the gate's next dated event
ALTER TABLE money_fronts ADD COLUMN IF NOT EXISTS unblocks  text;  -- for gate rows: what it frees

-- CV6839 now points at the dated gate
UPDATE money_fronts
   SET gate = 'Guardianship grant (SP2680)', gate_date = DATE '2026-11-11', updated_at = now()
 WHERE front_code = 'MF-CV6839';

-- (1) the guardianship GATE itself, as a dated milestone on the board
INSERT INTO money_fronts
  (front_code, client_code, matter_code, label, front_type, realization, tier,
   est_value_php, est_income_monthly, readiness, next_step, value_basis, provenance_level,
   source_ref, note, gate, gate_date, unblocks)
VALUES
  ('MF-SP2680-GUARDIANSHIP', 'MWK-001', 'SP2680',
   'Guardianship SP2680 (RTC Br.41 Daet, Judge Dating) — the gate in front of the Keesey cash',
   'gate', 'gate', 'earn_now',
   NULL, 0, 0.55,
   'Hearing Wed 11 Nov 2026 (AM): OSG cross of Jonathan; Botor carves out Gerry Hoppe''s 1/3. Then: grant → letters → authority to execute.',
   'Not money itself — the key. Petition property-only over T-32911 (pleaded ₱5M), ground absence+peril.',
   'verified',
   'case_work/SP2680/STATUS.md (20 Oct 2026); operator 2026-10-24',
   'Reset from 19 Oct (judge ill); 8 Sep opened & continued (OSG not ready). One objector: Gerry Hoppe. Also feeds the 26-360 indispensable-party cure (9 Dec).',
   NULL, DATE '2026-11-11',
   'MF-CV6839 (writ path); T-4497 recovery (26-360 indispensable-party cure); Hoppe/Marcia estate shares')
ON CONFLICT (front_code) DO UPDATE SET
  label=EXCLUDED.label, next_step=EXCLUDED.next_step, readiness=EXCLUDED.readiness,
  note=EXCLUDED.note, gate_date=EXCLUDED.gate_date, unblocks=EXCLUDED.unblocks,
  value_basis=EXCLUDED.value_basis, source_ref=EXCLUDED.source_ref, updated_at=now();

-- (2) the T-4497 NOW-MONEY lane: occupant compensation on Patricia's 1/3 (Art. 487), no guardianship gate
INSERT INTO money_fronts
  (front_code, client_code, matter_code, label, front_type, realization, tier,
   est_value_php, est_income_monthly, readiness, next_step, value_basis, provenance_level,
   source_ref, note, gate, gate_date, unblocks)
VALUES
  ('MF-T4497-OCCUPANT-COMP', 'MWK-001', 'MWK-001',
   'T-4497 occupant compensation / pay-to-stay — now-money on Patricia''s 1/3 (Art. 487)',
   'back_rent', 'income', 'earn_now',
   NULL, NULL, 0.15,
   'Run the T-32917 occupant census → serve pay-to-stay / reasonable-compensation demands (Art. 487, Patricia 1/3) → collect. NO guardianship gate.',
   'Unquantified until the census (occupant count × rate). Art. 487 lets one co-owner recover/charge for the whole; Patricia''s 1/3 authority suffices — this lane does NOT wait on guardianship.',
   'inferred_strong',
   'Art. 487 Civil Code; case_work/MWK-001 pay-to-stay demands + T-32917 census worklist',
   'The 4497 lane the magnate can turn on without waiting on SP2680. Value appears once the census lands.',
   NULL, NULL, NULL)
ON CONFLICT (front_code) DO UPDATE SET
  label=EXCLUDED.label, next_step=EXCLUDED.next_step, readiness=EXCLUDED.readiness,
  value_basis=EXCLUDED.value_basis, note=EXCLUDED.note, provenance_level=EXCLUDED.provenance_level,
  source_ref=EXCLUDED.source_ref, updated_at=now();

-- ── rebuild the board carrying gate/gate_date/unblocks ────────────────────────────────────────────
DROP VIEW IF EXISTS v_profit_frontboard;
CREATE VIEW v_profit_frontboard AS
WITH prop AS (
  SELECT a.asset_code AS front_code, 'property'::text AS source, a.asset_type AS front_type,
         a.client_code, a.controlling_matter AS matter_code, a.label, a.tier,
         a.est_value, a.est_income_monthly, a.needs_valuation,
         COALESCE(r.readiness_score,0)::numeric AS readiness,
         r.weakest_axis, r.next_prep_action AS next_step,
         CASE WHEN COALESCE(a.est_income_monthly,0) > 0 THEN 'income' ELSE 'hold' END AS realization,
         NULL::text AS gate, NULL::date AS gate_date, NULL::text AS unblocks
    FROM property_assets a
    LEFT JOIN property_readiness r ON r.asset_code = a.asset_code
   WHERE a.client_code IS NOT NULL
),
money AS (
  SELECT f.front_code, 'money_front'::text AS source, f.front_type,
         f.client_code, f.matter_code, f.label, f.tier,
         f.est_value_php AS est_value, f.est_income_monthly, false AS needs_valuation,
         COALESCE(f.readiness,0)::numeric AS readiness,
         NULL::text AS weakest_axis, f.next_step, f.realization,
         f.gate, f.gate_date, f.unblocks
    FROM money_fronts f
),
u AS (SELECT * FROM prop UNION ALL SELECT * FROM money)
SELECT u.front_code, u.source, u.front_type, u.client_code, u.matter_code, u.label, u.tier,
       u.est_value, u.est_income_monthly, u.needs_valuation,
       ROUND(u.readiness,3) AS readiness, u.realization, u.weakest_axis, u.next_step,
       u.gate, u.gate_date, u.unblocks,
       (CASE u.tier WHEN 'earn_now' THEN 1.0 WHEN 'develop' THEN 0.40
                    WHEN 'recover_then' THEN 0.15 ELSE 0.25 END) AS tier_factor,
       COALESCE(u.est_income_monthly,0)*12 AS annual_income,
       ROUND(CASE WHEN u.realization='cash_event'
                  THEN COALESCE(u.est_value,0) * u.readiness
                       * (CASE u.tier WHEN 'earn_now' THEN 1.0 WHEN 'develop' THEN 0.40
                                      WHEN 'recover_then' THEN 0.15 ELSE 0.25 END)
                  ELSE 0 END) AS one_time_cash,
       CASE WHEN u.realization='gate' THEN NULL
            WHEN u.est_value IS NULL AND COALESCE(u.est_income_monthly,0)=0 THEN NULL
            ELSE ROUND(COALESCE(u.est_income_monthly,0)*12*2
                 + CASE WHEN u.realization='cash_event'
                        THEN COALESCE(u.est_value,0) * u.readiness
                             * (CASE u.tier WHEN 'earn_now' THEN 1.0 WHEN 'develop' THEN 0.40
                                            WHEN 'recover_then' THEN 0.15 ELSE 0.25 END)
                        ELSE 0 END) END AS near_term_cash
FROM u;
