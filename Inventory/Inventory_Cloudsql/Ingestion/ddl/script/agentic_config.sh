#!/bin/bash
# --------------------------- Configuration -----------------------------------

#bucket creation varibles
export LOCATION="us-central1" # No need to change here
export STORAGE_CLASS="STANDARD" # No need to change here
export FOLDERS="" # Need to provide folder/sub folder in gcp for eg raw/forecast,raw/ecomm 
export CREATE_BUCKET="" #Need to provide bucket name for eg alloydb-gc-usecase

export PROJECT_ID="" # Need to provide project ID
export INSTANCE_NAME="" # Need to provide instance name for ex cloudsql-postgres-instance
export REGION="us-central1" # No Need to change here , Region for the instance
#export TIER="db-custom-2-8192" # Choose based on your need but should not be micro and small, example  # Custom tier: 2 vCPU, 8 GB RAM
export TIER="db-perf-optimized-N-2" # No need to change here
export ROOT_PASSWORD="" # Need to provide passwork for root user.
export DATABASE_VERSION="POSTGRES_17" # No need to change here PostgreSQL major version
export ACCOUNT=""  # Need to provide mail id gcloud account to use

# --- Configuration ---

export HOST="127.0.0.1" # No need to change here Local host used by the proxy
export PORT="5433" # No need to change here Local port used by the proxy
export DB_NAME="" # Need to provide database name , Target database for running DDL
export SQL_FILE="agentic_cloudsql_create_table.sql" # No need to change here, SQL script containing DDL
export DB_USER="" # Need to provide database user name
export PASSWORD="" #Need to provide Database password
export SCHEMA_NAME="" # Need to provide schema name for eg cloudsql_usecase