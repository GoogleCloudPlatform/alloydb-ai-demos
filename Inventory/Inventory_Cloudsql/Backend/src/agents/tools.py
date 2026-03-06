from __future__ import annotations
from typing import Optional

from vertexai import init
from langchain_google_vertexai import VertexAIEmbeddings
from sqlalchemy import create_engine, text, event
from sqlalchemy.engine import URL
from langchain_community.vectorstores.pgvector import PGVector
from src.utils.config import (
    CLOUDSQL_TABLESCHEMA,
    CLOUDSQL_HOST,
    CLOUDSQL_USER,
    CLOUDSQL_PASS,
    CLOUDSQL_NAME,
    EMBEDDING_DIM,
    VERTEX_LOCATION,
    PROJECT_ID,
    EMBEDDING_MODEL,
    CLOUDSQL_PORT,
)


# Initialize Vertex AI once
init(project=PROJECT_ID, location=VERTEX_LOCATION)

# ---------------------------------------------------------------------------
# Singletons for reuse across the app:
#   - _sqlalchemy_engine: pooled sync engine.
#   - _embeddings: Vertex AI embeddings client.
#   - _connection_string: rendered SQLAlchemy URL string.
# ---------------------------------------------------------------------------
_sqlalchemy_engine = None
_embeddings: Optional[VertexAIEmbeddings] = None
_connection_string: Optional[str] = None


def _build_connection_string() -> str:
    """
    Builds and caches a SQLAlchemy connection string for pg8000/postgres,
    using `URL.create` to avoid issues with special characters in credentials.

    Returns:
        str: A rendered connection string with the password unmasked.

    Raises:
        RuntimeError: When required environment variables are missing.
    """
    global _connection_string
    if _connection_string is not None:
        return _connection_string

    # Validate required environment variables for direct Cloud SQL connection.
    missing = []
    if not CLOUDSQL_HOST:
        missing.append("CLOUDSQL_HOST (or DB_HOST)")
    if not CLOUDSQL_USER:
        missing.append("CLOUDSQL_USER (or DB_USER)")
    if not CLOUDSQL_NAME:
        missing.append("CLOUDSQL_NAME (or DB_NAME)")
    if missing:
        raise RuntimeError(
            "Missing required env vars for direct Cloud SQL connection: "
            + ", ".join(missing)
        )

    # Construct the SQLAlchemy URL to safely handle credentials.
    url = URL.create(
        drivername="postgresql+pg8000",
        username=CLOUDSQL_USER,
        password=CLOUDSQL_PASS,
        host=CLOUDSQL_HOST,
        port=CLOUDSQL_PORT,
        database=CLOUDSQL_NAME,
    )
    # Render the URL as a string with the password unmasked
    _connection_string = url.render_as_string(hide_password=False)
    return _connection_string


def get_engine():
    """
    Returns a pooled synchronous SQLAlchemy engine (pg8000) using direct
    Cloud SQL Public IP connectivity. Also installs a `connect` event hook
    to set the `search_path` on newly opened DB-API connections and ensures
    the `vector` extension exists.

    Returns:
        sqlalchemy.engine.Engine: A configured engine instance ready for use.
    """
    global _sqlalchemy_engine
    if _sqlalchemy_engine is not None:
        return _sqlalchemy_engine

    # Build connection string and create the engine with common pool settings.
    conn_str = _build_connection_string()
    engine = create_engine(
        conn_str,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        future=True,  # SQLAlchemy 2.x style
    )

    # Ensure search_path is set on each new DB-API connection
    @event.listens_for(engine, "connect")
    def set_search_path(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"SET search_path TO public, {CLOUDSQL_TABLESCHEMA};")
        finally:
            cursor.close()

    # One-time extension check (safe if already present)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))

    _sqlalchemy_engine = engine
    return _sqlalchemy_engine


def get_embeddings():
    """
    Returns a cached Vertex AI embeddings client configured with `EMBEDDING_MODEL`.

    Returns:
        VertexAIEmbeddings: Client used to generate text embeddings (default 3072-d).
    """
    global _embeddings
    if _embeddings is not None:
        return _embeddings

    _embeddings = VertexAIEmbeddings(
        model_name=EMBEDDING_MODEL,
        project=PROJECT_ID,
        location=VERTEX_LOCATION,
    )
    return _embeddings


def ensure_pgvector_schema(table: str = "docs", dim: int | None = None):
    """
    Idempotently ensures the pgvector table and ANN index exist under the CLOUDSQL_TABLESCHEMA
    schema. Safe to call at app startup or via a setup script.

    Args:
        table (str, optional): Target table name under `CLOUDSQL_TABLESCHEMA` schema. Defaults to "docs".
        dim (int | None, optional): Embedding dimension. Defaults to `EMBEDDING_DIM`.

    Returns:
        None
    """
    engine = get_engine()
    dim = int(dim or EMBEDDING_DIM or 3072)

    with engine.begin() as conn:
        # Ensure schema and table
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {CLOUDSQL_TABLESCHEMA};"))
        conn.execute(
            text(
                f"""
            CREATE TABLE IF NOT EXISTS {CLOUDSQL_TABLESCHEMA}.{table} (
              doc_id      BIGSERIAL PRIMARY KEY,
              sku         TEXT NULL REFERENCES {CLOUDSQL_TABLESCHEMA}.products(sku),
              doc_type    TEXT,
              source_url  TEXT,
              body        TEXT NOT NULL,
              embedding   VECTOR({dim}),
              created_at  TIMESTAMPTZ DEFAULT now()
            );
        """
            )
        )
        # Create ANN index for cosine similarity (adjust operator if using L2/inner product)
        conn.execute(
            text(
                f"""
            CREATE INDEX IF NOT EXISTS idx_{table}_embedding
            ON {CLOUDSQL_TABLESCHEMA}.{table} USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100);
        """
            )
        )


def get_vector_retriever(
    table: str = "docs",
    column: str = "embedding",
    k: int = 4,
):
    """
    Attaches to an existing pgvector table and returns a LangChain retriever that
    performs top-k semantic search using the community PGVector store.

    Args:
        table (str, optional): Vector table name under CLOUDSQL_TABLESCHEMA schema. Defaults to "docs".
        column (str, optional): Embedding column name. Defaults to "embedding".
        k (int, optional): Number of nearest neighbors to retrieve. Defaults to 4.

    Returns:
        Any: A retriever compatible with `.invoke(text)` and related methods.

    Notes:
        - This variant of PGVector requires a connection string rather than an Engine.
        - Metadata columns returned with search results: ["doc_type", "source_url", "sku"].
    """
    # Build connection string once; PGVector client expects a string for its API.
    connection_string = _build_connection_string()
    embeddings = get_embeddings()

    # Attach to an existing index/table and expose a retriever interface.
    store = PGVector.from_existing_index(
        embedding=embeddings,
        connection_string=connection_string,
        table_name=table,
        schema_name=CLOUDSQL_TABLESCHEMA,
        id_column="doc_id",
        content_column="body",
        embedding_column=column,
        metadata_columns=["doc_type", "source_url", "sku"],
        use_jsonb=True,
    )
    return store.as_retriever(search_kwargs={"k": k})
