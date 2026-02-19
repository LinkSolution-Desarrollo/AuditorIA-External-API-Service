#!/usr/bin/env bash
# =============================================================================
# 1-setup.sh — Setup único de infraestructura GCP para AuditorIA
# =============================================================================
# Ejecutar UNA sola vez antes del primer deploy.
# Uso: bash gcp-deploy/1-setup.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/config.env"

echo "=============================================="
echo " AuditorIA — Setup de infraestructura GCP"
echo " Proyecto : ${GCP_PROJECT}"
echo " Región   : ${GCP_REGION}"
echo "=============================================="

# ── Configurar proyecto activo ─────────────────────────────────────────────
gcloud config set project "${GCP_PROJECT}"

# ── Habilitar APIs necesarias ──────────────────────────────────────────────
echo ""
echo "[1/8] Habilitando APIs de GCP..."
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  iam.googleapis.com \
  servicenetworking.googleapis.com \
  --quiet

# ── Artifact Registry ──────────────────────────────────────────────────────
echo ""
echo "[2/8] Creando Artifact Registry..."
if gcloud artifacts repositories describe "${AR_REPO}" \
     --location="${GCP_REGION}" --project="${GCP_PROJECT}" &>/dev/null; then
  echo "  → Ya existe: ${AR_REPO}"
else
  gcloud artifacts repositories create "${AR_REPO}" \
    --repository-format=docker \
    --location="${GCP_REGION}" \
    --description="Imágenes Docker de AuditorIA"
  echo "  → Creado: ${AR_REPO}"
fi
gcloud auth configure-docker "${AR_HOST}" --quiet

# ── Service Account ────────────────────────────────────────────────────────
echo ""
echo "[3/8] Creando Service Account..."
if gcloud iam service-accounts describe "${SA_EMAIL}" --project="${GCP_PROJECT}" &>/dev/null; then
  echo "  → Ya existe: ${SA_EMAIL}"
else
  gcloud iam service-accounts create "${SA_NAME}" \
    --display-name="AuditorIA Cloud Run Runner" \
    --project="${GCP_PROJECT}"
  echo "  → Creado: ${SA_EMAIL}"
fi

# Permisos necesarios para el Service Account
for ROLE in \
  "roles/cloudsql.client" \
  "roles/storage.objectAdmin" \
  "roles/secretmanager.secretAccessor" \
  "roles/run.invoker"; do
  gcloud projects add-iam-policy-binding "${GCP_PROJECT}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="${ROLE}" \
    --quiet
done
echo "  → Permisos asignados"

# ── GCS Bucket para MinIO ──────────────────────────────────────────────────
echo ""
echo "[4/8] Creando bucket GCS para datos de MinIO..."
if gsutil ls -b "gs://${MINIO_DATA_BUCKET}" &>/dev/null; then
  echo "  → Ya existe: gs://${MINIO_DATA_BUCKET}"
else
  gsutil mb -p "${GCP_PROJECT}" -l "${GCP_REGION}" "gs://${MINIO_DATA_BUCKET}"
  echo "  → Creado: gs://${MINIO_DATA_BUCKET}"
fi
# Dar acceso al SA sobre el bucket
gsutil iam ch "serviceAccount:${SA_EMAIL}:roles/storage.objectAdmin" "gs://${MINIO_DATA_BUCKET}"

# ── Cloud SQL ──────────────────────────────────────────────────────────────
echo ""
echo "[5/8] Creando instancia Cloud SQL (PostgreSQL 16)..."
echo "      NOTA: Este paso puede tardar 5-10 minutos..."
if gcloud sql instances describe "${SQL_INSTANCE}" --project="${GCP_PROJECT}" &>/dev/null; then
  echo "  → Ya existe: ${SQL_INSTANCE}"
else
  gcloud sql instances create "${SQL_INSTANCE}" \
    --database-version=POSTGRES_16 \
    --tier=db-f1-micro \
    --region="${GCP_REGION}" \
    --storage-type=SSD \
    --storage-size=10GB \
    --no-storage-auto-increase \
    --availability-type=zonal \
    --authorized-networks="0.0.0.0/0" \
    --project="${GCP_PROJECT}"
  echo "  → Instancia creada: ${SQL_INSTANCE}"
fi

# Capturar IP pública de Cloud SQL
SQL_PUBLIC_IP=$(gcloud sql instances describe "${SQL_INSTANCE}" \
  --project="${GCP_PROJECT}" \
  --format="value(ipAddresses[0].ipAddress)")
echo "  → IP pública Cloud SQL: ${SQL_PUBLIC_IP}"

# Capturar connection name para el Auth Proxy
CLOUD_SQL_CONNECTION_NAME=$(gcloud sql instances describe "${SQL_INSTANCE}" \
  --project="${GCP_PROJECT}" \
  --format="value(connectionName)")
