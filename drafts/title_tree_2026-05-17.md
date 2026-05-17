# Title Tree — MWK-001 (clean, phantom-filtered)

_94 normalized edges across 71 unique titles. Phantom T-YYYY (years) and T-NNN-NN... (tax PINs) filtered. Contested titles flagged inline._

## TRACK A — T-4497 / OCT T-106 Lineage (CV-26-360 theatre)

```
OCT T-106
    ├── T-079-2018001329
    ├── T-079-2021002127  [⚠ Issued from same cancelled mother T-52540]
    ├── T-111
    │   ├── T-30681
    │   ├── T-30683
    │   ├── T-32478
    │   ├── T-4493
    │   │   ├── T-14785
    │   │   ├── T-4502
    │   │   └── T-4503
    │   ├── T-4502 _(cycle detected, skipping)_
    │   └── T-4503 _(cycle detected, skipping)_
    ├── T-23796
    │   └── T-33365
    │       └── T-15616
    ├── T-30683 _(cycle detected, skipping)_
    ├── T-32911
    │   └── T-49037
    │       ├── T-51639
    │       └── T-51641
    ├── T-32913
    ├── T-32914
    ├── T-33350
    ├── T-33365 _(cycle detected, skipping)_
    ├── T-33776
    ├── T-36668
    ├── T-38838
    ├── T-4497
    │   ├── T-23796 _(cycle detected, skipping)_
    │   ├── T-31298
    │   ├── T-32911 _(cycle detected, skipping)_
    │   ├── T-32912
    │   │   └── T-15616 _(cycle detected, skipping)_
    │   ├── T-32913 _(cycle detected, skipping)_
    │   ├── T-32914 _(cycle detected, skipping)_
    │   ├── T-32917
    │   │   ├── T-147652
    │   │   ├── T-33350 _(cycle detected, skipping)_
    │   │   ├── T-33415
    │   │   ├── T-33776 _(cycle detected, skipping)_
    │   │   ├── T-38838 _(cycle detected, skipping)_
    │   │   ├── T-46038
    │   │   ├── T-47655
    │   │   ├── T-47656
    │   │   │   ├── T-47657
    │   │   │   │   └── T-69404
    │   │   │   └── T-48336
    │   │   ├── T-47657 _(cycle detected, skipping)_
    │   │   ├── T-52354
    │   │   └── T-52540  [⚠ Cancelled 2021 to issue Balane T-079 — CV-26-360 contesting cancellation]
    │   │       ├── T-079-2021002126  [⚠ Balane title — VOID per CV-26-360 theory (issued from 2016 void deed)]
    │   │       └── T-079-2021002127 _(cycle detected, skipping)_
    │   ├── T-33365 _(cycle detected, skipping)_
    │   ├── T-33415 _(cycle detected, skipping)_
    │   ├── T-33686
    │   ├── T-33776 _(cycle detected, skipping)_
    │   ├── T-34243
    │   ├── T-40718
    │   ├── T-45964
    │   ├── T-48335
    │   └── T-51640
    ├── T-4502 _(cycle detected, skipping)_
    ├── T-4503 _(cycle detected, skipping)_
    ├── T-45964 _(cycle detected, skipping)_
    ├── T-46038 _(cycle detected, skipping)_
    ├── T-47655 _(cycle detected, skipping)_
    ├── T-47657 _(cycle detected, skipping)_
    ├── T-51641 _(cycle detected, skipping)_
    ├── T-52537
    └── T-52538
```

## TRACK B — CARP / CV-6839 Lineage (Just-compensation track)

_The 8 CARP titles per CLAUDE.md context. These are typically standalone parcels under DAR/LBP proceedings, not a single lineage — but if any have parent/child structure in the DB, it'll appear here._

- **T-14** — no lineage data in DB (no parent, no derivatives)
- **T-4494** — no lineage data in DB (no parent, no derivatives)
### T-4501
```
T-4501
    └── T-30683
```

### T-4502
```
   (parent(s): OCT T-106, T-111, T-4493)
T-4502  _(no derivatives in DB)_
```

### T-4503
```
   (parent(s): OCT T-106, T-10784, T-111, T-4493)
T-4503  _(no derivatives in DB)_
```

### T-30681
```
   (parent(s): T-111)
T-30681  _(no derivatives in DB)_
```

### T-30682
```
T-30682
    └── T-32478
```

### T-30683
```
   (parent(s): OCT T-106, T-111, T-4501)
T-30683  _(no derivatives in DB)_
```


## ORPHANED TITLES

_Titles that appear as derivatives (children) elsewhere but have NO parent in the normalized edges. Either the parent was a phantom/typo we filtered, or the data has gaps._

- T-079
- T-33416
- T-33681
- T-4504
- T-46460
- T-49060
- T-772

## DATA COVERAGE

- **334** distinct title-IDs pass the real-title filter
- **49** distinct phantom/tax-PIN/typo IDs rejected (see top below)

**Top 10 phantom IDs (rejected):**
  - `T-0966698` (×8) — year-pattern or unrecognized format
  - `T-2021002` (×7) — year-pattern or unrecognized format
  - `T-0966-698` (×4) — year-pattern or unrecognized format
  - `T-2023-02` (×3) — year-pattern or unrecognized format
  - `T-1035055` (×3) — year-pattern or unrecognized format
  - `T-2023-05` (×3) — year-pattern or unrecognized format
  - `T-2022-12` (×2) — year-pattern or unrecognized format
  - `T-2018001` (×2) — year-pattern or unrecognized format
  - `T-1035932` (×2) — year-pattern or unrecognized format
  - `T-2022-11` (×2) — year-pattern or unrecognized format