-- deploy_687: geometry_priority — the drip queue for stripping plot geometry from the corpus.
--
-- The geometry-intake pipeline (geometry_pipeline.py) drains this worst-rank-first: for each
-- doc NOT yet re-OCR'd (reocr_log), it runs reocr_gemini.reocr() to replace garbled OCR with
-- faithful text (bearings preserved), then strip_plot_info converts the now-clean technical
-- description into a `parcels` shape. Bounded per run + stops cleanly on Gemini QuotaExhausted,
-- so it drains a few pages/day within the free tier.
--
-- Seeded with the MWK-BALANE chain (Civil Case 26-360): the subdivision plan + the mother/
-- derivative titles T-4497 -> T-32917 -> T-52540. NB: Balane's OWN lot title (T-079-2021002126,
-- Lot 2-X-6-I-4-C-1) is NOT in the corpus yet (awaiting the RD Daet CTC) — so we plot the chain
-- parents now and add Balane's lot when its CTC lands. Matter separation holds: only MWK titles.

CREATE TABLE IF NOT EXISTS geometry_priority (
    doc_id      INTEGER PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    title_no    TEXT,
    matter_code TEXT,
    rank        INTEGER NOT NULL DEFAULT 100,   -- lower = processed first
    note        TEXT,
    added_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed the Balane chain. INSERT ... SELECT so a stale doc_id (id absent) is skipped, never a
-- broken FK. rank: plan first (best geometry), then closest-to-Balane title outward.
INSERT INTO geometry_priority (doc_id, title_no, matter_code, rank, note)
SELECT v.doc_id, v.title_no, 'MWK-001', v.rank, v.note
FROM (VALUES
    (287, 'subdivision-plan', 10, 'Subdivision plan Mary Worrick Keesey (2021) — lot layout, has local file'),
    (104, 'title-plan',       15, 'MWK title plan (1975)'),
    (96,  'T-52540',          20, 'T-52540 certified copy — Balane parent title'),
    (48,  'T-52540',          25, 'T-52540 cancelled/fraud copy'),
    (21,  'T-32917',          30, 'T-32917 (Lot 2-X-6) — mid chain'),
    (1140,'T-32917',          32, 'T-32917 Heirs of MWK LOT 2-x-6'),
    (348, 'T-4497',           40, 'T-4497 Certified True Copy — mother title'),
    (39,  'T-4497',           42, 'T-4497 heirs')
) AS v(doc_id, title_no, rank, note)
WHERE EXISTS (SELECT 1 FROM documents d WHERE d.id = v.doc_id)
ON CONFLICT (doc_id) DO NOTHING;
