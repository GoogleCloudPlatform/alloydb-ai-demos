
# MedIQ Demo Application

## Application Overview
This demo application is designed to provide **quick, accurate clinical insights**. It integrates **comprehensive medical datasets** containing information such as:

- Disease details
- Diagnostic tests
- Definitions
- Symptoms
- Causes
- Diagnosis
- Treatment protocols
- Prognosis
- Prevention strategies

Users can query disease‑related information, and the system generates **natural language responses** by aggregating data from structured sources and PDFs. This helps **streamline diagnostic workflows** and **improve patient care**.

**Key AlloyDB Components Utilized**: 
- **AlloyDB for PostgreSQL** (provides the database foundation) 
- **Embeddings creation** (with google_ml extension) using text-embedding-005 model 
- **Vector similarity** (with pgvector extension) using cosine similarity 
- AlloyDB AI Query Operator: **ai.generate** for creating natural language response from search results 
- **ScaNN** (optional, for large-scale deployments): Prefer ScaNN index with post‑creation ANALYZE when working with very large corpora and if supported in your environment
  
The demo combines two distinct data sources: 
- **Unstructured PDF data** (processed into chunks) 
- **Structured CSV data** (rows of tabulated information)
  
By combining embeddings, semantic retrieval, and response generation inside SQL, the application demonstrates how AlloyDB can unify insights from heterogeneous sources. This is achieved through a Table-Valued Function (TVF), which encapsulates query logic and outputs a reusable set of records. Careful query planning and orchestration ensure that both PDF and CSV data contribute meaningfully to the final natural language summary. 
 
---

## Prerequisites

Before starting the setup, ensure the following are ready.

### **Accounts and Access**
- **GitHub account** — for accessing datasets and scripts
- **Google Cloud Platform (GCP) account** with Admin access
- **AlloyDB PostgreSQL admin access**
- **GCS bucket**, with structure such as:
  alloydb-usecase/search-usecase

### **Required IAM Roles**
The service account must have these roles:

- aiplatform.user
- vertexai.user

### **Environment Configuration**
Update these variables in medical_config.sh:

- PROJECT_ID (GCP project ID)
- REGION (e.g. us-central1)
- CLUSTER_ID (AlloyDB cluster name)
- INSTANCE_ID (AlloyDB instance name)
- DB_PASSWORD
- MACHINE_TYPE (e.g. n2-highmem-2)
- NETWORK_NAME
- ACCOUNT (GCP login ID)
- LOCATION
- BUCKET_NAME
- FOLDERS (e.g. raw/forecast,raw/ecomm,raw/eda)
- SCHEMA_NAME (default: alloydb_usecase)
- HOMEDIR (Cloud Shell home directory)
- CLONE_DIR and dataset-specific clone paths


These variables must be configured correctly for all scripts to run successfully.

---

## Generic Steps to Run Any Script in Google Cloud Shell

1. Open Cloud Shell and run:
   gcloud auth login
2. Press **Enter**, then type **Y** when prompted.
3. Click the authentication URL displayed in the shell.
4. Sign in to your Google account and approve permissions.
5. Copy the generated authorization code and paste it into Cloud Shell.
6. Set the required account and project:
   gcloud config set account "<Account Id>"
   gcloud config set project "<Project Id>"

---

## Installation

### **Available Scripts**

| Script Name | Purpose |
|-------------|----------|
| `alloydb_postgres_cluster_creation.sh` | Creates AlloyDB cluster & primary instance |
| `bucket_create.sh` | Creates GCS bucket |
| `medical_create_vm_inst.sh` | Creates VM & AlloyDB tables |
| `medical_create_table.sql` | Defines DDL |
| `medical_create_wrapper_ddl.sh` | Executes table DDL |
| `medical_load_alloydb.sh` | Loads GCS data into AlloyDB |
| `medical_config.sh` | Main configuration file |

### **Script Directory**

Place all scripts under:
<home-directory>/alloydb/medical/script

Dataset repository example:
https://github.com/ldap/srcdump/tree/main/Ecommerce/dataset

---

## Usage — End‑to‑End Execution

### **Step 1: Create AlloyDB Cluster**
Run:
alloydb_postgres_cluster_creation.sh

### **Step 2: Clone Dataset Repository**
Ensure dataset directory structure:
<home-directory>/raw_dataset/
<home-directory>/alloydb/medical/script/

### **Step 3: Upload Dataset to GCS**
Ensure `disease_datafile.csv` is placed in the correct Git path.
Run:
medical_git_to_gcs.sh

Uploads to:
alloydb-gc-usecase-newsetup/raw/medical

### **Step 4: Create VM and Database Objects**
Run:
medical_create_vm_inst.sh
This script:
- Creates the VM
- Creates schema `alloydb_usecase`
- Executes DDL
- Prompts for encryption key → enter **Alloydb**

### **Step 5: Load Data into AlloyDB**
Run:
medical_load_alloydb.sh

Loads data into:
alloydb_usecase.disease_tests_info

---
