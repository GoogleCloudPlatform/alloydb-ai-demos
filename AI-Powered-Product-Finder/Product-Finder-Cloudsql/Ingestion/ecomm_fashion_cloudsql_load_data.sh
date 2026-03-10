#!/bin/bash
# -----------------------------------------------------------------------------
# Script Name : ecomm_fashion_cloudsql_load_data.sh
# Purpose     : Grant Cloud SQL instance service account access to a GCS bucket
#               and import a CSV into a Cloud SQL PostgreSQL table.
#
# Prerequisites:
#   - gcloud CLI and gsutil installed & authenticated (gcloud auth login / ADC)
#   - You have Cloud SQL Admin + Storage Admin (or equivalent) to grant IAM and import
#   - The CSV exists at the specified GCS URI
#   - Target database & table exist in Cloud SQL (schema must match CSV)
# -----------------------------------------------------------------------------
source ./fashion_config.sh
echo "data loading started"

echo "${BUCKET_NAME}"
ECOMM_FILENAME="${ECOMM_FILENAME}" # CSV to import
echo "${ECOMM_FILENAME}"
ECOMM_TABLE="${ECOMM_TABLE}" # Destination table 
echo "${ECOMM_TABLE}"

echo "fetching service account detail"

# Get the service account for the Cloud SQL instance
SERVICE_ACCOUNT=$(gcloud sql instances describe "$INSTANCE_NAME" \
  --project="$PROJECT_ID" \
  --format="value(serviceAccountEmailAddress)")

# ----------------------------- Grant bucket access ----------------------------
# Grant the instance service account viewer access on the bucket, so Cloud SQL
# can read the CSV during import.

echo "${SERVICE_ACCOUNT} created"
echo "providing permission to service account ${SERVICE_ACCOUNT}"
# Grant access to GCS bucket
gsutil iam ch serviceAccount:$SERVICE_ACCOUNT:objectViewer $BUCKET_NAME_ROOT


echo "ecomm data loading started"
# ------------------------------- Import CSV -----------------------------------
# Import the CSV into the target table. Table must exist and match CSV columns.


gcloud sql import csv "$INSTANCE_NAME" "$BUCKET_NAME""$ECOMM_FILENAME" \
--database="${DB_NAME}" \
--user="${DB_USER}" \
--project="${PROJECT_ID}" \
--table="${SCHEMA_NAME}.fashion_products"
if [ $? -eq 0 ]; then
    echo "train file moved to GCS bucket successfully."
else
    echo "Error, train file not moved to GCS location. hence exiting."
    exit 1
fi