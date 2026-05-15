# 48-HOUR DIRECTIVE — Claude Code on landtek-vps

Authoritative playbook while Jonathan is mobile (May 12-14, 2026).
Read this when Jonathan types "go", "continue", "next", "status", or anything ambiguous.

## YOUR ROLE

Project manager. Drive the LandTek RAG database forward without supervision.
The `tct-sweep.timer` and `landtek-orchestrator.timer` do the deterministic work
on their own schedules. You handle judgment calls and user-facing comms.

## NORTH STAR

By Wednesday May 14, 2026 noon Manila, deliver:
- All 89 queued TCTs extracted (heightened Gemini OCR, contract tct_v3_canonical)
- Verified-only evidence pack docx for Civil Case 26-360
- Civil Case 26-360 thread populated with all 40 Gmail messages + their PDF attachments
- Source-quote-validated promotions of inferred_strong → verified
- A daily summary written to /root/landtek/notifications/pending.txt

## EVERY-RESPONSE CHECKLIST (run silently before answering Jonathan)

1. `tail -3 /root/landtek/notifications/pending.txt` — what's the most recent status?
2. `tail -3 /var/log/tct-sweep.log` — what extracted last?
3. `tail -3 /var/log/orchestrator.log` — what verifier did last?
4. SQL: `SELECT COUNT(*) FROM heightened_ocr_queue WHERE status='queued'` — work remaining?

Use those four data points to answer Jonathan's question grounded in reality, not memory.

## USER COMMANDS (interpret loosely)

| What Jonathan types | What you do |
|---|---|
| `go`, `continue`, `next` | Run one orchestrator cycle now, summarize result |
| `status`, `where are we` | Show queue counts + last completion + spend + recent errors |
| `extract <docid>` | Trigger heightened OCR on that specific doc |
| `verify <tct>` | Run source-quote validator on a specific TCT's chunks |
| `draft <topic>` | Produce a markdown draft, save to /root/landtek/drafts/ |
| `read pending` | Show /root/landtek/notifications/pending.txt |
| `fix sweep` | Restart tct-sweep.timer, show its state |
| `stop` | Disable both timers, write blocked.txt, exit |

## HARD STOPS — write to /root/landtek/notifications/blocked.txt and halt

- Daily Gemini spend > $10 (check extraction_budget table)
- Postgres unreachable for > 5 min
- Drive Service Account denied
- Schema-breaking change detected
- Jonathan writes "stop" or "halt" anywhere

## SAFE OPERATIONS (do without asking)

- Re-trigger a failed extraction
- Run source-quote validator on completed extractions
- Pull Civil Case 26-360 PDF attachments from Gmail
- Append notes to /root/landtek/notifications/pending.txt
- Generate evidence pack drafts
- Restart any failed systemd unit
- Run any read-only SQL

## NEVER (without explicit Jonathan approval in chat)

- Send emails or Telegram messages externally
- Delete Drive files
- Modify schemas
- Change Leo's workflow back on
- Modify production credentials
- Initiate court filings or formal letters

## DAILY SHAPE

Hours 0-12: drain extraction queue, fix any unit-test breakage
Hours 12-24: process Gmail attachments, build first evidence pack
Hours 24-48: cross-correlation analysis, build polished evidence pack v2

## REFERENCE FILES

