#!/usr/bin/env bash
# create_gcs_bucket_and_folders_gsutil.sh
# Usage:
#   ./create_gcs_bucket_and_folders_gsutil.sh \
#     --project my-project \
#     --bucket my-bucket-name \
#     --location asia-south1 \
#     --storage-class STANDARD \
#     --folders "raw/data,raw/logs,processed/daily,processed/monthly"

set -euo pipefail
source ./agentic_config.sh

print_usage() {
  cat <<EOF
Create a GCS bucket and sub-folders using gsutil.
Options:
  --project $PROJECT_ID  
  --bucket $CREATE_BUCKET 
  --location $REGION 
  --storage-class $STORAGE_CLASS
  --folders $FOLDERS
  --help
EOF
}

echo "while loop started"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT_ID="$2"; shift 2 ;;
    --bucket) CREATE_BUCKET="$2"; shift 2 ;;
    --location) LOCATION="$2"; shift 2 ;;
    --storage-class) STORAGE_CLASS="$2"; shift 2 ;;
    --folders) FOLDERS="$2"; shift 2 ;;
    --help|-h) print_usage; exit 0 ;;
    *) echo "Unknown option: $1"; print_usage; exit 1 ;;
  esac
done

if [[ -z "${PROJECT_ID}" || -z "${CREATE_BUCKET}" ]]; then
  echo "ERROR: --project and --bucket are required."
  print_usage
  exit 1
fi

echo "==> Setting project: ${PROJECT_ID}"
gcloud config set project "${PROJECT_ID}"
gcloud config set account "${ACCOUNT}"

# Create bucket if not exists
if gsutil ls -b "gs://${CREATE_BUCKET}" >/dev/null 2>&1; then
  echo "Bucket gs://${CREATE_BUCKET} already exists. Skipping creation."
else
  echo "==> Creating bucket gs://${CREATE_BUCKET} in ${LOCATION} (${STORAGE_CLASS})"
  gsutil mb -c "${STORAGE_CLASS}" -l "${LOCATION}" "gs://${CREATE_BUCKET}"
fi

echo "subfolder is getting create"
# Create sub-folders
if [[ -n "${FOLDERS}" ]]; then
  IFS=',' read -ra FOLDER_LIST <<< "${FOLDERS}"
  for folder in "${FOLDER_LIST[@]}"; do
    folder="${folder#/}"
    [[ "${folder}" != */ ]] && folder="${folder}/"
    echo "==> Creating folder: gs://${CREATE_BUCKET}/${folder}"
    gsutil -q cp -n /dev/null "gs://${CREATE_BUCKET}/${folder}"
  done
else
  echo "No folders requested. Bucket created/verified."
fi