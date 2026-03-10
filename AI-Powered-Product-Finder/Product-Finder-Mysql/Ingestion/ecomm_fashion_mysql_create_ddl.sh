#!/bin/bash
# ------------------------------------------------------------------------------
# Script: temp_script.sh
# Purpose:
#   - Connect to a Cloud SQL for MySQL instance via the Cloud SQL Auth Proxy
#   - Ensure an application database exists
#   - Execute DDL statements from a .sql file against that database
#   - Create an application user and grant privileges
#
# How it works:
#   1) Loads connection and runtime parameters from agentic_config.param
#   2) Finds a free local TCP port and starts the Cloud SQL Auth Proxy
#   3) Uses the MySQL CLI to run DDL and manage users
#   4) Performs a quick smoke test using the new app user
#
# Preconditions:
#   - gcloud/Cloud SQL Auth Proxy installed on this host
#   - IAM/service account has required Cloud SQL Client permissions
#   - agentic_config.param defines variables used below (see validation block)

# It lists all listening ports and subtracts them from a sequence, shuffles, and picks one.
source ./fashion_config.sh

PORT=$(comm -23 <(seq 1024 49151) <(ss -ltn | awk '{print $4}' | sed 's/.*://') | shuf | head -n 1)
echo "Using free port: $PORT"

# Export password for psql
export MYSQL_PWD=$PASSWORD

# Start Cloud SQL Auth Proxy
cloud-sql-proxy --port="$PORT" "$PROJECT_ID:$REGION:$INSTANCE_NAME" &
PROXY_PID=$!
sleep 10  # Wait for proxy to initialize

# --- Run DDL ---
# Notes:
#  - Using --protocol=TCP to force TCP to the proxy port.
#  - --ssl-mode=DISABLED is fine when connecting via the proxy’s local TCP.
#  - If your instance enforces SSL, remove --ssl-mode or set it appropriately.
#  - Redirecting the file via stdin ensures proper error handling.
MYSQL_CMD=(
  mysql
  --protocol=TCP
  -h "$HOST"
  -P "$PORT"
  -u "$DB_USER"
  --ssl-mode=DISABLED
  --database="$DB_NAME"
  --show-warnings
  --verbose
)
echo "${MYSQL_CMD}"

# --- Ensure app database exists (optional if your DDL creates it) ---
echo "Ensuring database ${APP_DB_NAME} exists..."
echo "CREATE DATABASE IF NOT EXISTS \`${APP_DB_NAME}\`;" | "${MYSQL_CMD[@]}"

# --- Run DDL on the app database ---
if [[ ! -f "${SQL_FILE}" ]]; then
  echo "ERROR: SQL file '${SQL_FILE}' not found."
  exit 1
fi

echo "Executing DDL from '${SQL_FILE}' on '${APP_DB_NAME}'..."
# Execute within the correct database
"${MYSQL_CMD[@]}" --database="${APP_DB_NAME}" < "${SQL_FILE}"
echo " DDL executed successfully."

# --- Create new user and grant privileges on the app database ---
echo "Creating user '${NEW_USER}' and granting privileges on ${APP_DB_NAME}..."
USER_CREATION_SQL=$(cat <<SQL
CREATE USER IF NOT EXISTS '${NEW_USER}'@'%' IDENTIFIED BY '${NEW_PASSWORD}';
GRANT ALL PRIVILEGES ON \`${APP_DB_NAME}\`.* TO '${NEW_USER}'@'%';
GRANT EXECUTE ON FUNCTION mysql.ML_EMBEDDING TO '${NEW_USER}'@'%';
GRANT SELECT ON mysql.cloudsql_ml_models TO '${NEW_USER}'@'%';
FLUSH PRIVILEGES;
SQL
)
echo "${USER_CREATION_SQL}" | "${MYSQL_CMD[@]}"

# --- Verify: check user exists and privileges ---
echo "Verifying user and grants..."
echo "SELECT user, host FROM mysql.user WHERE user='${NEW_USER}';" | "${MYSQL_CMD[@]}"
echo "SHOW GRANTS FOR '${NEW_USER}'@'%';" | "${MYSQL_CMD[@]}"

# --- Smoke test: login as app_user and query the app DB ---
echo "Running smoke test as '${NEW_USER}'..."
mysql --protocol=TCP -h "${HOST}" -P "${PORT}" -u "${NEW_USER}" -p"${NEW_PASSWORD}" \
      --ssl-mode=DISABLED --database="${APP_DB_NAME}" \
      -e "SELECT DATABASE() AS current_db, 1 AS ping;"

# --- Create New User and Grant Permissions ---
#echo "Creating new user '${NEW_USER}' and granting permissions..."

# SQL commands to create user and grant privileges
#USER_CREATION_SQL="
#CREATE USER '${NEW_USER}'@'%' IDENTIFIED BY '${NEW_PASSWORD}';
#GRANT ALL PRIVILEGES ON ${NEW_USER_DB_NAME}.* TO '${NEW_USER}'@'%';
#FLUSH PRIVILEGES;
#"
# Note: Using '%' for host means the user can connect from any host.
# For production, you might restrict this to specific IPs or subnet.

if echo "$USER_CREATION_SQL" | "${MYSQL_CMD[@]}"; then
  echo "User '${NEW_USER}' created and permissions granted successfully."
else
  echo "Error: Failed to create user or grant permissions. Exiting."
  kill "$PROXY_PID"
  exit 1
fi