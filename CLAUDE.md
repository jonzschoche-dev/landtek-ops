# ⚡ READ FIRST: MASTER_PLAN.md

`MASTER_PLAN.md` is the single source of truth for current direction, status, and the north
star. Read it before answering anything ambiguous from Jonathan. It is the **only** authoritative
plan — **update it in place; never create parallel directive / roadmap / status / deployment-plan
docs.** That sprawl, plus stale "READ FIRST" pointers into it, is exactly what kept dragging
sessions back to a May-2026 reality (the old DIRECTIVE.md "48-hour playbook, May 12-14" was the
worst offender). On 2026-06-12 the 9 prior planning docs were consolidated into `MASTER_PLAN.md`
and moved to `archive/planning-2026-06/`.

**North star (as of 2026-06-12): Aug 12, 2026 — Jonathan testifies as Patricia's witness** in Civil
Case 26-360 (MTC Mercedes, Summary Procedure); live Summary-Judgment motion + Balane judicial-
affidavit fight. (NOT the old "Aug 1 pre-trial"; pre-trial was May 13, passed.) See `MASTER_PLAN.md` §1.

---

## Session-start protocol (multi-agent git routine)

A **SessionStart hook** has just run `scripts/landtek_git_routine.sh start` — its
output appears in your context above this file. Read it before doing anything else.

- **"Working tree clean / Up to date"** → proceed normally.
- **"Pulled N new commits"** → the other agent (VPS or Mac) wrote those files for
  a reason that may affect your task. Read the new files before editing anything.
- **"Working tree dirty before pull"** → STOP. Surface the dirty files to Jonathan
  and decide together before any new work. Never blindly discard or commit them.

**Before saying "done for now"**, invoke `/session-end` to surface uncommitted /
unpushed / untracked work. The SessionEnd hook also fires on `/quit` as a safety
net, but `/session-end` mid-conversation lets you handle warnings in dialogue.

For commits, use the routine's deploy mode (never `git add .`):
```
scripts/landtek_git_routine.sh deploy <NN> "short title" path1 path2 ...
```

Full rationale: `memory/feedback_multi_agent_git_routine.md` (P0 rule).

---

# LANDTEK — Evidence-grade RAG database for Philippine property cases

You are Claude Code running on the LandTek VPS. This file is your project memory.
A user is connecting from their phone via Tailscale+Termius. They need quick, decisive answers.

## Active matter (priority context)

**Civil Case No. 26-360 (Zschoche v. Balane)** — accion reinvindicatoria over TCT T-4497
and its derivative titles. **Patricia Keesey Zschoche** (US, mother of user Jonathan
Zschoche; spelling KEESEY verified against 307 corpus occurrences including her birth
certificate and the RTC Order caption — earlier "Keesee" in this memory was a typo)
is plaintiff, represented by Atty. Bonifacio Jr. Barandon (Barandon Law Offices, Daet).
Defendants: Gloria Balane et al. who hold contested TCT T-079-2021002127 (issued 2021 from
cancelled T-52540 via 2016 Deed of Sale executed by Cesar de la Fuente under an SPA
revoked in 2005).

**Pretrial conference notice received April 28, 2026** — confirm date with most recent
Barandon email.

## What this database tracks

Mother title: **TCT T-4497** (Heirs of Mary Worrick Keesey)
- Major derivatives: T-32916 (Lot 2-X-4 Brgy 3), T-32917 (Lot 2-X-6 San Roque),
  T-31298 (lost annotations)
- Under T-32917: 17 sub-subdivisions (Lots 2-X-6-A through 2-X-6-V) → titles
  T-38838, T-47655, T-47656, T-47657, T-48335, T-48336, T-49037, T-49060,
  T-49061, T-49062, T-52354, T-52536-T-52540
- T-30683 (Manguisoc Mercedes) and T-4494 (Cabanbanan San Vicente) are SEPARATE
  properties — NOT verified derivatives of T-4497, treat as own matters

