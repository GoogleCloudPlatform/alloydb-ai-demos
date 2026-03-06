import os
from dotenv import load_dotenv
load_dotenv()
import logging

# --- Configurations ---
PROJECT_ID = os.getenv("PROJECT_ID")
LOCATION = os.getenv("LOCATION")
MODEL_NAME = os.getenv("MODEL_NAME")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL")


# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("alloydb-chatbot")
