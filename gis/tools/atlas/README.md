# Tie point atlas builder

Builds `maps/cn_tiepoints_atlas_v1.0.0.pdf` from the `ph-tiepoints-camarines-norte` dataset.

```bash
pip install geopandas contextily adjustText pyproj reportlab pypdf
# plus ghostscript (gs) on PATH
./run_all.sh            # -> build/cn_tiepoints_atlas_v1.0.0.pdf
```

| Script | Produces |
|---|---|
| `qa_boundaries.py` | `inputs/lgu_check.csv` — every point tested against its LGU polygon |
| `sheet_overview.py` | Sheet 1, province overview, 1:100,000 on 1350 × 840 mm |
| `sheet_detail.py "<LGU>"` | Sheets 2–13, one per LGU; A1, or A0 when A1 would force coarser than 1:50,000 |
| `appendix.py` | Appendices A–G on A3 |
| `merge.py` | Combined PDF with bookmarks |
| `atlas_common.py` | Symbology, PTM grid, WGS84 graticule, scale bar, north arrow |

**Inputs.** `inputs/region_adm3.gpkg` is geoBoundaries PHL ADM3 (NAMRIA / PSA / OCHA, 2020 boundaries,
CC BY 3.0 IGO), clipped to the Camarines Norte region. Administrative limits — not cadastral.
Basemaps are fetched at build time from Esri (World Light Gray Canvas, World Topographic Map).

**Colour.** Three categorical slots validated all-pairs for colour-vision deficiency (blue / orange /
aqua) carry the monument *family*; marker shape carries the class. Aqua sits below 3:1 contrast on white,
so every marker has a dark outline and the detail sheets label every point.

**Grids.** Every sheet is drawn in PRS92 / PTM Zone IV (EPSG:3124) with the PTM grid labelled bottom and
left. A WGS84 lat/lon graticule is overlaid, labelled top and right, so GPS readings can be plotted by eye.
