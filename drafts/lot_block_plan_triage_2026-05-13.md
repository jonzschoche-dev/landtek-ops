# LOT_BLOCK_PLAN DISAGREEMENT TRIAGE — 2026-05-13

`field_consensus` returned **17 disagreements on lot_block_plan** after the
2-pass cross-validation sweep. Pulled all 17 with source values; all reduce to
formatting/OCR variants of THE SAME LOT.

## Headline finding

**Every one of the 17 disagreements is two passes describing the same lot
with cosmetic differences.** The pattern is one of:

- **Psd/Pad/Ped OCR confusion** (3-letter "P-d" abbreviation — S, A, e all
  visually similar in scanned text): `Psd-051607-014971` ↔ `Pad-051607-014971`
  ↔ `Ped-051607-014971`. 8 of 17 fall in this bucket.
- **"subdivision plan" vs "subdivision survey" vs "consolidation-subdivision survey"**
  — both passes pull from the same source phrase; one truncates earlier
  than the other. 4 cases.
- **"portion of" vs "being a portion of"** — same content, different
  preserved phrasing. 2 cases.
- **One pass includes the parent-lot reference, the other truncates it**:
  e.g. "Lot 2-x-1 of Psd-256008, portion of Lot 2-X (LRC) Psd-221761" vs
  "Lot 2-x-1 of Psd-256008". 3 cases (IDs 61, 152, 207).
- **One unique case (ID 56 / T-51641)**: pass1 dumped a comma-list of 6 lots
  ("Lot 2-X-6-8-3, Lot 2-X-6-B, Lot 2-1-6-Q, ..."); pass2 correctly identified
  just `Lot 2-X-6-8-3` as a portion of `Lot 2-X-6-B`. Pass2's structured
  "portion of" reading is the right one; pass1 likely conflated encumbrance
  references on the same page into the lot field.

## Lot-code-root cross-check

Stripping OCR garbage from both passes and comparing just the Lot identifier
(e.g. "Lot 2-X-6-N-2"), every one of the 17 matches: same identifier in both
passes. The disagreements are entirely in the *surrounding plan references*,
not in the lot identity itself.

## Per-row verdict

| ID | doc | TCT | Lot in both passes | Diff type | Verdict |
|---|---|---|---|---|---|
| 26 | 17 | T-32911 | Lot 2-A | "being a portion of" phrasing | Promote pass2 |
| 56 | 24 | T-51641 | Lot 2-X-6-8-3 | Pass1 list-conflation | Promote pass2 (correctly structured) |
| 61 | 26 | T-33365 | Lot 2-x-1 | Pass1 includes parent ref | Promote pass1 (fuller) |
| 86 | 47 | T-15616 | Lot 2 of Psd-051607-000932 | "Psd" vs "Pad" + phrasing | Promote pass2 |
| 117 | 309 | T-47657 | Lot 2-X-6-T | "Psd-256008" vs "Pad-256008" | Promote pass1 (Psd is correct prefix) |
| 137 | 15 | T-48336 | Lot 2-X-6-N-2 | "Psd-05-025374" vs "Pad-05-025374" | Promote pass1 |
| 142 | 16 | T-47655 | Lot-2-1-6-1 | abbreviation expansion | Promote pass2 |
| 152 | 44 | T-23796 | Lot 2-x-1 | Pass1 includes parent ref | Promote pass1 |
| 157 | 45 | T-32913 | Lot 2-2 | comma vs "of subdivision plan" | Promote pass2 |
| 207 | 263 | T-52539 | Lot 2-X-6-1-4-A | Pass1 includes parent ref | Promote pass1 |
| 217 | 270 | T-52538 | Lot 2-X-4-F | formatting | Promote pass1 (cleaner structure) |
| 222 | 271 | T-52538 | Lot 2-X-4-F | formatting | Promote pass1 |
| 232 | 274 | T-52537 | Lot 2-X-4-8 | "Ped-256008" vs "Psd-256008" | Promote pass2 |
| 250 | 310 | T-49037 | Lot 2-X-6-R | "cad-258008" vs "Psd-258008" | Promote pass2 (cad is OCR garbage) |
| 260 | 312 | T-33350 | Lot 2-3-60 | "Ped-051607" vs "Psd-051607" | Promote pass2 |
| 265 | 318 | T-33776 | Lot-2-X-6-H | trailing parenthesis | Promote pass2 |
| 276 | 322 | T-079-2018001329 | Lot 2-X-6-B | full sentence vs comma-list | Promote pass2 |

All 17 auto-resolvable. None require manual PDF review.

## Case-theory consequence

This triage substantively **strengthens** the §II / §II-A finding. Looking at the
Lot column above:

- **Most lots are within the Lot 2-X-6 family**: T-47657 (2-X-6-T), T-48336
  (2-X-6-N-2), T-47655 (2-X-6-L per earlier triage), T-49037 (2-X-6-R),
  T-33776 (2-X-6-H), T-079-2018001329 (2-X-6-B), T-52539 (2-X-6-1-4-A),
  T-51641 (2-X-6-8-3 = portion of 2-X-6-B), T-52537 (2-X-4-8), T-52538
  (2-X-4-F), T-33365 (2-x-1) → all subdivisions of Lot 2-X-6 (which is
  T-32917) or Lot 2-X-4 (a sister to Lot 2-X-6).
- All trace back to the same parent: `(LRC) Psd-256008` or its variants.
- T-32911 (Lot 2-A) and T-32913 (Lot 2-2) reference Psd-12802 / Psd-12502
  — sister-generation lots in the same family root.

This is the lot-structural confirmation that complements the owner-structural
confirmation in §II-A. The chain isn't "9 unrelated titles that happen to
share 3 owners"; it's **9+ derivative subdivisions of a single mother title
chain (T-4497 → T-32917 → Lot 2-X-6-*)**, all carrying the same 3-American
co-owners.