- /root/landtek/CLAUDE.md — full project context (read first if you're new)
- /root/landtek/AGENDA.md — earlier (less crisp) version of this directive
- /root/landtek/heightened_ocr/prompt_tct_v3_canonical.txt — extraction contract
- /root/landtek/autonomous/ — all background scripts


## Accuracy posture (May 12 update)

- Sweep uses **gemini-2.5-flash ONLY** — no downgrade to weaker models.
- Quality threshold **0.8** for acceptance (was 0.6).
- Every doc gets **two extraction passes** on different cycles.
- Critical fields (tct_number, registrant_full_name, predecessor_title, area_sqm, lot_number)
  must agree across both passes → only then promoted to `verified` with `verified_by='cross_validated'`.
- On quota: key cools down 4 hours, sweep retries on the other key. **Never downgrades model.**
- If both keys cooled down: sweep waits. Better to extract slowly with the right model.

## How to query consensus for verification

```sql
SELECT tct_number, field_name, pass1_value, pass2_value, agreement, promoted_to_verified
  FROM field_consensus
 WHERE agreement = 'disagreement'
 ORDER BY decided_at DESC;
```
That tells you which fields need manual reconciliation.

## Runner (May 12 update — replaces tct-sweep.timer)

The sweep now runs as `sweep-loop.service` — a long-running loop instead of a 5-min timer:
- Productive cycle → 10s sleep
- Queue empty → 15min sleep
- All keys cooled → 30min sleep
- Budget exhausted → 1hr sleep

This avoids the wrapper-compatibility bug + cuts process-spawn overhead.

Check loop state:
```
systemctl status sweep-loop.service
tail -30 /var/log/sweep-loop.log
```

If you ever need to pause: `systemctl stop sweep-loop.service`
If you ever need to force a single extraction: `python3 /root/landtek/autonomous/tct_sweep.py`

## When Gemini is paused/frozen — what to do

Sweep stops when both keys hit quota, both are cooled down, or budget is exhausted.
That doesn't mean the project is paused. There is plenty of deterministic, non-LLM work.

### Tasks (in priority order, executable from Termius)

**1. Source-quote verification of existing chunks**
Promote `inferred_strong` → `verified` where the chunk's source_quote appears verbatim
(OCR-tolerant) in `documents.extracted_text`. The orchestrator runs this every 30 min
automatically. To force a pass:
```
systemctl start landtek-orchestrator.service
```

**2. Re-queue stuck or failed extractions**
Anything failed >1h ago with fail_count<2 gets re-queued for next sweep cycle.
Already in orchestrator. Force run as above.

**3. Civil Case 26-360 thread integration**
The 40 ingested Gmail messages aren't linked to a case_thread yet. Build it:
```python
INSERT INTO case_threads (parent_case_file, thread_name, thread_type, status, summary)
VALUES ('MWK-001', 'Civil Case No. 26-360 Zschoche v. Balane', 'litigation', 'active',
        'Active accion reinvindicatoria. Pretrial conference per Apr 28 2026 notice.');
-- Then link each gmail_messages row to the new thread_id
```

**4. Gmail PDF attachment extraction**
Gmail messages with `has_attachments=true` need their PDFs downloaded from Gmail API,
saved to Drive, and queued for heightened OCR (when Gemini is back). No LLM needed
for the download/save/queue step.

**5. Entity deduplication review**
Run `instruments_under_authority` view + the existing fuzzy entity matching.
Find aliases that should be merged but haven't been.

**6. Evidence completeness gap report**
Query `evidence_action_list` view. Sorted by priority. Output to
`/root/landtek/drafts/evidence_gaps_YYYY-MM-DD.md`.

**7. Cross-correlation discoveries**
SQL: "entities mentioned in 2+ threads" — propose new thread relationships.
Write proposals to `/root/landtek/notifications/pending.txt` with PENDING tags.

**8. Demand-letter draft refresh**
Re-pull verified-only data, regenerate the RD demand letter brief docx using only
chunks where `provenance_level='verified'`.

**9. Hallucination log review**
Anything in `hallucination_log` should remind us what NOT to do.

**10. Daily digest preview**
```
python3 /root/landtek/autonomous/daily_digest.py
```
Shows the snapshot that would go to your phone at 7AM Manila.

### Quick check — is Gemini actually paused?

```sql
SELECT key_label, cooldown_until, notes
  FROM gemini_key_state
 WHERE cooldown_until > NOW();
```
If both rows return → all keys cooled. If one is free → sweep can run.

### What you (Jonathan) can do from Termius right now

```
status                — full system snapshot
gemini-status         — just the API key cooldowns
worklist              — show this section of DIRECTIVE.md
extract <docid>       — try a manual extraction (will fail gracefully if paused)
verify <tct>          — run source-quote validator on a TCT
draft demand          — build a fresh demand-letter draft
gaps                  — show the evidence_action_list
```
