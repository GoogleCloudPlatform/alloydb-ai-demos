#!/bin/bash
# -----------------------------------------------------------------------------
# Script Name : ecomm_fashion_wrapper_ddl.sh
# Purpose     : Execute the DDL statements in a .sql file against an AlloyDB
#               (PostgreSQL) instance using psql.
#
# Prerequisites:
#   - VM/host has network reachability to AlloyDB (Private IP, firewall 5432)
#   - gcloud CLI installed and authenticated (if using dynamic IP discovery)
#   - IAM/permissions to run 'gcloud alloydb' (optional, for IP lookup)
#   - The SQL file exists in the working directory or path provided
# -----------------------------------------------------------------------------
. ./agentic_config.sh
echo "${SQL_FILE}"
# Export password for psql
export PGPASSWORD=$PASSWORD

gcloud config set account ${ACCOUNT}
gcloud config set project ${PROJECT_ID}

REMOTE_ALLOYDB_IP="$1"
echo "AlloyDB Primary Instance IP: $REMOTE_ALLOYDB_IP"

# SQL to create table
if command -v psql >/dev/null 2>&1; then
  echo "psql is already installed. Skipping installation."
else
 sudo apt install postgresql-client -y
 psql --version
fi
#psql -h "${REMOTE_ALLOYDB_IP}" -p $ALLOYDB_PORT -U $USER -d $DATABASE_NAME -f ${SQL_FILE}

psql \
  -h "${REMOTE_ALLOYDB_IP}" \
  -p "${ALLOYDB_PORT}" \
  -U "${USER}" \
  -d "${DATABASE_NAME}" \
  --set=ON_ERROR_STOP=1 \
  --set=schema_name="${SCHEMA_NAME}" \
  --file="${SQL_FILE}"