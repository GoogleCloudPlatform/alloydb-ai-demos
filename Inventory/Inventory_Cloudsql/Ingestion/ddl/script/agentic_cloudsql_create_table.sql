CREATE SCHEMA IF NOT EXISTS :"schema";
CREATE EXTENSION IF NOT EXISTS vector;
--this table holde product level info detail
CREATE TABLE IF NOT EXISTS :"schema".products (
  sku               TEXT PRIMARY KEY,
  title             TEXT NOT NULL,
  description       TEXT,
  category          TEXT,
  embedding         VECTOR(3072),
  last_embedded_at  TIMESTAMPTZ,
  created_at        TIMESTAMPTZ DEFAULT now()
);
--this table hold store level info
CREATE TABLE IF NOT EXISTS :"schema".stores (
  store_id   SERIAL PRIMARY KEY,
  code       TEXT UNIQUE NOT NULL,
  name       TEXT NOT NULL,
  region     TEXT,
  timezone   TEXT
);
--this table hold supplier detail
CREATE TABLE IF NOT EXISTS :"schema".suppliers (
  supplier_id     SERIAL PRIMARY KEY,
  name            TEXT NOT NULL,
  lead_time_days  INT NOT NULL DEFAULT 7,
  moq             INT NOT NULL DEFAULT 1,
  email           TEXT,
  terms           TEXT
);
--this table hold product and supplier info in detail
CREATE TABLE IF NOT EXISTS :"schema".product_suppliers (
  sku             TEXT NOT NULL REFERENCES :"schema".products(sku) ON DELETE CASCADE,
  supplier_id     INT  NOT NULL REFERENCES :"schema".suppliers(supplier_id) ON DELETE CASCADE,
  preferred       BOOLEAN DEFAULT FALSE,
  cost            NUMERIC(12,4) NOT NULL,
  lead_time_days  INT,
  moq             INT,
  PRIMARY KEY (sku, supplier_id)
);

CREATE TABLE IF NOT EXISTS :"schema".stock_levels (
  store_id        INT  NOT NULL REFERENCES :"schema".stores(store_id),
  sku             TEXT NOT NULL REFERENCES :"schema".products(sku),
  on_hand         NUMERIC(12,2) NOT NULL DEFAULT 0,
  in_transit      NUMERIC(12,2) NOT NULL DEFAULT 0,
  safety_stock    NUMERIC(12,2) NOT NULL DEFAULT 0,
  reorder_point   NUMERIC(12,2),
  updated_at      TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (store_id, sku)
);

CREATE TABLE IF NOT EXISTS :"schema".transactions (
  transaction_id  BIGSERIAL PRIMARY KEY,
  order_id        TEXT,
  order_ts        TIMESTAMPTZ NOT NULL,
  store_id        INT REFERENCES :"schema".stores(store_id),
  channel         TEXT,
  sku             TEXT REFERENCES :"schema".products(sku),
  quantity        INT NOT NULL,
  unit_price      NUMERIC(12,2) NOT NULL,
  country         TEXT
);

CREATE MATERIALIZED VIEW IF NOT EXISTS :"schema".mv_daily_demand AS
SELECT store_id, sku, date_trunc('day', order_ts)::date AS day, SUM(quantity) AS qty
FROM :"schema".transactions
GROUP BY 1,2,3;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE t.typname = 'po_status'
      AND n.nspname = '$schema'
  ) THEN
    EXECUTE $sql$
      CREATE TYPE cloudsql_usecase.po_status AS ENUM
        ('draft','pending_approval','approved','sent','received','closed','cancelled')
    $sql$;
  END IF;
END
$$;


CREATE TABLE IF NOT EXISTS :"schema".docs (
  doc_id      BIGSERIAL PRIMARY KEY,
  sku         TEXT NULL REFERENCES :"schema".products(sku),
  doc_type    TEXT,
  source_url  TEXT,
  body        TEXT NOT NULL,
  embedding   VECTOR(3072),
  created_at  TIMESTAMPTZ DEFAULT now()
);



CREATE TABLE IF NOT EXISTS :"schema".purchase_orders (
  po_id        BIGSERIAL PRIMARY KEY,
  supplier_id  INT NOT NULL REFERENCES :"schema".suppliers(supplier_id),
  status       :"schema".po_status NOT NULL DEFAULT 'draft',
  created_at   TIMESTAMPTZ DEFAULT now(),
  created_by   TEXT,
  approved_by  TEXT,
  expected_at  DATE,
  total_amount NUMERIC(14,2) DEFAULT 0
);

CREATE TABLE IF NOT EXISTS :"schema".purchase_order_lines (
  po_line_id   BIGSERIAL PRIMARY KEY,
  po_id        BIGINT NOT NULL REFERENCES :"schema".purchase_orders(po_id) ON DELETE CASCADE,
  sku          TEXT   NOT NULL REFERENCES :"schema".products(sku),
  qty          INT    NOT NULL,
  unit_cost    NUMERIC(12,4),
  promised_at  DATE
);

SET search_path TO public, :"schema";

-- If metadata doesn't exist, add it as JSONB
ALTER TABLE :"schema".docs
  ADD COLUMN IF NOT EXISTS metadata jsonb;

-- If metadata exists but is JSON, convert to JSONB
ALTER TABLE :"schema".docs
   ALTER COLUMN metadata TYPE jsonb
  USING metadata::jsonb;

-- Create GIN index for efficient metadata filtering
CREATE INDEX IF NOT EXISTS idx_docs_metadata_gin
ON :"schema".docs USING gin (metadata);

CREATE INDEX IF NOT EXISTS idx_docs_metadata_path_gin
ON :"schema".docs USING gin (metadata jsonb_path_ops);

COMMIT;