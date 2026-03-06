from google.cloud.sql.connector import Connector, IPTypes
from sqlalchemy import create_engine
from src.utils.config import (
    CLOUDSQL_INSTANCE_CONNECTION_NAME,
    CLOUDSQL_USER,
    CLOUDSQL_PASS,
    CLOUDSQL_NAME,
)


# ---------- Cloud SQL Connector Setup ----------
class CloudSQLClient:
    """
    Thin wrapper around the Cloud SQL Python Connector plus a SQLAlchemy engine.

    This class encapsulates:
      - Connector initialization and the connection creator function.
      - SQLAlchemy engine construction that delegates connection creation
        to the Cloud SQL connector (pg8000 driver).
      - A reusable `engine` property for dependency injection across the app.

    Args:
        instance_uri (str): Cloud SQL instance connection name (e.g., project:region:instance).
        user (str): Database username.
        password (str): Database password.
        database (str): Target database name.
        refresh_strategy (str, optional): Connector refresh strategy. Defaults to "background".

    Attributes:
        instance_uri (str): Stored instance connection name.
        user (str): Stored DB username.
        password (str): Stored DB password.
        database (str): Stored DB name.
        connector (Connector): Initialized Cloud SQL connector.
        cloudsql_engine (sqlalchemy.engine.Engine): Precreated SQLAlchemy engine.
    """

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
        self.cloudsql_engine = self.cloudsql_create_engine()

    def cloudsql_connection_creator(self):
        """
        Provides a live pg8000 DB-API connection via the Cloud SQL connector.

        IP type:
            - IPTypes.PUBLIC by default (set to PRIVATE if using private IP).
        """

        return self.connector.connect(
            self.instance_uri,
            "pg8000",
            user=self.user,
            password=self.password,
            db=self.database,
            ip_type=IPTypes.PUBLIC,  # Use PRIVATE if needed
        )

    def cloudsql_create_engine(self):
        """
        Builds a SQLAlchemy engine that uses the connector's `creator` callback
        to open connections. Pool parameters tune connection reuse and recycling.

        Returns:
            sqlalchemy.engine.Engine: Engine bound to Cloud SQL via pg8000.
        """

        return create_engine(
            "postgresql+pg8000://",
            creator=self.cloudsql_connection_creator,
            pool_timeout=30,
            pool_recycle=1800,
            pool_size=5,
        )

    @property
    def engine(self):
        """
        Exposes the preconstructed SQLAlchemy engine for application reuse.

        Returns:
            sqlalchemy.engine.Engine: Persistent pooled engine.
        """
        return self.cloudsql_engine


# Create a single, reusable client instance for the application
cloudsql_client = CloudSQLClient(
    CLOUDSQL_INSTANCE_CONNECTION_NAME, CLOUDSQL_USER, CLOUDSQL_PASS, CLOUDSQL_NAME
)


# Dependency function
def get_engine():
    """
    Provides the application-wide SQLAlchemy engine configured for Cloud SQL.

    Returns:
        sqlalchemy.engine.Engine: Engine retrieved from the shared CloudSQLClient.
    """
    return cloudsql_client.engine
