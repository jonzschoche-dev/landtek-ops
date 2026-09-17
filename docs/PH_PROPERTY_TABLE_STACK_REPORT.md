# Philippine Property Table Stack — Architecture Report & Accomplishment Plan

**Date:** 2026-07-16  
**Status:** Working architecture (live on VPS) + honest gaps + next objectives  
**Authority boundary:** `MASTER_PLAN.md` remains wartime north star. This report is the **technical spine** for continuous table population so answers never re-scramble the corpus at prompt time.  
**Audience:** Operator (Jonathan) + peer review (Claude / desk review).

---

## 1. Executive summary

LandTek is no longer “search the PDF when someone asks.” The intended product is a **layered precomputation stack** for Philippine property matters:

> Documents are broken into **typed tables continuously**. Inquiry reads **cards and fields**, not raw PDFs. Provenance is gated. Unclear data is flagged, never invented.

**Live reality (2026-07-16 census):**

| Layer | Table / signal | Count | Health |
|---|---|---:|---|
| Corpus | `documents` | 2,048 | Strong |
| Readable text | `extracted_text ≥ 80` | ~1,960 | Strong |
| Per-doc typed fields | `document_fields` | 14,610 | Strong (idempotent bulk) |
| Title mentions | `document_titles` | 2,174 | Strong |
| Parties | `matter_parties` | 4,507 | Strong |
| Matter truth stream | `matter_facts` | ~41,600 | Strong volume; **~13% verified** |
| Typed fact atoms | `fact_fields` | ~22k–41k* | Working; re-runs can rebalance |
| Matter cards | `matter_brief` | 36 | Usable; some need_review |
| Title cards | `title_brief` | 446 | **93.5% usable**; 29 unclear |
| Law library | `legal_chunks` | 6,688 (98 sources) | Growing; still thin on OP doctrine |
| Title registry | `titles` | 88 | Core set; briefs outnumber registry |
| Agent registry | `agent_mandates` | 6 active | Light but real |
| Overall awareness | `knowledge_coverage` | **74.7%** | Gaps: verified facts, valuations |

\* `fact_fields` count moves when extractors re-decompose; treat as operational range, not a single forever number.

**What we will accomplish (north of this report):** turn that 75% awareness into an **inquiry-ready Philippine property OS** — titles, parties, dockets, MRO/OP refs, tax decs, CTNs, surveys, filings, law, and role-aware answers — where every substantive claim is table-backed and provenance-safe.

---

## 2. Design principles (non-negotiable)

| # | Principle | Why |
|---|---|---|
| P1 | **Wire to existing** | One Postgres SoR (`n8n` DB). No dual-stack, no second brain. |
| P2 | **Tables before chat** | Chat is a consumer. Population runs on timers without prompts. |
| P3 | **Provenance gate** | `verified` / `operator` / `inferred_*` — never invent verified. |
| P4 | **Verbatim span rule** | Every typed field carries a `source_span` from the document. |
| P5 | **Unclear ≠ invent** | Flag for human queue; 90% intake target on *what exists*. |
| P6 | **Agent = mandate + owned tables** | Each agent owns a slice; no thrashing the same SoR. |
| P7 | **$0 bulk path** | Regex/deterministic populate first; LLM only residual/comprehend. |
| P8 | **A5 isolation** | Client/matter scope; no cross-client bleed. |

---

## 3. Architecture — layered precomputation

```
                    ┌─────────────────────────────────────────┐
                    │  CHANNELS (Messenger / Telegram / email) │
                    │  → channel_messages bus → leo_instant    │
                    │  → inquiry_stack / corpus_answer         │
                    └───────────────────┬─────────────────────┘
                                        │ READS (never re-OCR for every ask)
          ┌─────────────────────────────┼─────────────────────────────┐
          ▼                             ▼                             ▼
   matter_brief                  title_brief                    fact_fields
   (per matter card)             (per title card)               (typed atoms)
          ▲                             ▲                             ▲
          │ materialize                 │ materialize                 │ extract
          └───────────────┬─────────────┴──────────────┬──────────────┘
                          │                            │
                    matter_facts  ◄── verify_worker ────┤
                    (SoR stream)     harvest / doc_pop  │
                          ▲                            │
                          │                            │
              document_fields  document_titles  matter_parties
                          ▲
                          │ populate_tables_from_docs  (+ harvest_facts)
                          │
                    documents.extracted_text
                          ▲
                 OCR / Drive / email / scan intake
```

### 3.1 Layer map (what each layer is for)

