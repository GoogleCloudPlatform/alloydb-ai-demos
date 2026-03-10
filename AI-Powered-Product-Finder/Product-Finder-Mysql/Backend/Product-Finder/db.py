from sqlalchemy import create_engine
# import pymysql
from google.cloud.sql import connector
from config import INSTANCE_CONNECTION_NAME, DB_NAME, DB_PASS, DB_USER


# Initialize Cloud SQL Python Connector
def get_connection():
    """Creates and returns a MySQL database connection using the Cloud SQL Python Connector.

    The connection is established with the `pymysql` driver using instance details
    and credentials from environment variables.

    Returns:
        pymysql.connections.Connection: An active MySQL connection object.
    """
    # connector = Connector(ip_type=IPTypes.PUBLIC)  # Or IPTypes.PRIVATE if configured
    connect = connector.Connector()
    conn = connect.connect(
        INSTANCE_CONNECTION_NAME,
        "pymysql",
        user=DB_USER,
        password=DB_PASS,
        db=DB_NAME,
    )
    return conn


def get_engine():
    """Creates and returns a SQLAlchemy engine for interacting with the MySQL database.

    The engine uses the `pymysql` driver and relies on the `get_connection` function
    to establish connections via the Cloud SQL Python Connector.

    Returns:
        sqlalchemy.engine.Engine: A SQLAlchemy engine instance.
    """

    engine = create_engine(
        "mysql+pymysql://",
        creator=get_connection,
    )
    return engine
