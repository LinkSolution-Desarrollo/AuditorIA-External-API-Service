#!/usr/bin/env bash
# =============================================================================
# 2-deploy.sh — Build de imágenes y deploy de servicios a Cloud Run
# =============================================================================
# Uso: bash gcp-deploy/2-deploy.sh
# Prerequisito: haber ejecutado gcp-deploy/1-setup.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${SCRIPT_DIR}/config.env"
source "${SCRIPT_DIR}/.generated.env"   # CLOUD_SQL_CONNECTION_NAME, SQL_PUBLIC_IP

echo "=============================================="
echo " AuditorIA — Deploy a Cloud Run"
echo " Proyecto : ${GCP_PROJECT}"
echo " Región   : ${GCP_REGION}"
echo "=============================================="

# ── Leer secrets desde Secret Manager ─────────────────────────────────────
echo ""
echo "[0/6] Leyendo secrets..."
POSTGRES_PASSWORD=$(gcloud secrets versions access latest \
  --secret="POSTGRES_PASSWORD" --project="${GCP_PROJECT}")
MINIO_ROOT_PASSWORD=$(gcloud secrets versions access latest \
  --secret="MINIO_ROOT_PASSWORD" --project="${GCP_PROJECT}")
DEEPGRAM_API_KEY=$(gcloud secrets versions access latest \
  --secret="DEEPGRAM_API_KEY" --project="${GCP_PROJECT}")
OPENAI_API_KEY=$(gcloud secrets versions access latest \
  --secret="OPENAI_API_KEY" --project="${GCP_PROJECT}")
echo "  → Secrets cargados"

# Generar access key de MinIO desde la contraseña (user = "minioadmin")
MINIO_ROOT_USER="minioadmin"

# ── Función helper: obtener URL de un servicio Cloud Run ───────────────────
get_service_url() {
  gcloud run services describe "$1" \
    --region="${GCP_REGION}" \
    --project="${GCP_PROJECT}" \
    --format="value(status.url)" 2>/dev/null || echo ""
}

# ── [1/6] Build y deploy de MinIO ─────────────────────────────────────────
echo ""
echo "[1/6] Deployando MinIO..."

# MinIO usa imagen oficial — no requiere build
# Cloud Run con GCS FUSE para persistencia de datos
gcloud run deploy "${SVC_MINIO}" \
  --image="quay.io/minio/minio:RELEASE.2025-01-18T00-31-37Z" \
  --region="${GCP_REGION}" \
  --project="${GCP_PROJECT}" \
  --service-account="${SA_EMAIL}" \
  --port=9000 \
  --min-instances=1 \
  --max-instances=1 \
  --memory=512Mi \
  --cpu=1 \
  --no-cpu-throttling \
  --add-volume="name=minio-data,type=cloud-storage,bucket=${MINIO_DATA_BUCKET}" \
  --add-volume-mount="volume=minio-data,mount-path=/data" \
  --set-env-vars="MINIO_ROOT_USER=${MINIO_ROOT_USER},MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD}" \
  --args="server,/data,--console-address,:9001" \
  --allow-unauthenticated \
  --quiet

MINIO_URL=$(get_service_url "${SVC_MINIO}")
echo "  → MinIO URL: ${MINIO_URL}"

# ── [2/6] Deploy de Keycloak ───────────────────────────────────────────────
echo ""
echo "[2/6] Deployando Keycloak..."

# Keycloak conecta a Cloud SQL vía IP pública
KC_DB_URL="jdbc:postgresql://${SQL_PUBLIC_IP}:5432/keycloak"

