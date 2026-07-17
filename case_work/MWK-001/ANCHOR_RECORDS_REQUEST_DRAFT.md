# DRAFT — Records request for survey anchor data (MWK Mercedes parcels)

> **Status: DRAFT — held for Jonathan's review. Not sent.** Purpose: obtain the geodetic
> anchor data that converts our survey-exact parcel shapes from "approximately placed" to
> "survey-grade placed" on the map. One item (the BLLM No. 2 coordinate) anchors *every*
> MWK parcel tied to it in Mercedes.
>
> Follows up the PENRO inquiry already on file (corpus doc 894, 3 Sept 2025).

## Why this is needed (plain terms)
We have reconstructed the **exact metes-and-bounds** of the parcels from the titles —
e.g. the Balane lot (TCT 079-2021002126, Lot 2-X-6-I-4-C-1) computes to 2,586.8 m² and
closes to 1 cm, corroborated across 5 registry copies. What we lack is the **absolute
ground position**: the title fixes corner 1 as *"N. 07°52′ W, 251.99 m from BLLM No. 2,
Municipality of Mercedes."* The coordinate of **BLLM No. 2** (a Bureau of Lands Location
Monument) is a government geodetic record, not in our documents — with it, the whole
survey lands precisely on the map.

## Recipients (as applicable)
- **DENR – Land Management Bureau, Region V** (geodetic/cadastral records)
- **PENRO / CENRO, Camarines Norte** (local survey returns) — *ref: our 3 Sept 2025 inquiry*
- **DENR – NAMRIA** (geodetic control point coordinates)
- **Registry of Deeds / LRA** (approved subdivision plan copies)

## Records requested
1. **Lot Data Computation (LDC) / survey returns** for subdivision plan **(LRA) PSD-E2020005406**
   — the sheet listing each corner's **PRS92 grid coordinates (Northing/Easting)** for
   **Lot 2-X-6-I-4-C-1** and **Lot 2-X-6-I-4-C-2**. *(These corner coordinates georeference
   the parcel directly — no tie-line computation needed — and cross-check our reconstructed shape.)*
2. **Geodetic coordinate of BLLM No. 2, Municipality of Mercedes, Camarines Norte** — the tie
   point of record (PRS92 Northing/Easting and/or geographic lat/long, with datum + zone).
3. **Approved survey plan (approved blueprint)** for **PSD-E2020005406** and its parent
   **PSD-05-026197**, and any **isolated/relocation survey plan** on file for these lots.
4. *(If available)* The **cadastral map / projection** covering **Barangay San Roque, Mercedes**,
   showing the monument network (BLLM Nos.) referenced by these titles.
5. **The PRS92 grid coordinates of Cadastral Lots 401, 403, and 405, Cad 118-D, Mercedes Cadastre.**
   Per your Office's letter **LMS-25-550 (26 November 2025)**, Lot 2-A, (LRA) Psd-221861 (TCT T-32911,
   8,706 m²) was *projected in your records* as encompassing these three cadastral lots. Their cadastral
   coordinates georeference Lot 2-A directly and are the authoritative basis for resolving the technical-
   record overlap between the Psd-221861 plan and the Cad 118-D cadastre.

**Correlation established from your own records (for reference):**

| LRA plan lot | Title | Area (m²) | DENR cadastral projection (Cad 118-D) |
|---|---|---|---|
| Lot 2-A, Psd-221861 | TCT T-32911 | 8,706 | Lots 401 + 403 + 405 |

*This lot -> title -> cadastral-lot correlation is what independently corroborates each MWK parcel; the
cadastral coordinates above resolve both the mapping and the overlap question in a single step.*

## What we will do with it (internal note — not part of the request)
- LDC corner coordinates → convert **PRS92 → WGS84** → exact survey-tier placement on the client map.
- BLLM No. 2 coordinate → apply the recorded tie line → same result, and reusable for **all**
  Mercedes parcels tied to BLLM No. 2 (the whole MWK Mercedes portfolio in one shot).
- Either arriving as a coordinate: paste into the mapping tool's **monument mode** → done.

## Priority parcels (Mercedes / T-4497 family, tie point BLLM No. 2 where noted)
| Title | Lot / plan | Status in our system |
|---|---|---|
| 079-2021002126 | Lot 2-X-6-I-4-C-1 (PSD-E2020005406) | survey shape built, awaiting anchor |
| T-4497 family (T-47656, T-33776, T-36668, …) | subdivision lots, San Roque/Brgy 3 | survey shapes built, awaiting anchors |
