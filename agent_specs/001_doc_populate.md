# Agent 001 — `doc_populate`

**Status:** LIVE  
**Code:** `scripts/populate_tables_from_docs.py`  
**Timer:** `landtek-awareness.timer` (first step)  
**Fuel:** deterministic ($0, no LLM)

---

## 1. Mandate (one line)

**Turn every document with readable text into typed table rows so the rest of the stack can look up facts without re-reading PDFs.**

---

## 2. Capabilities (what it can do)

| # | Capability | Success looks like |
|---|---|---|
| C1 | **Scan** all docs with text ≥ min length | `table_populate_log.docs_scanned` rises each run |
| C2 | **Extract** typed fields from full text (TCT/OCT/e-title/CTN/tax_dec/date/amount/docket/survey/forum) | rows in `document_fields` with verbatim `source_span` |
| C3 | **Link titles** mentioned in a doc | `document_titles` (doc_id, tct_number) |
| C4 | **Write matter facts** when doc is matter-linked | `matter_facts` with `created_by='doc_populate'`, `provenance_level='inferred_strong'` |
| C5 | **Write labeled parties** when role-labeled in text + matter-linked | `matter_parties` inferred_strong + source_doc_id |
| C6 | **Refuse to invent** | no write without a span in the doc text; no “verified” tier |
| C7 | **Report** | `table_populate_log` row each run |

**Not capable of (out of mandate):**

- Promoting to `verified` (that is `verify_worker`)
- Answering chat / choosing dose (inquiry / role gate)
- Filing, outward email, strategy ranking
- Map geometry or law library maintenance

---

## 3. Knowledge it needs (to be capable)

| Knowledge | Why | Source table / place |
|---|---|---|
| Document body text | Only substrate for extraction | `documents.extracted_text` |
| Doc id | Stable key for rows | `documents.id` |
| Matter links (if any) | Where to attach facts/parties | `document_matter_links` |
| Field decoders | How to classify numbers delicately | `extract_fact_fields.extract_from_text` |
| Provenance rule | Only `inferred_strong` from regex | code + DB gate for verified |
| Prior populate rows | Idempotent rewrite per doc | `document_fields` delete-by-doc; `created_by=doc_populate` facts |

**Does not need:** chat history, role policy, legal_chunks, Ollama, client goals, map parcels.

---

## 4. Tables

| Role | Table | Owner? |
|---|---|---|
| **Own — primary product** | `document_fields` | **YES** |
| **Own — run log** | `table_populate_log` | **YES** |
| **Own — fact stream** | `matter_facts` where `created_by='doc_populate'` | **YES** (slice only) |
| **Own — party stream** | `matter_parties` written by this agent | **YES** (slice only) |
| **Write collaborator** | `document_titles` | shared write OK (doc_id+tct unique) |
| **Read** | `documents`, `document_matter_links` | no |
| **Do not write** | `matter_facts` verified, `titles` SoR registry, briefs | other agents materialize/verify |

Downstream (not this agent, but fed by it):

- `extract_fact_fields` → `fact_fields`
- `materialize_title_brief` → `title_brief`
- `materialize_matter_brief` → `matter_brief`

---

## 5. Inputs / outputs

```
IN:  documents.extracted_text + document_matter_links
OUT: document_fields
     document_titles
     matter_facts (inferred_strong, doc_populate)
     matter_parties (inferred_strong, labeled)
     table_populate_log
```

---

## 6. Health (mandate met?)

| Metric | Healthy |
|---|---|
| Docs with text scanned each run | ≈ count of docs with `length(text) ≥ 200` |
| Hit rate | `docs_with_hits / docs_scanned` high |
| `document_fields` non-empty growth or stable full pass | full rebuild still leaves tens of thousands of points |
| No `verified` written by this agent | always |
| Clarity: thin titles flagged later by materializer | not this agent’s job to fake completeness |

Check:

```bash
python3 scripts/populate_tables_from_docs.py --go
# last log:
# SELECT * FROM table_populate_log ORDER BY id DESC LIMIT 1;
```

---

## 7. Failure modes (fail closed)

| Situation | Behavior |
|---|---|
| No text / too short | skip doc |
| Extraction finds nothing | no rows (honest empty) |
| Matter not linked | still fill `document_fields`; skip matter_facts/parties |
| Gate / DB error on one insert | skip that row, continue corpus |
| Ambiguous bare number | decoder rejects or classifies carefully — no force into CTN |

---

## 8. Next agents this enables

1. **verify_worker** — upgrades best `doc_populate` / other facts to verified  
2. **title_brief materializer** — cards from titles + document_fields  
3. **inquiry** — answers from briefs/fields, not raw PDFs  

---

## 9. Operator one-liner

> **doc_populate** is the loader: every readable document becomes typed rows; it never claims verification; unclear later cards are someone else’s flag, not this agent’s invention.
