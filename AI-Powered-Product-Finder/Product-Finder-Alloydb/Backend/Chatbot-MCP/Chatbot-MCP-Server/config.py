import os
from dotenv import load_dotenv

load_dotenv()

INSTANCE_URI = os.getenv("INSTANCE_URI")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
SCHEMA_NAME = os.getenv("SCHEMA_NAME")