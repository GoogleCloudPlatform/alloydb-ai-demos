#!/bin/bash
# Before running this script:
# Make sure the .env file has DATABASE_URL and DATABASE_URL_V1 set to use localhost.
# For example:
# DATABASE_URL=postgresql://postgres:vecbench@localhost:5432/postgres_v2
# DATABASE_URL_V1=postgresql://postgres:postpost@localhost:5433/vecbench
set -e

REGION="us-central1"
PROJECT_ID="dotengage"
REPO_NAME="skincare-usecase-repo"
IMAGE_NAME="skincare-usecase-app"
TAG="py_try"
SERVICE_NAME="skincare-app-dev"
SERVICE_REGION="us-central1"
DEPLOYMENT_PROJECT="dotengage"

REMOTE_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:${TAG}"

set -a
source .env
set +a

echo "Building Docker image: ${REMOTE_IMAGE}"
docker build -t "${REMOTE_IMAGE}" .

echo "Pushing Docker image..."
docker push "${REMOTE_IMAGE}"

echo "Deploying to Cloud Run service: ${SERVICE_NAME}"

gcloud run deploy "${SERVICE_NAME}" \
  --image "${REMOTE_IMAGE}" \
  --region "${SERVICE_REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --project "${DEPLOYMENT_PROJECT}" \
  --set-env-vars "DATABASE_URL=${DATABASE_URL},DATABASE_URL_V1=${DATABASE_URL_V1},GOOGLE_API_KEY=${GOOGLE_API_KEY},NL_CONFIG_NAME=${NL_CONFIG_NAME},LANGSMITH_TRACING=${LANGSMITH_TRACING},LANGSMITH_API_KEY=${LANGSMITH_API_KEY},LANGSMITH_PROJECT=${LANGSMITH_PROJECT},LANGSMITH_ENDPOINT=${LANGSMITH_ENDPOINT}"
  
echo "Deployment complete."