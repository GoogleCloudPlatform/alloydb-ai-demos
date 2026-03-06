
# Intelligent Inventory Replenishment (Vertex AI + AlloyDB/CloudSQL + pgvector)

**Angular Frontend + FastAPI Backend + Batch/Streaming Pipelines**

Plan, simulate, and execute inventory replenishment across stores and warehouses. The system combines
Vertex AI (forecasting & embeddings) with PostgreSQL (AlloyDB or Cloud SQL) + `pgvector` for similarity search.
FastAPI exposes REST APIs, the Angular app is the primary UI, and Python jobs handle ingestion, forecasting,
reorder calculations, and purchase order (PO) creation.

---

## 🗂 Repository Layout
```
project-root/
│
├─ agents/                     # Optional: Agentic layer (Python)
│  ├─ demand_agent.py          # Calls Vertex AI to forecast demand
│  ├─ inventory_agent.py       # Computes reorder quantities & safety stock
│  ├─ po_agent.py              # Generates POs and resolves constraints
│  └─ notify_agent.py
   └─ policy_agent.py
   └─ supplier_agent.py
   └─ cordinator_agent.py
   └─ tools_agent.py          # Sends alerts (email/Slack/Pub/Sub)
│
├─ ingestion/
|  ├─ embeddings/                  # Batch/stream pipelines (Python)
│      ├─ embed_docs_vertex.py    
│      ├─ embed_rag_docs.py   
│      ├─ embed_products_vertex.py        # Vertex AI text embeddings → product_vectors
│  
│
├─ backend/                    # FastAPI (Python)
│  ├─ app/
│  │  ├─ main.py               # FastAPI entrypoint
│  │  ├─ service.py            # Business logic: SQL + vector search + forecasting calls
│  │  ├─ db.py                 # AlloyDB/CloudSQL connector → SQLAlchemy Engine
│  │  ├─ schema.py             # Pydantic models, validation
│  │  ├─ utils.py              # Helpers (GCS URLs, SQL preview, pagination)
│  │  └─ config.py             # Env-safe config & logging
│  ├─             
│  ├─
│  └─ requirements.txt
│
script/
|          ├── agentic_config.sh
|          ├── agentic_mysql_create_table.sql
|          ├── agentic_mysql_create_ddl.sh
|          ├── bucket_create.sh
|          └── cloudsql_mysql_instance_creation.sh
│
├─ frontend/                   # Angular app (TypeScript) — optional UI
│  ├─ src/
│  ├─ public/
│  ├─ angular.json
│  ├─ package.json
│  ├─ tsconfig.json
│  ├─ tsconfig.app.json
│  └─ tsconfig.spec.json
│                 
│
├─ .env.example                # Template (no secrets)
├─ .gitignore
└─ README.md
```

---

## 🧱 Architecture
- Angular SPA → FastAPI REST (`/forecast`, `/replenishment_plan`, `/stock_levels`, `/po`, `/healthz`)
- PostgreSQL (AlloyDB **or** Cloud SQL Postgres) + `pgvector` store facts, forecasts & vectors
- Server-side embeddings using Vertex AI text-embeddings for product similarity & substitutions
- (Optional) Vertex AI forecasting (Demand) + rules-based or service-level policies for reorder


**Core tables** (schema example)
```
products(id, sku, name, category, brand, unit_cost, unit_price, uom)
stores(id, code, name, region)
suppliers(id, name, lead_time_days, min_order_qty, service_level)
stock_levels(store_id, product_id, on_hand, on_order, safety_stock, reorder_point, updated_at)
transactions(id, store_id, product_id, ts, qty, type)           -- sales/receipt/return
purchase_orders(id, supplier_id, created_at, status)
po_lines(po_id, store_id, product_id, order_qty, due_date)
daily_demand(store_id, product_id, date, forecast_qty, method)
product(product_id, embedding vector(768))               -- pgvector
```
> Tip: keep `search_path` set to `${TABLE_SCHEMA}, public` for all sessions.

---

## ⚙️ Prerequisites
- Python **3.10/3.11** (backend & pipelines)
- Node.js **18+**, Angular CLI **16+** (frontend)
- GCP project with: Vertex AI, AlloyDB (or Cloud SQL Postgres), Secret Manager (optional), Cloud Storage
- Local ADC: `gcloud auth application-default login`

---

## 🔐 Configuration (`.env`)
Copy from `.env.example` and fill in:

```
# GCP
PROJECT_ID=your-gcp-project
VERTEX_LOCATION=us-central1

# Database (choose one target)
DATABASE_TARGET=alloydb        # alloydb | cloudsql
TABLE_SCHEMA=inventory_app

# AlloyDB
ALLOYDB_INSTANCE_URI=projects/.../clusters/.../instances/...
ALLOYDB_USER=postgres
ALLOYDB_PASSWORD=********
ALLOYDB_DATABASE=inventory_db
IP_TYPE=PUBLIC

# Cloud SQL Postgres (if used)
CLOUDSQL_INSTANCE_CONNECTION_NAME=project:region:instance
CLOUDSQL_USER=postgres
CLOUDSQL_PASSWORD=********
CLOUDSQL_DATABASE=inventory_db
CLOUDSQL_IP_TYPE=PUBLIC

# App defaults
FORECAST_HORIZON_DAYS=14
REVIEW_PERIOD_DAYS=7
ALLOW_ORIGINS=http://localhost:4200

# Embeddings
EMBED_MODEL="text-embedding-004"
EMBED_DIM=768

# Optional
USE_GCS=true
REPORTS_BUCKET=gs://your-bucket/reports
```
Every DB session should run `SET search_path TO ${TABLE_SCHEMA}, public` (enforced in code).

