# LandTek — Enterprise Architecture Assessment & Gap Analysis

> **Status:** assessment for review (2026-06-21). **`MASTER_PLAN.md` remains the single authority on
> direction, sequencing, and the north star.** This document is the *technical* reference: what we
> have, the enterprise target, and the gaps between — so we can choose what to build with eyes open.
> Nothing here is committed work until it lands in MASTER_PLAN's plan.

---

## 1. The mandate, reconciled

There are two timescales and they must not be confused:

- **Wartime (now):** win Patricia's case — Aug 12, 2026 testimony in CV-26360. Reliability, $0, earn
  autonomy slowly. This is the current MASTER_PLAN mandate.
- **Enterprise (trajectory):** an evidence-grade, hallucination-proof legal/land-ops *platform* that
  could serve multiple clients and matters with **data sovereignty** over privileged material.

The discipline that has kept this stack honest is **don't build ahead of need.** Most enterprise
architecture (HA, multi-tenancy, RBAC) is premature for a solo wartime operation. So this assessment
separates *what enterprise-grade requires* from *what wartime needs now*, and flags the rare gaps that
are **both** — those are the only ones to build during wartime.

**The one gap that is both:** the **inference layer**. It is simultaneously the acute wartime blocker
(verification is stalled at ~14 docs/day on free-tier API quota) and a hard enterprise-legal
requirement (privileged documents must not leave the perimeter). Everything else is roadmap.

---

## 2. Current architecture (honest inventory)

| Layer | What exists | Honest state |
|---|---|---|
| **Compute** | 1× VPS (Tailscale), Docker: n8n + Postgres. Mac Studio M2 Max / 32 GB on Tailscale. | Single node, no failover. **Mac Studio idle** (only runs the git-sync daemon). |
| **Inference** | API-only: Anthropic (depleted), Gemini free-tier (daily-capped), OpenAI. `model_router.py` ladder. | **THE binding constraint.** No owned compute; quota/credits gate everything. |
| **Data** | Postgres (n8n DB): documents, titles, title_chain, entities, matter_facts/parties/causes, gmail_messages. PostGIS parcels. | Solid schema. Single instance, no replication/PITR. |
| **Knowledge / truth** | Provenance write-gate (verified/operator/inferred), hardened verbatim-excerpt grounding, `_safe` views. | **Strong** — the core differentiator. Enforced in DB triggers, framework-agnostic. |
| **Pipelines (agents)** | verify_loop (scout) → verify_worker (reader) → gate → matter_facts → case_dossier; deadlines; cross_client_sentinel; comprehend; corpus_backfill (OCR). | Working, de-facto agents. Orchestrated by **systemd timers + Postgres state + the gate as contract** — deliberately framework-free. |
| **Interfaces** | Leo (Telegram, n8n AI-Agent node on LangChain.js) + simulator/smartness loop; web cockpit (`ops_dashboard`); committed case dossiers. | Functional. No adjudication UI for `proposed_facts`. |
| **Quality / safety** | `truth_tests` (76 assertions), provenance triggers, `leo_answer_gate`, sim safety rules (S1–S14). | Good for a solo build. |
| **Continuity** | Backblaze backups (lifecycle fixed). | Backups exist; **restore never drilled**. |

**Frameworks:** none in Python (no LangGraph/LangChain/CrewAI). The only LangChain is LangChain.js
*inside* n8n's AI-Agent node, used solely by Leo. This is a feature, not a gap — keep it.

---

## 3. Enterprise target architecture (the layered picture)

```
L1  INFERENCE      tiered: in-house (Mac Studio/Ollama, sovereign, unlimited)
                   → cheap API (Gemini) → frontier (Claude / Cowork) used sparingly
L2  DATA+KNOWLEDGE provenance-gated knowledge layer (have) + encryption-at-rest + access audit
L3  ORCHESTRATION  timers + Postgres + gate (have) + light agent registry + health supervisor
L4  INTERFACES     Telegram (Leo) · web cockpit · dossiers + a proposed_facts adjudication view
L5  RELIABILITY    backups (have) + PG replication/PITR + tested restore + failover + alerting
L6  GOVERNANCE     secret vault + RBAC + access audit + confidentiality/retention policy
```

The shape we already have (gated knowledge + framework-free orchestration) is correct. The target is
mostly **hardening + an owned inference tier**, not a redesign.

---

## 4. Gap analysis (ranked)

