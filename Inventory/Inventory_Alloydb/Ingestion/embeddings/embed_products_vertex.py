from __future__ import annotations
import os
from dotenv import load_dotenv
from langchain_google_vertexai import VertexAIEmbeddings
from src.utils.sql import fetchall, get_conn

load_dotenv()
PROJECT=os.getenv("PROJECT_ID")
LOCATION=os.getenv("VERTEX_LOCATION", os.getenv("REGION","us-central1"))
MODEL=os.getenv("EMBEDDING_MODEL","text-embedding-004")
EMBED_DIM=int(os.getenv("EMBEDDING_DIM","768"))

def get_items_to_embed(limit=5000):
    return fetchall("SELECT sku, COALESCE(description,title) AS text FROM retail.products WHERE embedding IS NULL LIMIT %s", (limit,))

if __name__=="__main__":
    embeddings=VertexAIEmbeddings(model_name=MODEL, project=PROJECT, location=LOCATION)
    rows=get_items_to_embed()
    with get_conn() as conn, conn.cursor() as cur:
        for r in rows:
            vec=embeddings.embed_query(r["text"])  # list[float]
            if len(vec)!=EMBED_DIM: raise ValueError("Embedding dim mismatch")
            cur.execute("UPDATE retail.products SET embedding=%s, last_embedded_at=now() WHERE sku=%s", (vec, r["sku"]))
        conn.commit()
    print(f"✅ Embedded {len(rows)} products via Vertex AI")
