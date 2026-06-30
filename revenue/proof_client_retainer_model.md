# Proof-Client Retainer Model — MWK-001 & Paracale-001

**Owner:** Revenue Engineer · **Date:** 2026-06-30 · **Status:** draft for Jonathan
**Frame:** LandTek is a land / mining-services property + legal-ops operation. This prices
property-records intelligence and legal-operations support — **not** attorney services.
**Money invariant:** no figure here is a payment, transfer, or money movement. QBO is
draft/estimate only; Jonathan executes every money action himself.

Targets from `MASTER_PLAN.md` §4A: **$6–15/day burn · $15–80/mo per-client inference ·
PHP 15–50k/mo retainer · >85% margin.**

---

## 1. Actual cost basis

### 1a. What the telemetry actually shows (booked — real)

```sql
-- llm_spend totals (VPS: docker exec n8n-postgres-1 psql -U n8n -d n8n)
SELECT count(*) rows, MIN(ts)::date first_ts, MAX(ts)::date last_ts,
       ROUND(COALESCE(SUM(cost_usd),0),4) total_usd FROM llm_spend;
-- rows | first_ts   | last_ts    | total_usd
--    1 | 2026-06-13 | 2026-06-13 |    0.0001     <- ONE router test row, sub-cent

SELECT source, count(*) n, ROUND(SUM(cost_usd),4) usd FROM llm_spend GROUP BY source;
-- router | 1 | 0.0001
```

```sql
-- finance ledger is empty -> no booked revenue or expense to compute P&L from
SELECT count(*) FROM finance_transactions;     -- 0
SELECT * FROM v_matter_pnl ORDER BY matter_code; -- (0 rows)
SELECT * FROM v_matter_roi;                      -- (0 rows)
```

