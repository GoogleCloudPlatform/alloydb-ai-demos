CREATE SCHEMA IF NOT EXISTS :"schema_name";
CREATE EXTENSION IF NOT EXISTS vector;
--This table holds product level detail.
CREATE TABLE IF NOT EXISTS :"schema_name".products (
  sku               TEXT PRIMARY KEY,
  title             TEXT NOT NULL,
  description       TEXT,
  category          TEXT,
  embedding         VECTOR(768),  -- Replace 768 with your actual embedding dimension
  last_embedded_at  TIMESTAMPTZ,
  created_at        TIMESTAMPTZ DEFAULT now()
);
--this table holds store level detail
CREATE TABLE IF NOT EXISTS :"schema_name".stores (
  store_id   SERIAL PRIMARY KEY,
  code       TEXT UNIQUE NOT NULL,
  name       TEXT NOT NULL,
  region     TEXT,
  timezone   TEXT
);
--this table holds uppliers detail
CREATE TABLE IF NOT EXISTS :"schema_name".suppliers (
  supplier_id     SERIAL PRIMARY KEY,
  name            TEXT NOT NULL,
  lead_time_days  INT NOT NULL DEFAULT 7,
  moq             INT NOT NULL DEFAULT 1,
  email           TEXT,
  terms           TEXT
);
-- this table holds product and supplier level information
CREATE TABLE IF NOT EXISTS :"schema_name".product_suppliers (
  sku             TEXT NOT NULL REFERENCES :"schema_name".products(sku) ON DELETE CASCADE,
  supplier_id     INT  NOT NULL REFERENCES :"schema_name".suppliers(supplier_id) ON DELETE CASCADE,
  preferred       BOOLEAN DEFAULT FALSE,
  cost            NUMERIC(12,4) NOT NULL,
  lead_time_days  INT,
  moq             INT,
  PRIMARY KEY (sku, supplier_id)
);

--this table holds stock level detail information
CREATE TABLE IF NOT EXISTS :"schema_name".stock_levels (
  store_id        INT  NOT NULL REFERENCES :"schema_name".stores(store_id),
  sku             TEXT NOT NULL REFERENCES :"schema_name".products(sku),
  on_hand         NUMERIC(12,2) NOT NULL DEFAULT 0,
  in_transit      NUMERIC(12,2) NOT NULL DEFAULT 0,
  safety_stock    NUMERIC(12,2) NOT NULL DEFAULT 0,
  reorder_point   NUMERIC(12,2),
  updated_at      TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (store_id, sku)
);


CREATE TABLE IF NOT EXISTS :"schema_name".transactions (
  transaction_id  BIGSERIAL PRIMARY KEY,
  order_id        TEXT,
  order_ts        TIMESTAMPTZ NOT NULL,
  store_id        INT REFERENCES :"schema_name".stores(store_id),
  channel         TEXT,
  sku             TEXT REFERENCES :"schema_name".products(sku),
  quantity        INT NOT NULL,
  unit_price      NUMERIC(12,2) NOT NULL,
  country         TEXT
);

CREATE MATERIALIZED VIEW IF NOT EXISTS :"schema_name".mv_daily_demand AS
SELECT store_id, sku, date_trunc('day', order_ts)::date AS day, SUM(quantity) AS qty
FROM :"schema_name".transactions
GROUP BY 1,2,3;


DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE t.typname = 'po_status' AND n.nspname = 'alloydb_usecase'
  ) THEN
    EXECUTE 'CREATE TYPE alloydb_usecase.po_status AS ENUM
      (''draft'',''pending_approval'',''approved'',''sent'',''received'',''closed'',''cancelled'')';
  END IF;
END$$;

CREATE TABLE IF NOT EXISTS :"schema_name".docs (
  doc_id      BIGSERIAL PRIMARY KEY,
  sku         TEXT NULL REFERENCES :"schema_name".products(sku),
  doc_type    TEXT,
  source_url  TEXT,
  body        TEXT NOT NULL,
  embedding   VECTOR(768),
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS :"schema_name".purchase_orders (
  po_id        BIGSERIAL PRIMARY KEY,
  supplier_id  INT NOT NULL REFERENCES :"schema_name".suppliers(supplier_id),
  status       :"schema_name".po_status NOT NULL DEFAULT 'draft',
  created_at   TIMESTAMPTZ DEFAULT now(),
  created_by   TEXT,
  approved_by  TEXT,
  expected_at  DATE,
  total_amount NUMERIC(14,2) DEFAULT 0
);

CREATE TABLE IF NOT EXISTS :"schema_name".purchase_order_lines (
  po_line_id   BIGSERIAL PRIMARY KEY,
  po_id        BIGINT NOT NULL REFERENCES :"schema_name".purchase_orders(po_id) ON DELETE CASCADE,
  sku          TEXT   NOT NULL REFERENCES :"schema_name".products(sku),
  qty          INT    NOT NULL,
  unit_cost    NUMERIC(12,4),
  promised_at  DATE
);