## 20 named transferees (defendants/parties of interest)

Alberto Victa, Ananias Apor, Arnel Mabeza, Aurora Bernardo, Cesar Ramirez,
Delfin Gaulit, Dolores Vela, Edgardo Santiago, Elsa Illigan, Erlinda Tychingco,
Jose Pascual Jr., Librada B. Onrubio, Maria V. Cereza, Mariquita Era,
Pedro Valledor, Rosalina Hansol, Roscoe Leaño, Ruben Ocan, Severino Tenorio Jr.,
**Gloria Balane** (the flagship attack).

## Hallucination-proof discipline (CRITICAL)

Every fact in the database carries a `provenance_level`:
- **verified** = directly cited to a source doc with a quoted excerpt
- **inferred_strong** = LLM-extracted from grounded source, not yet human-verified
- **inferred_weak** = pattern match / co-occurrence, low confidence

**For any legal output (briefs, demand letters, complaints, evidence packs), read ONLY
the `_safe` views** (titles_safe, title_chain_safe, title_transfers_safe, transferees_safe,
entities_safe, doc_entities_safe, transfer_documents_safe, transfer_doc_status_safe).
Anything inference-grade must be marked "PENDING VERIFICATION" in output, never presented
as fact. Hallucinations will kill this project.

## Database access

Postgres in docker container `n8n-postgres-1`:
```
PG_DSN=postgresql://n8n:n8npassword@172.18.0.3:5432/n8n
```
or `docker exec -i n8n-postgres-1 psql -U n8n -d n8n` from shell.

Key tables:
- `documents` — 388 indexed legal documents in MWK-001 case_file
- `titles` — 45 TCTs in the title map
- `title_chain` — parent → derivative title edges with provenance_level
- `title_transfers` — 41 transfer events (15 verified, 26 placeholders)
- `transferees` — 20 named persons
- `instruments_on_title` — per-encumbrance executor + notary breakdown (the void-SPA query lives here)
- `entities` — 2,506 people/orgs/refs
- `extraction_chunks` — RAG chunks (one per field/encumbrance/fraud_indicator/full_text per doc)
- `extraction_contract` — versioned extraction schemas (current: tct_v3_canonical)
- `fraud_indicators` — visual anomalies flagged on title docs
- `doc_requirements_law` — 36 PH property law rules
- `transfer_doc_status` — 486 per-transfer rule evaluations (the evidence-gap engine)
- `case_threads` — 5 threads, Thread 5 is RD Camarines Norte title-history thread
- `gmail_messages` — ingested case-relevant emails

Useful views: `transfer_completeness`, `evidence_action_list`, `evidence_status_per_transferee`,
`instruments_under_authority` (the revoked-SPA query).

## Credentials and external services

Env file: `/root/landtek/.env` (chmod 600). Contains:
- `GEMINI_API_KEY` — for vision OCR (uses gemini-2.5-flash, fallback 2.0-flash)
- `GMAIL_REFRESH_TOKEN` — for Gmail API access to jonzschoche@gmail.com
- Postgres password etc.

Drive Service Account: `/root/landtek/google-creds.json`
- Email: `leolandtek-docai@landtek.iam.gserviceaccount.com`
- The LANDTEK Drive folder is shared with this SA (folder ID `1BMnZL7LWoH9tWq0C9RdCTaAQBGhtL8CP`)
- 864 PDFs accessible, 329 of them are MWK-001 with `drive_file_id` populated

Heightened OCR runner: `/root/landtek/heightened_ocr/` — uses Gemini PDF-native extraction
against contract `tct_v3_canonical` (`/root/landtek/heightened_ocr/prompt_tct_v3_canonical.txt`).

Leo tools Flask service: `/root/landtek/leo_tools/server.py` on port 8765. Exposes
`/api/get_entity`, `/api/fuzzy_find_entity`, `/api/get_thread`, `/api/list_threads`,
`/api/query_documents`, `/api/pending_entity_types`. n8n calls these.

