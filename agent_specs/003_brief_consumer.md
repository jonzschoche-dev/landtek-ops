# Agent 003 — brief_consumer  (the READ / emission side)

*Number provisional: slot after 002_verify_worker. Producers write the substrate (001 load → materialize →
002 verify); this agent is the only one that READS it into a reply. Written 2026-07-17.*

Status: SPEC (no code). Closes the loop the closed-loop check found open — the materialized substrate
(`matter_brief` 36 · `fact_fields` 41,506 · `document_fields` 14,605) is populated but **read by zero
chat-path consumers**; every reader today is a producer or a report.

---

## Mandate (one line)

When a message resolves to a matter, answer by **looking up the materialized brief + typed fields** — never
re-derive from fact prose, never call the LLM for a factual / count / status ask, never count by ILIKE.

Success = a short, cold, correct answer produced with **zero Ollama calls** and **nothing to distill**.

---

## The A85 boundary this agent exists to enforce

There are currently **two owners of "the matter brief"** that never touch:

| Owner | What it is | Problem |
|---|---|---|
| **Materialized** `matter_brief` table (background) | headline, `ctns[]`, `angle_status`, `computed_at` | nobody in chat reads it |
| **Query-time** `matter_brief.py::assemble()` | re-queries `matters`/`matter_facts` every turn | ignores the materialized table |

And `corpus_answer.py` counts CTNs by **hardcoded `ILIKE '%Office of the President%'` with the codes written
as a source comment** — re-parsing prose, the exact thing decomposition was built to end, while 1,672 typed
`ctn` rows sit unused in `fact_fields`.

**Rule:** the materialized `matter_brief` is the **single source**; `assemble()` becomes a **reader of it**
(with a freshness fallback), not a parallel re-deriver. Prose counters are retired.

---

## Capabilities

| Can | Cannot |
|---|---|
| Read `matter_brief` columns (`status`, `stage`, `forum`, `ctns[]`, `tcts[]`, `dockets[]`, `next_deadline`, `headline`, `angle_status`, `n_facts_verified`) | Write ANY table (pure reader) |
| Count / list typed fields from `fact_fields` (`field_kind='ctn'|'tct'|'docket'|…`, verified-first) | Invoke the LLM for a factual / count / status ask |
| Return a **preformed** structured answer, ≤280, short by construction | Count by `ILIKE` prose matching (retired) |
| Check freshness (`computed_at` / `source_fingerprint`) and fall back to query-time assemble only if stale/missing | Serve a stale brief as if fresh |
| Honor the **tier wall**: assert only verified facts/fields; tag `inferred_strong` as provisional | Cross the client wall (A5) |
| Emit through the existing clamp/project/send (A79/A75/A21) | Send outward without the clamp |

The LLM is allowed **only** for genuinely open phrasing over the brief text — never as a SQL engine over
sentences, never for a count/status/CTN ask.

---

## Knowledge it needs

| Needs | Does not need |
|---|---|
| `matter_brief` (the materialized row) | Document text / OCR |
| `fact_fields` (typed rows, tier-labeled) | Ollama for facts |
| the matter resolver (which matter this ask is about) | Law library |
| identity → role + client_code (A25) | Chat memory as truth |
| freshness signal (`computed_at` vs matter's max fact `updated_at`, or `source_fingerprint`) | Strategy goals |

---

## Tables

| Owns | Reads |
|---|---|
| **nothing** (pure consumer) — optionally an answer/disclosure log (A39) | `matter_brief` (primary) |
| | `fact_fields` (typed counts/lists) |
| | `matters` (resolve) · `channel_users` (identity) |

If a disclosure log is added, it is the agent's *only* write and it is not a fact table.

---

## Capability ← knowledge picture

```
CAN answer a status ask short + no-LLM
  ← needs matter_brief row (fresh) + tier wall
  → "{code}: {status} at {forum}; stage {stage}. Ground(doc:{id}): …"   (≤280)

CAN answer "how many CTNs / which codes"
  ← needs fact_fields (field_kind='ctn', verified) OR matter_brief.ctns[]
  → "3 CTNs: 0690, 0747, 0792."   (count(DISTINCT value_norm), no ILIKE, no LLM)

CANNOT re-derive what is materialized
  ← if matter_brief is fresh, USE it; if stale, fall back AND flag re-materialize
  → never a second live computation of the same brief (A85)

CANNOT assert provisional as fact
  ← tier inherited on every field/fact
  → verified stated plainly + cited; inferred tagged "unconfirmed"
```

---

## Freshness contract (never serve stale-as-fresh)

1. Brief **fresh** (`computed_at >= max(matter_facts.updated_at)` for the matter, or fingerprint matches) → **lookup, answer**.
2. Brief **stale or missing** → fall back to query-time `assemble()` for THIS answer **and** enqueue a
   re-materialize (the loop refreshes it). Never silently serve the stale row; never block the reply on it.

---

## Truth-tests (the teeth)

- `count_from_typed_fields` — CTN count comes from `fact_fields`/`matter_brief.ctns`, NOT `ILIKE`; oracle:
  ARTA→OP = **3** with codes **0690, 0747, 0792**.
- `no_llm_on_factual` — the status/count path makes **zero** Ollama calls (monkeypatch `_llm` to raise).
- `tier_wall` — only verified facts/fields asserted plainly; `inferred_strong` never rendered untagged.
- `freshness_guard` — a stale brief triggers fallback + re-materialize flag, is never served as fresh.
- `single_brief_owner` — `assemble()` reads `matter_brief`; it does not recompute the materialized columns.
- `client_wall` — A5: zero cross-client rows in any consumer read.
- `short_by_construction` — factual answers ≤280 with no `distill()` needed (nothing to truncate).

---

## Wiring (one path, both channels — A85)

```
leo_service.try_purpose_route:
   title_fetch → corpus_answer → [NEW] brief_consumer.answer(cur, client, message, role) → else LLM
```

`brief_consumer.answer` returns a **preformed** dict (`{text, via, preformed:True, purpose}`) → clamp decides
whether/to-whom, projection does NOT rewrite it. Telegram (webhook) and Messenger (`leo_service.process`)
reach it through the same route. No fourth path.

---

## Done-when

1. "how many ARTA→OP CTNs?" → **"3 CTNs: 0690, 0747, 0792."** from `fact_fields`/`matter_brief.ctns`, zero LLM, ≤280.
2. `corpus_answer.py`'s hardcoded `ILIKE`-prose CTN counter is **deleted**.
3. `matter_brief.py::assemble()` **reads** the materialized `matter_brief` (freshness-guarded), not a parallel re-derive.
4. A status ask returns the brief's verified ground only; provisional is tagged; the `⚠ UNCLEAR` briefs
   surface their `oversight_reason` instead of a fluent guess.

---

## Why this agent (and why now)

The producers (001 load + materialize + 002 verify) built the substrate; **its value is collected only at
read time**, and today that value is zero — chat still re-derives and re-parses prose. This agent is where
"distilled quickly, not only when promoted" actually pays off. It writes nothing, so it is the safest agent to
land; and by making the materialized brief the single read source, it stops the field/brief tables from
fragmenting into a fourth and fifth owner.

## Non-goals

New store · LLM judge · writing fact tables · vector retrieval for facts · re-deriving materialized columns ·
a second brief assembler.
