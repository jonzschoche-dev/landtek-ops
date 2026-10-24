-- deploy_1269_cv6839_all_heirs_required.sql
-- Operator (Jonathan, 2026-10-24): "my understanding is that we needed all three heirs."
-- This is backed by the VERIFIED Land Bank FSSC5 reply (22 Oct 2026), which to RELEASE requires:
--   registered settlement of estate by ALL heirs + eCAR + publication; an updated apostilled SPA
--   from Patricia "and all heirs" on T-4494/4501/4502/4503; heir's bond; specimen signatures.
--   LBP's own note: each heir signs for their own share — Patricia cannot authorize for the others.
--
-- Supersedes deploy_1268's "Patricia moves alone" framing (that was the memo's joint-credit THEORY,
-- untested by counsel/payor). Practical reality: ALL THREE heirs' authority is needed to collect.
-- Hoppe refuses → her 1/3 needs an authority vehicle (administration/guardianship over her interest).
-- That is the real gate, and it reconciles the operator's earlier "writ waits for guardianship."
-- readiness 0.50 → 0.30. Internal/reversible.

UPDATE money_fronts
   SET gate = 'ALL-HEIRS authority to collect (LBP FSSC5 22 Oct 2026): estate settlement by all 3 heirs + eCAR + each heir''s apostilled SPA. Hoppe refuses → her 1/3 needs administration/authority vehicle.',
       gate_date = NULL,
       readiness = 0.30,
       next_step = 'Build all-heirs authority: (1) registered estate settlement of T-4494/4501/4502/4503 by all 3 heirs + eCAR + publication; (2) apostilled SPAs — Patricia (ready), Marcia (POA), Hoppe''s 1/3 via administration (she refuses); (3) heir''s bond + specimen signatures. Then substitute Cesar + motion for execution. (Fallback litigation theory: Art. 487 / joint-credit to move Patricia''s 1/3 alone — untested vs LBP process.)',
       note = COALESCE(note,'') || ' [2026-10-24 operator + VERIFIED LBP FSSC5 22 Oct: ALL THREE heirs needed to COLLECT — estate settlement by all heirs + each heir''s SPA. Supersedes the deploy_1268 "Patricia alone" framing (memo theory only). Hoppe''s refusal is the real blocker → her 1/3 via administration. This is why the writ path effectively waits on an authority/administration vehicle for the non-participating thirds.]',
       updated_at = now()
 WHERE front_code = 'MF-CV6839';
