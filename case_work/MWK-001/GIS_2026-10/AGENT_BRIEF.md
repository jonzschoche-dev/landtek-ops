# Brief: transcribe Lot 2-X title technical descriptions (vision) for mapping

Folder: `case_work/MWK-001/GIS_2026-10/` (call it GIS/). Read `sp2156_courses.json` first: it is the worked example and the exact output format.

## For each title assigned to you
1. Fetch and render the scan: `GIS/fetch_render.sh <drive_file_id> <TITLE>_d<doc>` → PNG pages in `GIS/scans/<name>/`. Read the pages with the Read tool (they are images). The technical description starts on the face ("A parcel of land (Lot …)") and usually continues on the back page ("Beginning at a point marked "1" … thence …"). Some continue onto page 3.
2. Transcribe EXACTLY what is printed:
   - lot, plan (e.g. Psd-051607-014971), parent lot/plan as stated;
   - the tie: bearing + distance from the monument to corner 1, and the monument's exact wording (e.g. "BLLM No. 2, Bo. of Mercedes" or "BLM No. 2, Municipality of Mercedes / Pls-677-D");
   - every course in order as ["N"|"S", deg, min, "E"|"W", distance];
   - stated area (sq m); survey line (date, geodetic engineer, approval date) if given.
   If a glyph is hard to read, re-render that region bigger on the VPS (PyMuPDF: `page.get_pixmap(dpi=400, clip=fitz.Rect(...))`, file is `/tmp/x2/<name>/src`) and read it again.
3. Check: `python3 GIS/ring_tools.py GIS/batch_<X>.json <TITLE>` — closure must be < 1 m and area within 1% of stated.
4. If it does not close: first re-read the scan. Only if a single candidate fix printed by ring_tools both closes and matches the area AND is corroborated (the scan is genuinely ambiguous at that spot, or another certified title prints the same shared course differently) may you apply it — and you must record it under `"corrections": [{"course":..., "title_reads":..., "used":..., "why":...}]`. Never invent values. If nothing corroborated closes it, move the entry to a key prefixed `_held_` with a `"hold_reason"`.
5. Add containment hints where the parent or a child is known (these are checked later, never assumed):
   - `"inside": ["MWK-T-38838"]` (centroid must be inside that already-mapped parcel) — mapped parcel codes are `MWK-<title>` e.g. MWK-T-38838, MWK-T-52540, MWK-T-47656, MWK-T-48336, MWK-T-47655, MWK-T-52536, MWK-BALANE, MWK-PSD221861-X;
   - for lots in the 2-X-1 / Pcs-051607-000932 / Lot 2-M,2-Q,2-R area or any lot tied to the 1975 barrio monument, set `"monument_key": "auto"` and `"inside_any": [...]` with the plausible 1975 parent lots (e.g. MWK-PSD221861-X, -M, -Q, -R).
6. Keys are the title number exactly as in the brief (e.g. "T-49061", "079-2021002127"). Include `src_doc`, `src_page`.

## Rules
- Output ONLY to `GIS/batch_<X>.json` (your batch letter). Do not edit any other file, do not write to the database, do not commit, do not send anything.
- Certified copies only; if a doc turns out not to be the title (e.g. a request form), say so and skip it.
- Report back: a table of each title → lot, closure, area check, PLOTTABLE / HELD (reason), and any corrections with their corroboration.