echo "  → Connection Name: ${CLOUD_SQL_CONNECTION_NAME}"

# Crear base de datos
if gcloud sql databases describe "${SQL_DB}" --instance="${SQL_INSTANCE}" --project="${GCP_PROJECT}" &>/dev/null; then
  echo "  → Base de datos '${SQL_DB}' ya existe"
else
  gcloud sql databases create "${SQL_DB}" \
    --instance="${SQL_INSTANCE}" \
    --project="${GCP_PROJECT}"
  echo "  → Base de datos '${SQL_DB}' creada"
fi

# Crear usuario de base de datos
echo "  → Configurando usuario de BD '${SQL_USER}'..."
echo ""
echo "  ⚠  Ingresá una contraseña segura para el usuario '${SQL_USER}' de PostgreSQL:"
read -s -r POSTGRES_PASSWORD
echo ""

gcloud sql users create "${SQL_USER}" \
  --instance="${SQL_INSTANCE}" \
  --password="${POSTGRES_PASSWORD}" \
  --project="${GCP_PROJECT}" 2>/dev/null || \
gcloud sql users set-password "${SQL_USER}" \
  --instance="${SQL_INSTANCE}" \
  --password="${POSTGRES_PASSWORD}" \
  --project="${GCP_PROJECT}"
echo "  → Usuario '${SQL_USER}' configurado"

# ── Secret Manager ─────────────────────────────────────────────────────────
echo ""
echo "[6/8] Configurando secrets en Secret Manager..."

create_or_update_secret() {
  local SECRET_NAME="$1"
  local SECRET_VALUE="$2"
  if gcloud secrets describe "${SECRET_NAME}" --project="${GCP_PROJECT}" &>/dev/null; then
    echo "${SECRET_VALUE}" | gcloud secrets versions add "${SECRET_NAME}" \
      --data-file=- --project="${GCP_PROJECT}"
    echo "  → Secret actualizado: ${SECRET_NAME}"
  else
    echo "${SECRET_VALUE}" | gcloud secrets create "${SECRET_NAME}" \
      --data-file=- \
      --replication-policy=automatic \
      --project="${GCP_PROJECT}"
    echo "  → Secret creado: ${SECRET_NAME}"
  fi
}

create_or_update_secret "POSTGRES_PASSWORD" "${POSTGRES_PASSWORD}"

echo ""
echo "  ⚠  Ingresá la contraseña para MinIO (MINIO_ROOT_PASSWORD):"
read -s -r MINIO_ROOT_PASSWORD
echo ""
create_or_update_secret "MINIO_ROOT_PASSWORD" "${MINIO_ROOT_PASSWORD}"

echo ""
echo "  ⚠  Ingresá tu DEEPGRAM_API_KEY:"
read -r DEEPGRAM_API_KEY
create_or_update_secret "DEEPGRAM_API_KEY" "${DEEPGRAM_API_KEY}"

echo ""
echo "  ⚠  Ingresá tu OPENAI_API_KEY:"
read -r OPENAI_API_KEY
create_or_update_secret "OPENAI_API_KEY" "${OPENAI_API_KEY}"

# ── Crear base de datos para Keycloak ─────────────────────────────────────
echo ""
echo "[7/8] Creando base de datos para Keycloak..."
if gcloud sql databases describe "keycloak" --instance="${SQL_INSTANCE}" --project="${GCP_PROJECT}" &>/dev/null; then
  echo "  → Base de datos 'keycloak' ya existe"
else
  gcloud sql databases create "keycloak" \
    --instance="${SQL_INSTANCE}" \
    --project="${GCP_PROJECT}"
  echo "  → Base de datos 'keycloak' creada"
fi

# ── Guardar valores generados ──────────────────────────────────────────────
echo ""
echo "[8/8] Guardando valores generados..."
cat > "${SCRIPT_DIR}/.generated.env" <<EOF
# Auto-generado por 1-setup.sh — NO commitear este archivo
export CLOUD_SQL_CONNECTION_NAME="${CLOUD_SQL_CONNECTION_NAME}"
export SQL_PUBLIC_IP="${SQL_PUBLIC_IP}"
EOF
echo "  → Guardado en gcp-deploy/.generated.env"

echo ""
echo "=============================================="
echo " Setup completado exitosamente!"
echo "=============================================="
echo ""
echo "  Cloud SQL Connection Name: ${CLOUD_SQL_CONNECTION_NAME}"
echo "  Cloud SQL IP pública:      ${SQL_PUBLIC_IP}"
echo "  Artifact Registry:         ${AR_HOST}/${GCP_PROJECT}/${AR_REPO}"
echo ""
echo "  Próximo paso: bash gcp-deploy/2-deploy.sh"
echo "=============================================="
