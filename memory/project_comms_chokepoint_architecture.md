---
name: comms-chokepoint-architecture-2026-05-19
description: "The Landtek client-comms chokepoint architecture — single comms_send() function, audience column, monkey-patch backstop, hourly repo scanner"
metadata: 
  node_type: memory
  type: project
  originSessionId: bd418b71-6636-441c-8ebd-97897cec3394
---

**Architecture (deployed 2026-05-19 after the comms-blackout + ops-leak incidents):**

All Telegram outbound flows through `/root/landtek/comms.py::comms_send()`:

```python
from comms import comms_send
ok, results = comms_send(
    text,
    audience="ops" | "client" | "both",     # REQUIRED — no default at call sites
    kind="gap_alert" | "intake_item" | ...,  # what kind of message
    case_file="MWK-001",                     # routes recipient lookup
)
```

**Layers (defense in depth):**

1. **Recipient registry** — `comms_recipients.py` holds the hardcoded (name, chat_id) tuples per case. `OPS_RECIPIENTS = [Jonathan]`, `MWK_001_CLIENT_RECIPIENTS = [Don Qi]`. Adding a new client = 1 file edit, visible in git diff.

2. **Audience column** — `tg_inquiry_queue.audience` (text, CHECK in `ops|client|both`, default `ops`). Every queued row carries its own routing decision. Existing rows backfilled from KIND_AUDIENCE taxonomy.

3. **comms_send chokepoint** (`comms.py`):
   - Required `audience` arg (no default — explicit at call site).
   - For `audience ∈ {client, both}`: runs `client_safe_check()` (denylist of ~30 ops-jargon patterns: `<code>`, `gap_alert`, `doc_date_norm`, P0/P1 labels, `meta-agent`, `systemd`, `cron`, `back-test`, etc.). Failure → BLOCK + ops alert.
   - For `kind ∈ STRICT_AUDIT_KINDS` (`report`, `brief`, `memo`, `demand_letter`, `mediation_memo`): runs `output_audit.audit_text(strict=True)`. Failure → BLOCK + ops alert.
   - Per-recipient HTTP status logged (no more silent "TG digest sent" lies).

4. **requests.post backstop** — `comms.install_telegram_backstop()` monkey-patches `requests.post` (filtered to api.telegram.org URLs). Any direct POST to a known CLIENT chat_id is intercepted, blocked (synthetic 403), and an ops alert is fired. Sends to ops chat_ids and non-Telegram URLs pass through unchanged. Auto-installed when `comms.py` is imported.

5. **Hourly repo scanner** — `comms_invariant_scanner.py` (systemd timer `comms-invariant-scanner.timer`). Walks `/root/landtek/*.py`, flags any file that contains a CLIENT chat_id literal outside `ALLOWED_FILES`. Enqueues an ops gap_alert if any violation. This is the CI substitute — catches new direct-send code before it ships.

**Migration strategy: gradual.** The 18 legacy scripts that hardcode Jonathan's chat_id (`6513067717`) keep working unchanged — they only send to ops, no client risk. As each is touched in normal work, replace its raw send with `comms_send(audience='ops', kind=..., case_file=...)`. The backstop guarantees no NEW client-leak code can run regardless.

**Why this design (incident chain that drove it):**
- 2026-05-17: legacy n8n decommission left bot webhook pointing at dead URL → 48h inbound blackout, see [[2026-05-17-comms-blackout-incident]]
- 2026-05-19 (morning): naive fan-out patch leaked meta-agent gap_alerts to Don Qi (the MWK-001 administrator) at msg_ids 1351 + 1355
- 2026-05-19 (afternoon): Jonathan: *"this can never happen again with any client ever in the future of Landtek"* — see [[feedback_no_ops_leak_to_client_ever]] + [[feedback_client_comms_hardcoded]]
- Architecture deployed same day: chokepoint + backstop + scanner

**Key files:**
- `/root/landtek/comms.py` — chokepoint, gate, backstop, BlockedResponse
- `/root/landtek/comms_recipients.py` — recipient registry + KIND_AUDIENCE map
- `/root/landtek/comms_invariant_scanner.py` — hourly repo scan
- `/root/landtek/tg_dispatcher.py:36` — `tg_send()` now thin wrapper over `comms_send`
- `/etc/systemd/system/comms-invariant-scanner.{service,timer}`

**Adding a new client (future Landtek client onboarding):**
1. Add `(NAME, "telegram_id") ` to `comms_recipients.py` under a new `<CASE>_CLIENT_RECIPIENTS` constant.
2. Add the `<CASE>_BOTH_RECIPIENTS` and update `recipients_for()` to route the new case_file.
3. Add the new chat_id to `CLIENT_CHAT_IDS` in both `comms.py` and `comms_invariant_scanner.py`.
4. Run `python3 comms.py` to confirm the gate self-test passes.
5. Commit. The chokepoint + backstop + scanner now protect the new client too.
