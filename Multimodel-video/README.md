
# Multimodal Video Search (Vertex AI + AlloyDB + pgvector)

## Application Overview: 
This demo application enables **semantic, image‑driven video retrieval** across a curated video dataset by converting both **query images** and **representative video keyframes** into a **shared multimodal embedding space (1408‑dim)** using Vertex AI Multimodal Embeddings. The system allows analysts to upload an image such as an incident snapshot, traffic frame, product defect photo, or CCTV still and instantly retrieve the **most semantically similar video segments** from cloud storage. The solution integrates **Vertex AI, AlloyDB/pgvector**, and **GCS**, providing high‑speed vector search. 
 
**Key Alloy DB Components**:

- **AlloyDB for PostgreSQL** serves as the operational backbone, storing video metadata (id, label, duration_s, gcs_uri) along with embedding **VECTOR** fields. 
- Maintain strict **embedding dimension** alignment by defining VECTOR sizes consistent with **Vertex AI Multimodal Embeddings** for video/text. 
- **ANN Indexes (pgvector)**: 
  - Use **HNSW** or **IVFFlat** with the cosine operator class (e.g. **vector_cosine_ops**) and the <=> query operator. 
  - Tune **IVFFlat** lists/probes or **HNSW** M / ef_search to balance latency and recall. 
- **ScaNN** (optional, for large-scale deployments): Prefer **ScaNN indexes** with post‑creation ANALYZE when working with very large corpora and if supported in your environment. 

## Angular Frontend + FastAPI Backend + Ingestion Pipelines

> Search short videos by **text** or **image**, powered by **Vertex AI multimodal embeddings** and **AlloyDB (pgvector)**. FastAPI exposes APIs, the **Angular** app is the primary UI, and Python jobs handle ingestion/embedding.

---

## 🗂 Repository Layout
```
project-root/
│
├─ ingestion/                 # Batch jobs (Python)
│  ├─ ingest_videos.py        # Writes video_meta + video_blobs
│  └─ embed_videos.py         # Calls Vertex AI, writes video_embeddings
│
│
├─ backend/                   # FastAPI (Python)
│  ├─ app/
│  │  ├─ main.py              # FastAPI entrypoint
│  │  ├─ service.py           # SQL & server-side embedding
│  │  ├─ utils.py             # GCS URL helpers, SQL preview
│  │  ├─ db.py                # AlloyDB connector → SQLAlchemy Engine
│  │  └─ config.py            # Env-safe config, logging
│  ├─ tests/
│  └─ requirements.txt
│
├─ frontend/                  # Angular app
│  └─ src/app/
│     ├─ dashboard/
│     ├─ journey-page-component/
│     └─ services/
│
├─ .env.example               # Template (no secrets)
├─ .gitignore
└─ README.md
```

---

## 🧱 Architecture
- **Angular** SPA → **FastAPI** REST (
  `/video_search`, `/categories_duration`, `/healthz`)
- **AlloyDB + pgvector** store metadata & vectors
- **Server-side** query embeddings using AlloyDB AI functions (text/image)
- Playback via **GCS** public or signed URLs

**Core tables**
- `video_meta(id, file_name, label, duration_sec, width, height, fps)`
- `video_embeddings(video_id PK, embedding vector(1408), frame_count)`
- `video_blobs(video_id PK, video_data BYTEA)` *(optional)*
- `video_assets(video_id PK, gcs_uri TEXT)` *(optional)*

> Keep `video_meta.file_name` as **basename** (e.g., `video8.mp4`). Backend builds `gs://<bucket>/data/<label>/<file_name>` and converts to public/signed URL.

---

## ⚙️ Prerequisites
- **Python 3.10/3.11** (backend & pipelines)
- **Node.js 18+**, **Angular CLI 16+** (frontend)
- **GCP Project** with Vertex AI & AlloyDB
- Local ADC: `gcloud auth application-default login`

---

## 🔐 Configuration (.env)
Create `.env` (copy from `.env.example`):
```
PROJECT_ID=your-gcp-project
VERTEX_LOCATION=us-central1

ALLOYDB_INSTANCE_URI=projects/.../clusters/.../instances/...
ALLOYDB_USER=postgres
ALLOYDB_PASSWORD=********
ALLOYDB_DATABASE=video_db
ALLOYDB_TABLE_SCHEMA=alloydb_usecase
IP_TYPE=PUBLIC

TOP_K_DEFAULT=20
SIM_THRESHOLD_DEFAULT=0.35
ALLOW_ORIGINS=http://localhost:4200

USE_GCS=false
FRAME_SAMPLE_PER_SEC=1.0
EMBED_DIM=1408
```

