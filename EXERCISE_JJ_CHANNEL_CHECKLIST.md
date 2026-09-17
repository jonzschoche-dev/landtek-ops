# Exercise JJ's headless Leo channel as a real client (hands-on proof)

**Purpose:** prove the full service loop end-to-end with a real human-as-client, on the
already-cut-over Messenger channel (deploy_853–857). You ARE the client here (JJ Ildefonso
Moreno is the in-house test identity). Nothing here needs Claude — you run it and watch.

## Preconditions (verify first, on the VPS)
1. Messenger channel is `headless`:
   docker exec -i n8n-postgres-1 psql -U n8n -d n8n -c "SELECT channel,mode FROM leo_channel_mode;"
   → expect messenger = headless, rest = n8n.
2. leo_service timer healthy:
   systemctl is-active landtek-leo-service.timer   (or whatever the unit is named)
   → active.
3. You are operator (internal) and JJ is a resolved client (outward). Confirm:
   psql: SELECT channel_user_id, mapped_client_code FROM channel_users
         WHERE channel_user_id LIKE '%JJ%' OR mapped_client_code LIKE '%JJ%';
   → JJ bound to his client_code (outward → held for approval).

## The test (do this as JJ, from his Messenger chat)
Send, in order, these 4 messages as JJ:
  A) "What's the status of my case?"            (normal question — should ground + hold)
  B) "The deed says Section 4, Rule 74 applies"  (uncited legal rule — gate should FAIL/remediate)
  C) "Here's a photo of the title"  + attach an image  (ingestion: sinks to documents, OCR-pending)
  D) "When is my next deadline?"                 (should pull from the date graph, project gently)

## What you should observe (the proof)
For each, check the shadow/held ledger on the VPS:
  psql: SELECT inbound_msg_id, client, guard_class, remediated, would_send_human, action
        FROM leo_shadow_replies ORDER BY id DESC LIMIT 10;

  A) guard_class = pass (or warn), action = held_for_approval, a new outward_action order queued.
     → JJ's reply is DRAFTED and WAITING on you. Nothing sent.
  B) guard_class = fail (after the legal-rule gate tightens) or warn (before) → remediated to
     grounded-only. Confirm the assertion was stripped, not shipped.
  C) a new documents row (ingest_source=comms_messenger, processing_mode=ocr_pending) linked to
     JJ's client_code. The artifact did NOT drop. Check comms_artifacts ledger = landed/ocr_pending.
  D) reply cites JJ's real next deadline from the date graph, projected in plain language.

## The human action (the one you kept)
Approve ONE held reply (A or D) via the supervisor:
  psql: SELECT id, title, status FROM work_orders
        WHERE kind='outward_action' AND status='queued' ORDER BY id DESC LIMIT 5;
  → pick the JJ order, set status='done' (certify). Next leo_service tick delivers it to JJ.
Confirm JJ actually RECEIVES the approved reply on Messenger. That is the authentic-service proof:
  message → grounded → projected → held → you certify → delivered. Zero unapproved client contact.

## Rollback (if anything looks wrong)
  docker exec -i n8n-postgres-1 psql -U n8n -d n8n \
    -c "UPDATE leo_channel_mode SET mode='n8n' WHERE channel='messenger';"
  → Messenger reverts to n8n fallback. No code change needed.

## Success criteria (all must hold)
- [ ] Every JJ inbound produced a ledger row (none dropped).
- [ ] Every client reply was HELD, never auto-sent (outward_sent_without_approval = 0).
- [ ] The uncited legal rule was caught (fail or remediated), not shipped.
- [ ] The attached image landed in documents under JJ's client_code (lossless).
- [ ] One certified reply was delivered to JJ on Messenger.
- [ ] You did NOT have to touch code — the loop worked as built.

## Notes
- This is IN-HOUSE (you as JJ). It proves the mechanism; it is not a real third-party client.
- If B ships a warning instead of failing, run WORKORDER_LEGAL_RULE_GATE.md first, then re-test.
- The collation-mismatch (deploy_856) is unrelated to this test but note it for a maintenance window.
