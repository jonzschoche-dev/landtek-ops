# 004 — reply_brain_convergence  (the A85 decision the channel work forced)

*Spec / decision doc (no code). Written 2026-07-18. Blocks 003: the brief consumer's value depends on which
brain survives, so this decision comes first.*

---

## The finding (verified on the live box, 2026-07-17)

Ingress consolidated; the **reply brain forked**. Two divergent live brains:

| | Telegram (`landtek_telegram/handlers/llm.py`) | Messenger (`scripts/leo_service.process`) |
|---|---|---|
| Model | **metered Anthropic first** (`claude-sonnet-4-5`, env `ANTHROPIC_API_KEY`); Ollama fallback (deploy_922) | **$0 local Ollama** (qwen2.5:14b) |
| Tools | rich registry → Flask :8765 (`semantic_search` · `query_documents` · `read_document` · `search_drive` · `vault_*`) | `title_fetch` · `corpus_answer` · MPRB (deploy_930) |
| Decomposition (`fact_fields` / `matter_brief` / typed lookups) | **none** | partial (MPRB) |
| Client wall (A5/A25) | `_resolve_client_code` + **prompt prose** ("Do NOT pass a different client…") | structural resolve-or-HOLD |
| A79 role clamp / A75 projection / A21 outward hold | **absent** | present (via the orchestrator path) |
| Answer gate (fabricated-cite block) | absent | present |
| Relationship profile / equilibrium feed | absent | present (shadow) |

Neither brain is complete: TG has the **tools and the smarter model**; Messenger has the **governance and the
decomposition**. This is the same split the convergence ledger closed once already (10/10 agree), re-opened
one layer up. A85: *exactly one brain owns replies.*

**Why prompt-level walls are not walls:** the TG brain asks its model not to cross clients. A prompt is a
request to a generator; A5 is a constraint on a system. Every other lane in this stack enforces isolation in
SQL/gates precisely because models comply until they don't. Telegram is currently the only outward surface
whose client wall is enforced by *politeness*.

---

## The decision (recommended)

**One brain = the governed spine (`leo_service` path), absorbing the TG tool registry. Model becomes config,
not identity.**

Two ideas the fork conflates, pulled apart:

1. **Brain** = the governed pipeline: resolve (A25) → purpose route (title_fetch / corpus_answer / brief
   lookup) → assemble → generate → answer-gate → clamp (A79) → project (A75) → hold/send (A21). There is
   exactly ONE of these, shared by every channel. Ingress stays per-channel (the 4-service TG app is good —
   keep anchor/inbox/media/router; only `handlers/llm.py`'s brain is replaced by a call into the spine).
2. **Model** = a config axis of that brain (this is `leo_config@N` from the Improvement Lab appendix arriving
   early): default `$0 Ollama`; optionally metered Anthropic for the **operator role only**, behind an env
   flag, honestly labeled. The operator's better model is a legitimate want — it must not cost the wall.

So convergence ≠ downgrade-Telegram-to-qwen. It's: same gates for everyone, model chosen per role/budget.

### What moves where

| Piece | Action |
|---|---|
| TG tool registry (`vault_*`, `query_documents`, `search_drive`, `read_document`) | becomes purpose routes / tools of the spine (all channels gain them — Messenger gets vault answers too) |
| `semantic_search` as a primary tool | demoted to last-resort doc-finder (measured ~9% recall); typed/brief lookups first |
| TG prompt-prose client wall | replaced by the spine's structural A5/A25 |
| `handlers/llm.py` Anthropic loop | model slot in the spine's config (operator-only, env-gated) |
| Messenger path | unchanged; gains the TG tools |

### Sequence (each step reversible)

1. **Freeze feature-adds to `handlers/llm.py`** (every add deepens the fork).
2. Port the TG tool registry into the spine as routes (server-side, same Flask :8765 endpoints).
3. Add the model-config slot to the spine (operator→sonnet if env key present, else local; all others local).
4. Flip the TG router to call the spine; keep `handlers/llm.py` as the rollback path for one soak window.
5. Convergence-diff ledger on real TG traffic (same instrument as before: agree/at-least-as-strict), then
   retire `handlers/llm.py`.

### Done-when

- One reply pipeline serves both channels (grep-floor: no second Anthropic/Ollama chat loop outside the spine).
- The same message + identity produces the same governed decision on TG and Messenger (parity test).
- "How many ARTA→OP CTNs?" answers cold from typed fields on **both** channels, zero LLM.
- Client-wall truth-test passes **structurally** on the TG path (planted cross-client ask → refused by SQL,
  not by prompt).
- Metered spend is **role-gated and env-gated** — a client message can never invoke the metered model.

### Non-goals

Rebuilding TG ingress (keep the 4-service app) · a third brain "for the transition" · removing the operator's
better model (config, not amputation) · touching n8n.

---

## Why this outranks 003 in order (not in importance)

003 (brief consumer) wired into `leo_service` today serves Messenger only — the fork would silently halve its
value and *feel* like "the decomposition doesn't work" on the channel the operator uses most. Converge first,
then 003 lands once and pays on every channel.
