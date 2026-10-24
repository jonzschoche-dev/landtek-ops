-- deploy_1270_focus_4497_squatter_parcels.sql
-- Operator (Jonathan, 2026-10-24): "we wait for guardianship, focus on the 4497 squatter parcels."
-- CV6839 stays parked (all-heirs/administration gate). Focus = the T-4497 occupied branch.
--
-- Anchor the now-money occupant-compensation front on T-32917 (Lot 2-X-6, San Roque, 85,149 sqm /
-- 8.5 ha) — the flagship squatter parcel — with the real structure from CENSUS_WORKLIST_T32917:
--   pilot ready (T-52537 / Sps. Gaulit, paper lead in hand); biggest single question T-38838 (3.2 ha);
--   ~4.2 ha unmapped (OCR-dirty sub-lots) hides the other transferees. Pay-to-stay on Patricia's 1/3
--   (Art. 487) — NO guardianship. Titled adverse holders (Leaño, Vergara, Balane) → nullity, not pay-to-stay.
-- The one no-gate desk step that unblocks naming occupants: vision re-OCR of the T-32917 deep courses.
-- Value stays unquantified until the canvass (no fabricated number). Internal/reversible.

UPDATE money_fronts
   SET label = 'T-32917 squatter branch (Lot 2-X-6, San Roque, 8.5 ha) — pay-to-stay compensation, Patricia 1/3 (Art. 487)',
       matter_code = 'MWK-001',
       readiness = 0.20,
       next_step = '(1) Vision re-OCR T-32917 deep courses [$0 desk, no gate] → names the ~4.2 ha unmapped sub-lots/occupants; (2) barangay canvass + assessor/RD cross-check → occupant per parcel + track; (3) serve pay-to-stay on informal occupants (Patricia 1/3) — PILOT: T-52537 / Sps. Gaulit (paper lead in hand) can go first; (4) collect → ledger. Titled adverse (Leaño/Vergara/Balane) → nullity track, not pay-to-stay.',
       value_basis = 'Unquantified until the canvass (occupant count × rate). T-32917 = 8.5 ha; sub-lots on paper ~4.3 ha (incl. T-38838 3.2 ha), ~4.2 ha unmapped/OCR-dirty. Pay-to-stay runs on Patricia 1/3 via Art. 487 — no guardianship.',
       source_ref = 'case_work/MWK-001/CENSUS_WORKLIST_T32917_2026-09.md; T4497_LANDBANK_SQUATTER_LEDGER.md; SQUATTER_ENGAGEMENT_RIGHTS_SCHEME.md; DRAFT_squatter_demand_and_ejectment.md; Art. 487 Civil Code',
       note = COALESCE(note,'') || ' [2026-10-24 FOCUS: the active 4497 front while CV6839 waits on guardianship. No-gate desk step = vision re-OCR T-32917 deep courses. Pilot = Gaulit/T-52537.]',
       updated_at = now()
 WHERE front_code = 'MF-T4497-OCCUPANT-COMP';

-- mark CV6839 explicitly PARKED (waits for guardianship/administration for the non-participating thirds)
UPDATE money_fronts
   SET note = COALESCE(note,'') || ' [2026-10-24 PARKED by operator: CV6839 waits for guardianship/administration (all-heirs collect). Focus moved to the 4497 squatter parcels.]',
       updated_at = now()
 WHERE front_code = 'MF-CV6839';
