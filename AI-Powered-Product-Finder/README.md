# AI-Powered Product Finder Demo Application

## Application Overview

This demo application allows users to explore a fashion product catalog using intelligent search powered by **AlloyDB for PostgreSQL** and **Cloud SQL for PostgreSQL**, **Cloud SQL for MySQL**. It showcases advanced capabilities such as: 
- Semantic Queries 
- Hybrid Relevance Scoring (Full-Text Search + Vector Search) 
- Natural Language-to-SQL Conversion (exclusive to AlloyDB)
  
The application demonstrates features like vector embeddings, ScaNN indexing and the AI query operator ai.if (exclusive to AlloyDB) for semantic search. 

**Key Components Utilized**:
**AlloyDB for PostgreSQL**:

*AI Powered Product Finder*
- AlloyDB for PostgreSQL as the core database engine. 
- Create embeddings using the google_ml extension. 
- Perform vector similarity search through the pgvector extension. 
- Use the NL to SQL capability via the Data Agents. 
- Set the google_ml_integration.enable_ai_query_engine flag to true to enable AI.IF. 
 
*MCP Chatbot* 
- AlloyDB for PostgreSQL: A high-performance, fully managed database engine that provides enterprise-grade scalability and 100% PostgreSQL compatibility. 
- Embeddings Creation (google_ml): A specialized extension that allows you to generate vector embeddings directly via SQL by calling Vertex AI models. 
- Vector Similarity (pgvector): An extension that enables storing high-dimensional vectors and performing fast semantic search to find contextually related data. 
 
 
**Cloud SQL for PostgreSQL**:

*AI Powered Product Finder*
- Cloud SQL for PostgreSQL as the primary database platform. 
- Embeddings creation (using google_ml extension): Enables generating text embeddings directly inside Cloud SQL using built‑in Google ML models. 
- Vector similarity (using pgvector extension): Provides native vector storage and similarity search capabilities for semantic and AI-driven queries. 

*MCP Chatbot*
- CloudSQL for PostgreSQL: A high-performance, fully managed database engine that provides enterprise-grade scalability and 100% PostgreSQL compatibility. 
- Embeddings Creation (google_ml): A specialized extension that allows you to generate vector embeddings directly via SQL by calling Vertex AI models. 
- Vector Similarity (pgvector): An extension that enables storing high-dimensional vectors and performing fast semantic search to find contextually related data. 
 
**Cloud SQL for MySQL**: 

*AI Powered Product Finder* 
- Cloud SQL for MySQL as the primary database platform. 
- Enable the cloudsql_vector flag to allow vector embedding storage and vector similarity search capabilities.
  
*MCP Chatbot* 
- Cloud SQL for MySQL: A high-performance, fully managed database engine that provides enterprise-grade scalability and 100% PostgreSQL compatibility. 
- Embeddings Creation (google_ml): A specialized extension that allows you to generate vector embeddings directly via SQL by calling Vertex AI models. 
- Vector Similarity (pgvector): An extension that enables storing high-dimensional vectors and performing fast semantic search to find contextually related data. 
 
**Environment setup** includes:

*   GCS bucket creation
*   SQL instance creation
*   Schema and table creation
*   VM creation (AlloyDB)
*   Configuration setup
*   Dataset loading & Pre‑SQL transformations

## Pre-requisites:

Before starting the setup, ensure the following:

### **Accounts & Access**

*   GitHub account
*   GCP account with **Admin** permissions
*   Cloud SQL MySQL admin access
*   Cloud SQL PostgreSQL admin access
*   AlloyDB PostgreSQL admin access
*   A GCS bucket created in the format:

alloydb-usecase/search-usecase  
  

### **Environment Configuration**

Update required variables(below) in fashion_config.sh under Ingestion folder:

*   PROJECT\_ID
*   REGION
*   DB\_PASSWORD
*   BUCKET\_NAME
*   FOLDERS (e.g., raw/forecast, raw/ecomm, raw/eda)
*   HOMEDIR
*   CLONE\_DIR
*   CLONE\_DIR\_ECOMM
*   CLUSTER\_ID, INSTANCE\_ID
*   MACHINE\_TYPE (e.g., n2-highmem-2)
*   NETWORK\_NAME
*   ACCOUNT
*   LOCATION

**Generic Steps to Run Any Script in Google Cloud Shell:**

1\. Open Google Cloud Shell and run the following command: **gcloud auth login**

