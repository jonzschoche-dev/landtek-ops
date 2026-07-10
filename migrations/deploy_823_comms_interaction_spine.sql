-- deploy_823: comms interaction spine — READ-ONLY VIEWS (greenlit: views-first, 6.2).
-- Unifies the three comms stores into one interaction timeline + a per-party relationship rollup.
-- Additive, reversible, zero write-path. Foundation for the agentic relationship engine (COMM-AGENT-MAX).
-- Grounded schemas (live 2026-07-09):
--   channel_messages(channel_id,channel_user_id,direction,text_content,status,sent_at)
--   leo_interactions(channel,sender_id,question,reply_text,case_file,timestamp)
--   outbound_messages(chat_id,recipient_name,content_preview,source,success,sent_at)
--
-- Apply (post-gate-green): docker exec -i n8n-postgres-1 psql -U n8n -d n8n < migrations/deploy_823_comms_interaction_spine.sql
-- Rollback: DROP VIEW IF EXISTS v_comms_relationship; DROP VIEW IF EXISTS v_comms_interactions;

CREATE OR REPLACE VIEW v_comms_interactions AS
  SELECT 'channel_messages'::text AS src, cm.id::text AS ref,
         c.name AS channel, cm.channel_user_id AS party_key,
         cm.direction, cm.sent_at AS ts,
         left(cm.text_content, 240) AS preview, cm.status AS meta
  FROM   channel_messages cm JOIN channels c ON c.id = cm.channel_id
UNION ALL
  SELECT 'leo_interactions', li.id::text,
         li.channel, li.sender_id,
         'exchange', li.timestamp,
         left(coalesce(li.question, li.reply_text), 240), li.case_file
  FROM   leo_interactions li
UNION ALL
  SELECT 'outbound_messages', om.id::text,
         coalesce(om.source,'telegram'), om.chat_id,
         'outbound', om.sent_at,
         left(om.content_preview, 240),
         (CASE WHEN om.success THEN 'sent' ELSE 'failed' END)
  FROM   outbound_messages om;

CREATE OR REPLACE VIEW v_comms_relationship AS
SELECT party_key,
       count(*)                                     AS interactions,
       count(*) FILTER (WHERE direction='inbound')  AS inbound,
       min(ts)                                      AS first_seen,
       max(ts)                                      AS last_seen,
       array_agg(DISTINCT channel)                  AS channels_used,
       max(meta) FILTER (WHERE meta LIKE 'MWK%' OR meta LIKE 'PAR%' OR meta LIKE '%-001') AS client_hint
FROM   v_comms_interactions
WHERE  party_key IS NOT NULL
GROUP  BY party_key;