> Every DB session runs `SET search_path TO ${ALLOYDB_TABLE_SCHEMA}, public` (enforced in code).

---

## ▶️ Run the Backend (FastAPI)
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```
OpenAPI docs: **http://localhost:8080/docs**

**Endpoints**
- `GET /healthz`
- `GET /categories_duration`
- `POST /video_search` (text or image)

---

## 🅰️ Run the Frontend (Angular)

### 1) Install deps
```bash
cd frontend
npm ci
```

### 2) Proxy API for local dev
Create `frontend/proxy.conf.json`:
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
Update `angular.json` → `architect > serve > options`:
```json
"proxyConfig": "proxy.conf.json"
```



### 3) Start Angular
```bash
npm run start    # or: ng serve
# http://localhost:4200
```

---

## 🔌 Angular ↔ API Integration (example)
**Service model** (`src/app/models/video.ts`):
```ts
export interface VideoHit {
  id: number; filename: string; similarity: number; label: string;
  duration: number | null; url: string; public_url: string;
}
export interface SearchResponse {
  sql_query: string; multimodal_video_search: VideoHit[];
}
export interface CategoriesDuration {
  [label: string]: { min_duration_sec: number; max_duration_sec: number };
}
```

**API Service** **(`src/app/services/video-service.ts`):(example)**
```ts
import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { environment } from '../../environments/environment';
import { Observable } from 'rxjs';
import { SearchResponse, CategoriesDuration } from '../models/video';

@Injectable({ providedIn: 'root' })
export class VideoApiService {
  private base = environment.apiBase;
  constructor(private http: HttpClient) {}

  categoriesDuration(): Observable<{ categories_duration: CategoriesDuration }> {
    return this.http.get<{ categories_duration: CategoriesDuration }>(`${this.base}/categories_duration`);
  }

  searchByText(query: string, categories = 'All Categories', duration = 0): Observable<SearchResponse> {
    return this.http.post<SearchResponse>(`${this.base}/video_search`, {
      query, categories, duration, input_type: 'text'
    });
  }

  searchByImage(imageBase64: string, mime: string, categories = 'All Categories', duration = 0) {
    return this.http.post<SearchResponse>(`${this.base}/video_search`, {
      query: imageBase64, categories, duration, input_type: mime
    });
  }
}
```

**Component render snippet**:
```@Component({
  selector: 'app-root',
  imports: [RouterOutlet],
  templateUrl: './app.html',
  styleUrl: './app.scss'
})
export class App {
  protected readonly title = signal('MultiModel');
}
```

---

## 📥 Pipelines
**Ingest**
```bash
cd ingestion
python ingest_videos.py --source-dir /path/to/videos --schema alloydb_usecase --dedupe-on-basename true
```
**Embed**
```bash
python embed_videos.py --schema alloydb_usecase --use-gcs false --frame-sample-per-sec 1.0
```
> If using `video_assets(gcs_uri)`, run with `--use-gcs true`.

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
- Don’t use `"*"` with `allow_credentials=true`
- Don’t commit secrets; add only `.env.example`

---

## 🚀 Deploy
**Angular**
```bash
npm run build           # outputs to dist/ per angular.json
```
Host the build (Cloud Storage + CDN, Firebase Hosting, or NGINX). Set `environment.prod.ts.apiBase` to your backend URL.

**Backend**
- Containerize `uvicorn app.main:app` → **Cloud Run**
- Provide env vars & a service account with AlloyDB/Vertex roles

**Jobs**
- Package `ingestion/` scripts as **Cloud Run Jobs**, schedule via **Cloud Scheduler**

---

## 🧰 Troubleshooting
- **Blank videos**: check `public_url` (403 → private; 404 → wrong path). Consider signed URLs/proxy.
- **No results**: confirm search path and vectors exist for those `video_id`s.
- **CORS**: proxy.conf + `ALLOW_ORIGINS`.
- **Dim mismatch**: ensure `vector(1408)` and Vertex `multimodalembedding@001`.

---

## 📈 Performance
- Prefer **HNSW** indexes; tune `hnsw.ef_search`
- Start with **1 fps** frame sampling for cost/quality balance
- Keep media in **GCS**; BYTEA only if compliance/portability required




