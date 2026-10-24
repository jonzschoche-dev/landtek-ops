-- deploy_1265_money_fronts_nearterm_cash.sql
-- Magnate engine, step 2: focus the money board on NEAR-TERM CASH and the Keesey estate.
--
-- Three fixes (all truthful; nothing fabricated):
--  (1) Correct soft property inputs per Jonathan 2026-10-24:
--        PA-MANILA-APT   jointly owned → only a partial undivided interest; realizable share unknown → clear value.
--        PA-RICEFIELD-CSUR value/ownership NOT known → clear speculative figures.
--        PA-GOLDEN-SAND  not moving (stalled) → note it; (no income → it already scores 0 near-term cash).
--  (2) Fix a formula flaw: the old money_score annualized one-time value at 8%/yr, which BURIED a one-time
--        collection (a ₱5.1M judgment showed as ~₱205k/yr). New model ranks by EXPECTED NEAR-TERM CASH:
--          near_term_cash = annual_income*2  +  one_time_cash
--          one_time_cash  = est_value * readiness * tier_factor   -- ONLY for cash-event fronts (judgment/sale)
--        Held/recover land (no income, not being sold) contributes 0 near-term cash — honest — while its
--        est_value is still shown as the long-run backdrop and used as the tiebreak.
--  (3) Bring judgment/collection money the property engine can't model onto the board via a money_fronts table,
--        seeded with CV6839 (the guaranteed Keesey CARP just-compensation receivable).
--
-- Internal/reversible (data edits + a table + a view). The running readiness engine is untouched;
-- money_fronts lives outside property_assets so the prep cycle emits no noise against it.

-- ── (1) truthful corrections to soft property inputs ──────────────────────────────────────────────
UPDATE property_assets
   SET est_value = NULL, est_income_monthly = NULL, needs_valuation = true,
       note = COALESCE(note,'') || ' [2026-10-24 Jonathan: jointly owned — partial undivided interest only; realizable share unquantified; cleared full-building figures]',
       updated_at = now()
 WHERE asset_code = 'PA-MANILA-APT';

UPDATE property_assets
   SET est_value = NULL, est_income_monthly = NULL, needs_valuation = true,
       note = COALESCE(note,'') || ' [2026-10-24 Jonathan: value/ownership NOT known — cleared speculative figures]',
       updated_at = now()
 WHERE asset_code = 'PA-RICEFIELD-CSUR';

UPDATE property_assets
   SET note = COALESCE(note,'') || ' [2026-10-24 Jonathan: not moving / stalled — not a near-term cash front]',
       updated_at = now()
 WHERE asset_code = 'PA-GOLDEN-SAND';

-- ── (3) money_fronts: judgment/collection fronts the property engine cannot model ─────────────────
CREATE TABLE IF NOT EXISTS money_fronts (
  front_code         text PRIMARY KEY,
  client_code        text NOT NULL,
  matter_code        text,
  label              text NOT NULL,
  front_type         text NOT NULL,                       -- judgment_receivable | collection | back_rent | sale
  realization        text NOT NULL DEFAULT 'cash_event',  -- cash_event | income
  tier               text NOT NULL DEFAULT 'earn_now',
  est_value_php      numeric,                              -- near-term collectible FLOOR (verified); upside noted
  est_income_monthly numeric DEFAULT 0,
  readiness          numeric DEFAULT 0,                    -- 0..1, how close to cash
  next_step          text,
  value_basis        text,
  provenance_level   text DEFAULT 'verified',
  source_ref         text,
  note               text,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now()
);

INSERT INTO money_fronts
  (front_code, client_code, matter_code, label, front_type, realization, tier,
   est_value_php, est_income_monthly, readiness, next_step, value_basis, provenance_level, source_ref, note)