| # | Gap | Why it matters | Enterprise / Wartime | Cost | Effort |
|---|---|---|---|---|---|
| 1 | **Owned, tiered inference** | Kills the fuel bottleneck; keeps privileged docs in-perimeter; ends vendor-outage risk | **Both** | ~$0 (own hardware) | **Low** (½ day) |
| 2 | **Tested DR / restore drill** | Backups untested = unknown if recoverable | Both (cheap insurance) | ~$0 | Low |
| 3 | **Security depth** — access audit, secret vault, encryption-at-rest | Privileged legal data; we audit *provenance* not *access* | Enterprise | Low | Med |
| 4 | **Resilience / HA** — PG replication, failover | Single VPS+PG = single point of failure | Enterprise | Low–Med | Med |
| 5 | **Confidentiality/retention policy** | Privilege, PII handling, data-sovereignty posture | Enterprise (legal) | ~$0 | Low (policy) |
| 6 | **Human-in-the-loop adjudication** | `proposed_facts` has no review workflow/UI | Both (quality) | ~$0 | Med |
| 7 | **Observability / alerting** | Logs + dashboards exist; no alerting | Enterprise | ~$0 | Low–Med |
| 8 | **Multi-tenancy / hard client isolation** | Needed only to *sell* to multiple clients | Product-only | Med | High |
| 9 | **Agent registry (light)** | Name/contract the de-facto agents (job/fuel/cadence) — NOT LangGraph | Low | ~$0 | Low |

---

## 5. The #1 gap in detail — owned, tiered inference

**Hardware you already own:** Mac Studio **M2 Max, 32 GB**, on Tailscale (`100.117.118.47`), **Ollama
already installed**, currently idle.

- **Capacity:** comfortably serves up to ~**32B** models (Qwen2.5-32B Q4 ≈ 20 GB); runs 7–14B *fast*
  (30–50 tok/s). **Ceiling is ~32B** — frontier-grade legal *reasoning* stays on Claude/Cowork.
- **Why a small local model is safe here:** the **provenance gate** adjudicates every write — a local
  model cannot land an ungrounded "verified" fact. Model quality affects *recall*, not *safety*. This
  is what makes a free local model viable for the bulk tier.
- **Tiering:**
  - *Tier 1 (in-house, unlimited, sovereign):* Qwen2.5-14B default / 32B when needed — verification,
    extraction, classification, OCR-assist (the workhorse, replaces the quota-capped Gemini calls).
  - *Tier 2 (cheap API fallback):* Gemini free-tier when the Mac is asleep/busy.
  - *Tier 3 (frontier, sparing):* Claude / Cowork (me, in-session) / credits — hard reasoning, briefs.
- **Integration (small):** workers already call models over plain HTTP; point them at
  `http://100.117.118.47:11434` (Ollama) and add `local` as the top rung of `model_router.py`. The gate
  and `truth_tests` are unchanged.
- **Payoff:** verification throughput goes from ~14 docs/day → continuous; the ~290-doc backlog drains
  in hours; documents never leave your hardware; no credit-outage can take it down.
- **Risks / caveats (honest):** Mac must stay awake + serving (`caffeinate` + Ollama launchd service);
  model files are 9–20 GB each (check free disk); it is a *workhorse not HA* (the API fallback covers
  Mac downtime); batch-grade throughput, not high-concurrency.

---

## 6. Suggested sequencing (proposal — MASTER_PLAN decides)

- **Now (serves Aug-12 *and* enterprise):** stand up the in-house inference tier (gap 1) → unblocks the
  case-corpus verification. Run a one-time **restore drill** (gap 2) — cheap insurance.
- **Near (post-fuel, $0):** doc-discovery + OCR-triage agents to finish the corpus; a `proposed_facts`
  adjudication view (gap 6); add the light agent registry (gap 9).
- **Later (only if this becomes a multi-client product):** HA/PITR (4), RBAC + access audit +
  encryption-at-rest (3), alerting (7), multi-tenancy (8). Write the confidentiality/retention policy
  (5) before any third party's data enters.
- **Explicitly deferred, with eyes open:** multi-tenancy and HA — they cost real complexity and serve
  *scale we don't have yet*. Building them now would violate "don't build ahead of need."

---

## 7. Decisions this surfaces for the operator

1. **Approve the in-house inference tier as the next build?** (Recommended — it's the rare both-now-and-
   enterprise move, and the hardware is already paid for and idle.)
2. **Is the goal a multi-client PRODUCT, or a sovereign personal platform?** This single answer decides
   whether gaps 4/8 (HA, multi-tenancy) are ever in scope. If "personal platform," skip them; still do
   security + DR lightly.
3. **Hardware ceiling:** accept the 32 GB / ≤32B local ceiling, or plan a 64–128 GB box later to run
   70B-class models in-house (closer to frontier, fully sovereign)?
