#!bin/bash

#bucket creation varibles
export LOCATION="us-central1" #No need to change this
export STORAGE_CLASS="STANDARD" #No need to change this
export FOLDERS="" #Need to provide folder and sub folders for eg raw/forecast,raw/ecommexport CREATE_BUCKET="" # Need to provide bucket name which we need to create for eg alloydb-gc-usecase-test12

export PROJECT_ID=""  # Need to provide project id name here
export INSTANCE_NAME="" # Need to provide Cloud SQL mysql instance name
export REGION="us-central1" # Region for the instance, No need to change here
export TIER="db-n1-standard-1" # No need to change machine type here
export EDITION="ENTERPRISE" #No need to change here.
export ROOT_PASSWORD="" # Need to provide root password here
export DATABASE_VERSION="MYSQL_8_0_36" # MySQL major version, No need to change here mysql version

# If you prefer Private IP only, set PRIVATE_ONLY=true and provide VPC self-link
export PRIVATE_ONLY=false # No need to change here.
export VPC_SELF_LINK=""  # e.g. "projects/${PROJECT_ID}/global/networks/default", No need to change here
export ACCOUNT="" # Need to provide your account id which use to connect GCP
#####################################################################################

export REPO_URL="" # Need to provide clone git repo link here
export CLONE_DIR="raw_dataset" # Local repo folder name
export CLONE_DIR_ECOMM="" # Need to provide directory path for eg : /home/deepak_kumar214e17/raw_dataset/Ecommerce/dataset
export BUCKET_NAME="" # Need to provide Destination GCS path eg gs://alloydb-usecase/search-usecase/
export HOMEDIR="" # Need to provide Base home directory eg /home/deepak_kumar214e17
export FILES_TO_UPLOAD="fashion_dataset.csv" # No need to change here
##################
###############################################################
export HOST="127.0.0.1" # Local host used by proxy, No need to change here
export DB_NAME="" #Need to provide database name for eg mysql 
export APP_DB_NAME="" # Need to provide schema name for eg cloudsql_usecase
export SQL_FILE="ecomm_fashion_mysql_create_table.sql" # No need to change here
export PRE_SQL_FILE="ecomm_fashion_mysql_presql.sql" # No need to change here
export DB_USER="root" # No need to change here
export PASSWORD="" # Need to provide root password.

# --- New User Details ---
export NEW_USER="" # Need to provide new username here for eg app_user
export NEW_PASSWORD="" # Need to provide password for new username
export NEW_USER_DB_NAME="" # Need to provide same database name, The database this new user will primarily access
###############################################################################
#############################################
export TABLE_NAME="fashion_products"           # No need to change here

# GCS locations
export BUCKET_NAME="" # Need to provide bucket root for IAM grant for eg gs://alloydb-gc-usecase-newsetup/raw/ecomm/
export OBJECT_URI=""  # Need to provide full CVS path of bucket for ex gs://alloydb-gc-usecase-newsetup/raw/ecomm/fashion_dataset.csv full
export BUCKET_ROOT="" #Need to provide root bucket path here for eg gs://alloydb-gc-usecase-newsetup/

# CSV parsing options
export CSV_HAS_HEADER="false"                   # No need to change here set to "true" if first line is header
export CSV_DELIMITER=","                      # No need to change here set delimiter: "," ";" "|"
export CSV_QUOTE="\""                         # No need to change here typical '"'
export CSV_ESCAPE="\\\\"                      # No need to change here typical '\\'
export CSV_LINE_ENDING="\n"                   # No need to change here LF; use "\r\n" if needed

# Optional explicit column order (comma-separated, matching CSV order)
# Leave empty if table’s column order matches CSV exactly

#COLUMNS_LIST="product_id,category,brand,price,currency,available_from"
export COLUMNS_LIST="" # No need to change here 

# Fallback (Option 2) local path if needed
export LOCAL_FILE="/tmp/fashion_dataset.csv" # No need to change here

# Proxy credentials (for fallback)
export ROOT_USER="root" # No need to change here.
export PROXY_PORT="6543" # No need to change here.