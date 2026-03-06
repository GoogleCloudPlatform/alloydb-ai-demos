#!/bin/bash
# -----------------------------------------------------------------------------
# Script Name : cloudsql_postgres_instance_creation.sh
# Purpose     : Creates a Google Cloud SQL for PostgreSQL instance if it doesn't
#               already exist, and enables IAM auth + Google ML integration.
# Prerequisites:
#   - gcloud CLI installed and authenticated (Application Default Credentials or gcloud auth login)
#   - You have 'Cloud SQL Admin' role (roles/cloudsql.admin) on the target project
#   - The selected tier/region is available in your project/quota
# -----------------------------------------------------------------------------
source ./agentic_config.sh
# --- Authenticate and Set Project ---
echo "Authenticating to Google Cloud..."
gcloud config set account "${ACCOUNT}"
gcloud config set project "${PROJECT_ID}"

# checking whether instance is running or pending state else it will create new instance.
SQL_STATUS=$(gcloud sql instances describe "$INSTANCE_NAME" --project="$PROJECT_ID" --format="value(state)" 2>/dev/null)

if [[ "$SQL_STATUS" == "RUNNABLE" || "$SQL_STATUS" == "PENDING_CREATE" ]]; then
  echo " Cloud SQL instance '$INSTANCE_NAME' already exists and is in state: $SQL_STATUS. Skipping creation."
else

# Create the Cloud SQL instance
gcloud sql instances create "$INSTANCE_NAME" \
  --database-version="$DATABASE_VERSION" \
  --tier="$TIER" \
  --region="$REGION" \
  --root-password="$ROOT_PASSWORD" \
  --enable-google-ml-integration \
  --database-flags="cloudsql.iam_authentication=on,cloudsql.enable_google_ml_integration=on,google_ml_integration.enable_model_support=on"
 echo "Cloud SQL instance '$INSTANCE_NAME' created successfully."
fi 

 echo "Cloud SQL instance '$INSTANCE_NAME' created successfully."
sleep 20
echo "Script completed.