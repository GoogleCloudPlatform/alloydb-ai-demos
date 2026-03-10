import os
from dotenv import load_dotenv
load_dotenv()
import logging

# --- Configurations ---
PROJECT_ID = os.getenv("PROJECT_ID", "dotengage")
LOCATION = os.getenv("LOCATION", "us-central1")
MODEL_NAME = os.getenv("MODEL_NAME")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL")

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("mysql-chatbot")

