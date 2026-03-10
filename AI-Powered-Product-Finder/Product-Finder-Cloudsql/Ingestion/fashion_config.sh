#!/bin/bash
# --------------------------- Configuration -----------------------------------

#bucket creation varibles
export LOCATION="us-central1" #No need to change this
export STORAGE_CLASS="STANDARD" #No need to change this
export FOLDERS="" #Need to provide folder and sub folder for eg raw/forecast,raw/ecomm
export CREATE_BUCKET="" #Need to provide bucket name

export PROJECT_ID=""  # Need to provide GCP Project ID
export INSTANCE_NAME="" # Need to provide Cloud SQL instance name for eg  (global)
export REGION="us-central1" # No need to change here, Region for the instance
export TIER="db-custom-2-8192" # No need to change here, Choose based on your need but should not be micro and small,example  Custom tier: 2 vCPU, 8 GB RAM
export ROOT_PASSWORD="" # Need to provide Password for 'postgres' user but it should be change as per need.
export DATABASE_VERSION="POSTGRES_17" # No need to change here PostgreSQL major version
export ACCOUNT=""  # Need to provide gcloud account to use
# --------------------------- Configuration -----------------------------------
export REPO_URL="" # Need to provide source repo URL for eg https://github.com/deepakbhalia1920/srcdump.git
export CLONE_DIR="raw_dataset" # Need to provide local repo directory for eg raw_dataset
export CLONE_DIR_ECOMM="" #Need to provide clone directory for eg /home/deepak_kumar214e17/raw_dataset/Ecommerce/dataset
# Target GCS bucket/folder (must exist or gsutil should have permissions to create)
export BUCKET_NAME="" #Need to provide bucket name for eg gs://alloydb-gc-usecase-newsetup/raw/ecomm/
export HOMEDIR="/home/deepak_kumar214e17" # Need to provide holme dir for eg /home/deepak_kumar214e17
export FILES_TO_UPLOAD="fashion_dataset.csv" #No need to change here.

# --- Configuration ---
export HOST="127.0.0.1" # No need to change here Local host
export PORT="5433" # No Need to change here Local port
export DB_NAME="" # Need to provide target database for eg postgres        
export SQL_FILE="ecomm_fashion_cloudsql_create_table.sql" # No Need to change here SQL file containing DDL statements
#BUCKET="gs://alloydb-usecase/uploads"
export DB_USER="" # Need to provide Database user
export PASSWORD="" # Need to provide database Password

################################################################################
export BUCKET_NAME_ROOT=""  # Need to provide bucket root directory for eg gs://alloydb-gc-usecase-newsetup
export ECOMM_FILENAME="fashion_dataset.csv" # No need to change this CSV to import
#export ECOMM_TABLE="fashion_products" # No need to change Destination table 

# --- Configuration ---
export PRE_SQL_FILE="ecomm_fashion_cloudsql_presql.sql" # No need to change this sql file
export SCHEMA_NAME="" #Need to change schema name here