gcloud run deploy "${SVC_KEYCLOAK}" \
  --image="quay.io/keycloak/keycloak:26.0.0" \
  --region="${GCP_REGION}" \
  --project="${GCP_PROJECT}" \
  --service-account="${SA_EMAIL}" \
  --port=8080 \
  --min-instances=1 \
  --max-instances=2 \
  --memory=1Gi \
  --cpu=1 \
  --set-env-vars="KC_DB=postgres,KC_DB_URL=${KC_DB_URL},KC_DB_USERNAME=${SQL_USER},KC_DB_PASSWORD=${POSTGRES_PASSWORD},KEYCLOAK_ADMIN=admin,KEYCLOAK_ADMIN_PASSWORD=admin,KC_HTTP_ENABLED=true,KC_PROXY_HEADERS=xforwarded" \
  --args="start-dev" \
  --allow-unauthenticated \
  --quiet

KEYCLOAK_URL=$(get_service_url "${SVC_KEYCLOAK}")
echo "  → Keycloak URL: ${KEYCLOAK_URL}"

# ── [3/6] Build y deploy del Backend ──────────────────────────────────────
echo ""
echo "[3/6] Build y deploy del Backend..."

# Build de imagen del Backend
BACKEND_IMAGE="${IMAGE_PREFIX}/backend:latest"
gcloud builds submit "${ROOT_DIR}/AuditorIA-App/Backend" \
  --tag="${BACKEND_IMAGE}" \
  --project="${GCP_PROJECT}" \
  --quiet

# Deploy Backend con Cloud SQL Auth Proxy (socket)
DB_URL="postgresql+asyncpg://${SQL_USER}:${POSTGRES_PASSWORD}@/${SQL_DB}?host=/cloudsql/${CLOUD_SQL_CONNECTION_NAME}"

gcloud run deploy "${SVC_BACKEND}" \
  --image="${BACKEND_IMAGE}" \
  --region="${GCP_REGION}" \
  --project="${GCP_PROJECT}" \
  --service-account="${SA_EMAIL}" \
  --port=8000 \
  --min-instances=1 \
  --max-instances=5 \
  --memory=1Gi \
  --cpu=2 \
  --add-cloudsql-instances="${CLOUD_SQL_CONNECTION_NAME}" \
  --set-env-vars="DB_URL=${DB_URL},KEYCLOAK_SERVER_URL=${KEYCLOAK_URL},KEYCLOAK_REALM=${KC_REALM},KEYCLOAK_CLIENT_ID=${KC_CLIENT_ID},MINIO_URL=${MINIO_URL},S3_ENDPOINT=${MINIO_URL},S3_ACCESS_KEY=${MINIO_ROOT_USER},S3_SECRET_KEY=${MINIO_ROOT_PASSWORD},MINIO_ACCESS_KEY=${MINIO_ROOT_USER},MINIO_SECRET_ACCESS_KEY=${MINIO_ROOT_PASSWORD},OPENAI_API_KEY=${OPENAI_API_KEY},APP_ENV=production" \
  --allow-unauthenticated \
  --quiet

BACKEND_URL=$(get_service_url "${SVC_BACKEND}")
echo "  → Backend URL: ${BACKEND_URL}"

# ── [4/6] Build y deploy del Worker-Deepgram ─────────────────────────────
echo ""
echo "[4/6] Build y deploy del Worker-Deepgram..."

WORKER_IMAGE="${IMAGE_PREFIX}/worker-deepgram:latest"
gcloud builds submit "${ROOT_DIR}/AuditorIA-App/Worker-Deepgram" \
  --tag="${WORKER_IMAGE}" \
  --project="${GCP_PROJECT}" \
  --quiet

gcloud run deploy "${SVC_WORKER_DEEPGRAM}" \
  --image="${WORKER_IMAGE}" \
  --region="${GCP_REGION}" \
  --project="${GCP_PROJECT}" \
  --service-account="${SA_EMAIL}" \
  --port=8080 \
  --min-instances=1 \
  --max-instances=1 \
  --memory=512Mi \
  --cpu=1 \
  --no-cpu-throttling \
  --set-env-vars="BACKEND_URL=${BACKEND_URL},MINIO_URL=${MINIO_URL},S3_ENDPOINT=${MINIO_URL},S3_ACCESS_KEY=${MINIO_ROOT_USER},S3_SECRET_KEY=${MINIO_ROOT_PASSWORD},AUDIO_BUCKET_NAME=audios,DEEPGRAM_API_KEY=${DEEPGRAM_API_KEY},DEEPGRAM_MODEL=nova-3" \
  --no-allow-unauthenticated \
  --quiet

