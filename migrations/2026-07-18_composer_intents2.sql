-- 2026-07-18_composer_intents2.sql — composer takes ownership of the deploy_972 failure shapes
-- (Grok review item 2): title_inventory + client_status registry rows. Idempotent.

BEGIN;

INSERT INTO consensus_registry (concept, store_rank, reconcile_rule, staleness_h, notes) VALUES
('title_inventory',
 '[{"store":"title_brief","role":"cache","rank":2},
   {"store":"titles","role":"answer","rank":1},
   {"store":"document_titles","role":"mention_only","rank":5}]',
 'authority', 26,
 'the deploy_972 clueless ask-shape, composer-owned: count + status split + slice ids, S14-dosed; slices one follow-up away'),
('client_status',
 '[{"store":"matter_brief","role":"cache","rank":2},
   {"store":"matters","role":"answer","rank":1}]',
 'authority', 26,
 'bare status-update ask, client-wide: active matter headlines next-dated-first; undated count reported never hidden; matter-specific asks stay with matter_status')
ON CONFLICT (concept) DO UPDATE
   SET store_rank = EXCLUDED.store_rank, reconcile_rule = EXCLUDED.reconcile_rule,
       staleness_h = EXCLUDED.staleness_h, notes = EXCLUDED.notes, updated_at = now();

COMMIT;
