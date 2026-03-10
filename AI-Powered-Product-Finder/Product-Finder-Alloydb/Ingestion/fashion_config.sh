#!/bin/bash
# --- Configuration Variables (Update these as needed) Ecomm Alloydb---

#bucket creation varibles
export LOCATION="us-central1" #No need to change this
export STORAGE_CLASS="STANDARD" #No need to change this
export FOLDERS="" #Need to provide folder and sub folders for eg raw/forecast,raw/ecomm
export CREATE_BUCKET="" # Need to provide bucket name which we need to create for eg alloydb-gc-usecase-test12


export PROJECT_ID=""  # Need to provide project id name here
export REGION="us-central1" # Region where AlloyDB cluster will be created, No need to change here.
export CLUSTER_ID="" # Need to provide name of cluster eg alloydb-dev-cluster-new
export INSTANCE_ID=""  # Need to provide Primary Instance name for eg alloydb-dev-primary-new
export DB_PASSWORD="" # Need to provide database password here.
export MACHINE_TYPE="n2-highmem-2" # Machine type for the instance, No need to change here
export NETWORK_NAME="alloydb-network" # VPC network name, No need to change here
export ACCOUNT="" # Need to provide your account id which use to connect GCP

# --------------------------- Git Configuration -----------------------------------
export REPO_URL="" # Need to provide Git repo link here eg https://github.com/deepakbhalia1920/srcdump.git
export CLONE_DIR="raw_dataset" # Local repo directory
export CLONE_DIR_ECOMM="" #Need to provide path for clone the directory for eg /home/<username>/raw_dataset/Ecommerce/dataset
# Target GCS bucket/folder (must exist or gsutil should have permissions to create)
export BUCKET_NAME="" # Need to provide bucket path here eg gs://alloydb-gc-usecase-newsetup/raw/medical/
export HOMEDIR="" # Need to provide your home directory path eg /home/deepak_kumar214e17

export FILES_TO_UPLOAD="fashion_dataset.csv" # No need to change here
# --------------------------- VM Configuration ---------------------------------
export PRIMARY_INSTANCE_ID=""  # Need to provide Primary Instance name for eg alloydb-dev-primary-new
export INSTANCE_NAME="" # Need to provide virtual instance name here eg agent-my-vm
export ZONE_NAME="us-central1-a" # Zone for VM , No need to change here
export MACHINE_NAME="e2-medium" # Machine type, No need to change here
export IMAGE_FAMILY="debian-11" # OS image family , No need to change here
export IMAGE_PROJECT="debian-cloud"  # OS image project No need to change here
export TAG="ssh-access" # Network tag used for firewall targeting, No need to change here
export SCOPES="https://www.googleapis.com/auth/cloud-platform" # Broad scope (consider least-privilege SA), No need to change here.
# --------------------------- Account / Project --------------------------------
export VPC_NAME="default" # Target VPC network, No need to change here
export SUBNET_NAME="default" # Target subnet within VPC, No need to change here
export ALLOYDB_PORT=5432 # No need to change here

#########
export DATABASE_NAME="" #Need to provide database name for eg postgres
export SQL_FILE="ecomm_fashion_ddl.sql" # SQL file to execute, No need to change here
export USER="" # Need to provide user here for eg postgres
export PASSWORD="" # Need to mention here password which user need to access database.
# gcloud account/project 
########################################################
# AlloyDB details
export ALLOYDB_HOST="10.123.50.2" # No need to change here

export PRE_SQL_FILE="ecomm_fashion_presql.sql" # No need to change here
export USERNAME="" # Need to provide username which was mentioned in home directory 
################################################
export BUCKET_NAME_ROOT="" # Need to provide bucket root path for eg alloydb-gc-usecase-newsetup
#export ECOMM_TABLE="alloydb_usecase.fashion_products_0120"
export SCHEMA_NAME="" # Need to provide schema name for eg alloydb_usecase
export SRC_ECOMM="" # Provide source path where scripts present for Hybrid use case in cloud shell eg /home/deepak_kumar214e17/alloydb/ecomm/script/