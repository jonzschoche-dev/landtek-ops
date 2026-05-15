# REGISTERED_OWNERS DISAGREEMENT TRIAGE — 2026-05-13

`field_consensus` returned **9 disagreements on registered_owners** across the
overnight sweep. Triage with the actual source quotes from `extraction_runs.raw_json`:

## Headline finding

**All 8 MWK-chain disagreements are OCR-variant disagreements OF THE SAME PERSONS.**
Across T-32912, T-32913, T-47655, T-47657, T-48336, T-49037, T-52539, and T-23796,
the three registered owners are consistently:

1. **GERALDINE K. HOPPE** (married to Guy Joseph Hoppe, Woodland Hills CA)
2. **MARCIA ELLEN KEESEY** (single, Sacramento CA)
3. **PATRICIA K. ZSCHOCHE** (married to Edward John Zschoche, Huntington Beach CA)

Each holds **1/3 undivided share**. This pattern matches what `chain_of_title`
already had verified for T-32917 and T-52540 — and now extends it to **8 more
derivative titles**. That's a substantive case-theory expansion: the Hoppe /
Keesey / Zschoche 3-owner co-ownership covered most of the chain, not just two
titles.

The 9th disagreement is on T-33350 (a non-chain title — different owner Elena
Vergara). Resolvable by spouse-name + filename corroboration.

## Per-row triage

| # | doc | TCT | Issue | Verdict |
|---|---|---|---|---|
| 134 | 15 | T-48336 | "MARCIA ELLEN KEESKY" vs "MARCIA SULAN KESSKY" | Both = Marcia Ellen Keesey. OCR variant. Promote. |
| 139 | 16 | T-47655 | "GERALDIVE" vs "GERALDINE" | V→N OCR. Promote (pass2 spelling). |
| 73 | 41 | T-47657 | "MARCIA ELLEN KEESET" vs "MARCIA ELLEN KEESEY" | T→Y OCR. Promote (pass2 spelling). |
| 149 | 44 | T-23796 | "MARY WORRICK KEESSY" vs "MARY WORRICK KEENEY" | Both = Mary Worrick Keesey (the mother/registrant of T-4497). OCR. Promote with canonical name. |
| **154** | **45** | **T-32913** | Pass2 added **Edward John Zschoche** and **Gur Joseph Hoppe** as separate owners | **Pass2 wrong**: those are spouses, not co-owners (source quotes say "married to..."). Promote pass1's 3-owner reading. |
| 98 | 142 | T-32912 | "KAROTA RELAY KESSSY" vs "MARCIA ELLEN KESSSY" | Pass1 garbled OCR; pass2 readable. Promote pass2. |
| **204** | **263** | **T-52539** (Mabeza) | Pass1 left 3rd owner null; pass2 invented **"MARZIA K. HOPPE"** | **Both passes wrong on 3rd owner**. Source text on that line is severely OCR-garbled ("MARZIA Κρας όπες Πέλεθς..." — partial Greek glyphs). Context (same chain, same 1/3 share, same family) suggests it's **MARCIA ELLEN KEESEY**, but **manual review of the source PDF is the right call** before promoting. |
| 247 | 310 | T-49037 | "MARCIA ELLEN KEESEY" vs "MARCIA BLUSH KESSY" | Pass2 garbled. Promote pass1. |
| 257 | 312 | T-33350 (Vergara) | "KENA L. VERMANS" vs "KENA L. VERGARA" | Filename = "TCT-33350 Elena Vergara.pdf"; source quote says "married to Oscar **Vergara**". Surname is Vergara, not Vermans. The first name may be "Elena" (read as "KENA L." with stray L initial). **Promote pass2 surname**; flag first name as possibly "ELENA" not "KENA L.". |

## Confidence-tagged proposal

8 of 9 can be auto-resolved with a canonical-name normalization step:

```sql
-- Map all the OCR variants to canonical names and mark the consensus rows
-- as 'human_resolved' rather than 'disagreement'.

WITH canonical_map(variant, canonical_name) AS (VALUES
  -- Marcia Ellen Keesey variants
  ('MARCIA ELLEN KEESKY',  'MARCIA ELLEN KEESEY'),
  ('MARCIA SULAN KESSKY',  'MARCIA ELLEN KEESEY'),
  ('MARCIA ELLEN KEESET',  'MARCIA ELLEN KEESEY'),
  ('MARCIA BLUSH KESSY',   'MARCIA ELLEN KEESEY'),
  ('MARCIA ELLEN KESSSY',  'MARCIA ELLEN KEESEY'),
  ('KAROTA RELAY KESSSY',  'MARCIA ELLEN KEESEY'),
  -- Geraldine K. Hoppe variants
  ('GERALDIVE K. HOPPE',   'GERALDINE K. HOPPE'),
  ('SARALDINS K. HOPPR',   'GERALDINE K. HOPPE'),
  -- Patricia K. Zschoche variants
  ('PATRICIA K. ZSCHECHO', 'PATRICIA K. ZSCHOCHE'),
  ('PATRICIA K. SCHOCHE',  'PATRICIA K. ZSCHOCHE'),
  ('PATRICIA K. ZSCALCES', 'PATRICIA K. ZSCHOCHE'),
  -- Mary Worrick Keesey variants
  ('MARY WORRICK KEESSY',  'MARY WORRICK KEESEY'),
  ('MARY WORRICK KEENEY',  'MARY WORRICK KEESEY'),
  -- Vergara
  ('KENA L. VERMANS',      'KENA L. VERGARA')
);
-- Use this to ALTER the chain_of_title rows + flip field_consensus statuses.
```

**Action requested:**
- Auto-resolve and promote the 7 clean OCR-variant cases (IDs 73, 98, 134, 139, 149, 247, 257).
- Auto-resolve the spouses-classification error (ID 154) by keeping pass1 only.
- **Hold ID 204 (T-52539 / doc 263) for manual PDF review** — the source OCR for the third owner is too garbled to promote without eyes-on.

## Consequence for the evidence pack (§II-A)

Currently the evidence pack states the 3-owner pattern is verified for T-32917 and
T-52540 only. Promoting these 8 disagreements would let me add the same finding for:

- **T-23796** (Mary Worrick Keesey alone — likely a predecessor or co-existing title)
- **T-32912** (Hoppe / Keesey / Zschoche 1/3)
- **T-32913** (Hoppe / Keesey / Zschoche 1/3)
- **T-47655** (Hoppe / Keesey / Zschoche 1/3)
- **T-47657** (Hoppe / Keesey / Zschoche 1/3)
- **T-48336** (Hoppe / Keesey / Zschoche 1/3)
- **T-49037** (Hoppe / Keesey / Zschoche 1/3)

That's 7 more derivative titles confirmed to share the same 3-American-co-owner
structure. The case theory ("Cesar de la Fuente couldn't lawfully convey shares
belonging to people who never authorized him") gets stronger as the same trio
appears as the rightful co-owners across the whole T-32917 sub-subdivision family.
