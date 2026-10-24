-- deploy_1111_profit_frontboard.sql
-- The magnate engine's MONEY layer: rank fronts by expected pesos, not just readiness.
--
-- Why: v_profitability_momentum ranks open prep moves purely by readiness urgency
-- (weakest + most-foundational axis, nudged by tier). It ignores est_value and
-- est_income_monthly entirely — so a P200k/mo asset ranks equal to a P15k/mo lot.
-- This view adds a transparent, auditable money score layered ON TOP of the running
-- readiness engine (which is left untouched). Internal/reversible (a view).
--
-- money_score (annual-peso terms, all components exposed so the ranking is auditable):
--   annual_income       = est_income_monthly * 12                      (recurring cash)
--   tier_factor         = earn_now 1.0 / develop 0.40 / recover_then 0.15 / other 0.25
--                         (how near this capital is to becoming cash)
--   realizable_capital  = est_value * readiness * tier_factor          (risk/time-adjusted capital)
--   money_score         = annual_income + 0.08 * realizable_capital    (0.08 = ~8%/yr yield proxy,
--                         to put one-time capital into comparable annual-peso terms)
--   NULL money_score     = no est_value AND no income  → VALUE UNKNOWN, ranked separately (honest),
--                         never treated as zero.
-- Provenance: uses only figures already on property_assets (operator/corpus-seeded);
-- fabricates nothing. Assets flagged needs_valuation surface as VALUE UNKNOWN.

CREATE OR REPLACE VIEW v_profit_frontboard AS
WITH base AS (
  SELECT a.asset_code, a.client_code, a.label, a.tier, a.title_status, a.possession,
         a.est_value, a.est_income_monthly, a.needs_valuation,
         COALESCE(r.readiness_score, 0)::numeric AS readiness,
         r.weakest_axis, r.next_prep_action
  FROM property_assets a
  LEFT JOIN property_readiness r ON r.asset_code = a.asset_code
  WHERE a.client_code IS NOT NULL
),
scored AS (
  SELECT b.*,
         CASE b.tier WHEN 'earn_now' THEN 1.0 WHEN 'develop' THEN 0.40
                     WHEN 'recover_then' THEN 0.15 ELSE 0.25 END AS tier_factor,
         COALESCE(b.est_income_monthly, 0) * 12 AS annual_income,
         COALESCE(b.est_value, 0) * b.readiness
           * CASE b.tier WHEN 'earn_now' THEN 1.0 WHEN 'develop' THEN 0.40
                         WHEN 'recover_then' THEN 0.15 ELSE 0.25 END AS realizable_capital
  FROM base b
)
SELECT asset_code, client_code, label, tier, title_status, possession,
       est_value, est_income_monthly, needs_valuation,
       ROUND(readiness, 3) AS readiness, weakest_axis, next_prep_action,
       tier_factor,
       annual_income,
       ROUND(realizable_capital) AS realizable_capital,
       CASE WHEN est_value IS NULL AND COALESCE(est_income_monthly, 0) = 0
            THEN NULL
            ELSE ROUND(annual_income + 0.08 * realizable_capital) END AS money_score
FROM scored;

COMMENT ON VIEW v_profit_frontboard IS
  'Money-weighted front ranking for the magnate engine (deploy_1111). money_score in annual-peso terms: annual_income + 0.08*est_value*readiness*tier_factor. NULL money_score = VALUE UNKNOWN (needs_valuation). Additive over v_profitability_momentum; running readiness engine untouched.';
