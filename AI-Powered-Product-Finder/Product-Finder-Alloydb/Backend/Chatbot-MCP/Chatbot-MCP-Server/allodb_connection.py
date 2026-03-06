from google.cloud.alloydbconnector import Connector
from sqlalchemy import text
import sqlalchemy
import pandas as pd

# ---------- AlloyDB Connector Setup ----------
class AlloyDBClient:
    def __init__(
        self, instance_uri, user, password, database, refresh_strategy="background"
    ):
        self.instance_uri = instance_uri
        self.user = user
        self.password = password
        self.database = database
        self.refresh_strategy = refresh_strategy
        self.connector = Connector(refresh_strategy=self.refresh_strategy)

    def create_engine(self):
        engine = sqlalchemy.create_engine(
            "postgresql+pg8000://",
            creator=self._connection_creator,
            pool_timeout=30,
            pool_recycle=1800,
            pool_size=50
        )
        engine.dialect.description_encoding = None
        return engine

    def _connection_creator(self):
        return self.connector.connect(
            self.instance_uri,
            "pg8000",
            user=self.user,
            password=self.password,
            db=self.database,
            ip_type="PUBLIC",
        )

    def close_connector(self):
        self.connector.close()
