# PARACALE CORPUS TRACKER — keep the work products in sync with the corpus

> **Why:** the Paracale-001 corpus is **actively growing** — `ingest_drive_folder.py` / `ingest_paracale_drive.py` (deploy_686) sweep Drive folders into the matter (first sweep: **143 Shishir FB-export docs**; "more folders coming"). This tracker guarantees **no newly-ingested fact is missed** by the dossier / roster / briefs.
> **Baseline:** 361 Paracale-relevant docs manifested **2026-07-04** (`corpus_manifest.json`).
> **Tool:** `scripts/paracale_corpus_watch.py` (runs on the VPS — it needs the DB).

---

## HOW IT WORKS
Each run snapshots every Paracale doc (case_file = Paracale-001 **plus** NULL-case docs that mention Inocalla/Paracale/Casper/etc.), diffs against `corpus_manifest.json`, and for every **NEW** or **CHANGED** doc it auto-checks the text against the **open-items watchlist** below — telling you which matter question that doc might answer.

```bash
# on the VPS (/root/landtek):
python3 scripts/paracale_corpus_watch.py            # show what's new/changed since baseline (no write)
python3 scripts/paracale_corpus_watch.py --update   # show, then re-baseline (do this AFTER incorporating)
python3 scripts/paracale_corpus_watch.py --full     # dump the entire current inventory
```

## INCORPORATION PROTOCOL (the discipline)
1. **After any ingest sweep**, run the watch (no `--update`).
2. For each NEW/CHANGED doc with a `>>> MAY RESOLVE` hit, **read the doc** and fold the fact into the right work product:
   - provenance stays honest — corpus doc = `[V]` with the doc id; mark inference/operator otherwise.
3. Log it in the **Incorporation Log** below (date · doc ids · what changed).
4. **Then** run `--update` to re-baseline, so the next run only surfaces the next batch.
> Rule: **never `--update` before incorporating** — the update is what marks a doc "seen," so update only once its facts are in the dossier.

## OPEN-ITEMS WATCHLIST (what each new doc is auto-checked against)
Maps to the dossier / roster / briefs. Coverage = # of current docs that touch it (signal available to mine).

| Open item | Feeds | Coverage now |
|---|---|---|
| Undertaking notarization | dossier §5-G / act 7a-iii | 32* |
| DBP full-payment proof | §5-G / act 7a-ii | 14 |
| — payment/release specifically | §5-G | **2 — thin; the proof we need** |
| RD title status (DBP lots / old #s 4781/5941/4251/4695) | §5-G / act 7a-iv | 13 |
| **Melvin alive-vs-dead** | roster / §3 | **20 — mine these to resolve** |
| **"Heirs of Ereneo Agon" identity** | roster / §3 | **27 — mine these to identify** |
| Radj Gymson / Senen rep | roster / §3 | 7 |
| **Senen heirless proof (CENOMAR)** | §3 | **0 — gap, must obtain** |
| PSA death certificates | roster / §8 | 79 |
| Barangay conciliation / CFA | ejectment §6 | 22 |
| Estate tax / amnesty | §11 | 8 |
| Partition docket 5625/5626 | §4 | 21 |
| Heir SPA / consent / waiver | §3 / §7 | 20 |
| Ace / Bombita / ejectment fronts | §6 | 47 |
| Mineral rights / MPSA / APSA | §6-B | 154 |
| Manila building / TCT 44055 | §6 Front 1B | 44 |
*(*"notarization" keyword is broad — most hits are unrelated notarial blocks; treat as a prompt to check, not a match.)*

## WHAT THE FRESH INGEST ALREADY UNLOCKS
The deploy_686 sweep means several open flags now have corpus signal to resolve **from documents, not just operator memory**:
- **Ereneo Agon (27 docs)** and **Melvin (20 docs)** — enough to likely identify the Agon branch and settle Melvin alive-vs-dead by reading.
- **79 death-certificate hits / 20 SPA-consent hits** — likely contain second-generation heir names for the roster.
- Still genuinely **absent**: Senen's CENOMAR (0), and a clean DBP release/full-payment certificate (2 weak hits) — these must be **obtained**, not mined.
> ⏭ Next incorporation pass: mine the newly-ingested docs for the Agon/Melvin/heir-name flags and update `INOCALLA_HEIR_ROSTER.md`.

## INCORPORATION LOG
| Date | Docs reviewed | Incorporated into | By |
|---|---|---|---|
| 2026-07-04 | baseline of 361 docs established | tracker created; dossier/roster/briefs reflect corpus through this date | — |
| _(next)_ | mine 143 FB-export docs for Agon/Melvin/heir names | INOCALLA_HEIR_ROSTER.md §3 | — |

---
*Companion: `INOCALLA_SPECIAL_ADMIN_DOSSIER.md`, `INOCALLA_HEIR_ROSTER.md`. Tool: `scripts/paracale_corpus_watch.py`. Baseline: `corpus_manifest.json`.*
