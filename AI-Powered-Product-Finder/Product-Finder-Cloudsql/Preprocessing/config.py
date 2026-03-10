RANDOM_SEED: int = 42
TARGET_SAMPLE_SIZE: int = 2000

# GCS paths (include SCHEMA_NAME and BUCKET_NAME)
GCS_STYLES_PATH: str = "gs://<SCHEMA_NAME>/<BUCKET_NAME>/styles.csv"
GCS_IMAGES_PATH: str = "gs://<SCHEMA_NAME>/<BUCKET_NAME>/images.csv"

# Output paths
LOCAL_OUTPUT_CSV: str = "fashion_products.csv"
# Optionally write back to GCS (requires gcsfs installed)
GCS_OUTPUT_PATH: str = None  # e.g., "gs://<SCHEMA_NAME>/<BUCKET_NAME>/fashion_products.csv"