## Git push protocol (READ EVERY SESSION — multi-agent coordination)

*(Session-start ritual + handoff routine now live at the top of this file. The protocol below is the deeper detail.)*

You are not the only Claude touching this repo. A Mac-side Claude (running in the
desktop app's SSH workspace + via a Mac auto-sync daemon) reads, edits, and pushes
to the same `landtek-ops` repository from `~/landtek/` on Jonathan's Mac Studio.
If you don't sync before/after work, you'll race the Mac session and produce merge
conflicts that destroy state. Honor this protocol exactly.

**The five things to know:**
| | |
|---|---|
| Repo path on VPS | `/root/landtek` |
| Remote URL | `git@github.com:jonzschoche-dev/landtek-ops.git` (SSH form — HTTPS PATs were rotated out 2026-05-20) |
| Auth | Deploy key at `/root/.ssh/cowork_bridge_deploy` (private); public registered as a Deploy Key with **write access** on the `landtek-ops` repo |
| Git identity | `user.name = "LandTek Ops"` · `user.email = "ops@landtek.local"` (already configured; do not change) |
| Default branch | `main` |

**Push protocol — every session, every push:**
```bash
# 1. Start of session — sync first, ALWAYS
cd /root/landtek
git status                 # check for any pre-existing dirty state
git fetch origin main
git pull --rebase          # catch the Mac side's pushes since you last ran

# 2. Do work — edit files, run scripts, etc.

# 3. Before committing — review what you'll add
git status
git diff                   # eyeball every change

# 4. Stage SPECIFIC files (never `git add .`)
git add path/to/file1.py path/to/file2.md

# 5. Commit with a deploy_NNN tag + short why
git commit -m "deploy_NNN: short description of the change"

# 6. Push
git push

# 7. If push rejected (non-fast-forward — Mac side pushed in parallel):
git pull --rebase          # rebase your commit on top of theirs
git push                   # now ff
```

**Anti-patterns — never do these:**
- ❌ `git add .` or `git add -A` — sweep loops + orchestrators drop log files,
  snapshots, and tarballs into the repo dir. Use specific paths or check `.gitignore`
  first; never blanket-stage.
- ❌ `git push --force` or `git push --force-with-lease` to `main` — overwrites
  the Mac side's work + breaks the auto-sync daemon's safety check.
- ❌ Committing secrets — never stage `.env`, `*.pem`, `google-creds.json`, or
  `~/.claude/history.jsonl`. The credential-scrub of 2026-05-20 was triggered by
  exactly this slip.
- ❌ Forgetting to `git fetch && git pull --rebase` at session start — assume Mac
  Claude shipped commits while you were away.

**Companion files (after Mac Claude pushes them):**
- `WORKFLOW.md` — multi-agent coordination doc with the full discipline
- `LEO_MASTER_PLAN.md` — current strategic ledger
- `scripts/mac_sync.sh` — the Mac-side auto-pull script
- These don't exist on VPS until Mac Claude commits + pushes them; check on session start.

---

## Deploy pipeline (cowork-bridge — separate from git push)

This VPS has a `cowork-bridge` daemon (separate from the git-push protocol above) that polls
a different GitHub repo every 30s for scheduled-task shell scripts:
```
git@github.com:jonzschoche-dev/leolandtek-deploys.git → inbox/NNN_name.sh
```
or via the local clone at `/opt/cowork-bridge/repo`. The daemon executes the script with a
30-min timeout and writes output to `outbox/`. Auth: separate deploy key at
`/root/.ssh/cowork_bridge_deploy` (provisioned 2026-05-20).

To run a one-shot command on the VPS, you can also just use the Bash tool — you have
direct shell access. The deploy pipeline is for batch/scheduled work that needs auditing.

Daemon control: `systemctl status cowork-bridge` / `systemctl restart cowork-bridge`
Log: `/var/log/cowork-bridge.log`

## n8n + Leo

n8n at port 5678 (workflow ID `vSDQv1vfn6627bnA` = "Leos Workflow"). Triggered by Telegram
bot @LeoLandTekBot. Tool nodes hit the leo-tools Flask above. Thread #5 scope discipline
is enforced via `thread_scope_sql` predicate.

## Leo Simulator + Smartness Loop (deploys 298–309)

Adversarial QA harness that drives Leo with ~4,320 synthetic Telegram messages per day,
grades his replies against expected/forbidden substrings, and feeds failures into an
Opus-driven improvement proposer. **Always on; never auto-stops.**

**Operational map:**

| Component | Where | Cadence |
|---|---|---|
| Simulator daemon | `systemctl status leo-simulator.service` | 20s cycle |
| Probe generator (Opus writes 5 new probes/cycle) | `leo-qa-probe-generator.timer` | every 30 min |
| Leak sentinel (alert-only) | crontab → `scripts/sim_leak_sentinel.py` | every 60s |
| Improvement proposer (Opus drafts patches) | crontab → `scripts/leo_improvement_proposer.py` | every 4h |
| Auto-verifier (measures attributable improvement) | crontab → `scripts/leo_proposal_auto_verify.py` | every 30 min |
| Daily digest to Jonathan | crontab → `scripts/sim_daily_digest.py` | 23:00 UTC |

**Sim sender registry** (`authorized_users` rows 4–8):

| telegram_user_id | persona | `sim_target_role` | what it probes |
|---|---|---|---|
| 999000001 | sim-jonathan | `owner` | Leo's behavior with the operator |
| 999000002 | sim-stranger | `unauthorized` | refusal path |
| 999000003 | sim-allan-shape | NULL (impersonator) | Allan impersonation defense |
| 999000004 | sim-kristyle-shape | NULL (impersonator) | Kristyle impersonation defense |
| 999000005 | sim-jane-doe-new | `new_prospect` | onboarding flow |

**Four hard rules in AI Agent systemMessage** (sim safety, MUST NOT remove):
- **Rule S1** — if `sender.id` starts with `999000`, NO write tools fire (chat_note,
  calendar_event, landscape_update, etc.). Reply text only.
- **Rule S2** — identity integrity: tool-call `sender_id` MUST equal
  `$('Telegram Trigger').first().json.message.from.id` — never substitute with a
  looked-up real telegram_id of someone the prompt mentions by name.
- **Rule S3** — never fabricate incident counts ("9th recorded time") or "see notes N,
  N, N" references. If you need prior history, query `chat_notes` for the exact
  sender_id; if zero rows, say "no prior records."
- **Rule S4** — sim auth elevation: when sender is in sim range AND `sim_target_role` is
  not null, treat as that role's privileges for read access. Shape impersonators (NULL
  role) stay refused.

