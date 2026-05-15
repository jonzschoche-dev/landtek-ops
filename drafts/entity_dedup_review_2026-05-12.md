# ENTITY DEDUPLICATION REVIEW — 2026-05-12

## Scope

The `entities` table has 2,506 rows. The phonetic-key + canonical-name
diagnostics reveal substantial duplication driven by (a) OCR-induced spelling
variants and (b) the same canonical string being recorded under multiple
`type` values (e.g. one TCT number ending up as `reference_number`,
`property`, and `deed_or_instrument` simultaneously).

This memo enumerates the duplication patterns and proposes the merge plan,
but **does not execute the merges**. Merging touches `doc_entities`,
`entity_aliases`, `entity_relationships`, and `mentions_count` aggregates,
plus the `titles.registrant_entity_id` FK. The directive requires explicit
approval before schema-touching changes; merges should be staged after
Jonathan reviews this proposal.

---

## I. PERSON-LEVEL DEDUP — Mary Worrick Keesey

**Canonical row:** `entities.id = 25`, type=person, canonical_name = "Mary
Worrick Keesey", mentions_count = 254.

**OCR-variant rows that should be merged in (sorted by mentions_count):**

| id | canonical_name | mentions | type |
|---|---|---|---|
| 768 | Mary Worick Keesey | 25 | person |
| 237 | Mary Worrick Keesee | 23 | person |
| 178 | Mary Worrick Keesey | 8 | property (mis-typed) |
| 1055 | Mary W. Keesey | 6 | person |
| 1737 | Mary Worriok Kasooy | 6 | person |
| 497 | Mary Worrick Kessey | 4 | person |
| 1684 | Mary Worrick Keesny | 3 | person |
| 939 | Mary Worrick Keeseey | 2 | person |
| 1720 | Mary Werrick Koasey | 2 | person |
| 1921 | Mary Worick | 2 | person |
| 1327 | Mary Worrick Keevey | 1 | person |
| 1513 | Mary Worrick Keevy | 1 | person |
| 379 | Mary Warrick-Tassey | 1 | person |
| 141 | Mary Herrick Kossoy | 1 | person |
| 1402 | Mary Arick | 1 | person |
| 1955 | Mary Irrick Kuay | 1 | person |
| 2609 | Mary Worrick Kesgey | 1 | person |
| 967 | Mary Wornd eeutu | 1 | person |

**Effect of merge:** mentions_count for id=25 rises from 254 to ~340. The
`titles_safe.registrant_entity_id=25` link gains all the document references
from the variants.