2\. Press Enter. When prompted to continue, type Y and press Enter again.

3\. A URL will be displayed. Click on the link, which will redirect you to the Google sign-in page.

4\. Select the appropriate Google account, click Continue, and grant the required permissions.

5\. After successful authentication, an authorization code will be generated.  
6\. Copy the code and paste it back into the Cloud Shell, then press Enter.

7\. Finally, set the required account and project by running the following commands:

*   gcloud config set account "<Account Id>"
*   gcloud config set project "Project Id"

**Cloud SQL for MySQL Parameters**

database-version = MYSQL\_8\_0\_36  
tier = db-n1-standard-1  
edition = ENTERPRISE  
enable-google-ml-integration = true  
  

**Required IAM Roles: Cloud SQL for PostgreSQL & AlloyDB for PostgreSQL**

*   aiplatform.user
*   vertexai.user

---

## Follow the Steps below to Create and Run the Application (Steps: 1-4):

## Step 1: Preprocessing

- Run the commands mentioned in README under Preprocessing folder
- fashion_products.csv (obtained as the output of preprocessing script) is used as the input dataset for the application.

---

## Step 2: Data Ingestion

**Clone or Download Scripts**

Place all setup scripts under the following path in Cloud Shell <home\_directory>/alloydb\_gc/agentic/script  

**Source Dataset Reference**

https://github.com/ldap/srcdump/tree/main/Ecommerce/dataset  
  

**Scripts Included**

**Common Scripts**

*   agentic\_config.sh
*   bucket\_create.sh

**Scripts to be used for AlloyDB for PostgreSQL**

*   alloydb\_postgres\_cluster\_creation.sh
*   ecomm\_fashion\_create\_vm\_inst.sh
*   ecomm\_fashion\_wrapper\_ddl.sh
*   ecomm\_fashion\_ddl.sql
*   ecomm\_fashion\_load\_data\_alloydb.sh
*   ecomm\_fashion\_pre\_sql.sh
*   ecomm\_fashion\_presql\_inst.sh
*   ecomm\_fashion\_presql.sql

**Scripts to be used for Cloud SQL for MySQL**

*   cloudsql\_mysql\_instance\_creation.sh
*   ecomm\_fashion\_mysql\_create\_table.sql
*   ecomm\_fashion\_mysql\_create\_ddl.sh
*   ecomm\_fashion\_mysql\_load\_data.sh
*   ecomm\_fashion\_mysql\_presql.sql
*   ecomm\_fashion\_mysql\_presql\_ddl.sh

**Scripts to be used for Cloud SQL for PostgreSQL**

*   cloudsql\_postgres\_instance\_creation.sh
*   ecomm\_fashion\_cloudsql\_create\_table.sql
*   ecomm\_fashion\_cloudsql\_create\_ddl.sh
*   ecomm\_fashion\_cloudsql\_load\_data.sh
*   ecomm\_fashion\_cloudsql\_presql.sql
*   ecomm\_fashion\_cloudsql\_presql.sh

**Step 2(a) – Create Required GCS Bucket Structure**

Run: bucket\_create.sh  
This creates the bucket + folders required to store datasets.

**Step 2(b) – Create Database Instances**

**MySQL**

Run: cloudsql\_mysql\_instance\_creation.sh  

**PostgreSQL**

Run: cloudsql\_postgres\_instance\_creation.sh  

**AlloyDB**

Run: alloydb\_postgres\_cluster\_creation.sh  
  

**Step 2(c) – Update Database Password (For Cloud SQL MySQL)**

Go to: GCP Console → Cloud SQL → Instances → Users  

Change **root** password → update in: agentic\_config.sh  
  

**Step 2(d) – Create Tables & Schema**

**MySQL**

Run: ecomm\_fashion\_mysql\_create\_ddl.sh  
Executes: ecomm\_fashion\_mysql\_create\_table.sql  

**PostgreSQL**

Run: ecomm\_fashion\_cloudsql\_create\_ddl.sh  
Executes: ecomm\_fashion\_cloudsql\_create\_table.sql  

**AlloyDB**

Run: ecomm\_fashion\_create\_vm\_inst.sh  

This:

*   Creates a VM
*   Executes ecomm\_fashion\_wrapper\_ddl.sh → runs ecomm\_fashion\_ddl.sql
*   Prompts encryption key → enter Alloydb
*   Creates schema: alloydb\_usecase

