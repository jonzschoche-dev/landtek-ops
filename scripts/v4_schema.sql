-- ============================================================================
-- LeoLandTek v4 schema migration
-- ============================================================================

-- Address collation version mismatch from postgres image swap
DO $$
BEGIN
  PERFORM pg_catalog.pg_database_collation_actual_version((SELECT oid FROM pg_database WHERE datname=current_database()));
  EXCEPTION WHEN OTHERS THEN NULL;
END $$;
ALTER DATABASE n8n REFRESH COLLATION VERSION;

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ----------------------------------------------------------------------------
-- cases (likely exists from n8n workflow; add columns if missing)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cases (
  case_file TEXT PRIMARY KEY,
  client_name TEXT,
  current_goals TEXT,
  next_milestone TEXT,
  key_risks TEXT,
  open_gaps TEXT,
  intelligence_summary TEXT,
  active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE cases ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT true;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE cases ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- ----------------------------------------------------------------------------
-- documents (likely exists; add v4 columns)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
  id SERIAL PRIMARY KEY,
  case_file TEXT,
  original_filename TEXT,
  smart_filename TEXT,
  mime_type TEXT,
  extracted_text TEXT,
  classification TEXT,
  strategic_relevance TEXT,
  analyst_memo JSONB,
  status TEXT DEFAULT 'ingested',
  page_count INT,
  novelty_score REAL,
  confidence REAL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS analyst_memo JSONB;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'ingested';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS page_count INT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS novelty_score REAL;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS confidence REAL;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- ----------------------------------------------------------------------------
-- entities canonical KB
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS entities (
  id SERIAL PRIMARY KEY,
  canonical_name TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  role TEXT,
  metadata JSONB DEFAULT '{}'::jsonb,
  first_seen_doc_id INT REFERENCES documents(id) ON DELETE SET NULL,
  last_seen_doc_id INT REFERENCES documents(id) ON DELETE SET NULL,
  case_files TEXT[] DEFAULT '{}',
  confidence REAL DEFAULT 1.0,
  status TEXT DEFAULT 'draft',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (canonical_name, entity_type)
);
CREATE INDEX IF NOT EXISTS entities_name_trgm_idx ON entities USING gin (canonical_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS entities_type_idx ON entities (entity_type);
CREATE INDEX IF NOT EXISTS entities_cases_idx ON entities USING gin (case_files);

-- ----------------------------------------------------------------------------
-- entity_aliases — fuzzy resolution surface
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS entity_aliases (
  id SERIAL PRIMARY KEY,
  entity_id INT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  alias TEXT NOT NULL,
  alias_confidence REAL DEFAULT 1.0,
  first_seen_doc_id INT REFERENCES documents(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (entity_id, alias)
);
CREATE INDEX IF NOT EXISTS aliases_lower_idx ON entity_aliases (lower(alias));
CREATE INDEX IF NOT EXISTS aliases_trgm_idx ON entity_aliases USING gin (alias gin_trgm_ops);

-- ----------------------------------------------------------------------------
-- document_entities (m2m with mention spans)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS document_entities (
  document_id INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  entity_id INT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
  mention_count INT DEFAULT 1,
  spans JSONB DEFAULT '[]'::jsonb,
  first_mentioned_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (document_id, entity_id)
);
CREATE INDEX IF NOT EXISTS dent_entity_idx ON document_entities (entity_id);

-- ----------------------------------------------------------------------------
-- document_chunks (pgvector — halfvec(3072) for OpenAI text-embedding-3-large)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS document_chunks (
  id BIGSERIAL PRIMARY KEY,
  document_id INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_index INT NOT NULL,
  page_number INT,
  spans_pages INT[],
  chunk_type TEXT,
  xml_path TEXT,
  content TEXT NOT NULL,
  content_hash TEXT,
  embedding halfvec(3072),
  entity_ids INT[],
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (document_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS dchunks_embedding_idx
  ON document_chunks USING hnsw (embedding halfvec_cosine_ops);
CREATE INDEX IF NOT EXISTS dchunks_entities_idx ON document_chunks USING gin (entity_ids);
CREATE INDEX IF NOT EXISTS dchunks_metadata_idx ON document_chunks USING gin (metadata);
CREATE INDEX IF NOT EXISTS dchunks_doc_idx ON document_chunks (document_id, chunk_index);

-- ----------------------------------------------------------------------------
-- conversation_chunks (replaces Qdrant landtek_conversations)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS conversation_chunks (
  id BIGSERIAL PRIMARY KEY,
  case_file TEXT,
  client_name TEXT,
  sender_name TEXT,
  chat_id TEXT,
  message_text TEXT NOT NULL,
  summary TEXT,
  classification TEXT,
  embedding halfvec(3072),
  sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS cchunks_embedding_idx
  ON conversation_chunks USING hnsw (embedding halfvec_cosine_ops);
CREATE INDEX IF NOT EXISTS cchunks_case_time_idx ON conversation_chunks (case_file, sent_at DESC);
CREATE INDEX IF NOT EXISTS cchunks_chat_idx ON conversation_chunks (chat_id, sent_at DESC);

-- ----------------------------------------------------------------------------
-- pending_docs queue (worker pulls from here via LISTEN/NOTIFY)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pending_docs (
  id SERIAL PRIMARY KEY,
  document_id INT REFERENCES documents(id) ON DELETE CASCADE,
  source_path TEXT NOT NULL,
  source_filename TEXT NOT NULL,
  source_origin TEXT,
  content_hash TEXT,
  status TEXT DEFAULT 'received',
  attempt_count INT DEFAULT 0,
  last_error TEXT,
  worker_id TEXT,
  locked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS pending_status_idx ON pending_docs (status, created_at);
CREATE INDEX IF NOT EXISTS pending_doc_idx ON pending_docs (document_id);

-- ----------------------------------------------------------------------------
-- review_queue (human transcription)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS review_queue (
  id SERIAL PRIMARY KEY,
  document_id INT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  page_number INT NOT NULL,
  image_path TEXT,
  ocr_attempted_text TEXT,
  ocr_confidence REAL,
  reason TEXT,
  status TEXT DEFAULT 'pending',
  assigned_to TEXT,
  human_transcription TEXT,
  transcribed_at TIMESTAMPTZ, transcribed_by TEXT,
  verified_at TIMESTAMPTZ, verified_by TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (document_id, page_number)
);
CREATE INDEX IF NOT EXISTS review_status_idx ON review_queue (status, created_at);

-- ----------------------------------------------------------------------------
-- case_intelligence_log (append-only)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS case_intelligence_log (
  id SERIAL PRIMARY KEY,
  case_file TEXT NOT NULL,
  source_filename TEXT,
  source_doc_id INT REFERENCES documents(id) ON DELETE SET NULL,
  intelligence_update TEXT NOT NULL,
  novelty_score REAL,
  superseded_by INT REFERENCES case_intelligence_log(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS intel_case_idx ON case_intelligence_log (case_file, created_at DESC);

-- ----------------------------------------------------------------------------
-- pending_questions (analyst-raised, awaiting answer)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pending_questions (
  id SERIAL PRIMARY KEY,
  case_file TEXT NOT NULL,
  source_filename TEXT,
  source_doc_id INT REFERENCES documents(id) ON DELETE SET NULL,
  question TEXT NOT NULL,
  context TEXT,
  priority TEXT DEFAULT 'normal',
  status TEXT DEFAULT 'open',
  answer TEXT,
  answered_by TEXT,
  answered_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS questions_status_idx ON pending_questions (status, case_file, created_at);

-- ----------------------------------------------------------------------------
-- audit_log
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
  id BIGSERIAL PRIMARY KEY,
  actor TEXT NOT NULL,
  actor_type TEXT,
  action TEXT NOT NULL,
  target_type TEXT,
  target_id TEXT,
  before_state JSONB,
  after_state JSONB,
  ip TEXT,
  user_agent TEXT,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS audit_actor_idx ON audit_log (actor, created_at DESC);
CREATE INDEX IF NOT EXISTS audit_target_idx ON audit_log (target_type, target_id);

-- ----------------------------------------------------------------------------
-- audit_rejected_messages (failed auth attempts)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_rejected_messages (
  id BIGSERIAL PRIMARY KEY,
  source TEXT NOT NULL,
  identifier TEXT,
  payload_excerpt TEXT,
  reason TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- authorized_users (whitelist; seed Jonathan as owner)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS authorized_users (
  id SERIAL PRIMARY KEY,
  telegram_user_id TEXT UNIQUE,
  email TEXT UNIQUE,
  name TEXT NOT NULL,
  role TEXT DEFAULT 'analyst',
  can_transcribe BOOLEAN DEFAULT true,
  can_verify BOOLEAN DEFAULT false,
  can_admin BOOLEAN DEFAULT false,
  active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
INSERT INTO authorized_users (telegram_user_id, name, role, can_transcribe, can_verify, can_admin, active)
  VALUES ('6513067717', 'Jonathan Zschoche', 'owner', true, true, true, true)
  ON CONFLICT (telegram_user_id) DO NOTHING;

-- ============================================================================
-- VERIFICATION
-- ============================================================================
\echo === v4 tables and column counts ===
SELECT table_name,
       (SELECT count(*) FROM information_schema.columns
        WHERE table_name=t.table_name AND table_schema='public') AS columns
FROM information_schema.tables t
WHERE table_schema='public'
  AND table_name IN (
    'cases','documents','entities','entity_aliases','document_entities',
    'document_chunks','conversation_chunks','pending_docs','review_queue',
    'case_intelligence_log','pending_questions','audit_log',
    'audit_rejected_messages','authorized_users'
  )
ORDER BY table_name;

\echo === existing data preserved ===
SELECT 'cases' AS tbl, COUNT(*) AS rows FROM cases
UNION ALL SELECT 'documents', COUNT(*) FROM documents
UNION ALL SELECT 'authorized_users', COUNT(*) FROM authorized_users;

\echo === HNSW indexes on vector columns ===
SELECT indexname, tablename FROM pg_indexes
WHERE tablename IN ('document_chunks','conversation_chunks')
  AND indexname LIKE '%embedding%';
