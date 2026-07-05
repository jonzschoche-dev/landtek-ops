-- Trigram GIN indexes so the Ombudsman Hunter combs the corpus fast at scale (pg_trgm already installed).
-- Accelerates the ILIKE / ~* scans in _hunt_one / _scoped_docs / discover_officers / _gather_element_evidence.
CREATE INDEX IF NOT EXISTS idx_mf_statement_trgm  ON matter_facts USING gin (statement gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_doc_extracted_trgm ON documents    USING gin (extracted_text gin_trgm_ops);
ANALYZE matter_facts; ANALYZE documents;
