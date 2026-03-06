from google.cloud.alloydbconnector import Connector
import sqlalchemy
import pg8000.dbapi


# ---------- AlloyDB Connector Setup ----------
class AlloyDBClient:
    """Manages connections to an AlloyDB database using the AlloyDB Python Connector."""

    def __init__(
        self, instance_uri, user, password, database, refresh_strategy="background"
    ) -> None:
        """Initializes the AlloyDBClient.

        Args:
            instance_uri (str): The instance URI of the AlloyDB cluster.
            user (str): The database user.
            password (str): The database user's password.
            database (str): The name of the database to connect to.
            refresh_strategy (str, optional): The refresh strategy for the connector.
                Defaults to "background".
        """
        self.instance_uri = instance_uri
        self.user = user
        self.password = password
        self.database = database
        self.refresh_strategy = refresh_strategy
        self.connector = Connector(refresh_strategy=self.refresh_strategy)

    def create_engine(self) -> sqlalchemy.engine.Engine:
        """Creates and returns a SQLAlchemy engine for interacting with the AlloyDB database.

        The engine is configured with a connection pool and uses the internal
        `_connection_creator` method to establish new connections.

        Returns:
            sqlalchemy.engine.Engine: A SQLAlchemy engine instance.
        """
        engine = sqlalchemy.create_engine(
            "postgresql+pg8000://",
            creator=self._connection_creator,
            pool_timeout=30,
            pool_recycle=1800,
            pool_size=50,
        )
        engine.dialect.description_encoding = None
        return engine

    def _connection_creator(self) -> pg8000.dbapi.Connection:
        """Creates a database connection using the AlloyDB Python Connector.

        This method is used as the `creator` for the SQLAlchemy engine.
        It's responsible for calling the connector's `connect` method with the
        appropriate credentials and settings.
        """
        return self.connector.connect(
            self.instance_uri,
            "pg8000",
            user=self.user,
            password=self.password,
            db=self.database,
            ip_type="PUBLIC",
        )

    def close_connector(self) -> None:
        """Closes the AlloyDB connector and releases its resources.

        It is important to call this method when the application is shutting down
        to ensure a clean exit and to release background refresh threads.
        """
        self.connector.close()
