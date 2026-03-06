import os
from dotenv import load_dotenv

load_dotenv()

# ---------- AlloyDB ----------
ALLOYDB_INSTANCE_URI = os.getenv("ALLOYDB_INSTANCE_URI")
ALLOYDB_USER = os.getenv("ALLOYDB_USER")
ALLOYDB_PASS = os.getenv("ALLOYDB_PASS")
ALLOYDB_NAME = os.getenv("ALLOYDB_NAME")
REGION = os.getenv("REGION")

# ---------- Service Account Credentials ----------
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
# GOOGLE_APPLICATION_CREDENTIALS="/home/bhanumathi_munuswamy/Inventory Replenishment/inventory-management-alloydb-app/key.json"

# ---------- Vertex AI ----------
PROJECT_ID = os.getenv("PROJECT_ID")
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION")
VERTEX_MODEL = os.getenv("VERTEX_MODEL")
VERTEX_TEMPERATURE = os.getenv("VERTEX_TEMPERATURE")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")
EMBEDDING_DIM = os.getenv("EMBEDDING_DIM")
ALLOYDB_CLUSTER = os.getenv("ALLOYDB_CLUSTER")
ALLOYDB_INSTANCE = os.getenv("ALLOYDB_INSTANCE")
ALLOYDB_DATABASE = os.getenv("ALLOYDB_DATABASE")
ALLOYDB_TABLESCHEMA = os.getenv("ALLOYDB_TABLESCHEMA")