**Step 2(e) – Upload Dataset to GCS**

Place the dataset (fashion\_dataset.csv) into your Git folder.

Run: ecomm\_fashion\_git\_to\_gcs.sh  
This loads dataset into: alloydb-gc-usecase-newsetup/raw/ecomm  
  

**Step 2(f) – Load Data into Database** - Creates table fashion_products and loads data

**Cloud SQL for MySQL**

ecomm\_fashion\_mysql\_load\_data.sh  

**Cloud SQL for PostgreSQL**

ecomm\_fashion\_cloudsql\_load\_data.sh  

**AlloyDB for PostgreSQL**

ecomm\_fashion\_load\_data\_alloydb.sh  
  

**Step 2(g) – Pre‑SQL / Embedding Column Creation**

**Cloud SQL for MySQL**

ecomm\_fashion\_mysql\_presql\_ddl.sh  

Executes: ecomm\_fashion\_mysql\_presql.sql  

**Cloud SQL for PostgreSQL**

ecomm\_fashion\_cloudsql\_presql.sh  

**AlloyDB for PostgreSQL**

ecomm\_fashion\_presql\_inst.sh 

---

## Step 3: Run Backend

- **Step 3(a) AI Powered Product Finder (Search application)**

1. Create Configuration (.env) and replace with your credentials:

**AlloyDB for PostgreSQL**

*Note: For Data Agents, roles assigned to service account*:
- *roles/alloydb.databaseUser*
- *roles/cloudaicompanion.user*
- *roles/geminidataanalytics.dataAgentUser*
- roles/geminidataanalytics.queryDataUser
- *roles/serviceusage.serviceUsageConsumer*

```
CLUSTER_ID = <CLUSTER_ID>
INSTANCE_ID = <INSTANCE_ID>
INSTANCE_URI=<INSTANCE_URI>
PROJECT_ID = <PROJECT_ID>
LOCATION=<LOCATION_ID>
DB_USER=<DB_USER>
DB_PASSWORD=<DB_PASSWORD>
DB_NAME=<DB_NAME>
ALLOYDB_SCHEMA_NAME=<ALLOYDB_SCHEMA_NAME>
TABLE_NAME = "fashion_products"
EMBEDDING = "text-embedding-005" # Can be replaced with any google embedding models

# For Data Agent
NLA_API = "https://geminidataanalytics.googleapis.com/v1alpha/projects/<PROJECT_ID>/locations/<LOCATION_ID>:queryData" 

# To obtain a Google Cloud service account JSON key for a Data Agent, navigate to the IAM & Admin > Service Accounts section in the Google Cloud Console, select the service account, navigate to the "Keys" tab, select "Add Key" -> "Create new key", and choose JSON format.
NLA_SERVICE_ACCOUNT = "/nla-service-account.json" # Replace this with service account JSON key created by you (Provide the full path of the json)

CONTEXT_SET_ID = "projects/<PROJECT_ID>/locations/<LOCATION_ID>/contextSets/<DATA_AGENT_NAME>"
SCOPES = 'https://www.googleapis.com/auth/cloud-platform'

# Threshold values can be changed as per the requirement for the dataset
VECTOR_THRESHOLD = 0.5 
HYBRID_THRESHOLD = 0.3
RATING_THRESHOLD = 5
```

**Cloud SQL for PostgreSQL**
```
INSTANCE_CONNECTION_NAME=<NSTANCE_CONNECTION_NAME>
DB_USER=<DB_USER>
DB_PASSWORD=<DB_PASSWORD>
DB_NAME=<DB_NAME>
CLOUDSQL_SCHEMA_NAME=<CLOUDSQL_SCHEMA_NAME>
TABLE_NAME = "fashion_products"
VERTEX_LOCATION=<VERTEX_LOCATION>
EMBEDDING = "text-embedding-005" # Can be replaced with google embedding models of your choice to get best results
GENERATIVE_MODEL="gemini-2.5-flash-lite" # Can be replaced with gemini models of your choice to get best results

# Threshold values can be changed as per the requirement for the dataset
VECTOR_THRESHOLD = 0.5 
HYBRID_THRESHOLD = 0.3
RATING_THRESHOLD = 5
```

