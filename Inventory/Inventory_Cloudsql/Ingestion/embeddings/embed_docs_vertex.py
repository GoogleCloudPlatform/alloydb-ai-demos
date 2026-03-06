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

def get_docs():
    return fetchall("SELECT doc_id, body FROM retail.docs WHERE embedding IS NULL")

if __name__=="__main__":
    embeddings=VertexAIEmbeddings(model_name=MODEL, project=PROJECT, location=LOCATION)
    rows=get_docs()
    with get_conn() as conn, conn.cursor() as cur:
        for r in rows:
            v=embeddings.embed_query(r["body"])  # list[float]
            assert len(v)==EMBED_DIM
            cur.execute("UPDATE retail.docs SET embedding=%s WHERE doc_id=%s", (v, r["doc_id"]))
        conn.commit()
    print(f"✅ Embedded {len(rows)} docs via Vertex AI")
