# Cloud Run Deployment Script

This project uses a `deploy.sh` script to automate:

- Building a Docker image
- Pushing it to Google Artifact Registry
- Deploying it to our existing **Cloud Run** service

---

## .env Setup

The .env file has the following variables, ensure they are correct.

```env
DATABASE_URL
DATABASE_URL_V1
GOOGLE_API_KEY
NL_CONFIG_NAME
LANGSMITH_TRACING
LANGSMITH_API_KEY
LANGSMITH_PROJECT
LANGSMITH_ENDPOINT
```

**Note:** Ensure `DATABASE_URL` and `DATABASE_URL_V1` use **localhost** before running the script.
For example:
DATABASE_URL=postgresql://postgres:vecbench@localhost:5432/postgres_v2
DATABASE_URL_V1=postgresql://postgres:postpost@localhost:5433/vecbench

---

## Script Variables (in `deploy.sh`)

| Variable            | Description |
|---------------------|-------------|
| `REGION`            | GCP region for **Artifact Registry** (e.g., `us-west4`) |
| `PROJECT_ID`        | GCP project ID where the registry exists |
| `REPO_NAME`         | Name of your **Artifact Registry** repository |
| `IMAGE_NAME`        | Name of the Docker image to build and push |
| `TAG`               | Docker image tag (used for versioning, e.g., `py_try`) |
| `SERVICE_NAME`      | Name of your existing **Cloud Run** service |
| `SERVICE_REGION`    | Region where the Cloud Run service is deployed (e.g., `us-west2`) |
| `DEPLOYMENT_PROJECT`| GCP project ID where the **Cloud Run** service is deployed |
| `REMOTE_IMAGE`      | Full path to the Docker image in Artifact Registry |
| `.env`              | File containing all runtime environment variables |
| `--set-env-vars`    | Passes environment variables into the Cloud Run service during deployment |

---

## Running the Script

To deploy the updated image to Cloud Run:

```bash
chmod +x deploy.sh
./deploy.sh
```

---