---

## ▶️ Run the Backend (FastAPI)
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head     # optional: run DB migrations
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```
OpenAPI docs: http://localhost:8080/docs

**Endpoints**
```
GET  /healthz
GET  /stock_levels?store_id=...&product_id=...&page=...
POST /forecast                 # { store_id, product_id, horizon_days }
POST /replenishment_plan       # { store_id, review_period_days, service_level }
POST /substitutions/search     # { query | sku, top_k }
POST /po/preview               # returns draft POs for approval
POST /po/commit                # persists POs and returns IDs
```

---

## 🅰️ Run the Frontend (Angular)
1) **Install deps**
```bash
cd frontend
npm ci
```
2) **Proxy API for local dev** — create `frontend/proxy.conf.json`:
```json
{
  "/api": {
    "target": "http://localhost:8080",
    "secure": false,
    "changeOrigin": true,
    "pathRewrite": { "^/api": "" }
  }
}
```
Update `angular.json` → architect > serve > options:
```json
{
  "proxyConfig": "proxy.conf.json"
}
```
3) **Environments**
`frontend/src/environments/environment.ts`:
```ts
export const environment = { production: false, apiBase: '/api' };
```
`environment.prod.ts`:
```ts
export const environment = { production: true, apiBase: 'https://<your-backend-domain>' };
```
4) **Start Angular**
```bash
npm run start    # or: ng serve
# http://localhost:4200
```

**Angular ↔ API Integration (example)**
Model (e.g., `src/app/models/inventory.ts`):
```ts
export interface StockLevel {
  store_id: number; product_id: number; on_hand: number; on_order: number;
  safety_stock: number; reorder_point: number; updated_at: string;
}
export interface PlanLine {
  store_id: number; product_id: number; order_qty: number; due_date: string; supplier_id?: number;
}
export interface PlanResponse { sql_query: string; plan: PlanLine[] }
```
Service (e.g., `src/app/services/inventory-api.service.ts`):
```ts
@Injectable({ providedIn: 'root' })
export class InventoryApiService {
  private base = environment.apiBase;
  constructor(private http: HttpClient) {}

  stockLevels(params: any) { return this.http.get<StockLevel[]>(`${this.base}/stock_levels`, { params }); }
  forecast(body: any) { return this.http.post(`${this.base}/forecast`, body); }
  plan(body: any) { return this.http.post<PlanResponse>(`${this.base}/replenishment_plan`, body); }
  poPreview(body: any) { return this.http.post(`${this.base}/po/preview`, body); }
  poCommit(body: any) { return this.http.post(`${this.base}/po/commit`, body); }
}
```

---

## 📥 Pipelines
**Ingest master & transactions**
```bash
cd ingestion
python load_online_retail.py --schema inventory_app --files ./data
python run_single_pass.py --schema 
```
**Compute product embeddings** (substitution & similarity search)
```bash
python embed_products_vertex.py --schema inventory_app --model textembedding --embed-dim 768
python embed_docs_vertex.py --schema inventory_app --model textembedding --embed-dim 768
python generate_rag_docs.py --schema inventory_app --model textembedding --embed-dim 768
```

---

## 🧪 Quality
**Angular**
```bash
npm run lint
npm run test
npm run build
```
**Python**
```bash
pip install pytest black isort flake8
black . && isort . && flake8
pytest backend/tests -q
```

---

## 🔒 Security & CORS
- Backend: set `ALLOW_ORIGINS=http://localhost:4200` (comma‑separated in prod)
- Avoid `"*"` with `allow_credentials=true`
- Store secrets in Secret Manager or local `.env` (never commit real secrets)
- Grant least-privilege roles to the service account for DB/Vertex/GCS access

---

## 🚀 Deploy
**Angular**
```bash
npm run build   # outputs to dist/ per angular.json
```
Host the build (Cloud Storage + CDN, Firebase Hosting, or NGINX). Set `environment.prod.ts.apiBase` to your backend URL.

**Backend**
- Containerize `uvicorn app.main:app` → Cloud Run or GKE
- Provide env vars & a service account with AlloyDB/Cloud SQL + Vertex AI + GCS roles
- Run Alembic migrations on deploy

**Jobs**
- Package `ingestion/` scripts as Cloud Run Jobs, schedule via Cloud Scheduler
- Optionally trigger via Pub/Sub on new data arrivals

---

## 🧰 Troubleshooting
- **Empty plan**: ensure `daily_demand` exists for horizon; verify `service_level`, `lead_time_days`, and `review_period_days`
- **Vector dim mismatch**: `product_vectors.embedding` must match `EMBED_DIM`
- **Slow queries**: check indexes on `(store_id, product_id)`, HNSW for vectors, and partition large tables by date
- **DB auth/connection**: verify `IP_TYPE`, network paths, and that the instance accepts your client IP (or use Cloud SQL Connector)
- **CORS**: use `proxy.conf.json` locally + configure `ALLOW_ORIGINS`

---

## 📈 Performance
- Use `pgvector` HNSW indexes for fast similarity search (tune `hnsw.ef_search` & `hnsw.m`)
- Cache recent forecasts; batch embedding requests to Vertex AI for throughput
- Start with weekly review periods and adjust per category ABC/XYZ segmentation
- Keep large reports in GCS; fetch via signed URLs when needed

---

## 📝 Notes
- Works with either **AlloyDB** or **Cloud SQL Postgres**. Switch using `DATABASE_TARGET` env var without changing application code.
- All SQL is parameterized. The backend returns an optional `sql_query` with responses for transparency/debugging.

---