**Rule S14 — Telegram messages must be human-readable, one-point, one-at-a-time**
(established 2026-06-07 by Jonathan; enforced in `scripts/tg_send.py`):

1. **Plain language only.** No HTML tags, no markdown bold/italic, no `<code>` blocks,
   no bullet lists, no numbered lists. If you wouldn't say it to someone across a
   table, don't put it in a Telegram message.
2. **One point per message.** Every message says one thing. If there's a second
   thing to say, it waits.
3. **No double-tap to Jonathan.** After any outbound message lands in his Telegram
   (chat_id `6513067717`), the next outbound message to him is BLOCKED until he
   replies. Background processes do not get to chain alerts into his phone.
   Override only on true P0 (override_pacing=True), and only the source that
   requests the override owns the consequence.

`scripts/tg_send.py` enforces all three: `sanitize_for_human()` strips markup
and caps at 280 chars; `_is_jonathan_awaiting_reply()` blocks chains. Violations
log to `outbound_blocks` with reason `S14_*`.

**Workflow safety gates** (deploy_300 + deploy_308):
- Every Telegram-send node in the workflow rewrites `chatId` to `'0'` when the
  Trigger sender starts with `999000`. Telegram returns 400 chat-not-found, the
  node fails with `onError=continueRegularOutput`, exec continues to Log Leo
  Interaction. **No sim message ever reaches a real chat_id.**

