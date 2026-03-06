# logger.py
import logging
from functools import wraps
import time

# Configure logger (stdout for Cloud Run)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("InventoryManagement-Alloydb")


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
            logger.info(f"Args: {args}, Kwargs: {kwargs}")
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
