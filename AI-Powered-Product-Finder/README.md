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
 
The environment setup includes:

*   GCS bucket creation
*   SQL instance creation
*   Schema and table creation
*   VM creation (AlloyDB)
*   Configuration setup
*   Dataset loading & Pre‑SQL transformations

**Prerequisites:**

Before starting, ensure the following.

**Accounts & Access**

*   GitHub account
*   GCP account with **Admin** permissions
*   Cloud SQL MySQL admin access
*   Cloud SQL PostgreSQL admin access
*   AlloyDB PostgreSQL admin access
*   A GCS bucket created in the format:

alloydb-usecase/search-usecase  
  

**Configurations**

You must update required variables in the environment config files such as:

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

**Cloud SQL MySQL Parameters**

database-version = MYSQL\_8\_0\_36  
tier = db-n1-standard-1  
edition = ENTERPRISE  
enable-google-ml-integration = true  
  

**Cloud SQL PostgreSQL Required Roles**

Assign the following roles to the service account:

*   aiplatform.user
*   vertexai.user

**Installation:**

**Clone or Download Scripts**

Place all setup scripts under the following path in Cloud Shell <home\_directory>/alloydb\_gc/agentic/script  

**Source Dataset Reference**

https://github.com/ldap/srcdump/tree/main/Ecommerce/dataset  
  

**Scripts Included**

**Common Scripts**

*   agentic\_config.sh
*   bucket\_create.sh

**AlloyDB Scripts**

*   alloydb\_postgres\_cluster\_creation.sh
*   ecomm\_fashion\_create\_vm\_inst.sh
*   ecomm\_fashion\_wrapper\_ddl.sh
*   ecomm\_fashion\_ddl.sql
*   ecomm\_fashion\_load\_data\_alloydb.sh
*   ecomm\_fashion\_pre\_sql.sh
*   ecomm\_fashion\_presql\_inst.sh
*   ecomm\_fashion\_presql.sql

**Cloud SQL MySQL Scripts**

*   cloudsql\_mysql\_instance\_creation.sh
*   ecomm\_fashion\_mysql\_create\_table.sql
*   ecomm\_fashion\_mysql\_create\_ddl.sh
*   ecomm\_fashion\_mysql\_load\_data.sh
*   ecomm\_fashion\_mysql\_presql.sql
*   ecomm\_fashion\_mysql\_presql\_ddl.sh

**Cloud SQL PostgreSQL Scripts**

*   cloudsql\_postgres\_instance\_creation.sh
*   ecomm\_fashion\_cloudsql\_create\_table.sql
*   ecomm\_fashion\_cloudsql\_create\_ddl.sh
*   ecomm\_fashion\_cloudsql\_load\_data.sh
*   ecomm\_fashion\_cloudsql\_presql.sql
*   ecomm\_fashion\_cloudsql\_presql.sh

**Usage:**

Below is the unified runbook for all three databases.

**Step 0 – Create Required GCS Bucket Structure**

Run: bucket\_create.sh  
This creates the bucket + folders required to store datasets.

**Step 1 – Create Database Instances**

**MySQL**

Run: cloudsql\_mysql\_instance\_creation.sh  

**PostgreSQL**

Run: cloudsql\_postgres\_instance\_creation.sh  

**AlloyDB**

Run: alloydb\_postgres\_cluster\_creation.sh  
  

**Step 2 – Update Database Password (For Cloud SQL MySQL)**

Go to: GCP Console → Cloud SQL → Instances → Users  

Change **root** password → update in: agentic\_config.sh  
  

**Step 3 – Create Tables & Schema**

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

**Step 4 – Upload Dataset to GCS**

Place the dataset (fashion\_dataset.csv) into your Git folder.

Run: ecomm\_fashion\_git\_to\_gcs.sh  
This loads dataset into: alloydb-gc-usecase-newsetup/raw/ecomm  
  

**Step 5 – Load Data into Database**

**MySQL**

ecomm\_fashion\_mysql\_load\_data.sh  

**PostgreSQL**

ecomm\_fashion\_cloudsql\_load\_data.sh  

**AlloyDB**

ecomm\_fashion\_load\_data\_alloydb.sh  
  

**Step 6 – Pre‑SQL / Embedding Column Creation**

**MySQL**

ecomm\_fashion\_mysql\_presql\_ddl.sh  

Executes: ecomm\_fashion\_mysql\_presql.sql  

**PostgreSQL**

ecomm\_fashion\_cloudsql\_presql.sh  

**AlloyDB**

ecomm\_fashion\_presql\_inst.sh  
  

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

**Folder Structure:**

alloydb\_gc/  
└── agentic/  
└── script/  
├── agentic\_config.sh  
├── bucket\_create.sh  
├── cloudsql\_mysql\_instance\_creation.sh  
├── cloudsql\_postgres\_instance\_creation.sh  
├── alloydb\_postgres\_cluster\_creation.sh  
├── ecomm\_fashion\_mysql\_create\_table.sql  
├── ecomm\_fashion\_mysql\_create\_ddl.sh  
├── ecomm\_fashion\_cloudsql\_create\_table.sql  
├── ecomm\_fashion\_cloudsql\_create\_ddl.sh  
├── ecomm\_fashion\_wrapper\_ddl.sh  
├── ecomm\_fashion\_ddl.sql  
└── (all other scripts)
