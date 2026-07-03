# Jurisprudence ingest record — the shared LandTek case-law library

Auditable, reproducible record of the Supreme Court decisions embedded into the shared law library
(`legal_authorities` + `legal_chunks` + `matter_authorities`). Each `batch*.json` is a manifest of
target cases with, per case: `gr`, `date`, `title`, `holding`, `forum`, and `links[]` (the matters +
elements it proves, with `relevance` and `note`). Fed to the verified ingest path:

```
python3 scripts/ingest_jurisprudence.py --file jurisprudence/batchN.json --status   # resolve + verify, no writes
python3 scripts/ingest_jurisprudence.py --file jurisprudence/batchN.json            # embed + link
```

## Discipline (why this is evidence-grade)
- **Verbatim from lawphil** (public-domain SC decisions); AnyCase is only the *finder* — its proprietary
  text is never embedded. See [[project-jurisprudence-ingest]].
- **G.R.-in-text verified** before embedding — a wrong/typo'd citation can never bind to the wrong decision.
- **Law is shared firm-wide; matter-LINKS respect client separation** (MWK / Paracale-Inocalla / NIBDC).

## Batches
| Batch | Theme | Matters served |
|---|---|---|
| 1 | Void agency/SPA, forged-deed / innocent-purchaser, accion reivindicatoria elements | MWK-CV26360, MWK-DLF-VOID |
| 2 | Ejectment/Summary Procedure, void donation (Art. 749, Mariano v. Naga ×2), just compensation/SAC, guardianship | MWK-CV26360, MWK-LGU-RECOVERY, MWK-CV6839, MWK-GUARDIANSHIP |
| 2b | Fix-ups (PDF-hosted lawphil recovery, e.g. Echanes) | MWK-CV26360, MWK-GUARDIANSHIP |
| 3 | Mining (RA 7942 / FPIC), direct-vs-collateral attack (Sec 48 PD 1529), double sale (Art 1544), forgery / notarized-deed rebuttal | NIBDC-EXPA/APSA, MWK-DLF-VOID, MWK-CV26360 |
| 4 | RA 11032 mandamus / duty-to-act (ARTA cluster), Register-of-Deeds ministerial duty, immutability + supplemental judgment, compel-surrender of owner's duplicate | 8× MWK-ARTA, PAR-CAPACUAN, MWK-TCT4497 |

## Status
Shared library grew 4 → 49 case authorities. Firm-wide coverage (steward gap-scan):
dark:20/thin:4/covered:4 → **dark:11/thin:11/covered:6**. Ongoing growth is autonomous via the weekly
**Jurisprudence Steward** (`scripts/jurisprudence_steward.py`, `landtek-jurisprudence-steward.timer`):
`--gap-scan` maintains the wishlist, `--harvest` pulls relevant new lawphil decisions. Doctrinal depth
for the remaining dark matters is assisted-AnyCase work (the finder needs a logged-in browser).

Rejects the verify-guard correctly refused (not embedded): pre-lawphil old cases (Navarro L-27402 1956-era,
RD-Pasig L-7261 1956) and occasional AnyCase wrong-year citations (Poblete 228620, Hocorma 267084) —
source from the SC e-library if ever needed.
