import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ---------- CloudSQL ----------
CLOUDSQL_INSTANCE_CONNECTION_NAME = os.getenv("CLOUDSQL_INSTANCE_CONNECTION_NAME")
CLOUDSQL_NAME = os.getenv("CLOUDSQL_NAME")
CLOUDSQL_USER = os.getenv("CLOUDSQL_USER")
CLOUDSQL_PASS = os.getenv("CLOUDSQL_PASS")
CLOUDSQL_TABLESCHEMA = os.getenv("CLOUDSQL_TABLESCHEMA")
CLOUDSQL_IP_TYPE = os.getenv("CLOUDSQL_IP_TYPE")
CLOUDSQL_CONNECT_TIMEOUT = os.getenv("CLOUDSQL_CONNECT_TIMEOUT")
CLOUDSQL_HOST = os.getenv("CLOUDSQL_HOST")
CLOUDSQL_PORT = os.getenv("CLOUDSQL_PORT")
CLOUDSQL_SSLMODE = os.getenv("CLOUDSQL_SSLMODE")
REGION = os.getenv("REGION")

# ---------- Service Account Credentials ----------
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
# GOOGLE_APPLICATION_CREDENTIALS="/home/bhanumathi_munuswamy/Inventory Replenishment/inventory-management-cloudsql-app/key.json"

# ---------- Vertex AI ----------
PROJECT_ID = os.getenv("PROJECT_ID")
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION")
VERTEX_MODEL = os.getenv("VERTEX_MODEL")
VERTEX_TEMPERATURE = os.getenv("VERTEX_TEMPERATURE")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")
EMBEDDING_DIM = os.getenv("EMBEDDING_DIM")