**NOT a merge target (different person):**
- 540 / 2066 / 2164 / 2392 / 2492 — variants of "Marcia Ellen Keesey"
  (Mary's daughter or relative). Distinct from Mary.
- 320 — "Marcia Tien Keesey", possibly the same as Marcia Ellen line above.
- 439 / 2099 / 1045 — "Ernest Francis Keesey" variants — distinct person.
- 1419 — "Francis Keesey" — distinct.
- 511 — "Marsha Ellen Keesey" — likely Marcia Ellen variant.
- 1260 — "Kara Tamlet Keesey" — distinct.
- 933 — "Elmer Worick Keesey" — distinct.
- 695 / 2187 — "Pat Keesey" / "Patricia Anne Keesey" — likely
  Patricia Keesee Zschoche (the plaintiff). **High-value separate dedup chain.**

---

## II. PERSON-LEVEL DEDUP — Jonathan Zschoche

**Canonical row:** `entities.id = 1184`, type=person, canonical_name =
"Jonathan Paul Zschoche", mentions_count = 153.

**Merge candidates:**

| id | canonical_name | mentions |
|---|---|---|
| 73 | Jonathan Zschoche | 57 |
| 1676 | Jonathan 'JJ Illdefonso Moreno' Zschoche | 6 |
| 2228 | Jonathan Ildefonso Moreno | 4 |
| 2344 | Jonathan Zchoche | 4 |
| 2000 | Jonathan 'JJ Ildefonso Moreno' Zschoche | 4 |
| 1611 | Jonathan 'JJ ldefonso Moreno' Zschoche | 4 |
| 1930 | Jonathán Zschoche | 2 |
| 2036 | Jonathan Ildefonso Moreno Zschoche | 1 |
| 2446 | Jonathan 'JJ Ilidefonso Moreno' Zschoche | 1 |
| 1633 | Jonathan Illdefonso Zschoche | 1 |
| 1648 | Jonathan 'JJ Idefonso Moreno Zschoche | 2 |

**Effect:** id=1184 gains ~86 mentions, reaches ~240, and a single user
identity rather than 12 fragments.

**Note:** "Jonathan Ildefonso Moreno" alone (id 2228) is risky to merge —
it could be a separate person whose middle name overlaps. Check before
merging.

---

## III. PATRICIA KEESEE ZSCHOCHE — plaintiff dedup

The "Pat Keesey" / "Patricia Anne Keesey" rows above plus the existing
"Patricia Keesee Zschoche" row need triage. Per CLAUDE.md, the plaintiff is
**Patricia Keesee Zschoche** (US, mother of Jonathan). Worth a separate
pass to confirm which rows are her under maiden vs. married names.

---

## IV. TCT-NUMBER ENTITY MISCLASSIFICATION (each TCT appears as 3 types)

Pattern: a TCT number gets entity-extracted three times — once as
`reference_number`, once as `property`, once as `deed_or_instrument`.

Examples (each is one TCT recorded as 3 rows):

| TCT | entity rows | types |
|---|---|---|
| TCT T-4497 | {218, 391, 572} | reference_number, deed_or_instrument, property |
| TCT No. T-4497 | {1431, 634, 489} | reference_number, deed_or_instrument, property |
| TCT T-32917 | {169, 574, 390} | reference_number, deed_or_instrument, property |
| TCT T-38838 | {143, 576, 1218} | reference_number, deed_or_instrument, property |
| TCT T-47657 | {247, 312, 389} | reference_number, deed_or_instrument, property |
| TCT T-48335 | {419, 1179, 1655} | reference_number, deed_or_instrument, property |
| T-32916 | {1087, 1489, 2457} | reference_number, deed_or_instrument, property |

**Plus** the "TCT T-4497" rows are duplicated by "TCT No. T-4497" rows
because the extractor sometimes preserves the "No." token.

**Recommended canonical type:** `reference_number` — keeps the row that
actually represents the docket-style identifier; the `property` row should
be reclassified as a reference back to the `titles` table proper, and
`deed_or_instrument` is the wrong type for an identifier (an identifier
isn't a deed). Then dedupe "TCT T-4497" vs. "TCT No. T-4497" by stripping
the optional "No." token.

This pattern repeats for likely every TCT in the corpus (the diagnostic only
showed 15 examples — full sweep would surface many more).

---

## V. LOCATION DUPLICATES

Multiple representations of the same place:

- **Mercedes** — 4 rows: "Mercedes" / "Mercedes, Camarines Norte" /
  "Mercedes, Camarines Norte, Philippines" / "Municipality of Mercedes,
  Province of Camarines Norte". One canonical hierarchy needed.
- **Quezon City** — 2 rows: "Quezon City" / "Quezon City, Philippines".
- **Camarines Norte** — 3 rows of mixed type (location/property/organization).

---

## VI. PROPOSED MERGE PRIMITIVE (DO NOT RUN WITHOUT APPROVAL)

```sql
-- For each (keep_id, merge_id) pair:
BEGIN;
-- Append the merged name as alias
UPDATE entities e
   SET aliases = ARRAY(SELECT DISTINCT unnest(e.aliases || ARRAY[m.canonical_name])),
       mentions_count = e.mentions_count + m.mentions_count,
       updated_at = NOW()
  FROM entities m
 WHERE e.id = :keep_id AND m.id = :merge_id;

-- Re-point doc_entities (with ON CONFLICT to skip dupes)
INSERT INTO doc_entities (doc_id, entity_id, mention_count, last_seen_at)
SELECT doc_id, :keep_id, mention_count, last_seen_at
  FROM doc_entities WHERE entity_id = :merge_id
  ON CONFLICT (doc_id, entity_id) DO UPDATE
     SET mention_count = doc_entities.mention_count + EXCLUDED.mention_count;
DELETE FROM doc_entities WHERE entity_id = :merge_id;

-- Re-point entity_relationships
UPDATE entity_relationships SET from_entity_id = :keep_id WHERE from_entity_id = :merge_id;
UPDATE entity_relationships SET to_entity_id = :keep_id WHERE to_entity_id = :merge_id;

-- Re-point titles
UPDATE titles SET registrant_entity_id = :keep_id WHERE registrant_entity_id = :merge_id;

-- Log the merge in entity_aliases
INSERT INTO entity_aliases (entity_id, alias_text, source) VALUES
  (:keep_id, (SELECT canonical_name FROM entities WHERE id = :merge_id),
   'auto-merge 2026-05-12 entity_dedup_review');

DELETE FROM entities WHERE id = :merge_id;
COMMIT;
```

## VII. RECOMMENDED EXECUTION ORDER

1. Mary Worrick Keesey merges (18 rows → 1) — highest-mentions, safest
   because the canonical row already dominates the entity graph for her.
2. Jonathan Paul Zschoche merges (11 rows → 1) — pause on the
   "Ildefonso Moreno" row to confirm.
3. Patricia Keesee Zschoche merges — after Mary completes, since some Pat
   Keesey variants may be intermediate.
4. TCT identifier merges — large in count but mechanical. Make sure the
   canonical kept row has type=`reference_number`.
5. Location merges last (lowest-risk; mostly cosmetic).

---

## VIII. WHAT'S NOT IN THIS REPORT

- `entity_aliases` table contents (not queried — would also factor in).
- `instruments_under_authority` view check for any Cesar de la Fuente
  variants that need merging (the view returned 0 rows; once OCR runs over
  the 2005 revocation document and the 2016 Deed, de la Fuente entities
  may appear with spelling variants and need their own dedup pass).
- Org-level dedup (Banco Legaspi vs Banco de Oro variations, etc).
- Reference-number dedup beyond TCTs (Civil-Case numbers, BIR forms, etc.).
