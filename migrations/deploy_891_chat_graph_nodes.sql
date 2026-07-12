-- deploy_888: chat-as-graph-node — every inbound chat becomes a first-class, matter-anchored node so the
-- A76 internal recompute (L4) is seeded from REAL context, not an arbitrary ORDER BY matter_code.
--
-- Corrections over the naive prompt: (a) channel_messages has no mapped_client_code/ts (client is on
-- channel_users); (b) v_relationship_graph is EDGE-shaped so a chat becomes a node via chat->X EDGES;
-- (c) fact->matter MEMBERSHIP edges added (without them matters barely connect to facts → ego=0);
-- (d) each chat anchors to ONE matter (client's most fact-rich) so the ego is bounded, not the whole client.
--
-- PERF (the real blocker): the co-citation self-join ('shares_source', ~27k over 5015^2) is computed on
-- ANY reference to the view — filtering it in a WHERE does not skip it. So we SPLIT: a STRUCTURAL view
-- (no self-join, cheap — the traversal surface) and the FULL view = structural ∪ shares_source (unchanged
-- for fact-graph consumers). The ego traversal uses the structural view → fast.
-- Additive + idempotent. Rollback = re-apply deploy_relationship_graph.sql + DROP VIEW …_structural.

CREATE INDEX IF NOT EXISTS idx_matter_facts_source_id ON matter_facts (source_id);

-- ── STRUCTURAL view: every edge EXCEPT the co-citation self-join (the traversal surface) ──
CREATE OR REPLACE VIEW v_relationship_graph_structural AS
WITH contra_ids AS (
  SELECT c.ctid AS cid, (regexp_matches(c.fact_ids, '\d+', 'g'))[1]::bigint AS fid
    FROM contradictions c WHERE c.fact_ids ~ '\d'
)
SELECT 'fact'::text AS src_type, a.fid::text AS src_id, 'fact'::text AS tgt_type, b.fid::text AS tgt_id,
       'contradicts'::text AS edge_type, _client_of(m1.matter_code) AS client_code
  FROM contra_ids a JOIN contra_ids b ON a.cid = b.cid AND a.fid < b.fid
  JOIN matter_facts m1 ON m1.id = a.fid JOIN matter_facts m2 ON m2.id = b.fid
 WHERE _client_of(m1.matter_code) IS NOT DISTINCT FROM _client_of(m2.matter_code)
UNION ALL
SELECT 'fact', cml.fact::text, 'matter', cml.supports_matter, 'supports', _client_of(cml.source_matter)
  FROM cross_matter_links cml WHERE cml.fact IS NOT NULL
   AND _client_of(cml.source_matter) IS NOT DISTINCT FROM _client_of(cml.supports_matter)
UNION ALL
SELECT 'matter', k.controlling_matter, 'matter', cm, 'cascade', _client_of(k.controlling_matter)
  FROM keystones k, unnest(k.cascade_matters) AS cm
 WHERE _client_of(k.controlling_matter) IS NOT DISTINCT FROM _client_of(cm)
UNION ALL
SELECT 'channel_user', cu.channel_user_id, 'client', cu.mapped_client_code, 'identity', cu.mapped_client_code
  FROM channel_users cu WHERE cu.mapped_client_code IS NOT NULL
UNION ALL
SELECT 'fact', mf.id::text, 'document', mf.source_id, 'provenance', _client_of(mf.matter_code)
  FROM matter_facts mf WHERE mf.provenance_level='verified' AND mf.source_id ~ '^[0-9]+$'
UNION ALL
SELECT 'message', ca.channel_message_id::text, 'document', ca.doc_id::text, 'attachment', ca.client_code
  FROM comms_artifacts ca WHERE ca.doc_id IS NOT NULL
UNION ALL
-- fact -> matter MEMBERSHIP (matters now connect to their facts)
SELECT 'fact', mf.id::text, 'matter', mf.matter_code, 'in_matter', _client_of(mf.matter_code)
  FROM matter_facts mf WHERE mf.provenance_level='verified' AND _client_of(mf.matter_code) IS NOT NULL
UNION ALL
-- chat -> matter: inbound chat anchored to ONE matter (client's most fact-rich); A5-safe (same client)
SELECT 'chat', cm.id::text, 'matter', anchor.matter_code, 'chat_context', cu.mapped_client_code
  FROM channel_messages cm
  JOIN channel_users cu ON cu.channel_id = cm.channel_id AND cu.channel_user_id = cm.channel_user_id
  JOIN LATERAL (
        SELECT mf.matter_code FROM matter_facts mf
         WHERE _client_of(mf.matter_code) = cu.mapped_client_code AND mf.provenance_level='verified'
         GROUP BY mf.matter_code ORDER BY count(*) DESC LIMIT 1
       ) anchor ON true
 WHERE cm.direction = 'inbound' AND cu.mapped_client_code IS NOT NULL
UNION ALL
-- chat -> channel_user: the sender identity of an inbound chat
SELECT 'chat', cm.id::text, 'channel_user', cm.channel_user_id, 'chat_sender', cu.mapped_client_code
  FROM channel_messages cm
  JOIN channel_users cu ON cu.channel_id = cm.channel_id AND cu.channel_user_id = cm.channel_user_id
 WHERE cm.direction = 'inbound' AND cu.mapped_client_code IS NOT NULL;

-- ── FULL view = structural ∪ the co-citation self-join (unchanged surface for fact-graph consumers) ──
CREATE OR REPLACE VIEW v_relationship_graph AS
SELECT * FROM v_relationship_graph_structural
UNION ALL
SELECT 'fact'::text, f1.id::text, 'fact'::text, f2.id::text, 'shares_source'::text, _client_of(f1.matter_code)
  FROM matter_facts f1
  JOIN matter_facts f2 ON f1.source_id = f2.source_id AND f1.id < f2.id
 WHERE f1.provenance_level='verified' AND f2.provenance_level='verified' AND f1.source_id ~ '^[0-9]+$'
   AND _client_of(f1.matter_code) IS NOT NULL
   AND _client_of(f1.matter_code) IS NOT DISTINCT FROM _client_of(f2.matter_code);

-- ── MATERIALIZED structural graph: the traversal surface, precomputed. The view's per-edge _client_of()
-- cost (~15-30s to walk a client subgraph live) becomes a one-time refresh cost; ego queries are then
-- millisecond index scans. Refreshed on a timer (scripts/refresh_relationship_graph.py); staleness is
-- bounded + acceptable for the internal reasoning plane (shadow). ──
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_relationship_graph_structural AS
  SELECT * FROM v_relationship_graph_structural WITH NO DATA;
REFRESH MATERIALIZED VIEW mv_relationship_graph_structural;
CREATE INDEX IF NOT EXISTS idx_mvrg_src ON mv_relationship_graph_structural (src_type, src_id, client_code);
CREATE INDEX IF NOT EXISTS idx_mvrg_tgt ON mv_relationship_graph_structural (tgt_type, tgt_id, client_code);
CREATE INDEX IF NOT EXISTS idx_mvrg_client ON mv_relationship_graph_structural (client_code);

SELECT 'structural edge types: ' || string_agg(DISTINCT edge_type, ', ') FROM v_relationship_graph_structural;
SELECT 'mv_relationship_graph_structural rows: ' || count(*)::text FROM mv_relationship_graph_structural;
