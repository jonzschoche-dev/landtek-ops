-- deploy_1267_decouple_6839_from_4497.sql
-- CORRECTION (Jonathan, 2026-10-24): "4497 has nothing to do with 6839."
--
-- CV6839 = CARP just compensation on titles T-4494/4501/4502/4503 (Cabanbanan/San Vicente,
--   267.71 ha) — a SEPARATE matter from the T-4497 Mercedes residential estate.
-- SP2680 guardianship is pleaded over T-32911 (a T-4497 derivative) → it is a 4497-side matter
--   and does NOT gate CV6839.
-- Prior deploy_1266 wrongly set SP2680 as CV6839's gate and listed T-4497 recovery next to CV6839
--   in SP2680.unblocks. De-link both.
--
-- CV6839's real authority track (its own, not SP2680): Patricia's 1/3 via a supplemental apostilled
--   SPA (LBP FSSC5 track); the non-participating thirds (Hoppe/Marcia) need their own authority;
--   the dead party-of-record (Cesar) must be substituted. Whether a guardianship/administration is
--   the vehicle for those thirds is being reconciled with the operator — left undated, not guessed.
-- Internal/reversible.

UPDATE money_fronts
   SET gate = 'Authority over the heirs'' shares in the 6839 judgment — its OWN track (NOT T-4497 / NOT SP2680)',
       gate_date = NULL,
       next_step = 'Patricia 1/3: supplemental apostilled SPA naming T-4494/4501/4502/4503 + claim folder 05-CA-94-097 (LBP FSSC5 track) — does not wait on any guardianship. Non-participating thirds (Hoppe/Marcia): own authority/administration. Substitute the dead party-of-record (Cesar).',
       note = COALESCE(note,'') || ' [2026-10-24 CORRECTION: CV6839 (T-4494/4501/4502/4503, Cabanbanan/San Vicente) is a SEPARATE matter from the T-4497 Mercedes estate and from SP2680 (pleaded over T-32911). De-linked from both. Confirm the authority vehicle for the non-participating thirds.]',
       updated_at = now()
 WHERE front_code = 'MF-CV6839';

UPDATE money_fronts
   SET label = 'Guardianship SP2680 (RTC Br.41 Daet, Judge Dating) — authority gate for the T-4497 estate (pleaded over T-32911)',
       unblocks = '26-360 indispensable-party cure (9 Dec); authority over T-32911 + T-4497 estate acts (sales/leases via Rule 95, case by case)',
       note = COALESCE(note,'') || ' [2026-10-24: SP2680 is a T-4497-side guardianship (T-32911); it does NOT gate CV6839 — 6839 is a separate matter.]',
       updated_at = now()
 WHERE front_code = 'MF-SP2680-GUARDIANSHIP';
