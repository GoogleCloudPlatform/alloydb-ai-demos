#!/bin/bash
# -----------------------------------------------------------------------------
# Script Name : ecomm_fashion_create_vm_inst.sh
# Purpose     : Create (or reuse) a Compute Engine VM, ensure network access
#               to AlloyDB (TCP 5432), copy DDL scripts to the VM, and execute
#               the wrapper script that applies DDL to AlloyDB.
#
# Prerequisites:
#   - gcloud CLI installed and authenticated (gcloud auth login or ADC)
#   - Roles: Compute Admin (roles/compute.admin) and ability to create firewall rules
#   - VPC routing allows VM-to-AlloyDB connectivity (typically Private IP/peering)
#   - The source files exist at SRC_PATH on the local machine running this script
# -----------------------------------------------------------------------------
source ./agentic_config.sh
echo "Creating or verifying VM instance: $INSTANCE_NAME"
# setting up account and project.
gcloud config set account ${ACCOUNT}
gcloud config set project ${PROJECT_ID}

# Check if VM exists and is running
VM_STATUS=$(gcloud compute instances describe "$INSTANCE_NAME" --zone="$ZONE_NAME" --format='get(status)' 2>/dev/null)
echo "Current VM status: $VM_STATUS"

if [[ "$VM_STATUS" == "RUNNING" ]]; then
    echo "VM $INSTANCE_NAME is already running. Continuing..."
else
    echo "VM $INSTANCE_NAME is not running. Creating VM..."
    gcloud compute instances create "${INSTANCE_NAME}" \
        --zone="${ZONE_NAME}" \
        --machine-type="${MACHINE_NAME}" \
        --image-family="${IMAGE_FAMILY}" \
        --image-project="${IMAGE_PROJECT}" \
        --tags="${TAG}" \
        --scopes="${SCOPES}" \
        --network="${VPC_NAME}" \
        --subnet="${SUBNET_NAME}" \
        --no-address
fi

if [ $? -ne 0 ]; then
    echo "Error while creating VM. Exiting."
    exit 1
fi
# ----------------------- Firewall for AlloyDB Access --------------------------
# Create a firewall rule that allows TCP 5432 from instances with the 'ssh-access' tag.


echo "Ensuring firewall rule for AlloyDB connectivity..."
gcloud compute firewall-rules describe allow-alloydb --format='get(name)' 2>/dev/null
if [ $? -ne 0 ]; then
    gcloud compute firewall-rules create allow-alloydb \
        --allow=tcp:${ALLOYDB_PORT} \
        --network=${VPC_NAME} \
        --source-tags=${TAG}
fi

echo "Waiting for VM and AlloyDB to be ready..."
gcloud compute ssh "${INSTANCE_NAME}" --zone="${ZONE_NAME}" --command="sudo apt-get update && sudo apt-get install -y netcat"

# Optional settle time; consider replacing with health checks if needed.
sleep 30

# Check connectivity from VM to AlloyDB
echo "Checking connectivity to AlloyDB from VM..."

# Copy DDL files to VM
SCRIPT_FILES=("agentic_config.sh" "agentic_alloydb_create_ddl.sh" "agentic_alloydb_create_table.sql")

TGT_PATH="/home/${USERNAME}/"
SRC_PATH="$SRC_AGENT"

for FILE in "${SCRIPT_FILES[@]}"; do
    echo "Copying $SRC_PATH$FILE"
    gcloud compute scp "${SRC_PATH}${FILE}" "${USERNAME}@${INSTANCE_NAME}:${TGT_PATH}" --zone="${ZONE_NAME}"
done

echo "Files copied successfully."

# --------------------------- Execute DDL Wrapper ------------------------------
#AlloyDB identifiers (optional, used for dynamic IP retrieval)
ALLOYDB_CLUSTER_ID="${CLUSTER_ID}"
ALLOYDB_PRIMARY_INSTANCE_ID="${PRIMARY_INSTANCE_ID}"
ALLOYDB_REGION="${REGION}"

ALLOYDB_IP=$(gcloud alloydb instances describe ${ALLOYDB_PRIMARY_INSTANCE_ID} \
    --cluster=${ALLOYDB_CLUSTER_ID} \
    --region=${ALLOYDB_REGION} \
    --format="value(ipAddress)") # Or value(networkConfig.privateIpAddress) if that's what worked

echo "${ALLOYDB_IP}"
if [ -z "$ALLOYDB_IP" ]; then
    echo "Error: Could not retrieve AlloyDB IP address. Exiting."
    exit 1
fi

echo "AlloyDB Primary Instance IP: ${ALLOYDB_IP}"
export ALLOYDB_IP

echo "Executing DDL wrapper script on VM..."
gcloud compute ssh "${INSTANCE_NAME}" --zone="${ZONE_NAME}" --command="bash ${TGT_PATH}agentic_alloydb_create_ddl.sh \"${ALLOYDB_IP}\""

if [ $? -eq 0 ]; then
    echo "DDL created successfully in AlloyDB."
else
    echo "Error creating DDL in AlloyDB. Exiting."
    exit 1
fi

echo "All done."