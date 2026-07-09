#!/usr/bin/env bash
# Deploy prompt-optimizer to Cloud Run. All settings live in deploy.env.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$(dirname "$SCRIPT_DIR")"
# shellcheck source=deploy.env
source "$SCRIPT_DIR/deploy.env"

IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/${SERVICE_NAME}"
TAG="$(git -C "$SRC_DIR" rev-parse --short HEAD 2>/dev/null || echo manual)"
SA_EMAIL="${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "==> Enabling required APIs"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com aiplatform.googleapis.com \
  --project "$PROJECT_ID"

echo "==> Ensuring Artifact Registry repo '${AR_REPO}' in ${REGION}"
if ! gcloud artifacts repositories describe "$AR_REPO" \
    --location "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$AR_REPO" \
    --repository-format docker --location "$REGION" --project "$PROJECT_ID"
fi

echo "==> Ensuring runtime service account ${SA_EMAIL}"
if ! gcloud iam service-accounts describe "$SA_EMAIL" \
    --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$SERVICE_ACCOUNT" \
    --display-name "Prompt Optimizer Cloud Run" --project "$PROJECT_ID"
fi
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:${SA_EMAIL}" \
  --role roles/aiplatform.user --condition None >/dev/null

echo "==> Building ${IMAGE}:${TAG} with Cloud Build"
gcloud builds submit "$SRC_DIR" \
  --config "$SCRIPT_DIR/cloudbuild.yaml" \
  --substitutions "_IMAGE=${IMAGE}:${TAG}" \
  --ignore-file deploy/.gcloudignore \
  --project "$PROJECT_ID"

AUTH_FLAG="--no-allow-unauthenticated"
[ "$ALLOW_UNAUTHENTICATED" = "true" ] && AUTH_FLAG="--allow-unauthenticated"

echo "==> Deploying ${SERVICE_NAME} to Cloud Run (${REGION})"
gcloud run deploy "$SERVICE_NAME" \
  --image "${IMAGE}:${TAG}" \
  --region "$REGION" --project "$PROJECT_ID" \
  --service-account "$SA_EMAIL" \
  --memory "$MEMORY" --cpu "$CPU" \
  --min-instances "$MIN_INSTANCES" --max-instances "$MAX_INSTANCES" \
  --set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${VERTEX_LOCATION},GEMINI_MODEL=${GEMINI_MODEL}" \
  "$AUTH_FLAG"

URL="$(gcloud run services describe "$SERVICE_NAME" \
  --region "$REGION" --project "$PROJECT_ID" --format 'value(status.url)')"
echo "==> Deployed: $URL"
# Note: /healthz is a reserved path on *.run.app — Google's frontend intercepts
# it and returns its own 404, so probe /docs (or /openapi.json) instead.
echo "==> API docs: $URL/docs"
