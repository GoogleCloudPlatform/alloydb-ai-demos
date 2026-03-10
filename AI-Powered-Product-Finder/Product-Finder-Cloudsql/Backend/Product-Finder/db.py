import os
from sqlalchemy import create_engine
from google.cloud.sql.connector import Connector, IPTypes
from config import INSTANCE_CONNECTION_NAME, DB_NAME, DB_PASS, DB_USER


# Initialize Cloud SQL Python Connector
def get_connection():
    
    """Creates and returns a PostgreSQL database connection using the Cloud SQL Python Connector.

    The connection is established with pg8000 using credentials and instance details
    from environment variables.

    Returns:
        pg8000.dbapi.Connection: An active PostgreSQL connection object.
    """

    connector = Connector(ip_type=IPTypes.PUBLIC)  # Or IPTypes.PRIVATE if configured

    conn = connector.connect(
        INSTANCE_CONNECTION_NAME,
        "pg8000",
        user=DB_USER,
        password=DB_PASS,
        db=DB_NAME,
    )
    return conn


def get_engine():
    """Creates and returns a SQLAlchemy engine for interacting with the AlloyDB database.

        The engine is configured with a connection pool and uses the internal
        `_connection_creator` method to establish new connections.

        Returns:
            sqlalchemy.engine.Engine: A SQLAlchemy engine instance.
    """
    engine = create_engine(
        "postgresql+pg8000://",  # Or "mysql+pymysql://" for MySQL
        creator=get_connection,
    )
    return engine
