#!/bin/bash
# Script Name: alloydb_postgres_cluster_creation.sh
# Purpose: Automates creation of AlloyDB cluster and primary instance in Google Cloud.
# Prerequisites: gcloud CLI installed and authenticated.
source ./agentic_config.sh
# Display configuration for verification
echo $PROJECT_ID
echo $REGION
echo $CLUSTER_ID


# --- Authenticate and Set Project ---
gcloud config set account ${ACCOUNT}

# --- Authenticate and Set Project ---
echo "Authenticating to Google Cloud..."
#gcloud auth login --no-launch-browser # Use --no-launch-browser for scripting
gcloud config set project "${PROJECT_ID}"

# --- Create AlloyDB Cluster ---
# Check if cluster exists
if gcloud alloydb clusters describe "$CLUSTER_ID" --region="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
 echo "Cluster '$CLUSTER_ID' already exists. Skipping creation."
else 
 echo "Creating AlloyDB cluster: ${CLUSTER_ID} in ${REGION}..."
 gcloud alloydb clusters create "${CLUSTER_ID}" \
     --region="${REGION}" \
     --network="projects/${PROJECT_ID}/global/networks/default" \
     --password="${DB_PASSWORD}" \
     --database-version=POSTGRES_16
fi

# Check if cluster creation succeeded
if [ $? -eq 0 ]; then
    echo "AlloyDB cluster '${CLUSTER_ID}' created successfully."
else
    echo "Error creating AlloyDB cluster '${CLUSTER_ID}'. Exiting."
    exit 1
fi

if gcloud alloydb instances describe "$INSTANCE_ID" --cluster="$CLUSTER_ID" --region="$REGION" --format="value(name)" >/dev/null 2>&1; then
  echo "AlloyDB instance '$INSTANCE_ID' already exists in cluster '$CLUSTER_ID' (region $REGION). Skipping creation."
else
# --- Create Primary Instance ---
 echo "Creating primary instance: ${INSTANCE_ID} in cluster ${CLUSTER_ID}..."
 gcloud alloydb instances create "${INSTANCE_ID}" \
     --cluster="${CLUSTER_ID}" \
     --region="${REGION}" \
     --instance-type=PRIMARY \
     --machine-type="${MACHINE_TYPE}" \
     --database-flags="alloydb_ai_nl.enabled=on,alloydb.iam_authentication=on,google_ml_integration.enable_model_support=on,password.enforce_complexity=on,google_ml_integration.enable_ai_query_engine=on" \
     --availability-type=REGIONAL # Use REGIONAL for HA, ZONAL for basic instance
fi

# Check if instance creation succeeded
if [ $? -eq 0 ]; then
    echo "AlloyDB primary instance '${INSTANCE_ID}' created successfully."
else
    echo "Error creating primary instance '${INSTANCE_ID}'. Exiting."
    exit 1
fi

echo "AlloyDB cluster and primary instance creation script completed."