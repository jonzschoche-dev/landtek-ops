# HALLUCINATION LOG REVIEW — 2026-05-12

Only one entry currently recorded in `hallucination_log`, but it's instructive
about the kinds of errors that have been observed in earlier LLM-driven outputs
on this project. Capturing it here so future drafting/extraction passes don't
repeat the pattern.

## The recorded incident

**Source:** LeoLandTekBot (n8n agent, recorded 2026-05-12 07:15:54)
**Prompt:** "when did Mary Worrick Keesey pass away?"
**Response:** "March 30, 2024 with TCT docs 10/11/372/418 citing lots
10727-A-1-B-* with co-owners Gloria Balane + Francisco Delfin Keesey"

**Fabrications captured:**

| Item | Fabricated value | Reality |
|---|---|---|
| Death date | "March 30, 2024" | Unverified — no source document confirms |
| Lot numbers | 10727-A-1-B-1-A through -D | T-4497 chain is Lot 2-X-4 / 2-X-6 derivatives |
| Areas | 98 / 111 / 72 / 103 sqm | T-32917 is 85,149 sqm; the small-area lots don't exist |
| Doc 418 | cited | Does not exist in `documents` table |
| Person "Francisco Delfin Keesey" | cited as co-owner | Not in `entities` graph |
| Gloria Balane | "co-owner" | She is the **flagship defendant** in Civil Case 26-360 |

## Why this matters (the pattern)

A single LLM call was confidently asked an unanswered factual question and
**invented an entire alternative chain of title** — different lot numbers, different
people, different areas, a fictitious document ID, and a category error (defendant
named as co-owner). Every layer of the fabricated answer was internally
consistent and would have read plausibly to a non-expert; only direct DB checks
exposed it.

## Operational guardrails this implies

These are not aspirational — they map directly to the directive's
"hallucination-proof discipline" section in `/root/landtek/CLAUDE.md`:

1. **Never answer a factual question about people, dates, lots, or document
   IDs from memory.** Always run a query against the appropriate `_safe` view
   (or the raw table with a `provenance_level='verified'` filter) and quote
   the column value.

2. **If the verified-data answer is "unknown," say "unknown."** Do not improvise.
   That's exactly the pattern that produced "March 30, 2024" out of nothing.

3. **Gloria Balane is the defendant, not a co-owner.** Any output that
   characterizes her as anything other than "defendant" or "transferee #20
   holding TCT T-079-2021002126" is wrong.

4. **The 20 named transferees list is authoritative** (`transferees` table,
   `case_file='MWK-001'`). Any person named in a substantive response should
   either be in that list, in `entities`, or be a named lawyer/judge from a
   document with a quoted citation.

5. **Lot numbering for T-4497's chain follows the 2-X-* convention**
   (Lot 2-X-4, Lot 2-X-6, then Lot 2-X-6-A through 2-X-6-V for the 17 sub-
   subdivisions under T-32917). Any "10727-A-*" pattern would be a smoking-gun
   hallucination — it's not the family.

6. **Document IDs must be verifiable.** Anywhere a doc_id is cited, it should
   be cross-checked against `SELECT id FROM documents WHERE id = <n>`. Doc 418
   in the recorded hallucination was simply invented; current max id is in
   the high 400s but with gaps, so plausibility is no defense.

7. **Areas have a single canonical source.** Per the verified `titles_safe`
   rows: T-32917 = 85,149 sqm; T-32916 = 14,416 sqm. Anything else for those
   two titles is wrong; for other titles, query rather than recall.

## How to grow this log

Anything that survives review (e.g., an LLM response that's later corrected by
a human or a sweep) should be inserted into `hallucination_log` with the
six-field schema:
```sql
INSERT INTO hallucination_log
  (source, user_question, bot_response, fabricated_claims, why_wrong)
VALUES
  ('<which agent/script>', '<original prompt>', '<offending text>',
   '<jsonb of specific claims>', '<correction tied to verified data>');
```

This becomes a regression set: future prompts/extractions can be evaluated
against it.
