# LandTek Mapping Division — GIS corpus

Spatial reference data for the LandTek matters. Self-contained: every dataset
here can be rebuilt from its source file by the scripts in `tools/`, and
verified by `tools/verify_dataset.py`.

## Layout

```
gis/
├── README.md                      you are here
├── MANIFEST.json                  machine-readable dataset registry
├── datasets/
│   └── ph-tiepoints-camarines-norte/
│       ├── DATASET.md             datasheet: provenance, method, caveats
│       ├── VERSION                1.0.0
│       ├── CHECKSUMS.sha256       sha256 of every file below
│       ├── data/                  GeoPackage + GeoJSON (the canonical layers)
│       ├── exports/               CSV, KMZ, KML (derived, disposable)
│       ├── project/               QGIS project
│       └── source/                raw harvest, exactly as pulled
├── schema/
│   ├── tiepoints.schema.json      JSON Schema for a tie point record
│   ├── monument_types.csv         controlled vocabulary
│   └── lgu_psgc_camarines_norte.csv   LGU ↔ PSGC, with source spellings
├── maps/
│   └── cn_tiepoints_atlas_v1.0.0.pdf   38-page atlas: overview, 12 LGU sheets, appendices A–G
├── sql/
│   └── 001_gis_tiepoints.sql      Postgres DDL, views, provenance columns
└── tools/
    ├── harvest_tiepoints.py       pull from the Geoportal service
    ├── build_dataset.py           classify, reproject, emit layers
    ├── make_qgis_project.py       generate the .qgz
    ├── make_kmz.py                generate the Google Earth KMZ
    ├── verify_dataset.py          10-check verification suite
    ├── load_to_postgres.py        idempotent upsert into the corpus DB
    └── atlas/                     builds maps/ — see atlas/README.md
```

**The rule for this tree:** `data/` and `source/` are canonical, `exports/` and
`project/` are derived. If they ever disagree, rebuild the derived side rather
than editing it.

## Datasets

| id | records | coverage | version | provenance |
|---|---:|---|---|---|
| `ph-tiepoints-camarines-norte` | 1,076 | all 12 LGUs of Camarines Norte | 1.0.0 | `inferred_strong` |

## Maps

`maps/cn_tiepoints_atlas_v1.0.0.pdf` is the field and desk reference for any mapping work in the
province: a 1:100,000 overview, one sheet per LGU with every monument labelled, a WGS84 graticule over
the PTM grid on every sheet, and appendices covering boundary QA, the survey project index, PRS92
control, PAGeNet CORS, reference-system parameters, and a full gazetteer in PTM, WGS84 and UTM 51N.
Rebuild with `tools/atlas/run_all.sh`.

## Provenance discipline

Everything here enters the corpus as **`inferred_strong`**, never `verified`.

The source is a government service and the coordinates are internally
consistent to millimetres, but it publishes *positions only* — no monument
description, no recovery status, no certification, no accuracy order. Under
the corpus rules that is not a verified fact.

`sql/001_gis_tiepoints.sql` enforces this structurally:

- `gis_tiepoints_safe` returns only rows promoted to `verified`. **It is empty
  on a fresh load.** That is correct. Legal output reads this view and nothing
  else.
- `gis_tiepoints_reference` returns everything else with a
  `verification_notice` column attached in-band, so the caveat travels with the
  row and cannot be silently dropped into a brief.
- A row cannot be promoted to `verified` without `verified_source_doc` and
  `verified_excerpt` — a CHECK constraint refuses it.
- Re-harvesting never demotes verified work: the upsert leaves
  `provenance_level` and the `verified_*` columns alone.

To promote a monument, obtain the DENR-LMB certified monument description, file
the PDF in the document corpus, then set the three `verified_*` columns
together with the doc id and a quoted excerpt.

## Quick start

```bash
# load into the corpus DB
python3 tools/load_to_postgres.py                      # dry run
python3 tools/load_to_postgres.py --apply --dsn "$PG_DSN"

# check nothing has drifted
python3 tools/verify_dataset.py

# rebuild everything from the raw harvest
python3 tools/build_dataset.py
python3 tools/make_qgis_project.py
python3 tools/make_kmz.py

# extend to another province
python3 tools/harvest_tiepoints.py --list-provinces
python3 tools/harvest_tiepoints.py "CAMARINES SUR"
```

Dependencies: `pyproj`, `requests`, `psycopg2` (loader only), and GDAL's
`ogr2ogr` on PATH for the GeoPackage step.

## Adding a dataset

1. `datasets/<id>/` with the same five subfolders.
2. A `DATASET.md` that states the source, the method, the datum, and what the
   data does *not* contain.
3. Regenerate `CHECKSUMS.sha256` and add the entry to `MANIFEST.json`.
4. Extend `verify_dataset.py` with whatever check would have caught the most
   likely way that dataset could be wrong.

That last point is the one that matters. For the tie points it was the datum:
the source never states it, and getting it wrong displaces everything by 217 m
while looking entirely plausible. Find the equivalent trap in the new data and
write the check first.