VALUES
  ('MF-CV6839', 'MWK-001', 'MWK-CV6839',
   'CV6839 CARP just compensation — 4 titles (T-4494/4501/4502/4503), Land Bank debtor, final & executory',
   'judgment_receivable', 'cash_event', 'earn_now',
   5124922.47, 0, 0.30,
   'GATE: guardianship grant (SP2680, RTC Daet Br.41) — the writ/execution path is waiting on it (operator, 2026-10-24). After the grant: supplemental apostilled SPA (Patricia) naming T-4494/4501/4502/4503 + claim folder 05-CA-94-097 with power to receive/acquit, then motion to substitute + execute.',
   'Verified unpaid PRINCIPAL floor ₱5,124,922.47 (doc#376 Yuzon reproducing 07-Feb-2024 dispositive). Interest 12%→6% over 30+ yrs UN-COMPUTED → true collectible plausibly ₱15–25M+.',
   'verified',
   'doc#376 (Yuzon); doc#345; LBP FSSC5 reply 2026-10-22; operator 2026-10-24; case_work/MWK-001/CV6839_WRIT_COLLECTION_PATH.md',
   'readiness 0.30 = final & executory + LBP engaged (22 Oct 2026), BUT the writ path is gated on the guardianship grant (SP2680), which is pending — operator-confirmed 2026-10-24, overriding the memo''s "move Patricia 1/3 now" thesis. Rises when guardianship is granted.')
ON CONFLICT (front_code) DO UPDATE SET
  label=EXCLUDED.label, front_type=EXCLUDED.front_type, realization=EXCLUDED.realization, tier=EXCLUDED.tier,
  est_value_php=EXCLUDED.est_value_php, est_income_monthly=EXCLUDED.est_income_monthly, readiness=EXCLUDED.readiness,
  next_step=EXCLUDED.next_step, value_basis=EXCLUDED.value_basis, provenance_level=EXCLUDED.provenance_level,
  source_ref=EXCLUDED.source_ref, note=EXCLUDED.note, updated_at=now();

-- ── (2) rebuild the board: UNION property fronts + money fronts, rank by near-term cash ───────────
DROP VIEW IF EXISTS v_profit_frontboard;  -- deploy_1264 version had different column order; replace fully
CREATE VIEW v_profit_frontboard AS
WITH prop AS (
  SELECT a.asset_code AS front_code, 'property'::text AS source, a.asset_type AS front_type,
         a.client_code, a.controlling_matter AS matter_code, a.label, a.tier,
         a.est_value, a.est_income_monthly, a.needs_valuation,
         COALESCE(r.readiness_score,0)::numeric AS readiness,
         r.weakest_axis, r.next_prep_action AS next_step,
         CASE WHEN COALESCE(a.est_income_monthly,0) > 0 THEN 'income' ELSE 'hold' END AS realization
    FROM property_assets a
    LEFT JOIN property_readiness r ON r.asset_code = a.asset_code
   WHERE a.client_code IS NOT NULL
),
money AS (
  SELECT f.front_code, 'money_front'::text AS source, f.front_type,
         f.client_code, f.matter_code, f.label, f.tier,
         f.est_value_php AS est_value, f.est_income_monthly, false AS needs_valuation,
         COALESCE(f.readiness,0)::numeric AS readiness,
         NULL::text AS weakest_axis, f.next_step, f.realization
    FROM money_fronts f
),
u AS (SELECT * FROM prop UNION ALL SELECT * FROM money)
SELECT u.front_code, u.source, u.front_type, u.client_code, u.matter_code, u.label, u.tier,
       u.est_value, u.est_income_monthly, u.needs_valuation,
       ROUND(u.readiness,3) AS readiness, u.realization, u.weakest_axis, u.next_step,
       (CASE u.tier WHEN 'earn_now' THEN 1.0 WHEN 'develop' THEN 0.40
                    WHEN 'recover_then' THEN 0.15 ELSE 0.25 END) AS tier_factor,
       COALESCE(u.est_income_monthly,0)*12 AS annual_income,
       ROUND(CASE WHEN u.realization='cash_event'
                  THEN COALESCE(u.est_value,0) * u.readiness
                       * (CASE u.tier WHEN 'earn_now' THEN 1.0 WHEN 'develop' THEN 0.40
                                      WHEN 'recover_then' THEN 0.15 ELSE 0.25 END)
                  ELSE 0 END) AS one_time_cash,
       CASE WHEN u.est_value IS NULL AND COALESCE(u.est_income_monthly,0)=0 THEN NULL
            ELSE ROUND(COALESCE(u.est_income_monthly,0)*12*2
                 + CASE WHEN u.realization='cash_event'
                        THEN COALESCE(u.est_value,0) * u.readiness
                             * (CASE u.tier WHEN 'earn_now' THEN 1.0 WHEN 'develop' THEN 0.40
                                            WHEN 'recover_then' THEN 0.15 ELSE 0.25 END)
                        ELSE 0 END) END AS near_term_cash
FROM u;