| Layer | Tables | Job | Owner agent |
|---|---|---|---|
| L0 Corpus | `documents` | Bytes + extracted text | ingest / OCR / Drive |
| L1 Doc atoms | `document_fields`, `document_titles` | Typed numbers & title mentions **per doc** | **doc_populate** |
| L2 Parties | `matter_parties` | Labeled roles from text | **doc_populate** (+ harvest) |
| L3 Fact stream | `matter_facts` | Matter-scoped statements + provenance | **doc_populate**, **harvest**, **verify_worker** |
| L4 Typed facts | `fact_fields` | Delicate kinds: TCT, OCT, e-title, CTN, tax_dec, docket, MRO, date, amount, survey… | **fact_field_extractor** |
| L5 Cards | `matter_brief`, `title_brief` | Short-by-construction digests for UI + inquiry | **matter_brief_materializer**, **title_brief_materializer** |
| L6 Law | `legal_chunks` | Doctrine / statute / OP-relevant law | jurisprudence steward (separate) |
| L7 Inquiry | `inquiry_runs`, `inquiry_scrutiny`, `inquiry_answer_atoms`, `agent_work_queue` | Scrutinize stack → answer → writeback → trigger | **inquiry_stack** |
| L8 Role / human | `channel_users`, human_pass threshold, operator TG | Who may see what; when to escalate | onboarding + human_pass |

### 3.2 Runtime (how it stays alive)

| Cadence | Unit | Pipeline |
|---|---|---|
| Hourly | `landtek-awareness.timer` | populate → harvest → extract_fact_fields → matter_brief → title_brief → intake_clarity → comprehend residual → awareness score |
| ~15 min | `landtek-verify-worker.timer` | Promote grounded claims toward **verified** |
| 5 min | `fact-extractor.timer` | Chat-note / residual fact encoding (legacy path; not the bulk spine) |
| Continuous | `landtek-leo-instant` | Chat bus → headless answer (Messenger solid; Telegram wiring half-cutover — separate workstream) |

Log: `/var/log/landtek_awareness.log`  
Populate log: `table_populate_log`

### 3.3 Philippine property ontology (what “correct tables” means)

The stack is optimized for **PH land/property practice**, not generic RAG:

| Domain concept | How it is stored | Example kinds |
|---|---|---|
| Torrens title | `titles` + `title_brief` + fields | `tct`, `oct`, `e_title` |
| Survey / technical | `fact_fields` / facts | `survey`, `area` |
| Tax declaration | fields + facts | `tax_dec` |
| CTN / DENR / LMS-style ids | fields (delicate decoder) | `ctn` |
| Court docket | fields + facts | `docket`, `forum` |
| OP / MRO living refs | fields + facts | `mro_ref` (e.g. `050526-MRO-234187`) |
| Parties | `matter_parties` | plaintiff / defendant / heir / AIF |
| Money | fields + facts | `amount`, `financial` |
| Law | `legal_chunks` | statute / doctrine chunks |
| Filings (gap) | not yet first-class table | vault locators + docs today |

**RAG is not the SoR.** Vector search (if any) finds documents; **truth lives in tables with provenance**.

---

## 4. Agents and ownership (no thrash)

Six active mandates (`agent_mandates`):

| Agent | Mandate (one line) | Owns |
|---|---|---|
| `doc_populate` | Every readable doc → typed rows | `document_fields`, `table_populate_log` (+ matter_facts/parties slice) |
| `fact_field_extractor` | Prose facts → typed atoms | `fact_fields` |
| `verify_worker` | Upgrade grounded claims to verified | `matter_facts` (verified), `proposed_facts` |
| `matter_brief_materializer` | One digested row per matter | `matter_brief` |
| `title_brief_materializer` | One card per title for property UI | `title_brief` |
| `inquiry_stack` | Scrutinize → answer → writeback → trigger | inquiry_* + `agent_work_queue` |

Spec already exists: `agent_specs/001_doc_populate.md`.  
**Next agents (planned, not yet first-class):** filing_table agent, legal_harvest (OP/Property Registration Decree depth), geometry/map agent, role/dossier agent.

---

## 5. Current accomplishment (honest)

### 5.1 What is already world-class *direction*

1. **Continuous bulk populate** without waiting for a human prompt.  
2. **Typed PH identifiers** with delicate decoders (TCT vs OCT vs e-title vs CTN vs MRO).  
3. **Provenance discipline** — inferred vs verified is real, not marketing.  
4. **Intake clarity meter** — 90% targets with unclear flags (title cards ~93.5% usable).  
5. **Card layer** — inquiry can read `matter_brief` / `title_brief` instead of re-scraping 2k docs.  
6. **Agent ownership** — mandates + owned tables reduce dual-write chaos.

