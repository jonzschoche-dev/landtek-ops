-- A76 P1 — the unified relationship graph. Two parts, both grounded against the live schema:
--   (1) fact_edges (from_fact,to_fact int) is fact->fact ONLY — make its backfill idempotent.
--   (2) v_relationship_graph: the UNIFIED typed-edge view over every carrier, A5 enforced IN THE QUERY
--       (cross-client edges are REFUSED, never weighted — A5 is a hard constraint, not a parameter).
-- The paste's "backfill all edge types into fact_edges" is schema-impossible (from_fact/to_fact are
-- integer FKs to matter_facts) — heterogeneous edges live in the view, per RELATIONSHIP_EQUILIBRIUM.md §5
-- ("unify into one typed relationship VIEW/store"). kg_triples is NOT paralleled; fact_edges stays the
-- fact->fact spine and the view is the read surface.
-- Idempotent. Rollback: DROP VIEW v_relationship_graph; DROP INDEX uq_fact_edges_triple;

CREATE UNIQUE INDEX IF NOT EXISTS uq_fact_edges_triple ON fact_edges (from_fact, to_fact, edge_kind);

CREATE OR REPLACE VIEW v_relationship_graph AS
-- fact -> fact  (co-citation / contradiction; populated in fact_edges, backfill already A5-scoped)
SELECT 'fact'::text AS src_type, fe.from_fact::text AS src_id,
       'fact'::text AS tgt_type, fe.to_fact::text AS tgt_id,
       fe.edge_kind AS edge_type, _client_of(f1.matter_code) AS client_code
FROM fact_edges fe JOIN matter_facts f1 ON f1.id = fe.from_fact
UNION ALL
-- fact -> matter  (cross-matter support, A14 proof_doc_id-gated) — A5: same client both sides
SELECT 'fact', cml.fact::text, 'matter', cml.supports_matter, 'supports', _client_of(cml.source_matter)
FROM cross_matter_links cml
WHERE cml.fact IS NOT NULL
  AND _client_of(cml.source_matter) IS NOT DISTINCT FROM _client_of(cml.supports_matter)
UNION ALL
-- matter -> matter  (keystone cascade) — A5: same client both sides
SELECT 'matter', k.controlling_matter, 'matter', cm, 'cascade', _client_of(k.controlling_matter)
FROM keystones k, unnest(k.cascade_matters) AS cm
WHERE _client_of(k.controlling_matter) IS NOT DISTINCT FROM _client_of(cm)
UNION ALL
-- channel_user -> client  (identity, A25/V7)
SELECT 'channel_user', cu.channel_user_id, 'client', cu.mapped_client_code, 'identity', cu.mapped_client_code
FROM channel_users cu WHERE cu.mapped_client_code IS NOT NULL
UNION ALL
-- fact -> document  (provenance root; the document is client-agnostic, edge carries the fact's client)
SELECT 'fact', mf.id::text, 'document', mf.source_id, 'provenance', _client_of(mf.matter_code)
FROM matter_facts mf WHERE mf.provenance_level='verified' AND mf.source_id ~ '^[0-9]+$'
UNION ALL
-- message -> document  (sink link; currently 0 rows — present-but-empty until chat media arrives)
SELECT 'message', ca.channel_message_id::text, 'document', ca.doc_id::text, 'attachment', ca.client_code
FROM comms_artifacts ca WHERE ca.doc_id IS NOT NULL;
-- NB deferred to P1.1: person->matter (doc_entities JOIN document_matter_links) — needs the entity->doc->matter
-- join; omitted here rather than guessed, so the view stays correct. Added when doc_entities schema is wired.

SELECT 'v_relationship_graph edge types: ' || string_agg(DISTINCT edge_type, ', ')
FROM v_relationship_graph;
