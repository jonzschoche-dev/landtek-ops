-- A76 P1 — the unified relationship graph, VIEW-ONLY.
--
-- AUDIT-THEN-BUILD CORRECTION (2026-07-11): the work order said "populate fact_edges". But the live
-- ontology_validator V1 BLOCKS writes to fact_edges as a DRIFT table (ONTOLOGY §3) — the desk's §5
-- "fact_edges vs kg_triples" ruling is already made: fact_edges is drift. So we do NOT write it (that
-- would bypass the truth gate). Instead the unified graph is a VIEW that COMPUTES every edge — fact->fact
-- included — live from the canonical source tables. No drift write; always current; A5 enforced IN THE
-- QUERY (a cross-client edge is refused, never weighted — hard constraint, not a parameter).
--
-- Idempotent. Rollback: DROP VIEW v_relationship_graph;

CREATE OR REPLACE VIEW v_relationship_graph AS
WITH contra_ids AS (   -- parse numeric fact ids out of contradictions.fact_ids (text)
  SELECT c.ctid AS cid, (regexp_matches(c.fact_ids, '\d+', 'g'))[1]::bigint AS fid
    FROM contradictions c WHERE c.fact_ids ~ '\d'
)
-- fact -> fact  (co-citation: two verified facts citing the SAME document = shared-provenance support)
SELECT 'fact'::text AS src_type, f1.id::text AS src_id, 'fact'::text AS tgt_type, f2.id::text AS tgt_id,
       'shares_source'::text AS edge_type, _client_of(f1.matter_code) AS client_code
  FROM matter_facts f1
  JOIN matter_facts f2 ON f1.source_id = f2.source_id AND f1.id < f2.id
 WHERE f1.provenance_level='verified' AND f2.provenance_level='verified' AND f1.source_id ~ '^[0-9]+$'
   AND _client_of(f1.matter_code) IS NOT NULL
   AND _client_of(f1.matter_code) IS NOT DISTINCT FROM _client_of(f2.matter_code)   -- A5
UNION ALL
-- fact -> fact  (contradiction register; A65 owns the arrow-of-time)
SELECT 'fact', a.fid::text, 'fact', b.fid::text, 'contradicts', _client_of(m1.matter_code)
  FROM contra_ids a
  JOIN contra_ids b ON a.cid = b.cid AND a.fid < b.fid
  JOIN matter_facts m1 ON m1.id = a.fid
  JOIN matter_facts m2 ON m2.id = b.fid
 WHERE _client_of(m1.matter_code) IS NOT DISTINCT FROM _client_of(m2.matter_code)   -- A5
UNION ALL
-- fact -> matter  (cross-matter support, A14 proof_doc_id-gated)
SELECT 'fact', cml.fact::text, 'matter', cml.supports_matter, 'supports', _client_of(cml.source_matter)
  FROM cross_matter_links cml WHERE cml.fact IS NOT NULL
   AND _client_of(cml.source_matter) IS NOT DISTINCT FROM _client_of(cml.supports_matter)   -- A5
UNION ALL
-- matter -> matter  (keystone cascade)
SELECT 'matter', k.controlling_matter, 'matter', cm, 'cascade', _client_of(k.controlling_matter)
  FROM keystones k, unnest(k.cascade_matters) AS cm
 WHERE _client_of(k.controlling_matter) IS NOT DISTINCT FROM _client_of(cm)   -- A5
UNION ALL
-- channel_user -> client  (identity, A25/V7)
SELECT 'channel_user', cu.channel_user_id, 'client', cu.mapped_client_code, 'identity', cu.mapped_client_code
  FROM channel_users cu WHERE cu.mapped_client_code IS NOT NULL
UNION ALL
-- fact -> document  (provenance root; document is client-agnostic, edge carries the fact's client)
SELECT 'fact', mf.id::text, 'document', mf.source_id, 'provenance', _client_of(mf.matter_code)
  FROM matter_facts mf WHERE mf.provenance_level='verified' AND mf.source_id ~ '^[0-9]+$'
UNION ALL
-- message -> document  (sink link; 0 rows today — present-but-empty until chat media arrives)
SELECT 'message', ca.channel_message_id::text, 'document', ca.doc_id::text, 'attachment', ca.client_code
  FROM comms_artifacts ca WHERE ca.doc_id IS NOT NULL;
-- P1.1 deferred: person->matter (doc_entities JOIN document_matter_links) — omitted rather than guessed.

SELECT 'v_relationship_graph edge types: ' || string_agg(DISTINCT edge_type, ', ') FROM v_relationship_graph;
