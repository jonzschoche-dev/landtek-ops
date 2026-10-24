-- deploy_1271_gaulit_is_titled_not_paytostay.sql
-- Operator (Jonathan, 2026-10-24): "the gaulit pilot — they have a title."
-- VERIFIED: RD annotation (doc 135, TCT 45616) — "Affidavit of Confirmation executed by Cesar dela
-- Fuente confirming the previous sale in favor of Delfin Gaulit" (Lot 2-B, Pcd-05-023697, 1993 sale).
-- Gaulit took title through the Cesar de la Fuente chain (same void-SPA chain as Balane) and is on
-- the 20-transferee list → TITLED ADVERSE HOLDER → de la Fuente void-chain NULLITY/reconveyance,
-- NOT pay-to-stay. The CENSUS_WORKLIST mislabeled him as an informal tax-declarant; pay-to-stay to a
-- titled holder would wrongly concede his possession/title.
--
-- Fix: the pay-to-stay lane applies ONLY to genuinely no-title informal settlers. Named de la Fuente
-- transferees (Gaulit, Leaño, Balane, etc.) go to the void-chain nullity track. There is no ready
-- pay-to-stay pilot until the canvass finds a true no-title occupant. Internal/reversible.

UPDATE money_fronts
   SET next_step = '(1) Vision re-OCR T-32917 deep courses [$0 desk, no gate] → name the ~4.2 ha unmapped sub-lots; (2) barangay canvass → CLASSIFY each occupant: TITLED (de la Fuente transferee) vs NO-TITLE informal; (3) pay-to-stay (Patricia 1/3, Art. 487) ONLY for no-title informal settlers; (4) TITLED transferees (Gaulit, Leaño, Balane, etc.) → de la Fuente void-chain nullity/reconveyance, NOT pay-to-stay. No ready pilot until the canvass surfaces a true no-title occupant.',
       value_basis = 'Unquantified until the canvass. CAUTION: most named occupants on T-32917 appear to be de la Fuente TITLED transferees (nullity track), not informal settlers — pay-to-stay fits only no-title occupants, count unknown pre-canvass.',
       note = COALESCE(note,'') || ' [2026-10-24 CORRECTION: Gaulit is a de la Fuente TITLED transferee (RD doc 135, TCT 45616, Cesar sale) → NULLITY track, NOT the pay-to-stay pilot. Worklist mislabel fixed. Pay-to-stay = no-title settlers only.]',
       updated_at = now()
 WHERE front_code = 'MF-T4497-OCCUPANT-COMP';
