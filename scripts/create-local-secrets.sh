#!/usr/bin/env bash
# Create local development Secrets for the kind cluster (TASK-078).
#
# This script creates the three platform Secrets using kubectl create
# rather than applying the YAML manifests directly. This is the
# recommended approach for local development because:
#   1. It avoids committing base64-encoded placeholder values
#   2. It mirrors how Secrets would be created in a real environment
#   3. Values can be customized per developer without editing YAML
#
# Usage:
#   bash scripts/create-local-secrets.sh
#
# Prerequisites:
#   - kind cluster running (bash scripts/kind-cluster.sh create)
#   - kubectl context pointing to the kind cluster

set -euo pipefail

NAMESPACE="ai-data-platform"

echo "Creating local development Secrets in namespace '${NAMESPACE}'..."

# MinIO credentials (matches Docker Compose defaults)
kubectl create secret generic minio-credentials \
  --namespace "${NAMESPACE}" \
  --from-literal=minio-access-key=minioadmin \
  --from-literal=minio-secret-key=minioadmin \
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

echo ""
echo "All local development Secrets created."
echo "Verify with: kubectl get secrets -n ${NAMESPACE}"
