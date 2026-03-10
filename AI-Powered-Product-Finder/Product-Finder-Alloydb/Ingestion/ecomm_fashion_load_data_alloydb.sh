#!/bin/bash
# -----------------------------------------------------------------------------
# Script Name : ecomm_fashion_load_data_alloydb.sh
# Purpose     : Load a CSV file from a GCS bucket into an AlloyDB table using
#               `gcloud alloydb clusters import`.
#
# Prerequisites:
#   - gcloud CLI installed and authenticated (gcloud auth login / ADC)
#   - Caller has AlloyDB and Storage permissions (read GCS object, import into AlloyDB)
#   - The CSV file exists at the specified GCS path
#   - Target database & table exist in AlloyDB (schema should match CSV)
# -----------------------------------------------------------------------------
source ./fashion_config.sh
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
echo "${PROJECT_NUMBER}"
SA_EMAIL="service-${PROJECT_NUMBER}@gcp-sa-alloydb.iam.gserviceaccount.com"
echo "${SA_EMAIL}"
echo "Granting Storage permissions to AlloyDB service account: $SA_EMAIL"

gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_NAME_ROOT}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.objectViewer"

# loading csv file in alloydb table.
# # ----------------------------- Import Command ---------------------------------
# --csv tells gcloud this is a CSV file; table must be pre-created with proper columns.
# The import connects to the AlloyDB cluster and loads the file into the specified table.
gcloud alloydb clusters import "${CLUSTER_ID}" \
--region="${REGION}" \
--gcs-uri="${BUCKET_NAME}""${FILES_TO_UPLOAD}" \
--database="${DATABASE_NAME}" \
--user="${USER}" \
--csv \
--table="${SCHEMA_NAME}.fashion_products"

if [ $? -eq 0 ]; then
    echo "Data loaded successfully in AlloyDB."
else
    echo "Error while loading table in AlloyDB. Exiting."
    exit 1
fi