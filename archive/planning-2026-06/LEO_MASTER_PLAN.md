# LEO — Master Plan & Deployment Roadmap

> The single source of truth for where Leo is going, how we get there, and how we
> deploy without breaking what works.
>
> Authored: 2026-05-20
> Owner: Jonathan Zschoche
> Operating discipline: see `WORKFLOW.md` (multi-agent collaboration)
> Existing 90-day phasing: `memory/project_90day_roadmap.md` (this doc carries it forward)
>
> **This is a living document. Update it when reality changes. Both VPS Claude and
> Cowork have edit rights, via the git discipline in WORKFLOW.md.**

---

## 1. Vision

> **Leo is the most forward-thinking, truth-seeking, dependable property-management
> AI in the world.** It never misses a deadline, never invents a fact, and constantly
> finds ways to push every client's agenda — and Landtek's firm agenda — forward
> without being asked.

Five layers, each independently elite:

1. **Per-matter elite** — instant case theory, evidence gap detection, deadline
   radar, document drafting, opposing-counsel response prediction, settlement
   modeling.
2. **Per-portfolio elite** — every title valued, risk-rated, opportunity-tagged;
   auto-surfaces "buy this depressed parcel," "sell that one," "this title is
   shaky, fix it before it bites."
3. **Per-firm elite** — financial planning, capacity, intake automation, revenue
   forecasting, investor-grade reporting — Landtek as a fundable business.
4. **Per-channel elite** — WhatsApp + web + email + voice + Telegram + custom
   client portal — one brain, every surface.
5. **Per-jurisdiction elite** — fluent in PH property law today, designed so a new
   jurisdiction is an extension, not a rewrite.

---

## 2. Non-negotiable principles

These are immutable. Innovation must respect them or it doesn't ship.

| # | Principle | Source rule file |
|---|---|---|
| 1 | **No hallucination in any output.** Every claim cites a source doc + provenance + validity verdict. | `feedback_output_no_hallucination_discipline.md` |
| 2 | **Never miss a deadline.** Multi-step escalation ladder + audit trail. Missed = P0 incident. | `feedback_leo_mission_agency.md` |
| 3 | **Never break client comms.** Outbound goes through `comms.comms_send()` chokepoint. "We die when this breaks." | `feedback_client_comms_hardcoded.md`, `project_comms_chokepoint_architecture.md` |
| 4 | **Never present inference as fact.** `provenance_level` is sacred. Legal output reads `_safe` views only. | `CLAUDE.md` (hallucination-proof discipline) |
| 5 | **Information is gold.** No uploads lost. Deletions require explicit approval + audit trail. | `feedback_information_is_gold.md` |
| 6 | **Self-research before asking.** Search the corpus, propose an answer, escalate only when truly unknown. | `feedback_leo_must_self_research.md` |
| 7 | **Innovate in the clone, deploy when ready.** Edits flow through git. No more "hand-edit on the VPS." | `WORKFLOW.md` |
| 8 | **Hard stops on cost.** Daily Gemini spend > $10 = halt. | `DIRECTIVE.md` |

---

## 3. Current state (2026-05-20 snapshot)

What's working:

- 388 documents indexed in MWK-001 case_file
- 45 TCTs in the title map
- 41 transfer events (15 verified, 26 placeholder)
- 2,506 entities
- 354/682 chunks verified (≈52%)
- Comms chokepoint architecture deployed 2026-05-19
- n8n + Leo + tg-dispatcher consolidated post-blackout
- Cowork-bridge daemon repaired today
- Mediation pack drafted for Civil Case 26-360 (2026-05-17)

What's clumsy / at risk:

- ⚠ `pending.txt` heartbeat stopped 2026-05-17 09:36 UTC — sweep may have stalled
- ⚠ Memory tree (50+ feedback files) accreted, not consolidated
- ⚠ Single-cockpit dependency on Jonathan in Termius
- ⚠ No client-facing layer (Telegram only)
- ⚠ Financial layer flagged P0 but not yet visibly built
- ⚠ Multi-channel still aspirational
- ⚠ Desktop app SSH bridge crashes (sidestepped via Cowork direct)
- ⚠ Manual per-matter setup — no intake wizard

---

## 4. The forcing function — Civil Case 26-360

Real-world deadlines drive the schedule. Leo's roadmap must serve them.

| Event | Date | Days out | What Leo must deliver |
|---|---|---|---|
| **Mediation** | 2026-06-02 | 13 | Polished verified-only mediation pack docx; closed primary-instrument gaps where possible; updated settlement range with FMV refinement |
| Pre-Trial Order issuance | ~June 2026 | unknown | Auto-detect when filed; trigger Intake#3/#4 follow-up; reset case stage |
| Trial date | TBD | TBD | Set in Pre-Trial Order; populate full deadline ladder |

Anything Leo ships in the next 30 days must either:
(a) directly support the 6-2 mediation, or
(b) be a low-risk parallel improvement (like the WORKFLOW.md, a refactor, a memory consolidation).

