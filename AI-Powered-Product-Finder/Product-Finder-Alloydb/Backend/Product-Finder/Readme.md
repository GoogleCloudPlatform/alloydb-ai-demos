**SERVICE ACCOUNT FOR NLA**:

To utilize the Natural Language API (NLA) and AlloyDB services within the <PROJECT_ID> project, a dedicated Service Account is required. This section details the identity, required permissions, and the IAM policy bindings.
Replace <PROJECT_ID> with your project id.

IAM Policy Bindings (JSON) The snippet below illustrates the official IAM policy bindings for the service account principal. This confirms the account is correctly mapped to the necessary roles. 
Assign the roles specified in the following JSON to your service account to enable NLA agent access.
Service account name : aia-alloydb-nla@<PROJECT_ID>.iam.gserviceaccount.com 
Sample JSON: 
[ { "bindings": { "members": "serviceAccount:aia-alloydb-nla@<PROJECT_ID>.iam.gserviceaccount.com", "role": "roles/alloydb.databaseUser" }, "etag": "BwZMkhhh2FY=", "version": 3 }, { "bindings": { "members": "serviceAccount:aia-alloydb-nla@<PROJECT_ID>.iam.gserviceaccount.com", "role": "roles/cloudaicompanion.user" }, "etag": "BwZMkhhh2FY=", "version": 3 }, { "bindings": { "members": "serviceAccount:aia-alloydb-nla@<PROJECT_ID>.iam.gserviceaccount.com", "role": "roles/geminidataanalytics.dataAgentUser" }, "etag": "BwZMkhhh2FY=", "version": 3 }, { "bindings": { "members": "serviceAccount:aia-alloydb-nla@<PROJECT_ID>.iam.gserviceaccount.com", "role": "roles/geminidataanalytics.queryDataUser" }, "etag": "BwZMkhhh2FY=", "version": 3 }, { "bindings": { "condition": { "expression": "request.time < timestamp(\"2026-01-08T11:19:33.767Z\")", "title": "developer-connect-connection-setup" }, "members": "serviceAccount:aia-alloydb-nla@<PROJECT_ID>.iam.gserviceaccount.com", "role": "roles/geminidataanalytics.queryDataUser" }, "etag": "BwZMkhhh2FY=", "version": 3 }, { "bindings": { "members": "serviceAccount:aia-alloydb-nla@<PROJECT_ID>.iam.gserviceaccount.com", "role": "roles/serviceusage.serviceUsageConsumer" }, "etag": "BwZMkhhh2FY=", "version": 3 } ]
 

**Sample input Payload**:

Vector:

{
  "question": "black shoes",
  "filters": {
        "price": {"min": 3, "max": 50},
        "rating": 2}
}
{
  "question": "watches for casual use for women",
  "filters": {"category": "Accessories",
        "price": {"min": 3, "max": 50},
        "brand": "Being Human",
        "rating": 2
}
}


Hybrid:

{
  "question": "black sports shoes",
  "filters": {
        "category": "Footwear",
        "price": {"min": 3, "max": 50},
        "brand": "Nike",
        "rating": 2
    }
}

NLTOSQL:
{
  "question": "shoes for women with price less than 10$",
  "filters": {
        "category": "Footwear",
        "price": {"min": 3, "max": 10},
        "brand": "Nike",
        "rating": 2
    }
}

AI.IF:

{
  "question": "Show me kurta sets similar to the ethnic summer ones but avoid anything too bright",
  "filters": {
        "category": "Apparel",
        "price": {"min": 3, "max": 50},
        "brand" : "Biba",
        "rating": 2
    }
}
