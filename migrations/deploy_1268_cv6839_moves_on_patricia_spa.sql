-- deploy_1268_cv6839_moves_on_patricia_spa.sql
-- Operator (Jonathan, 2026-10-24): CV6839 moves NOW on Patricia's supplemental apostilled SPA,
-- on behalf of the co-heirs (co-ownership / Art. 487) — NO guardianship gate.
--
-- Encodes: CV6839 is ungated by any court; the live vehicle is Patricia's supplemental SPA.
-- readiness 0.30 → 0.50 (actionable, not court-gated), but not collected: SPA not yet executed/
-- apostilled, motion to substitute + execute not filed, and the Land Bank FSSC5 reply (22 Oct 2026)
-- flagged that RELEASE of each co-heir's share wants that heir's own SPA/settlement — so Patricia
-- can DRIVE the execution now, while the co-heirs' shares at the release stage may still need their
-- own authority. Kept visible to square with LBP, not asserted away.
-- Internal/reversible.

UPDATE money_fronts
   SET gate = NULL,
       gate_date = NULL,
       readiness = 0.50,
       next_step = 'Draft + execute Patricia''s SUPPLEMENTAL apostilled SPA (name T-4494/4501/4502/4503 + claim folder 05-CA-94-097; powers to receive/acquit compensation, sign CIS/specimen, post heir''s bond, substitute, and act for the co-ownership) → motion to substitute the dead party-of-record (Cesar) → motion for execution. No guardianship.',
       value_basis = 'Verified unpaid PRINCIPAL floor ₱5,124,922.47 (doc#376). Patricia moves for the co-ownership (Art. 487). Interest 12%→6% UN-COMPUTED → true collectible plausibly ₱15–25M+.',
       note = COALESCE(note,'') || ' [2026-10-24 operator: moves NOW on Patricia''s supplemental SPA on behalf of the co-heirs; NO guardianship gate. Constraint to square: LBP FSSC5 (22 Oct) wants each co-heir''s own SPA/settlement to RELEASE that heir''s share — Patricia drives execution now; co-heirs'' shares at release may need their own authority. Confirm with LBP.]',
       updated_at = now()
 WHERE front_code = 'MF-CV6839';
