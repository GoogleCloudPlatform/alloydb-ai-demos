#!/bin/bash
# -----------------------------------------------------------------------------
# Script Name : ecomm_fashion_pre_sql_wrapper.sh
# Purpose     : Execute pre-setup SQL/DDL statements in a .sql file against an
#               AlloyDB (PostgreSQL) instance using psql.
#
# Prerequisites:
#   - VM/host has network reachability to AlloyDB (Private IP, firewall for TCP 5432)
#   - 'postgresql-client' available (script installs it if missing)
#   - The SQL file exists in the working directory or given path
# -----------------------------------------------------------------------------
. ./fashion_config.sh
# Export password for psql
export PGPASSWORD=$PASSWORD
REMOTE_ALLOYDB_IP="$1"
echo "AlloyDB Primary Instance IP: $REMOTE_ALLOYDB_IP"
# SQL to create table
if command -v psql >/dev/null 2>&1; then
  echo "psql is already installed. Skipping installation."
else
 sudo apt install postgresql-client -y
 psql --version
fi

psql \
  -h "${REMOTE_ALLOYDB_IP}" \
  -p "${ALLOYDB_PORT}" \
  -U "${USER}" \
  -d "${DATABASE_NAME}" \
  --set=ON_ERROR_STOP=1 \
  --set=schema_name="${SCHEMA_NAME}" \
  --file="${PRE_SQL_FILE}"

echo "Pre-setup SQL executed successfully."