**Cloud SQL for MySQL**
```
INSTANCE_CONNECTION_NAME=<NSTANCE_CONNECTION_NAME>
DB_USER=<DB_USER>
DB_PASSWORD=<DB_PASSWORD>
DB_NAME=<DB_NAME>
MYSQL_SCHEMA_NAME=<MYSQL_SCHEMA_NAME>
TABLE_NAME = "fashion_products"
EMBEDDING = "text-embedding-005" # Can be replaced with google embedding models of your choice to get best results
VECTOR_THRESHOLD = 0.6 # Threshold value can be changed as per the requirement for the dataset
```

2. Run the below commands(common to all DBs- AlloyDB for PostgreSQL/Cloud SQL for PostgreSQL/ Cloud SQL for MySQL): 
```
cd Backend/Product-Finder
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port <PORT_NUMBER> --reload # Port number: 8080 or 8081 used
```
OpenAPI docs: 
http://localhost:<PORT_NUMBER>/docs

Endpoints: 
- GET /list-products (common to all)
- GET /list-brands (common to all)
- GET /list-categories (common to all)
- POST /search (for AlloyDB for PostgreSQL)
- POST /cloudsql/search (for Cloud SQL for PostgreSQL)
- POST /mysql/vector (for Cloud SQL for MySQL)

- **Step 3(b) AI Powered Product Finder (MCP Chatbot application)**

1. Create Configuration (.env) and replace with your credentials:

**AlloyDB for PostgreSQL**
```
INSTANCE_URI=<INSTANCE_URI>
DB_USER=<DB_USER>
DB_PASSWORD=<DB_PASSWORD>
DB_NAME=<DB_NAME>
ALLOYDB_SCHEMA_NAME=<ALLOYDB_SCHEMA_NAME>
PROJECT_ID=<PROJECT_ID>
LOCATION=<LOCATION>
MODEL_NAME=<MODEL_NAME>
MCP_SERVER_URL=<MCP_SERVER_URL>
```

**Cloud SQL for PostgreSQL**
```
INSTANCE_CONNECTION_NAME=<NSTANCE_CONNECTION_NAME>
DB_USER=<DB_USER>
DB_PASSWORD=<DB_PASSWORD>
DB_NAME=<DB_NAME>
CLOUDSQL_SCHEMA_NAME=<CLOUDSQL_SCHEMA_NAME>
PROJECT_ID=<PROJECT_ID>
LOCATION=<LOCATION>
MODEL_NAME=<MODEL_NAME>
MCP_SERVER_URL=<MCP_SERVER_URL>
```

**Cloud SQL for MySQL**
```
INSTANCE_CONNECTION_NAME=<NSTANCE_CONNECTION_NAME>
DB_USER=<DB_USER>
DB_PASSWORD=<DB_PASSWORD>
DB_NAME=<DB_NAME>
MYSQL_SCHEMA_NAME=<MYSQL_SCHEMA_NAME>
PROJECT_ID=<PROJECT_ID>
LOCATION=<LOCATION>
MODEL_NAME=<MODEL_NAME>
MCP_SERVER_URL=<MCP_SERVER_URL>
```

2. Run the below commands (common to all DBs- AlloyDB for PostgreSQL/Cloud SQL for PostgreSQL/ Cloud SQL for MySQL): 
```
cd Backend/Chatbot-MCP
python -m venv .venv && source .venv/bin/activate
```

- **Run MCP Server**:
```
cd Chatbot-MCP-Server
pip install -r requirements.txt
python <DB_NAME>_server.py # Replace <DB_NAME> with alloydb, cloudsql or mysql as per DB used 
```
*Note: This is a pre-requisite for running the below (for running MCP Client).*

Optional: Create a test script and run to make sure server is running correctly.

Upon successful testing, deploy the Chatbot MCP server to Google Cloud Run and retrieve the service URL. Configure this URL within the Chatbot MCP client application, then proceed with the client's final deployment to establish the cloud-based connection.

Tool created:
- Name: retrieve_neighbors_from_<DB_NAME>
- Purpose: Retrieve nearest-neighbor products from <DB_NAME> for the given natural language query

- **Run MCP Client**:
```
cd Chatbot-MCP-Client
pip install -r requirements.txt
python mcp_client.py
```
OpenAPI docs: 
http://localhost:<PORT_NUMBER>/docs # Port number used is 8001 in the script

Endpoints: 
- GET /health
- POST /chat

---

## Step 4: Run the Frontend (Angular)

*Follow the steps mentioned in README under Frontend folder*

 
  