---

## 5. The deployment roadmap

### Phase 0 — Safety substrate (next 7 days, by 2026-05-27)

**Goal:** make innovation cheap to reverse. Build the floor that prevents another May 17.

| # | Deploy | Description | Risk | Estimated effort |
|---|---|---|---|---|
| 0.1 | Auto-rollback sentinel | Detect comms silence / sweep stall → revert last deploy automatically (not just alert) | Low (read+revert) | 2 days |
| 0.2 | Critical-path test suite | 30-second smoke test: comms send, sweep one cycle, audit gate on a known-good doc | Low (read-only tests) | 1 day |
| 0.3 | Staging branch protocol | `staging` git branch + per-deploy snapshot; promote to main only after passing tests | Low (process change) | 0.5 day |
| 0.4 | Heartbeat dashboard | Single page summarizing every sentinel + service + last-success time | Low (read-only) | 1.5 days |
| 0.5 | Restart wedged sweep | One-shot fix: diagnose why pending.txt heartbeat stopped May 17; restart loop | Low (already known how) | 0.5 day |

After Phase 0: every subsequent phase deploys behind these guardrails.

### Phase 1 — Flawless Data Integrity (by 2026-05-30) — carries forward from project_90day_roadmap

**Goal:** the base layer of facts must be indisputable.

| # | Deploy | Description |
|---|---|---|
| 1.1 | Calibrate Truth-Negotiator | Tune challenger so it refutes ≤1 of 5 verified back-tests (currently 4 of 5) |
| 1.2 | Clear ingestion backlog | 341 of 937 Drive files unsynced + 19 image-PDFs awaiting Gemini Vision fallback → 100% readable |
| 1.3 | Party Classifier refinement | Haiku pass on 202 "ambiguous" classifications to lock down plaintiff/respondent posture |
| 1.4 | Memory tree consolidation | Merge duplicates, resolve contradictions, version the rule files (50+ → ~25 canonical) |
| 1.5 | Heightened OCR queue closure | 28 TCTs in queue as of last log → drain to 0 |

### Phase 2 — Relational & Financial Deepening (by 2026-06-30)

**Goal:** link isolated facts into a multidimensional graph. Build the financial layer.
Mediation (6-2) lands inside this phase — mediation prep is the practical test of Phase 1's integrity.

| # | Deploy | Description |
|---|---|---|
| 2.1 | Financial ledger | `extract_bills_from_emails.py` + `accounts/transactions/monthly_overhead` schema; convert estimated overhead → audited data; track Leo's own infrastructure costs |
| 2.2 | Investor-grade reports | P&L, runway, ROI per matter, valuation memos per property — the deck that attracts capital |
| 2.3 | TCT-ARP spine | Only 5 confirmed links today; Haiku batch on Mercedes Statements + lot-code inference to map every tax dec to its physical title |
| 2.4 | Granular RPT extraction | Re-extract Mercedes Statements: year-by-year RPT grid per ARP (currently totals only) |
| 2.5 | Mediation pack v2 (polished docx) | Verified-only data, gap-closures from Phase 1.5, settlement range refined with FMV |
| 2.6 | Per-transferee recovery posture | All 20 named transferees → individual case strategies (extension of mediation theory to the other 19) |

### Phase 3 — Autonomous Agency & Predictive Analytics (by 2026-08-14)

**Goal:** Leo tells Jonathan what to do before he asks.

| # | Deploy | Description |
|---|---|---|
| 3.1 | Low-Hanging-Fruit Engine | Feed pristine TCT-ARP financial data into Asset Valuation; auto-flag intrinsic > 1.4 × market + low mitigation cost. The competitive moat. |
| 3.2 | Goal Accelerator daily proposals | 1-3 actions per case + 1-2 firm-level actions, delivered Telegram with one-tap accept/decline |
| 3.3 | Procedural deadline prediction | 18 PH civil-procedure stages → Leo predicts deadlines, doesn't just log them |
| 3.4 | Hyper-vigilance meta-agent (full) | Second AI node audits Leo every hour; back-tests truth_negotiator; auto-remediates gaps before Jonathan flags them |

### Phase 4 — Channel expansion + product surface (by 2026-09-30)

**Goal:** Leo's brain reaches every client surface; firm becomes licensable.

| # | Deploy | Description |
|---|---|---|
| 4.1 | WhatsApp Business adapter | 95% of PH clients use WhatsApp; Meta Business Verification + WABA provider (360dialog or Twilio) |
| 4.2 | Web chat widget | Embed on landtek.com / client portal; first-contact + lead capture |
| 4.3 | Email reply bot | Leo replies to client emails directly via existing Gmail integration |
| 4.4 | Public REST API (v1) | `/api/v1/leo/chat`, `/api/v1/leo/verify`, `/api/v1/leo/extract` — the licensable product surface |
| 4.5 | Client portal | Per-client dashboard showing all matters, titles, deadlines, valuations, proposed actions; clients self-serve |