### 5.2 Intake meter (last awareness pass)

| Metric | Result | Target |
|---|---|---|
| Linked+text docs → produced facts | **92.4%** | ≥90% |
| Facts typed (≥1 field) | ~88% | ≥90% |
| Title cards usable (clear+partial) | **93.5%** | ≥90% |
| Facts verified | **~13%** | climb steadily |
| Overall awareness | **74.7%** | 85% → 95% wartime |

### 5.3 What is *not* yet advanced enough

| Gap | Why it hurts PH property work |
|---|---|
| **Verification depth** | Strategy/testimony needs verified, not only inferred_strong |
| **Asset valuation** | Awareness shows ~8% assets with real valuation |
| **Title registry vs title_brief** | 446 cards vs 88 `titles` rows — card layer ahead of registry SoR |
| **Filings not first-class** | Vault + docs exist; no clean `filings` spine for court paper chronology |
| **OP / ARTA legal density** | MRO refs extracted; doctrine chunks still sparse for “OP ignores us” class questions |
| **fact_edges = 0** | No graph of fact↔fact / fact↔title relations yet |
| **Comms dual-path (Telegram)** | Table stack is solid; TG still half on side-path vs `channel_messages` bus |
| **Parties sometimes zero on a populate pass** | Log showed parties_written=0 on a later run — idempotency / wipe path needs discipline |

---

## 6. What we will accomplish (program of work)

### Phase A — **Solidify the table spine** (now → 1–2 weeks)

**Goal:** Every readable document reliably contributes; cards stay fresh; unclear queue is visible.

| # | Deliverable | Success metric |
|---|---|---|
| A1 | Keep hourly awareness green | `table_populate_log` + awareness_log every hour |
| A2 | Close docs-with-text missing `document_fields` | Residual unfacted docs → 0 or human-flagged |
| A3 | Stabilize party writes | `matter_parties` non-zero each full populate when labels exist |
| A4 | fact_fields ≥90% of facts typed | Intake meter green |
| A5 | Title unclear queue triage | 29 unclear → resolved or explicitly human-held |
| A6 | Matter briefs for all active matters | `need_review` shrinks; zero-verified flagged |

### Phase B — **Philippine property depth** (parallel)

**Goal:** Tables that a Camarines / Torrens practice actually needs day-to-day.

| # | Deliverable | Tables / artifacts |
|---|---|---|
| B1 | **Title SoR alignment** | `titles` registry ↔ `title_brief` ↔ `document_titles` consistent |
| B2 | **Filings first-class** | `filings` (or equivalent): type, date, forum, docket, matter, doc_id, vault locator |
| B3 | **OP / MRO pack** | `mro_ref` complete; legal_chunks for OP procedure + ARTA; matter_brief OP section |
| B4 | **Tax / CTN / survey pack** | Delicate kinds quality audit; no cross-kind collisions |
| B5 | **Party graph** | Roles + representation (AIF/SPA) linked to matters and titles |
| B6 | **Deadline surface** | Already partial; bind to matter_brief + calendar without duplicate SoR |

### Phase C — **Verification & human threshold** (quality)

**Goal:** Move from “we extracted it” to “we can stand on it.”

| # | Deliverable | Success metric |
|---|---|---|
| C1 | verify_worker continuous climb | verified share 13% → 25% → 40% on active matters first |
| C2 | Human-pass equation live | score ≥ threshold → operator TG; facts-only draft otherwise |
| C3 | proposed_facts adjudication | Operator can promote/reject without SQL |
| C4 | No keyword-router debt for strategy | inquiry_stack + tables, not brittle if/else answers |

### Phase D — **Inquiry as product** (stack access)

**Goal:** Any channel that lands on the bus gets the same table-backed brain.

| # | Deliverable | Success metric |
|---|---|---|
| D1 | Single chat bus | All channels → `channel_messages` → `leo_instant` |
| D2 | inquiry_stack default | Scrutinize briefs/fields/law before free prose |
| D3 | Role-first disclosure | Operator / filing_assistant / client see correct dose |
| D4 | Scenario packs | OP silence, title fetch, vault coordination — table-first |

### Phase E — **“Most advanced in the world” bar** (definition of done)

Not marketing. Concrete bar for **Philippine property matters**:

