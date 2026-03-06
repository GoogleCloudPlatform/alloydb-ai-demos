# src/utils/alloydb_connect.py
from google.cloud.alloydbconnector import Connector
import sqlalchemy
from src.utils.config import (
    ALLOYDB_PASS,
    ALLOYDB_USER,
    ALLOYDB_NAME,
    ALLOYDB_INSTANCE_URI,
    PROJECT_ID,
    REGION,
    ALLOYDB_CLUSTER,
    ALLOYDB_INSTANCE,
)

# ADD THIS:
from functools import lru_cache
from langchain_google_alloydb_pg import AlloyDBEngine  # LangChain engine wrapper


# ---------- AlloyDB Connector Setup (pg8000) ----------
class AlloyDBClient:
    def __init__(
        self,
        instance_uri: str,
        user: str,
        password: str,
        database: str,
        refresh_strategy: str = "background",
    ):
        self.instance_uri = instance_uri
        self.user = user
        self.password = password
        self.database = database
        self.connector = Connector(refresh_strategy=refresh_strategy)
        self.alloydb_engine = self.alloydb_create_engine()

    def alloydb_create_engine(self) -> sqlalchemy.engine.Engine:
        return sqlalchemy.create_engine(
            "postgresql+pg8000://",
            creator=self.alloydb_connection_creator,
            pool_timeout=30,
            pool_recycle=1800,
            pool_size=5,
        )

    def alloydb_connection_creator(self):
        return self.connector.connect(
            self.instance_uri,
            "pg8000",
            user=self.user,
            password=self.password,
            db=self.database,
            ip_type="PUBLIC",
        )

    @property
    def engine(self) -> sqlalchemy.engine.Engine:
        return self.alloydb_engine


# Singleton pg8000 engine for normal SQL
alloydb_client = AlloyDBClient(
    ALLOYDB_INSTANCE_URI, ALLOYDB_USER, ALLOYDB_PASS, ALLOYDB_NAME
)


def get_engine() -> sqlalchemy.engine.Engine:
    """Use this for all normal SQL (non-vector) operations."""
    return alloydb_client.engine


# ---------- ADD THIS: Singleton vector engine for LangChain VectorStore ----------
## TRIED TO TEST THIS ENGINE KEEPING THIS FUNCTION AS BACKUP HERE
@lru_cache(maxsize=1)
def get_vector_engine() -> AlloyDBEngine:
    """
    Use this ONLY for LangChain AlloyDBVectorStore.
    statement_cache_size=0 prevents InvalidSQLStatementNameError under pooling.
    """
    return AlloyDBEngine.from_instance(
        PROJECT_ID,
        REGION,
        ALLOYDB_CLUSTER,
        ALLOYDB_INSTANCE,
        ALLOYDB_NAME,
        user=ALLOYDB_USER,
        password=ALLOYDB_PASS,
        engine_args={
            "pool_pre_ping": True,
            "connect_args": {"statement_cache_size": 0},
        },
    )
