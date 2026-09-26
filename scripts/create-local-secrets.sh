#!/usr/bin/env bash
# Create local development Secrets for the kind cluster (TASK-078, TASK-134).
#
# This script creates the platform Secrets using kubectl create rather than
# applying the YAML manifests directly. This is the recommended approach for
# local development because:
#   1. It avoids committing base64-encoded placeholder values
#   2. It mirrors how Secrets would be created in a real environment
#   3. Values can be customized per developer without editing YAML
#
# Airflow secrets (fernet key, secret key) are generated at runtime and
# never printed to stdout or stored in Git.
#
# Usage:
#   bash scripts/create-local-secrets.sh
#
# Prerequisites:
#   - kind cluster running (bash scripts/kind-cluster.sh create)
#   - kubectl context pointing to the kind cluster
#   - python3 (for Fernet key generation)

set -euo pipefail

NAMESPACE="ai-data-platform"

echo "Creating local development Secrets in namespace '${NAMESPACE}'..."

# MinIO credentials (matches Docker Compose defaults)
kubectl create secret generic minio-credentials \
  --namespace "${NAMESPACE}" \
  --from-literal=minio-access-key=minioadmin \
  --from-literal=minio-secret-key=minioadmin-local \
  --dry-run=client -o yaml | kubectl apply -f -

echo "  Created minio-credentials"

# PostgreSQL password (matches Docker Compose default)
kubectl create secret generic database-credentials \
  --namespace "${NAMESPACE}" \
  --from-literal=db-password=postgres \
  --dry-run=client -o yaml | kubectl apply -f -

echo "  Created database-credentials"

# Ingestion API keys (placeholder — replace before real use)
kubectl create secret generic ingestion-api-keys \
  --namespace "${NAMESPACE}" \
  --from-literal=bestbuy-api-key=placeholder-replace-me \
  --dry-run=client -o yaml | kubectl apply -f -

echo "  Created ingestion-api-keys"

# Airflow metadata DB password (matches database-credentials default)
kubectl create secret generic airflow-metadata-credentials \
  --namespace "${NAMESPACE}" \
  --from-literal=db-password=postgres \
  --dry-run=client -o yaml | kubectl apply -f -

echo "  Created airflow-metadata-credentials"

# Airflow Fernet key and session secret key (generated at runtime)
# The Fernet key is a 32-byte random key encoded as url-safe base64.
# The secret key is a random 32-byte hex string for Flask sessions.
FERNET_KEY=$(python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode(), end='')")
SECRET_KEY=$(python3 -c "import os; print(os.urandom(32).hex(), end='')")

kubectl create secret generic airflow-keys \
  --namespace "${NAMESPACE}" \
  --from-literal=fernet-key="${FERNET_KEY}" \
  --from-literal=secret-key="${SECRET_KEY}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "  Created airflow-keys (generated Fernet key + session secret)"

echo ""
echo "All local development Secrets created."
echo "Verify with: kubectl get secrets -n ${NAMESPACE}"
