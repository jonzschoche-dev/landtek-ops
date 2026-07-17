# Agent 002 — verify_worker  (the TRUST side)

*Spec of a LIVE agent (`scripts/verify_worker.py`, ranked by `scripts/verify_loop.py`). Written 2026-07-17.
Where 001 fills breadth (bulk inferred), 002 earns trust (careful verified); 003 reads the result.*

Status: LIVE. This spec documents the existing agent in the 001/002/003 template + names its boundary.

---

## Mandate (one line)

Read the ranked source documents and write **verified** facts through the hardened excerpt-grounding gate: a
claim becomes `verified` **only if its quote is a real substring of the cited document**. Everything it cannot
ground goes to `proposed_facts` for a human — **never auto-verified**.

Success = the verified fraction climbs on **earned** ground, and nothing ungrounded ever wears the `verified`
tag.

---

## The gate (the whole guarantee)

> `verified` ⟺ the claim's contiguous ≥8-word quote is a **real substring** of the cited doc's OCR text.

The LLM (Gemini free-tier ladder → Ollama fallback, **$0** re: Anthropic) only *proposes* atomic claims + a
verbatim quote. The **substring check is deterministic**, so a hallucinating model **cannot** land a verified
fact — it can only fail the check and fall to `proposed_facts`. That inversion (untrusted generator, trusted
verifier) is why this agent is safe to run autonomously.

---

## Capabilities

| Can | Cannot |
|---|---|
| Read the ranked doc worklist (verify_loop points; worker reads), neglected-matter-first | Verify a claim whose quote is **not** a substring of the doc (→ `proposed_facts`) |
| Extract atomic claims via free-tier Gemini / Ollama, each with a verbatim ≥8-word quote | Auto-verify on model confidence |
| Write `verified` `matter_facts` **only** when excerpt-grounded (source_doc_id + excerpt) | Overwrite / contradict a `verified` fact (A78 → HOLD) |
| Route ungroundable claims → `proposed_facts` (human review) | Form an edge on an owner-unresolved doc (A77 `ingest_gate` → HOLD) |
| HOLD on contradiction with verified (A78) and on unresolved owner (A77) | Chat, file, email, set dose, decide strategy |
| Attempt-track (`verify_worker_log`, 14-day cooldown); rate-limit to free tier | Re-read a dry doc inside its cooldown |

---

## Knowledge it needs

| Needs | Does not need |
|---|---|
| ranked doc worklist (`verify_loop`, A75 `verify-worker` projection) | Chat / Messenger |
| `documents.extracted_text` (OCR) | Role / dose policy |
| the doc's owner/matter link (A77) | Law library |
| free-tier Gemini key×model ladder / local Ollama | Client strategy goals |
| the A78 contradiction gate + A77 ingest_gate | Anthropic credit |

---

## Tables

| Owns | Reads |
|---|---|
| `matter_facts` where `created_by='verify_worker'` **and** `provenance_level='verified'` (the earned promotions) | `documents` (OCR text) |
| `proposed_facts` (ungroundable claims → human) | `document_matter_links` / owner |
| `verify_worker_log` (attempts, cooldown) | `matter_facts` (contradiction check) |

---

## Capability ← knowledge picture

```
CAN write a VERIFIED fact
  ← needs doc OCR + a verbatim quote that is a real substring
  → matter_facts(verified, source_doc_id, excerpt)

CANNOT verify a claim it can't ground
  ← the substring check fails
  → proposed_facts (human review) — never verified

CANNOT contradict earned truth
  ← A78: incoming conflicts with a verified fact
  → HOLD (proposed_facts / contradiction_challenge), never overwrite

CANNOT touch an owner-unresolved doc
  ← A77 ingest_gate
  → HOLD until the owner resolves (A74 recheck)
```

---

## Boundary in the trio (the insight 001+002 makes visible)

001 and 002 both read documents, but they are **complementary, not duplicate**:

| | 001 doc_populate | 002 verify_worker |
|---|---|---|
| Output tier | `inferred_strong` (bulk) | `verified` (earned) |
| Method | regex, deterministic, fast | LLM-proposed + substring-gated, careful |
| Purpose | findability breadth | trust depth |

**The efficiency lane worth naming (for the desk, not a redesign of 002):** 001 already wrote **26,965
inferred facts that each carry a verbatim excerpt**. Those are **pre-screened promotion candidates** — a
deterministic, $0 promoter could re-check `excerpt ⊂ doc` + run A78 and promote the strongest to `verified`
**without an LLM re-read**. 002's LLM path stays valuable for the atomic claims regex *missed*. So the two
promotion routes are: (a) cheap deterministic promotion of 001's excerpted rows; (b) 002's LLM re-read for new
claims. Both feed the same gate. This is how the trio lifts the **13.2% verified ceiling** without re-reading
every doc from scratch. (Recorded here as a boundary note; 002's own mandate stays "the gate.")

003 (consumer) prefers this agent's `verified` output; 001's `inferred_strong` is tagged provisional.

---

## Why this agent (and why it's the ceiling-lifter)

001 fills breadth; 003 reads it. But 003's answers are only as strong as the **verified** fraction — today
13.2% (5,478 / 41,525). **002 is the only lane that raises that number honestly.** Without it, the cold
structured answers are mostly "provisional / unconfirmed," and the felt "Leo actually knows this matter" never
arrives.

---

## Truth-tests

- `excerpt_grounded_or_not_verified` — a claim whose quote is not a real substring → `proposed_facts`, never `verified`.
- `no_verify_without_source` — every `verified` row this agent writes has `source_doc_id` **and** a non-empty excerpt.
- `contradiction_holds` — a claim conflicting with a `verified` fact → HOLD, never overwrite (A78).
- `owner_unresolved_holds` — a fact citing an owner-unresolvable doc → HOLD (A77).
- `cooldown_respected` — a dry doc is not re-read within 14 days (`verify_worker_log`).
- `free_tier_only` — inference path is Gemini free ladder / Ollama; zero metered Anthropic calls.

---

## Cadence / wiring

`verify_loop` ranks (neglected-matter-first) → `verify_worker` reads N docs per tick via
`landtek-awareness.service` (continuous, paced) or `--loop`. Degrade-don't-crash: no OCR / no owner / no
free-tier quota → logged + skipped + cooldown, never a hang, never an ungrounded write.

---

## Done-when (health, since it is live)

1. Verified fraction **trends up** cycle-over-cycle (the ceiling-lift signal).
2. `proposed_facts` has a **human drain** (a review surface) — it must not silently accumulate.
3. **Zero** `verified` facts exist without `source_doc_id` + excerpt (audit query returns 0).
4. Contradiction HOLDs are **visible** (surfaced, re-checkable per A74), not silent losses.

## Non-goals

Verify without an excerpt · chat / send / file · auto-promote inference on confidence · overwrite a verified
fact · a second provenance definition.
