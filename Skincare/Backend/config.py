"""Configuration settings for the application."""
from functools import lru_cache
import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load environment variables from .env file first
load_dotenv()


class Settings(BaseSettings):
  # Define ONLY the settings your application directly needs to access
  # via this object
  database_url: str
  database_url_v1: str
  google_api_key: str  # Renamed for LangChain compatibility
  nl_config_name: str = "google_io"
  default_user_id: int = 123

  # Configure Pydantic settings behavior
  model_config = SettingsConfigDict(
      env_file=".env",
      extra=(
          "ignore"
      ),
  )


@lru_cache()
def get_settings():
  # The Settings() call will now load from .env and ignore
  # the extra LangSmith vars
  try:
    return Settings()
  except Exception as e:
    print(f"ERROR loading settings: {e}")
    # Optionally, re-raise or handle differently depending on whether
    # settings are critical
    raise


settings = get_settings()

# --- Optional: Check for Langsmith vars directly from environment if needed ---
# Langsmith usually reads these directly, so you often don't need them in the
# Settings object.
# This check just confirms they are set if tracing is enabled.
LS_TRACING_ENABLED = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"

if LS_TRACING_ENABLED:
  print("LangSmith tracing is enabled via environment variable.")
  if not os.getenv("LANGSMITH_ENDPOINT"):
    print(
        "Warning: LANGSMITH_TRACING is true, but LANGSMITH_ENDPOINT is not set"
        " in environment."
    )
  if not os.getenv("LANGSMITH_API_KEY"):
    print(
        "Warning: LANGSMITH_TRACING is true, but LANGSMITH_API_KEY is not set"
        " in environment."
    )
  if not os.getenv("LANGSMITH_PROJECT"):
    print(
        "Warning: LANGSMITH_TRACING is true, but LANGSMITH_PROJECT is not set"
        " in environment."
    )
else:
  print("LangSmith tracing is not enabled via environment variable.")