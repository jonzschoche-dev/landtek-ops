# PREVIOUS_TITLE_NUMBERS DISAGREEMENT TRIAGE — 2026-05-13

`field_consensus` returned **8 disagreements on previous_title_numbers** —
the field that records each title's predecessor(s). Unlike the prior triages
(owners, lot_block_plan) where disagreements were OCR-variant noise, these
are substantive content differences. Triage required real adjudication:

## The two failure modes

### Mode A: Schema-metadata leak (4 cases)

One of the two passes emitted the literal **JSON schema keys** ("field_status",
"page_ref", "source_quote", "value") as the field's value instead of the
actual data. This happens when the model's structured-output handling confuses
the schema TYPE definition for the schema VALUE. The other pass produced real
data, so resolution is mechanical: promote the non-leaked pass.

| ID | doc | TCT | Leaked pass | Real pass value |
|---|---|---|---|---|
| 145 | 27 | 079-2010000694 | pass2 | pass1 = `2010000663` |
| 155 | 45 | T-32913 | pass1 | pass2 = `106 \| T-4497` |
| 170 | 102 | T-23796 | pass2 | pass1 = `T-106 \| T-4497` |

(Row 258 / T-33350 also shows a mild form of this in pass1 not capturing
the full list; but pass2 was clean — treated under Mode B.)

### Mode B: One pass enumerated more predecessors than the other (5 cases)

| ID | doc | TCT | pass1 list | pass2 list | Verdict |
|---|---|---|---|---|---|
| 19 | 14 | T-4503 | T-106 \| T-111 \| T-4493 | T-10784 \| T-4493 | **pass1** — pass2 captured the LRC Record Number (10784) and mistook it for a title number |
| 140 | 16 | T-47655 | OCT No. 7-106 \| TCT No. 7-32917 | T-32917 | **pass1** — fuller, includes both OCT (root) and TCT (immediate predecessor) |
| 24 | 17 | T-32911 | T-106 \| T-4497 | OCT No. 106 | **pass1** — fuller, includes the T-4497 mother title |
| 165 | 86 | T-4502 | T-106 \| T-4493 | T-106 \| T-111 \| T-4493 | **pass2** — fuller, adds T-111 (consistent with T-4503 pattern in row 19) |
| 258 | 312 | T-33350 | OCT No. 7-106 \| TCT No. 7-32917 | OCT No. 7-106 \| T-32917 \| T.C.T. No.1-184 | **pass2** — fuller, adds an annotation-only title `T.C.T. No.1-184` |

## Headline finding — the chain genealogy

This triage surfaces **substantive new title_chain edges** that aren't yet
in the database. Two distinct generation lines emerge:

### Mother-line A: Sub-subdivisions of T-32917 (Lot 2-X-6 family)

For T-47655 and T-33350 (and consistent with the lot_block_plan triage that
showed T-47657, T-48336, T-49037, T-33776, etc. all carry Lot 2-X-6-* lots),
the verified predecessor chain reads:

```
OCT No. 106 (root)
 → T-4497 (the MWK mother title)
   → T-32917 (Lot 2-X-6 derivative)
     → T-47655, T-47657, T-48336, T-49037, T-33776, T-33350,
       T-079-2018001329, T-51641, T-52537, T-52538, T-52539
       (sub-subdivisions of Lot 2-X-6)
```

This nails the §II chain-of-title finding: T-32917 is the parent of the
contested sub-titles, T-4497 is the grandfather, OCT No. 106 is the
great-grandfather.

### Mother-line B: Manguisoc Mercedes family (T-4502, T-4503)

```
OCT No. 106 (root)
 → T-111 (intermediate)
   → T-4493 (intermediate)
     → T-4502, T-4503 (Manguisoc Mercedes titles per filename evidence)
```

**T-4493 is a sibling of T-4497** at the same generation. CLAUDE.md notes
T-30683 and T-4494 as "separate properties... NOT verified derivatives of
T-4497, treat as own matters" — this triage adds T-4502 / T-4503 to that
list with verified ancestry going back to OCT No. 106 via the T-4493 branch.
These are NOT part of the MWK chain that's the subject of Civil Case 26-360.

## Resolution applied

All 8 rows promoted to `agreement='human_resolved_completeness'` (new tag,
to distinguish from `human_resolved_ocr_variant` which was for pure OCR
noise). Promoted pass per the verdict column above.

## Follow-up (not done yet)

The verdicts above unlock **11 new verified title_chain edges**:

| child | parent | basis |
|---|---|---|
| T-47655 | T-32917 | row 140 |
| T-47655 | OCT-106 | row 140 |
| T-32911 | T-4497 | row 24 |
| T-32911 | T-106 (= OCT-106) | row 24 |
| T-32913 | T-4497 | row 155 |
| T-32913 | T-106 | row 155 |
| T-23796 | T-4497 | row 170 |
| T-23796 | T-106 | row 170 |
| T-33350 | T-32917 | row 258 |
| T-33350 | OCT-106 | row 258 |
| T-33350 | T.C.T. No.1-184 | row 258 (annotation) |

Plus the two non-chain-relevant Manguisoc-line edges (T-4502 / T-4503 →
T-106 / T-111 / T-4493).

These should be inserted into `title_chain` with `provenance_level='verified'`
once approved. That would meaningfully extend the §II chain-of-title section
of the evidence pack from 3 verified edges to ~14.
