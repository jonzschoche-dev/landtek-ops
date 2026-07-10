-- deploy_824: channel_users.entity_id — the cross-channel person-key (greenlit: add now, 6.1).
-- Unblocks A25 Part 2 (same human across channels -> one client) AND gives the relationship graph
-- its person node. Mirrors the deploy_733 / parcels.client_code pattern: additive, nullable, reversible.
-- Forward-filled by platform_coordinator.py --resolve (entity-resolution path); NULL until resolved.
--
-- Apply (post-gate-green): docker exec -i n8n-postgres-1 psql -U n8n -d n8n < migrations/deploy_824_channel_users_entity_id.sql
-- Rollback: DROP VIEW IF EXISTS v_ontology_channel_person_cross; ALTER TABLE channel_users DROP COLUMN IF EXISTS entity_id;

ALTER TABLE channel_users ADD COLUMN IF NOT EXISTS entity_id integer REFERENCES entities(id);

-- V7 Part 2 detector (ships alongside V7 Part 1's 'log' shadow): one entity must not carry two clients.
CREATE OR REPLACE VIEW v_ontology_channel_person_cross AS
SELECT entity_id,
       count(DISTINCT mapped_client_code)     AS n_clients,
       array_agg(DISTINCT mapped_client_code) AS codes
FROM   channel_users
WHERE  entity_id IS NOT NULL AND mapped_client_code IS NOT NULL
GROUP  BY entity_id
HAVING count(DISTINCT mapped_client_code) > 1;   -- >1 client for one human = A25 violation

-- NB: register V7-Part2 config ('V7b','log') and wire --resolve to fill entity_id in the follow-up;
-- this migration is the schema delta only (schema-first, enforcement-later, per the V6/V7 discipline).
