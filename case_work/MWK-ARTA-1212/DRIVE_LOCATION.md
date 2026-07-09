# ARTA-1212 deliverable PDFs — Drive-canonical location (offloaded 2026-07-09)

The stamped/bound PDFs for this matter are **Drive-canonical** (kept out of git per policy). They now
live in Jonathan's own Drive (`jonathan@hayuma.org`, owner-quota), synced via Google Drive Desktop:

```
My Drive / LANDTEK / 01 - Clients / Heirs of Mary Worrick Keesey- LTC-002 /
  Correspondence / 2026 / ARTA 1212 Manifestation + Annexes A-I (Jul 2026) /
```

Contents (18 PDFs, ~30 MB): the bound **Annexes A–I** deliverable (8.5×13) + `stamped/` (Annex A–I,
no G — no standalone scan) + `source/` (raw pulls) + `candidates/` (CART Res. No. 03). Local working
copies remain under this dir's `annexes/{stamped,source,candidates}/` (gitignored); `_scratch/` was not
offloaded (un-trimmed working intermediates, regenerable).

**How it was offloaded — and why NOT via the service account:** copied into the `drive_local` mount
(Jonathan's Drive). The `drive_offload.py` / SA path does **not** work for new files — a Google
Service Account has **zero storage quota**, so any SA upload to the shared LANDTEK folder returns
`403 storageQuotaExceeded`. Owner-quota upload (the Drive Desktop mount, or OAuth delegation, or a
Shared Drive) is the only path that works for fresh files. See `[[feedback-drive-canonical-storage]]`.

Lost a PDF? Regenerate from the committed recipe (`annexes/{stamp_annexes,build_bound,finalize_8x13}.py`
+ `INDEX_OF_ANNEXES.md`) against the corpus.
