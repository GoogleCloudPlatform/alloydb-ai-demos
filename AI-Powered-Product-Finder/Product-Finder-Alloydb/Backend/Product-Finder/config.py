# Load application configuration from a .env file (ensure all required environment variables are defined)
import os
from dotenv import load_dotenv
import logging
import time
from functools import wraps

load_dotenv()

INSTANCE_URI = os.getenv("INSTANCE_URI")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
ALLOYDB_SCHEMA_NAME = os.getenv("ALLOYDB_SCHEMA_NAME")
TABLE_NAME = os.getenv("TABLE_NAME")
EMBEDDING = os.getenv("EMBEDDING")
NLA_API = os.getenv("NLA_API")
NLA_SERVICE_ACCOUNT = os.getenv("NLA_SERVICE_ACCOUNT")
CLUSTER_ID = os.getenv("CLUSTER_ID")
INSTANCE_ID = os.getenv("INSTANCE_ID")
VECTOR_THRESHOLD = float(os.getenv("VECTOR_THRESHOLD"))
HYBRID_THRESHOLD = float(os.getenv("HYBRID_THRESHOLD"))
RATING_THRESHOLD = float(os.getenv("RATING_THRESHOLD"))

CONTEXT_SET_ID = os.getenv("CONTEXT_SET_ID")
PROJECT_ID = os.getenv("PROJECT_ID")
LOCATION = os.getenv("LOCATION")
SCOPES = os.getenv("SCOPES")

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("Alloydb-SearchService")


def log_execution(is_api=False):
    """
    Decorator to log start and end of function execution.
    If is_api=True, logs will have API-specific markers.
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            func_name = func.__name__.upper()
            start_marker = "===== API STARTED" if is_api else "===== FUNCTION STARTED"
            end_marker = "===== API ENDED" if is_api else "===== FUNCTION ENDED"

            logger.info(f"{start_marker}: {func_name} =====")
            # logger.info(f"Args: {args}, Kwargs: {kwargs}")
            start_time = time.time()

            try:
                # ✅ Await the async function
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                logger.info(
                    f"{end_marker}: {func_name} | Duration: {duration:.2f}s ====="
                )
                return result
            except Exception as e:
                logger.error(f"❌ ERROR in {func_name}: {e}", exc_info=True)
                raise

        return wrapper

    return decorator
