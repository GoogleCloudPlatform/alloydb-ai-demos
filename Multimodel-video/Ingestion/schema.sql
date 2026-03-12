
-- optional: improves ANN search
CREATE EXTENSION IF NOT EXISTS alloydb_scann;

CREATE EXTENSION IF NOT EXISTS vector;

-- Videos and metadata
CREATE TABLE IF NOT EXISTS video_meta (
  id BIGSERIAL PRIMARY KEY,
  file_name TEXT NOT NULL UNIQUE,
  label TEXT,
  split TEXT,
  duration_sec INT,
  width INT,
  height INT,
  fps REAL
);

CREATE TABLE IF NOT EXISTS video_blobs (
  video_id BIGINT PRIMARY KEY REFERENCES video_meta(id) ON DELETE CASCADE,
  video_data BYTEA NOT NULL
);

CREATE TABLE IF NOT EXISTS video_embeddings (
  video_id BIGINT PRIMARY KEY REFERENCES video_meta(id) ON DELETE CASCADE,
  embedding vector(1408) NOT NULL,
  frame_count INT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_video_embeddings_ivfflat_cos
  ON video_embeddings USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

CREATE EXTENSION IF NOT EXISTS vector;
DO $$ BEGIN
  BEGIN
    CREATE EXTENSION IF NOT EXISTS alloydb_scann;
  EXCEPTION WHEN undefined_file THEN NULL;
  END;
END $$;

-- Drop any existing ANN index on this table/column to keep ONE active
DO $$
DECLARE idx RECORD;
BEGIN
  FOR idx IN
    SELECT schemaname, indexname
    FROM pg_indexes
    WHERE schemaname = current_schema()
      AND tablename  = 'video_embeddings'
      AND indexdef ~* '(USING\s+(scann|ivfflat|hnsw))'
  LOOP
    EXECUTE format('DROP INDEX IF EXISTS %I.%I', idx.schemaname, idx.indexname);
  END LOOP;
END $$;

-- Prefer ScaNN; fallback to IVFFLAT if ScaNN isn’t present
DO $$
DECLARE has_scann BOOLEAN;
BEGIN
  SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'alloydb_scann') INTO has_scann;
  IF has_scann THEN
    EXECUTE format($sql$
      CREATE INDEX IF NOT EXISTS idx_video_embeddings_scann_cos
      ON %I.video_embeddings
      USING scann (embedding vector_cosine_ops)
      WITH (num_leaves = 200, training_sample_size = 50000, quantization_bytes = 16)
    $sql$, current_schema());
  ELSE
    EXECUTE format($sql$
      CREATE INDEX IF NOT EXISTS idx_video_embeddings_ivfflat_cos
      ON %I.video_embeddings
      USING ivfflat (embedding vector_cosine_ops)
      WITH (lists = 100)
    $sql$, current_schema());
  END IF;
END $$;

ANALYZE :"schema_name".video_embeddings;



-- Store object-storage URIs for videos (instead of BYTEA)
CREATE TABLE IF NOT EXISTS video_assets (
  video_id   BIGINT PRIMARY KEY REFERENCES video_meta(id) ON DELETE CASCADE,
  gcs_uri    TEXT NOT NULL,
  size_bytes BIGINT,
  mime_type  TEXT DEFAULT 'video/mp4'
);


