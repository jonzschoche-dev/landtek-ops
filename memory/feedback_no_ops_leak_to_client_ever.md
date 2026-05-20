---
name: no-ops-leak-to-client-ever-p0
description: "P0 hard rule — internal ops content must never reach any Landtek client, ever. Every outbound to a client chat_id passes a content gate or is blocked."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: bd418b71-6636-441c-8ebd-97897cec3394
---

**P0 — INVIOLABLE RULE FOR ALL LANDTEK CLIENTS, CURRENT AND FUTURE:**

Internal operational content must NEVER reach a client through any channel, at any time, on any case. This is not aspirational. It is enforced in code with a hard fail-closed gate.

**What counts as "ops content" (denylist tells, blocked at the gate):**
- HTML `<code>` blocks (database row dumps, dict literals, SQL fragments)
- Meta-agent / gap_alert / sentinel terminology ("gap_alert", "meta-agent", "invariant", "back-test", "truth-negotiator", "axiom-validator")
- Internal IDs and column names ("doc_date_norm", "case_file=NULL", "matter_code=", "intake_response_id", "tg_inquiry_queue", "execution_status")
- Priority labels in ops format ("P0", "P1", "P2", "P3", "🆘 P", "🚨 P")
- Database health / pipeline jargon ("NULL", "unextracted", "unclassified", "sparse timeline", "stub", "scanner-skipped", "OCR")
- Cron / service / infrastructure language ("heartbeat", "deactivated", "systemd", "cron")

**What may reach a client (whitelist intent):**
- Case-relevant updates ("Pretrial confirmed for June 30…")
- Direct questions for the client ("Did the May 22 meeting in Naga happen as planned?")
- Document acknowledgments ("Received your upload of [filename] — under review")
- Deadline reminders relevant to the client's own action items
- Scheduled status reports written for the client (drafted, audited, approved)

**Enforcement (mechanical, not procedural):**
1. `client_safe_gate.py` runs a denylist regex over every message routed with audience ∈ {`client`, `both`}.
2. `tg_send` in `tg_dispatcher.py` calls the gate before any send to a client chat_id. If the gate fails, the send is BLOCKED, the failure is queued as an ops alert to Jonathan, and `tg_inquiry_queue.notes` records the block reason.
3. `comms_recipients.py` keeps a CLIENT_CHAT_IDS registry. Any future Telegram-API call site that includes a known client chat_id must route through `tg_send` (no raw `requests.post` to a client ID). A pre-commit test scans the repo for raw chat_id literals matching the registry and fails CI.
4. Regression test in `tests/test_client_safe_gate.py` asserts that every known ops `kind` value (gap_alert, report, comms_probe-failure, etc.) is correctly blocked from client delivery.

**Why this rule exists (concrete incident, 2026-05-19):** Meta-agent gap digests at message_ids 1351 and 1355 (full of `<code>{'arta_case': 'CTNSL202510210747'}</code>`, "Truth-negotiator may have regressed", "executed_filed doc with no parseable date — breaks stage-awareness") were delivered to Don Qi, the MWK-001 estate Administrator, as a downstream side effect of an ops fix. Jonathan's verbatim response: *"there should never be a message like this sent to our client"* and *"this can never happen again with any client ever in the future of Landtek."*

**How to apply:**
- When adding a new outbound sender script, import `client_safe_gate.assert_client_safe(text, audience)` and call it BEFORE any send where the audience includes a client.
- When adding a new inquiry `kind`, classify it in `comms_recipients.KIND_AUDIENCE`. Unknown kinds default to ops, but the rule is: classify explicitly, do not rely on the default.
- Client-facing messages should be drafted in the same way as a Landtek partner emails the client. If you would not type the literal text into a client-facing email, the gate should block it. If the gate doesn't, add the missing pattern to the denylist.
- Run `python3 client_safe_gate.py --selftest` periodically; the meta-agent sentinel does so hourly.
- A client-facing message that gets blocked is NOT an error to silently retry. It is a signal that an ops template leaked into a client path. Fix the source, never bypass the gate.

This rule supersedes any inherited convenience pattern. Any future LLM session, deploy script, or n8n flow that violates it is doing the wrong thing — even if "it worked before."
