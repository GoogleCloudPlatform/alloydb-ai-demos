#!/bin/bash
# -----------------------------------------------------------------------------
# Script Name : ecomm_fashion_create_vm_pre_inst.sh
# Purpose     : Create (or reuse) a Compute Engine VM, optionally ensure network
#               access to AlloyDB (TCP 5432), copy pre-DDL scripts to the VM,
#               and execute the wrapper script that applies pre-setup SQL/DDL.
#
# Prerequisites:
#   - gcloud CLI installed and authenticated (gcloud auth login or ADC)
#   - Roles: Compute Admin (roles/compute.admin) to create VM/firewall rules
#   - VPC routing allows VM-to-AlloyDB connectivity (Private IP/peering/PSC)
#   - The source files exist at SRC_PATH on the local machine running this script
# -----------------------------------------------------------------------------
source ./fashion_config.sh
echo "Creating or verifying VM instance: $INSTANCE_NAME"

# --------------------------- gcloud Context -----------------------------------
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


sleep 30

# Check connectivity from VM to AlloyDB
echo "Checking connectivity to AlloyDB from VM..."
# ------------------------------ Copy Pre-DDL Files ----------------------------
# Pre-setup SQL scripts to be executed on the VM.

SCRIPT_FILES=("fashion_config.sh" "ecomm_fashion_pre_sql_wrapper.sh" "ecomm_fashion_presql.sql")
TGT_PATH="/home/${USERNAME}/"
SRC_PATH="$SRC_ECOMM"

for FILE in "${SCRIPT_FILES[@]}"; do
    echo "Copying $SRC_PATH$FILE"
    gcloud compute scp "${SRC_PATH}${FILE}" "${USERNAME}@${INSTANCE_NAME}:${TGT_PATH}" --zone="${ZONE_NAME}"
done

echo "Files copied successfully."

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
##############

# --------------------------- Execute Pre-DDL Wrapper --------------------------
echo "Executing DDL wrapper script on VM..."
gcloud compute ssh "${INSTANCE_NAME}" --zone="${ZONE_NAME}" --command="bash ${TGT_PATH}ecomm_fashion_pre_sql_wrapper.sh \"${ALLOYDB_IP}\""

if [ $? -eq 0 ]; then
    echo "DDL created successfully in AlloyDB."
else
    echo "Error creating DDL in AlloyDB. Exiting."
    exit 1
fi

echo "All done."