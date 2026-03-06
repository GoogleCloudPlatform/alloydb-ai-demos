#!/bin/bash
# Purpose: Create database objects (DDL) in a Cloud SQL for PostgreSQL instance
#          by executing a local SQL file via the Cloud SQL Auth Proxy.
# Usage:   ./agentic_cloudsql_create_ddl.sh
# Requires:
#   - cloud-sql-proxy available in PATH
#   - psql (PostgreSQL client) installed
#   - gcloud authenticated to the correct project
source ./agentic_config.sh
# Export password for psql
export PGPASSWORD=$PASSWORD

FREE_PORT=$(
  comm -23 <(seq 1024 49151) \
           <(ss -ltn | awk 'NR>1{print $4}' | sed 's/.*://') \
  | shuf | head -n 1
)
echo "Using free port: $FREE_PORT"


# Start Cloud SQL Auth Proxy
cloud-sql-proxy --port=${FREE_PORT} "$PROJECT_ID:$REGION:$INSTANCE_NAME" &
PROXY_PID=$!
sleep 5  # Wait for proxy to initialize

# Run the SQL file
PGPASSWORD="$PASSWORD" psql \
  "host=$HOST port=$FREE_PORT dbname=$DB_NAME user=$DB_USER sslmode=disable" \
  -v schema="$SCHEMA_NAME" \
  -f "$SQL_FILE"

if [ $? -eq 0 ]; then
    echo "DDL created Successfully."
else
    echo "Error, DDL not created. hence exiting."
    exit 1
fi

kill $PROXY_PID