### Phase 5 — Best-in-class (beyond 90 days)

| # | Vision-level deploys |
|---|---|
| 5.1 | iOS/Android branded app |
| 5.2 | Voice channel (Twilio Voice + STT/TTS) — clients can call Leo |
| 5.3 | Second jurisdiction onboarding (proof Leo is jurisdiction-extensible) |
| 5.4 | Licensable platform offered to other PH property firms |
| 5.5 | Investor round on the back of Phase 2.2 financials + Phase 3.1 LHF engine track record |

---

## 6. Parallel tracks (always running)

These don't have phases — they're continuous improvement.

| Track | Cadence | Owned by |
|---|---|---|
| **Memory consolidation** | Weekly review of new rule files; merge duplicates, retire stale | VPS Claude (during quiet hours) |
| **Hallucination log review** | Daily check of `hallucination_log`; remind Leo what NOT to do | meta-agent |
| **Cost monitoring** | Hourly token-health-sentinel + daily Gemini-spend audit | already running |
| **Backup integrity** | Nightly backup + weekly off-site verification | landtek-backup.timer + manual quarterly restore test |
| **Discipline drift detection** | Hourly meta-agent audit of Leo's outputs against canonical principles | already running, needs Phase 3.4 to upgrade |

---

## 7. Deployment cadence & gates

Every deploy passes through these checkpoints. See `WORKFLOW.md` for the full rules.

1. **Authored in `~/landtek` (Mac clone) by Cowork** — never on the VPS directly.
2. **Diff reviewed by Jonathan in chat.**
3. **Critical-path tests run** (Phase 0.2 once it exists).
4. **Snapshot saved** for any Leo n8n workflow / schema change.
5. **Commit to `staging` branch first** (Phase 0.3 once it exists). Merge to `main` when green.
6. **Push to `landtek-ops`.**
7. **If activation needed:** deploy script to `leolandtek-deploys/inbox/`. Cowork-bridge daemon executes.
8. **Watch heartbeat** for at least one full sentinel cycle (30 min) to verify no regression.

**If anything in section 5's "non-negotiable principles" breaks during step 8 → automatic revert.**

---

## 8. Metrics — how we know we're winning

| Metric | Phase | Target |
|---|---|---|
| Verified chunks / total chunks | 1 | ≥ 90% (today: 52%) |
| Documents fully extracted via heightened OCR | 1 | All 89 in queue (today: ~partial) |
| Truth-negotiator back-test pass rate | 1.1 | ≥ 4 of 5 (today: 1 of 5) |
| Memory rule files (canonical) | 1.4 | ≤ 25 (today: 50+) |
| Per-transferee recovery posture documented | 2.6 | 20 of 20 (today: 0) |
| Mediation pack v2 polished docx | 2.5 | shipped by 5-30 |
| Financial ledger live | 2.1 | shipped by 6-30 |
| Goal accelerator daily proposals delivered to Telegram | 3.2 | ≥ 3 per active case per day |
| Channels active | 4.1-4.4 | WhatsApp + web + email + REST API by 9-30 |
| Missed deadlines | always | **zero** |
| Comms blackouts > 1 hour | always | **zero** (last: 2026-05-17, must never repeat) |
| Hallucinations in client-facing output | always | **zero** |

---

## 9. Known risks & how we mitigate

| Risk | Mitigation |
|---|---|
| Another comms blackout | Phase 0.1 auto-rollback sentinel; comms chokepoint already deployed |
| Sweep stall unnoticed (May 17 onward) | Phase 0.4 heartbeat dashboard; alerts on > 1 hr heartbeat gap |
| Memory drift / contradictions | Phase 1.4 consolidation; weekly review track |
| Gemini cost spike | Hard $10/day cap, key cool-down logic, fallback model paths |
| Mediation date moves | Polled from Gmail/Barandon correspondence; Leo flags any date-shift signal |
| Pre-trial order delay | Intake#3/#4 already open; periodic chase emails proposed by goal_accelerator |
| Single-person dependency (Jonathan) | Phase 0.4 dashboard + Phase 4.5 client portal reduce single-cockpit load |
| Repo authentication failures (like today's clone) | Document SSH key setup in WORKFLOW.md; deploy keys for VPS-side pushes |

---

## 10. How this plan evolves

- Reviewed **weekly** during Phase 0 and Phase 1.
- Reviewed **biweekly** during Phases 2-3.
- Reviewed **monthly** in Phase 4+.
- Any new project_*.md or feedback_*.md in `memory/` that creates a new direction
  must be reconciled here — either by updating a phase or by adding a parallel track.
- When a phase target date slips, document the slip + cause + new date below.

### Slip log

| Date | Phase | Original | Revised | Cause |
|---|---|---|---|---|
| _none yet_ | | | | |

---

_Related: `WORKFLOW.md` (how we deploy), `CLAUDE.md` (project context), `DIRECTIVE.md` (legacy 48-hour playbook), `memory/MEMORY.md` (rule index)._