echo "  → Worker-Deepgram deployado"

# ── [5/6] Build y deploy del Frontend ─────────────────────────────────────
echo ""
echo "[5/6] Build y deploy del Frontend..."

# El Frontend necesita las URLs como build-args (baked at build time).
# gcloud builds submit no soporta --build-arg directamente, usamos un cloudbuild.yaml temporal.
FRONTEND_IMAGE="${IMAGE_PREFIX}/frontend:latest"
FRONTEND_CB_YAML="${ROOT_DIR}/AuditorIA-App/Frontend/cloudbuild-deploy.yaml"
cat > "${FRONTEND_CB_YAML}" <<CBEOF
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args:
      - build
      - '--build-arg=NEXT_PUBLIC_API_URL=${BACKEND_URL}'
      - '--build-arg=NEXT_PUBLIC_KEYCLOAK_URL=${KEYCLOAK_URL}'
      - '--build-arg=NEXT_PUBLIC_KEYCLOAK_REALM=${KC_REALM}'
      - '--build-arg=NEXT_PUBLIC_KEYCLOAK_CLIENT_ID=${KC_CLIENT_ID}'
      - '-t'
      - '${FRONTEND_IMAGE}'
      - '.'
images:
  - '${FRONTEND_IMAGE}'
CBEOF

gcloud builds submit "${ROOT_DIR}/AuditorIA-App/Frontend" \
  --config="${FRONTEND_CB_YAML}" \
  --project="${GCP_PROJECT}" \
  --quiet

rm -f "${FRONTEND_CB_YAML}"

gcloud run deploy "${SVC_FRONTEND}" \
  --image="${FRONTEND_IMAGE}" \
  --region="${GCP_REGION}" \
  --project="${GCP_PROJECT}" \
  --service-account="${SA_EMAIL}" \
  --port=3000 \
  --min-instances=0 \
  --max-instances=5 \
  --memory=512Mi \
  --cpu=1 \
  --set-env-vars="API_URL=${BACKEND_URL}" \
  --allow-unauthenticated \
  --quiet

FRONTEND_URL=$(get_service_url "${SVC_FRONTEND}")
echo "  → Frontend URL: ${FRONTEND_URL}"

# ── [6/6] Actualizar Keycloak con URL pública ─────────────────────────────
echo ""
echo "[6/6] Actualizando Keycloak con su URL pública..."
gcloud run services update "${SVC_KEYCLOAK}" \
  --region="${GCP_REGION}" \
  --project="${GCP_PROJECT}" \
  --update-env-vars="KC_HOSTNAME=${KEYCLOAK_URL}" \
  --quiet
echo "  → Keycloak hostname actualizado"

# ── Resumen ────────────────────────────────────────────────────────────────
echo ""
echo "=============================================="
echo " Deploy completado exitosamente!"
echo "=============================================="
echo ""
echo "  Frontend  : ${FRONTEND_URL}"
echo "  Backend   : ${BACKEND_URL}"
echo "  Keycloak  : ${KEYCLOAK_URL}"
echo "  MinIO API : ${MINIO_URL}"
echo ""
echo "  Realm de Keycloak : ${KC_REALM}"
echo "  Admin Keycloak    : admin / admin"
echo ""
echo "  IMPORTANTE: Configurá los redirect URIs en Keycloak:"
echo "  → ${KEYCLOAK_URL}/admin → Realm '${KC_REALM}' → Clients → ${KC_CLIENT_ID}"
echo "  → Valid redirect URIs: ${FRONTEND_URL}/*"
echo "  → Web origins: ${FRONTEND_URL}"
echo "=============================================="
