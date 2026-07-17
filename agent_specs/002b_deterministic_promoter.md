# Agent 002b — deterministic_promoter  (the cheap ceiling-lift)

*Spec (no code). A $0, no-LLM candidate SOURCE that feeds the EXISTING provenance gate. Written 2026-07-17.
Sibling of 002 (verify_worker): same gate, same guarantee, different — cheaper — source of candidates.*

---

## Mandate (one line)

Promote the strongest of 001's **already-excerpted** inferred facts to `verified` **without reading a
document with an LLM** — by re-checking, deterministically, that each fact's excerpt is a real substring of
its cited doc and that it does not conflict with earned truth. Cheapest honest lift of the verified fraction.

Success = verified count rises on facts that were **provably grounded all along**, at $0, with zero model calls.

---

## The A85 point (why this is NOT a second verified-writer)

There is **one** owner of the `verified` tag: the **provenance gate** (the same excerpt-substring gate
`verify_worker` writes through, backed by `enforce_provenance_facts` + the V3 block). This agent does **not**
`UPDATE provenance_level='verified'` on its own. It is a **candidate source** into that one gate — exactly as
002 is, except:

| | 002 verify_worker | 002b deterministic_promoter |
|---|---|---|
| Where the claim comes from | Gemini/Ollama reads the doc | 001 already extracted it (`matter_facts` inferred + excerpt) |
| Cost | free-tier LLM | **$0, no model at all** |
| What it adds | claims regex/001 **missed** | promotes claims 001 **already has** |

Both propose `(claim, cited_doc, verbatim_excerpt)`; the gate's substring check is the verifier. Same
guarantee: a claim whose excerpt is not a real substring **cannot** be promoted.

---

## Capabilities

| Can | Cannot |
|---|---|
| Read `matter_facts` where `provenance_level='inferred_strong'` AND `created_by='doc_populate'` AND excerpt≠'' AND `source_id ~ '^[0-9]+$'` | Promote a fact whose excerpt is **not** a substring of `documents.extracted_text` for its `source_id` |
| Deterministically verify `excerpt ⊂ doc.extracted_text` (exact, then whitespace-normalized) | Promote on confidence / similarity / LLM (no model in the loop) |
| Run the A78 contradiction check against existing `verified` | Overwrite or contradict a `verified` fact (A78 → HOLD) |
| Route passing candidates **through the existing gate** to `verified` (basis: the excerpt span) | Promote a fact citing an owner-unresolvable doc (A77 → HOLD) |
| Log every promotion (fact_id, doc_id, method='deterministic') | Directly flip `provenance_level` outside the gate |
| Be idempotent (a promoted fact is skipped next run) | Chat, send, file, set dose |

---

## Knowledge it needs

| Needs | Does not need |
|---|---|
| `matter_facts` inferred rows (statement, excerpt, source_id, matter_code) | An LLM / Gemini / Ollama |
| `documents.extracted_text` (to substring-check against) | Chat / role / dose |
| the A78 contradiction gate + A77 owner check | Law library, strategy |
| the existing verified-write path (verify_worker's gate) | Document re-OCR |

---

## Tables

| Owns | Reads |
|---|---|
| `promotion_log` (fact_id, doc_id, verdict, reason) — its only write besides the gated promotion | `matter_facts` (inferred candidates + verified for A78) |
| (promotions land via the gate, owned by the provenance layer — not a new writer) | `documents.extracted_text` |

---

## Capability ← knowledge picture

```
CAN promote an inferred fact to verified
  ← needs its excerpt to be a REAL substring of the cited doc + no A78 conflict + owner resolved
  → gate writes verified (basis = excerpt span), method='deterministic'

CANNOT promote what it can't ground
  ← excerpt not found in doc.extracted_text (OCR changed, wrong doc, paraphrase)
  → leave inferred; optionally flag for 002 (LLM) or human

CANNOT out-rank earned truth
  ← A78: candidate conflicts with a verified fact
  → HOLD (never overwrite)
```

---

## Why this agent (the arithmetic)

The verified fraction is **13.2%** (5,478 / 41,525) and it is the ceiling on how much of any answer can be
stated as fact. 001 wrote **26,965 inferred facts, 100% with an excerpt** — a pool of pre-screened candidates.
Some unknown fraction of those excerpts are exact substrings of their cited docs (they were extracted *from*
that text), i.e. **already deterministically provable**. Promoting that subset costs **$0 and zero LLM calls**
and lifts the ceiling immediately; whatever fails the substring check (OCR drift, paraphrase) stays for 002's
LLM re-read or a human. It is the cheapest lever in the trust stack, and it runs before spending a single
free-tier token.

**Honest expectation:** the promotable fraction is a **measured number, not a promise** — report it (candidates
scanned → substring-passed → A78-cleared → promoted). If it's small, that itself is signal (001's excerpts are
paraphrases, not verbatim spans — a bug in 001 worth fixing).

---

## Truth-tests

- `promote_only_if_substring` — a fact whose excerpt is not in `doc.extracted_text` is never promoted.
- `no_llm` — zero model calls (pure substring + SQL); monkeypatch any LLM to raise.
- `contradiction_holds` — a candidate conflicting with a `verified` fact → HOLD (A78), never overwrite.
- `owner_resolved` — a candidate citing an owner-unresolvable doc → HOLD (A77).
- `gate_is_sole_verified_writer` — promotions route through the existing gate; the agent never `UPDATE`s `provenance_level` directly.
- `idempotent` — re-running does not re-promote or double-log.

---

## Cadence / wiring

Runs as a step in `landtek-awareness.service` **after** 001 (doc_populate) and **before** 002 (verify_worker)
— so the free-tier LLM only spends tokens on what deterministic promotion could not already earn. Paced,
degrade-don't-crash.

## Non-goals

A second definition of `verified` · promoting on confidence · an LLM anywhere in the path · overwriting earned
truth · touching chat.