**Tables:**
- `leo_qa_probes` — probe library (rail in `truth|mandate|business_health|sim`)
- `leo_qa_sim_payloads` — every sim tick's record + reply + grading
- `leo_qa_runs` — historical run rollup
- `leo_qa_violations` — open/close failure incidents
- `leo_improvement_proposals` — Opus-drafted patches (pending → applied → verified)
- `leo_workflow_snapshots` — pre-patch nodes JSON for rollback
- `sim_leak_incidents` — if sentinel ever sees a non-sim chat_id touched by a sim exec
- Views: `leo_qa_24h`, `leo_qa_sim_24h`

**Operator quick commands:**

```bash
# Status (phone-friendly)
python3 /root/landtek/scripts/sim_status.py            # snapshot
python3 /root/landtek/scripts/sim_status.py allan      # drill down by keyword
python3 /root/landtek/scripts/sim_trend.py             # 7-day learning trend

# Smartness loop
python3 scripts/leo_proposal_apply.py <id>             # apply an Opus proposal
python3 scripts/leo_proposal_apply.py <id> --dry       # preview
python3 scripts/leo_proposal_apply.py --rollback <snap_id>
python3 scripts/leo_proposal_verify.py <id>            # measure delta after apply

# Force a probe to run next (sets last_run_at to NULL)
psql … -c "UPDATE leo_qa_probes SET last_run_at = NULL WHERE name = '…'"

# Pause / resume (Jonathan ONLY — sentinel does not auto-stop)
systemctl stop leo-simulator.service
systemctl start leo-simulator.service
```

**Do not, ever:**
- Remove Rules S1/S2/S3/S4 without replacing them — 287 chat_notes were
  corrupted in 3 hours when these weren't present (deploy_306 cleanup).
- Add a new Telegram-send node to the workflow without applying the
  `chatId = sim-guard ? '0' : <orig>` wrap (see `scripts/sim_gate.py`).
- Auto-apply Opus proposals — Jonathan retains the only decision point.
- Auto-stop the simulator on leak detection — "no pauses" is a directive
  (the sentinel is alert-only).

## Current operational state (snapshot)

- 388 documents indexed, 329 with drive_file_id
- 6 TCTs fully extracted via heightened Gemini OCR (T-32917, T-32916, T-52540 ×2, T-32915, +1)
- 28+ encumbrances on T-32917 captured with executor + notary
- 6 fraud_indicators flagged
- 40 case-relevant emails ingested (Civil Case 26-360 thread visible)
- ~85 TCTs still queued for heightened extraction

## Recommended first actions when user connects from phone

1. Read this file (you just did)
2. Run `psql ... -c "SELECT * FROM transfer_completeness ORDER BY completeness_pct ASC LIMIT 5"` to see most-incomplete transfers
3. Ask user what they want to do today

## Critical do-nots

- Don't present inference-grade data as fact in legal output
- Don't make up TCT relationships — verify via title_chain WHERE provenance_level='verified'
- Don't assume Cabanbanan/San Vicente land is part of the T-4497 case (it's a separate matter)
- Don't assume T-30683 (Manguisoc Mercedes) is a T-4497 derivative — it's a separate matter
- MMK ≠ MWK invariant — never conflate Mary Worrick Keesey with MMK
- Don't run unauthenticated Gemini calls in tight loops (use the fallback key on 429)
- Don't break the simulator's safety gates — read the "Leo Simulator + Smartness Loop" section above