**Honest read:** `llm_spend` reads **$0.0001 total, all-time** — a single 2026-06-13 router
probe. This is **not** evidence of a cheap stack; it's evidence the stack is **inert /
creditless** and the **spend-bridge is built but disabled** (`MASTER_PLAN.md` §3, §4A "spend-bridge
(built, **disabled**)"). Per §3, real historical burn was **~$40/day**, driven by the
now-dead `leo-simulator` through n8n — and `cost_governor` **did not see it** because the
bridge timer was off. So the booked number is honest but useless for pricing: **margin you
can't see, you don't have.** Every cost figure below the booked line is therefore **modeled**
and tagged `[HUMAN VERIFY]`.

### 1b. Infrastructure (booked — real, fixed)

| Item | Cost | Basis |
|---|---|---|
| DigitalOcean droplet (VPS, whole stack) | **$16/mo** | `MASTER_PLAN.md` §3 |
| Sovereign inference — Ollama 7B/14B (local) | **$0** | §4A "$0 unlimited"; runs on the droplet, no per-token cost |
| Postgres / n8n / cockpit | $0 incremental | co-resident on the same droplet |

Infra is a **shared fixed cost across all clients**, not per-client. With the two proof
clients live, the droplet is **$8/mo per client** ($16 ÷ 2). The local Ollama core (verify
loop, bulk extraction, 7B/14B synthesis) carries the **majority of routine work at $0
marginal cost** — that is the structural reason margin can clear 85%.

### 1c. Modeled per-client inference (activated state) — `[HUMAN VERIFY]`

When the spend-bridge is enabled and Leo runs live, frontier tokens are spent only on what
the local models can't do well (hard legal synthesis, sharpest dossier verdict). Modeled off
the §4A ladder (Opus $15/$75 · Sonnet $3/$15 · Haiku $0.80/$4 · GPT-4o-mini $0.15/$0.60 ·
Gemini Flash $0.075/$0.30 per 1M in/out) and the §4A routing target (~70% to local/cheap).

Per the §4A validated data point: **25 sim execs = $2.82 ≈ $0.11/probe at ~32k input tok
each** — that was the ~$40/day burner. A *real* client's monthly work is **not** thousands of
sim probes; it is a bounded set of genuine actions. Modeled monthly mix per active proof
client:

| Workload (monthly, per client) | Volume | Routed to | Modeled cost/mo |
|---|---|---|---|
| Bulk doc extract / classify on ingest | ~40 docs | GPT-4o-mini + local | ~$3 |
| Embeddings / RAG refresh | continuous | Gemini Flash + local | ~$1 |
| Daily digest + deadline reasoning | 30 days | Haiku + local 7B | ~$3 |
| Dossier synthesis (frontier pass) | 2–4 dossiers | Sonnet default | ~$8 |
| Hard legal synthesis (verdict/red-team) | a few | Opus, gated | ~$10 |
| **Modeled inference subtotal** | | | **~$25/mo `[HUMAN VERIFY]`** |
| **+ infra share** | | | **+$8/mo (booked)** |
| **Modeled all-in cost / client / mo** | | | **≈ $33/mo `[HUMAN VERIFY]`** |

$33/mo ≈ **$1.10/day per client** — comfortably inside the §4A **$6–15/day** total-burn
envelope (both clients ≈ $2.20/day) and inside the **$15–80/mo per-client inference** band.

**`[HUMAN VERIFY]` gate (the only thing that makes this real):** enable the spend-bridge
timer (`scripts/anthropic_spend_bridge.py`, `MASTER_PLAN.md` §"Activation"), run **one real
client-month**, then re-query `llm_spend` grouped by client/source and replace the modeled
$25 with the booked number. **Do not quote 85% as measured until that month is booked.**

---

## 2. Retainer offer (PHP 15–50k/mo band)

Priced against **what the workspace delivers today** (verified below), not roadmap. PHP
conversion at ~₱57/USD for the cost cross-check only.

**Delivered-today evidence (booked, real — VPS queries):**

| Capability | MWK-001 | Paracale-001 | Source |
|---|---|---|---|
| Matters under management | 20 | 9 | `matters` table |
| Indexed documents | **628** | **46** | `documents ⋈ matters` |
| Verified/extracted facts (fact graph) | **7,381** | **474** | `matter_facts` |
| Live deadline tracking + reminders | yes (reminders fired, gcal fields) | yes | `case_deadlines` |
| Daily digest (7AM) | live | live | §4A pillar 5 |
| Dossier pipeline (bound-PDF deliverable) | live | live | §4A pillar 2 |
| Per-client cockpit / file access | live | live | `/ops`, `/files/c` |

### Tiers

| | **Records Watch** | **Legal-Ops Active** ★ | **Recovery Partner** |
|---|---|---|---|
| **PHP / mo** | **₱15,000** | **₱30,000** | **₱50,000** |
| **USD ≈** | ~$263 | ~$526 | ~$877 |
| Document index + RAG search | ✓ | ✓ | ✓ |
| Deadline tracking + countdown reminders | ✓ | ✓ | ✓ |
| Daily digest (7AM) | ✓ | ✓ | ✓ |
| Per-client cockpit + file access | ✓ | ✓ | ✓ |
| New-doc ingest / month | up to 20 | up to 60 | unlimited (fair use) |
| Evidence dossiers (bound PDF) / mo | — | 2 | 4 + on-demand |
| Element→gap matrix per active matter | — | ✓ | ✓ |
| Cross-matter strategy / recovery mapping | — | — | ✓ |
| Frontier (Opus) hard-synthesis pass | — | metered | priority |
| À-la-carte extra dossier | ₱4,000 | ₱3,000 | included |
| À-la-carte rush ingest (per 20 docs) | ₱2,500 | ₱2,000 | included |

★ Recommended landing tier for both proof clients.

**What is roadmap, not sold here (do not promise):** live Leo control plane (n8n workflow
inactive), signature/authentication validation, PostGIS boundary maps, omnichannel
(WhatsApp/Viber), 4-layer RBAC, property-management (tenants/rent). These are §6 roadmap —
sell them when live, not before.

---

## 3. Margin proof (per-client P&L)

Revenue side is a **proposed price** (not yet booked — no `finance_transactions` rows). Cost
side is **§1**: $8/mo booked infra share + $25/mo modeled inference. All non-booked lines
`[HUMAN VERIFY]`. Per-client only — **no matters mingled across clients.**

### MWK-001 @ Legal-Ops Active (₱30,000 ≈ $526/mo)

| Line | Monthly | Provenance |
|---|---|---|
| Retainer revenue | ₱30,000 (~$526) | **proposed** `[HUMAN VERIFY]` |
| Infra share (½ droplet) | $8 | **booked** |
| Inference (modeled) | $25 | modeled `[HUMAN VERIFY]` |
| **Total cost** | **$33** | mixed |
| **Net** | **~$493** | derived |
| **Margin** | **~93.7%** | `[HUMAN VERIFY]` — modeled cost |

### Paracale-001 @ Legal-Ops Active (₱30,000 ≈ $526/mo)

| Line | Monthly | Provenance |
|---|---|---|
| Retainer revenue | ₱30,000 (~$526) | **proposed** `[HUMAN VERIFY]` |
| Infra share (½ droplet) | $8 | **booked** |
| Inference (modeled, lower doc volume) | $20 | modeled `[HUMAN VERIFY]` |
| **Total cost** | **$28** | mixed |
| **Net** | **~$498** | derived |
| **Margin** | **~94.7%** | `[HUMAN VERIFY]` — modeled cost |

**Margin floor stress test (worst-case real):** if booked inference comes in at the **top of
the $80/mo §4A band** + $8 infra = $88/mo cost against the **lowest** tier (₱15,000 ≈ $263):
margin = (263−88)/263 = **~67%** — *below* 85%. So the 85% guarantee holds at the **₱30k+
tiers**, and the **₱15k Records Watch tier only clears 85% if its inference stays ≤ ~$31/mo**
(which its 20-doc cap and digest-only scope should ensure, but must be verified once booked).
**Action:** cap Records Watch inference via `cost_governor` so it cannot silently breach.

**Both proof clients at ₱30k = ₱60,000/mo (~$1,052) revenue against ~$61/mo total modeled
cost (~$2.20/day) → blended margin ~94%, inside every §4A envelope.** Real, only once the
spend-bridge is on and one month is booked.

---

## 4. GTM — landing the first paying retainer

**The two proof clients are warm:** MWK-001 and Paracale-001 already have live workspaces
(628 + 46 docs, deadline tracking, dossiers). The sale is **converting delivered value to a
signed retainer**, not cold prospecting.

**Step 1 — the proof artifact (this week).** Generate one current bound-PDF dossier per client
from the live pipeline and pair it with a one-page "what your workspace did this month" sheet
(docs indexed, deadlines caught, next actions). That sheet *is* the pitch — it shows the
₱30k/mo value in their own matter.

**Step 2 — price conversation.** Land both at **Legal-Ops Active (₱30k/mo)**. Anchor on the
deadline-miss risk avoided and the dossier deliverable, not on tokens.

**Step 3 — wire billing (draft only, Jonathan executes).** QBO MCP is **connected but not yet
OAuth-authorized this session** (`company_info` returned auth-required). Once authorized:
draft two **estimates** (one per client, ₱30k/mo recurring) via `qbo_sales_create_estimate`
— **draft/estimate only, never send, never create a payment link.** Jonathan reviews and
sends/collects himself. Set up the per-client product/service items so QBO P&L mirrors
`v_matter_pnl` per client.

**Step 4 — book reality before claiming margin.** Enable the spend-bridge timer, let one
client-month run, then book the retainer income + real inference into
`finance_transactions` (client-tagged) and read `v_matter_roi`. That turns the §3 margins
from `[HUMAN VERIFY]` modeled into measured. **This is the definition-of-done gate.**

**What makes client #3 repeatable:** the offer is already productized into 3 fixed tiers
priced against capabilities that exist for *any* property/recovery matter (ingest → fact
graph → deadlines → dossier). Onboarding = create a `client_code`, ingest their docs, point
the cockpit at it. The only per-client variable is doc volume, which the tier caps + à-la-carte
ingest already handle. Client #3 is the same SKU, not a new build.

---

## Open decisions to push to MASTER_PLAN §7

1. Confirm **₱30k Legal-Ops Active** as the standard proof-client landing price.
2. Authorize the QBO MCP this session so estimates can be drafted.
3. Enable the spend-bridge timer to convert modeled margin → measured (DoD gate).
4. Apply a `cost_governor` per-client inference cap on the ₱15k tier so it cannot breach 85%.