1. **Any TCT / OCT / e-title** in corpus has a title card with status, linked docs, open gaps.  
2. **Any active matter** has a matter brief with parties, dockets, key dates, verified vs inferred split.  
3. **Any docket or MRO ref** mentioned in filings is findable in ≤1 table lookup (not LLM guess).  
4. **Any substantive Leo answer** cites table rows + source doc spans.  
5. **Unclear ≤10%** of title/matter cards; rest either clear or explicitly human-queued.  
6. **Verified ≥40%** of facts on active wartime matters (not whole historical dump).  
7. **Law packs** for Property Registration Decree, land registration practice, OP/ARTA procedure loadable and cited.  
8. **Zero dual SoR** — one Postgres truth, channels are I/O only.

---

## 7. Data flow for one document (example)

```
PDF land on Drive/scan
  → documents row + OCR → extracted_text
  → populate_tables_from_docs
       → document_fields (TCT-32911, dates, amounts…)
       → document_titles
       → matter_facts (if matter-linked)
       → matter_parties (if role-labeled)
  → extract_fact_fields
       → fact_fields atoms
  → materialize_title_brief / matter_brief
  → verify_worker (when excerpt grounds)
  → inquiry_stack can answer "fetch me TCT 32911" from cards/fields
```

---

## 8. What we will *not* do (anti-goals)

- Second vector DB as truth store  
- Keyword routers that invent docket/MRO numbers  
- Promoting `inferred` to `verified` without excerpt  
- Dual Telegram brains that skip `channel_messages`  
- Populating tables only when someone chats  
- Premature multi-tenant SaaS while wartime case is live  

---

## 9. Peer review (Claude-style desk critique)

### 9.1 What is strong

- **Correct architecture for legal/property data:** precompute + provenance beats chat-time RAG scramble.  
- **Agent ownership model** is the right antidote to dual-write thrash.  
- **Intake clarity meter** forces honesty (unclear counts).  
- **PH-specific field kinds** (CTN, MRO, tax_dec, e_title) show domain fitness, not generic NLP.

### 9.2 Risks / failure modes

| Risk | Severity | Mitigation |
|---|---|---|
| Populate passes that zero parties or shrink fact_fields silently | High | Assert non-regression in `table_populate_log` + truth_tests |
| Awareness “100%” on some bars while verified is 13% | Med | Weight verified + valuation in operator dashboard |
| Title_brief 446 vs titles 88 | Med | Explicit reconcile job; cards must not invent registry |
| Telegram not on bus | High for ops UX | Bridge inbox → channel_messages (separate wiring fix) |
| Comprehend residual “no parse” | Low–Med | Don’t let LLM residual block deterministic path |
| Legal_chunks volume ≠ doctrine coverage | Med | Curate OP/PRD packs by matter need, not chunk count |

### 9.3 Recommended sequencing (reviewer)

1. **Freeze regressions** on populate (parties + fields counts).  
2. **Phase A** completeness (unfacted docs, type rate).  
3. **B1–B3** title/filing/OP depth (wartime value).  
4. **C1** verified climb on active matters only.  
5. **D1** channel bus unity (so table brain is always used).  
6. Defer HA/multi-tenant until wartime milestones clear.

### 9.4 Verdict

The project is **already past prototype**: continuous population and card layers are real.  
It is **not yet** “most advanced in the world” — that claim becomes true only when **verification, filings spine, title SoR alignment, and single-bus inquiry** are finished. The architecture to get there is sound; the work is **execution on tables**, not more framework shopping.

---

## 10. Immediate next actions (operator checklist)

- [ ] Confirm hourly awareness still green after next tick  
- [ ] Diff last two `table_populate_log` rows (fields / parties / facts)  
- [ ] List residual docs with text and zero `document_fields`  
- [ ] Promote OP/MRO + TCT-32911 class queries to inquiry_stack-only answers  
- [ ] Schedule Phase B1 title registry ↔ brief reconcile  
- [ ] Keep Telegram bus fix on parallel track (does not block table population)

---

## 11. Related artifacts

| Artifact | Path |
|---|---|
| Doc populate agent | `agent_specs/001_doc_populate.md` |
| Bulk populate | `scripts/populate_tables_from_docs.py` |
| Field extract | `scripts/extract_fact_fields.py` |
| Harvest | `scripts/harvest_facts.py` |
| Briefs | `scripts/materialize_matter_brief.py`, `materialize_title_brief.py` |
| Inquiry | `scripts/inquiry_stack.py`, `corpus_answer.py` |
| Enterprise assessment | `ARCHITECTURE.md` |
| Awareness unit | `landtek-awareness.service` / timer |

---

*End of report. Numbers are live-as-of 2026-07-16 VPS census; re-run awareness for updated scorecard.*
