# Load application configuration from a .env file (ensure all required environment variables are defined)
import os
from dotenv import load_dotenv
import logging
from functools import wraps
import time

load_dotenv()

INSTANCE_CONNECTION_NAME = os.getenv("INSTANCE_CONNECTION_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME")

MYSQL_SCHEMA_NAME = os.getenv("MYSQL_SCHEMA_NAME")
TABLE_NAME = os.getenv("TABLE_NAME")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")
VECTOR_THRESHOLD = os.getenv("VECTOR_THRESHOLD")

# Configure logger (stdout for Cloud Run)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("Hybrid Search - MySQL")


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
