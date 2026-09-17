-- deploy_978_portfolio_publish.sql — Client portfolio publish set (curated storefront)
-- Only published=true rows hit /client/<token> Portfolio Home.
-- Warehouse titles stay full; client never sees junk IDs.

CREATE TABLE IF NOT EXISTS portfolio_publish (
  id                bigserial PRIMARY KEY,
  client_code       text NOT NULL REFERENCES clients(client_code),
  title_no          text NOT NULL,
  display_registrant text,
  lifecycle         text,
  location          text,
  area_sqm          numeric,
  sort_order        int,
  published         boolean NOT NULL DEFAULT true,
  notes             text,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (client_code, title_no)
);

CREATE INDEX IF NOT EXISTS idx_portfolio_publish_client
  ON portfolio_publish (client_code) WHERE published IS TRUE;

-- MWK v1 curated storefront (operator-editable). Prefer estate living + contested Balane chain.
INSERT INTO portfolio_publish
  (client_code, title_no, display_registrant, lifecycle, location, area_sqm, sort_order, notes)
VALUES
  ('MWK-001', 'T-4497',  'Heirs of Mary Worrick Keesey', 'active',    'Mother title · Mercedes, Camarines Norte', NULL, 10, 'estate root'),
  ('MWK-001', 'T-32911', 'Heirs of Mary Worrick Keesey', 'active',    'Lot 2-A · Mercedes', NULL, 20, 'core estate'),
  ('MWK-001', 'T-32912', 'Heirs of Mary Worrick Keesey', 'active',    'Mercedes, Camarines Norte', 1395, 30, NULL),
  ('MWK-001', 'T-32913', 'Heirs of Mary Worrick Keesey', 'active',    'Mercedes, Camarines Norte', 1022, 40, NULL),
  ('MWK-001', 'T-32914', 'Heirs of Mary Worrick Keesey', 'active',    'Mercedes, Camarines Norte', NULL, 50, NULL),
  ('MWK-001', 'T-15616', 'Heirs of Mary Worrick Keesey', 'active',    'Mercedes, Camarines Norte', NULL, 60, NULL),
  ('MWK-001', 'T-147652','Heirs of Mary Worrick Keesey', 'active',    'Mercedes, Camarines Norte', NULL, 70, NULL),
  ('MWK-001', 'T-30681', 'Heirs of Mary Worrick Keesey', 'active',    'Mercedes, Camarines Norte', 804188, 80, NULL),
  ('MWK-001', 'T-30683', 'Mary Worrick Keesey',          'active',    'Manguisoc, Mercedes, Camarines Norte', 804148, 90, NULL),
  ('MWK-001', 'T-38838', 'Mary Worrick Keesey',          'active',    'Mercedes, Camarines Norte', 32448, 100, NULL),
  ('MWK-001', 'T-4502',  'Mary Worrick Keesey',          'active',    'Mercedes, Camarines Norte', 804188, 110, NULL),
  ('MWK-001', 'T-32478', 'Heirs of Mary Worrick Keesey', 'active',    'Mercedes, Camarines Norte', NULL, 120, NULL),
  ('MWK-001', 'T-33776', 'Rosco Leano',                  'active',    'Lot 2-X-6-H', 1295, 200, 'derivative on map'),
  ('MWK-001', 'T-36668', 'Alsa O. Iligan',               'active',    'Lot 2-X-6-A', 500, 210, 'derivative on map'),
  ('MWK-001', 'T-47656', '—',                            'active',    'Lot 2-X-6-N', NULL, 220, 'derivative'),
  ('MWK-001', 'T-52540', '—',                            'cancelled', 'Cancelled → 079-2021002126', NULL, 300, 'chain trap demo'),
  ('MWK-001', '079-2021002126', 'Gloria H. Balane',      'contested', 'Subject of CV-26360 · 2,587 sqm', 2587, 310, 'Balane flagship'),
  ('MWK-001', 'T-079-2018001329', 'Elsa O. Iligan',      'active',    'Mercedes, Camarines Norte', NULL, 230, NULL)
ON CONFLICT (client_code, title_no) DO UPDATE SET
  display_registrant = EXCLUDED.display_registrant,
  lifecycle = EXCLUDED.lifecycle,
  location = EXCLUDED.location,
  area_sqm = COALESCE(EXCLUDED.area_sqm, portfolio_publish.area_sqm),
  sort_order = EXCLUDED.sort_order,
  published = TRUE,
  notes = EXCLUDED.notes,
  updated_at = now();
