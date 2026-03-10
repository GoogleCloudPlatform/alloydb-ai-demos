#!/bin/bash
# --- Configuration Variables ---
source ./fashion_config.sh

# If you prefer Private IP only, set PRIVATE_ONLY=true and provide VPC self-link
PRIVATE_ONLY=false
VPC_SELF_LINK=""  # e.g. "projects/${PROJECT_ID}/global/networks/default"

# --- Set the project ---
gcloud config set project "$PROJECT_ID"
gcloud config set account "$ACCOUNT"

# --- Check instance existence/state (idempotent) ---
SQL_STATUS=$(gcloud sql instances describe "$INSTANCE_NAME" --project="$PROJECT_ID" --format="value(state)" 2>/dev/null)
if [[ "$SQL_STATUS" == "RUNNABLE" || "$SQL_STATUS" == "PENDING_CREATE" ]]; then
  echo "Cloud SQL instance '$INSTANCE_NAME' already exists and is in state: $SQL_STATUS. Skipping creation."
else
  echo "Creating Cloud SQL MySQL instance '$INSTANCE_NAME' in $REGION ..."

  # Build base create command
   gcloud sql instances create "$INSTANCE_NAME" \
   --database-version="$DATABASE_VERSION" \
   --tier="$TIER" \
   --region="$REGION" \
   --edition="$EDITION" \
   --enable-google-ml-integration \
   --database-flags="sql_mode=STRICT_TRANS_TABLES,activate_all_roles_on_login=on,cloudsql_vector=on" \
   --root-password="$ROOT_PASSWORD"
fi