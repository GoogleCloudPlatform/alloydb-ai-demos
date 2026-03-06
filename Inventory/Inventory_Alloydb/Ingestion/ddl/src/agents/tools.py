from __future__ import annotations
import os
from vertexai import init
from langchain_google_vertexai import VertexAIEmbeddings
from langchain_google_alloydb_pg import AlloyDBEngine, AlloyDBVectorStore

from src.utils.config import PROJECT_ID, VERTEX_LOCATION, ALLOYDB_TABLESCHEMA, REGION
from sqlalchemy.pool import NullPool
from sqlalchemy import event

init(project=PROJECT_ID, location=VERTEX_LOCATION)


def get_engine():
    print("Inside tools.py get_engine()")
    user = os.getenv("ALLOYDB_USER")
    password = os.getenv("ALLOYDB_PASS")
    database = os.getenv("ALLOYDB_NAME")
    cluster = os.getenv("ALLOYDB_CLUSTER")
    instance = os.getenv("ALLOYDB_INSTANCE")

    if not all([cluster, instance, database, user, password]):
        raise ValueError("Missing required AlloyDB environment variables.")

    engine_obj = AlloyDBEngine.from_instance(
        project_id=PROJECT_ID,
        region=REGION,
        cluster=cluster,
        instance=instance,
        database=database,
        user=user,
        password=password,
        engine_args={
            "poolclass": NullPool,  # <--- 1. Kill connections on app exit
            "connect_args": {
                "statement_cache_size": 0,
                "server_settings": {
                    "application_name": "MY_AI_AGENT",
                    "idle_session_timeout": "5000",
                },
            },
        },
    )

    # 2. THE FIX: Attach the Janitor to the underlying SQLAlchemy engine
    @event.listens_for(engine_obj._pool.sync_engine, "connect")
    def receive_connect(dbapi_connection, connection_record):
        """Forces the session to forget all previous prepared statements."""
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("DEALLOCATE ALL;")
            print("Deallocated previous details.")
        except Exception as e:
            print(f"Cleanup warning: {e}")
        finally:
            cursor.close()

    return engine_obj


def get_embeddings():
    """
    Instantiates a Vertex AI embedding model client for text embeddings.

    Environment variables used:
        - EMBEDDING_MODEL (str, optional): Vertex model id for embeddings.
          Defaults to "text-embedding-004".
        - PROJECT_ID / VERTEX_LOCATION: Used for Vertex initialization.

    Returns:
        VertexAIEmbeddings: Embedding client configured for the specified model.
    """
    return VertexAIEmbeddings(
        model_name=os.getenv("EMBEDDING_MODEL", "text-embedding-004"),
        project=PROJECT_ID,
        location=VERTEX_LOCATION,
    )


def get_vector_retriever(
    engine, table: str = "docs", column: str = "embedding", k: int = 4
):
    # pg_engine = PGEngine.from_sync_engine(engine)
    engine = get_engine()
    embeddings = get_embeddings()
    store = AlloyDBVectorStore.from_texts(
        texts=[],  # attach to existing table
        embedding=embeddings,
        engine=engine,
        # engine=get_vector_engine(),   # <-- LangChain AlloyDBEngine singleton
        # engine=pg_engine,
        table_name=table,
        schema_name=ALLOYDB_TABLESCHEMA,
        id_column="doc_id",
        content_column="body",
        embedding_column=column,
        metadata_columns=["doc_type", "source_url", "sku"],
    )
    return store.as_retriever(search_kwargs={"k": k})


# if __name__=="__main__":
#     print("Alloydb engine!!")
#     engine = get_engine()
#     print(engine)
#     print(f"Statement Cache Size: {engine.engine.dialect.statement_cache_size}")
