#!/usr/bin/env bash
set -euo pipefail

#############################################
# Configuration (EDIT)
#############################################
source ./fashion_config.sh
#############################################
# Setup
#############################################
gcloud config set project "${PROJECT_ID}" >/dev/null

echo "==> Verifying Cloud SQL instance '${INSTANCE_NAME}'..."
gcloud sql instances describe "${INSTANCE_NAME}" --project="${PROJECT_ID}" >/dev/null

# Get instance service account (used by Cloud SQL to access GCS during managed import)
echo "==> Fetching Cloud SQL instance service account..."
SERVICE_ACCOUNT=$(gcloud sql instances describe "${INSTANCE_NAME}" \
  --project="${PROJECT_ID}" \
  --format="value(serviceAccountEmailAddress)")
echo "    Service account: ${SERVICE_ACCOUNT}"

# Grant bucket read access (least privilege)
echo "==> Granting Storage Object Viewer on bucket to instance service account..."
gsutil iam ch "serviceAccount:${SERVICE_ACCOUNT}:roles/storage.objectViewer" "${BUCKET_ROOT}"
#gcloud storage buckets add-iam-policy-binding gs://alloydb-gc-usecase-newsetup \
#    --member="${SERVICE_ACCOUNT}" \
#    --role="roles/storage.objectViewer"



#############################################
# Option 1: Managed import from GCS with gcloud
#############################################
echo "==> Starting managed import from '${OBJECT_URI}' into ${APP_DB_NAME}.${TABLE_NAME} ..."
IMPORT_ARGS=(
  sql import csv "${INSTANCE_NAME}" "${OBJECT_URI}"
  --project="${PROJECT_ID}"
  --database="${APP_DB_NAME}"
  --table="${TABLE_NAME}"
  --quiet
)

# If you want to map columns explicitly:
if [[ -n "${COLUMNS_LIST}" ]]; then
  IMPORT_ARGS+=( "--columns=${COLUMNS_LIST}" )
fi

# NOTE: Some SDK versions expose additional flags for format; if your gcloud supports them, uncomment:
# IMPORT_ARGS+=( "--fields-terminated-by=${CSV_DELIMITER}" )
# IMPORT_ARGS+=( "--quote=${CSV_QUOTE}" )
# IMPORT_ARGS+=( "--escape=${CSV_ESCAPE}" )
# IMPORT_ARGS+=( "--lines-terminated-by=${CSV_LINE_ENDING}" )
# IMPORT_ARGS+=( "--ignore-first-row=${CSV_HAS_HEADER}" )

set +e
gcloud "${IMPORT_ARGS[@]}"
RC=$?
set -e

if [[ ${RC} -eq 0 ]]; then
  echo " Managed import started successfully."
  echo "   Tip: You can check operation status:"
  echo "     gcloud sql operations list --instance='${INSTANCE_NAME}' --filter='operationType=IMPORT'"
  exit 0
fi

echo "Managed import failed (exit code ${RC}). Falling back to Proxy + LOAD DATA LOCAL INFILE."