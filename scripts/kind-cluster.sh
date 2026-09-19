#!/usr/bin/env bash
# kind cluster lifecycle for the AI Data Platform (Milestone 8).
#
# Wraps kind create/delete and applies the platform namespace.
# Designed for reproducible local development — the cluster is
# disposable and can be recreated at any time.
#
# Usage:
#   bash scripts/kind-cluster.sh create    — create cluster + apply namespaces
#   bash scripts/kind-cluster.sh delete    — delete cluster
#   bash scripts/kind-cluster.sh recreate  — delete + create
#   bash scripts/kind-cluster.sh verify    — check cluster + namespace health
#   bash scripts/kind-cluster.sh load IMAGE [IMAGE ...] — load local Docker images
#
# Prerequisites: kind, kubectl, docker (for image loading)

set -euo pipefail

CLUSTER_NAME="${KIND_CLUSTER_NAME:-ai-data-platform}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KIND_CONFIG="${REPO_ROOT}/kubernetes/kind/kind-config.yaml"
NAMESPACE_MANIFEST="${REPO_ROOT}/kubernetes/namespaces/platform-namespace.yaml"

usage() {
    echo "Usage: $0 {create|delete|recreate|verify|load IMAGE [IMAGE ...]}"
    echo ""
    echo "Commands:"
    echo "  create    Create kind cluster and apply platform namespaces"
    echo "  delete    Delete the kind cluster"
    echo "  recreate  Delete then create the cluster"
    echo "  verify    Check cluster connectivity and namespace status"
    echo "  load      Load local Docker images into the kind cluster"
    echo ""
    echo "Environment:"
    echo "  KIND_CLUSTER_NAME  Override cluster name (default: ai-data-platform)"
    exit 1
}

check_prerequisites() {
    local missing=()
    if ! command -v kind &>/dev/null; then
        missing+=("kind")
    fi
    if ! command -v kubectl &>/dev/null; then
        missing+=("kubectl")
    fi
    if [[ ${#missing[@]} -gt 0 ]]; then
        echo "ERROR: Missing prerequisites: ${missing[*]}" >&2
        echo "Install them before continuing." >&2
        exit 1
    fi
}

cmd_create() {
    check_prerequisites

    if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
        echo "Cluster '${CLUSTER_NAME}' already exists. Use 'recreate' to start fresh."
        return 0
    fi

    echo "Creating kind cluster '${CLUSTER_NAME}'..."
    kind create cluster \
        --name "${CLUSTER_NAME}" \
        --config "${KIND_CONFIG}" \
        --wait 60s

    echo "Applying platform namespaces..."
    kubectl apply -f "${NAMESPACE_MANIFEST}"

    echo ""
    echo "Cluster ready. Verify with: $0 verify"
}

cmd_delete() {
    check_prerequisites

    if ! kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
        echo "Cluster '${CLUSTER_NAME}' does not exist. Nothing to delete."
        return 0
    fi

    echo "Deleting kind cluster '${CLUSTER_NAME}'..."
    kind delete cluster --name "${CLUSTER_NAME}"
    echo "Cluster deleted."
}

cmd_recreate() {
    cmd_delete
    cmd_create
}

cmd_verify() {
    check_prerequisites

    if ! kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
        echo "ERROR: Cluster '${CLUSTER_NAME}' does not exist. Run: $0 create" >&2
        exit 1
    fi

    echo "=== Cluster info ==="
    kubectl cluster-info --context "kind-${CLUSTER_NAME}"
    echo ""

    echo "=== Nodes ==="
    kubectl get nodes --context "kind-${CLUSTER_NAME}"
    echo ""

    echo "=== Namespace: ai-data-platform ==="
    kubectl get namespace ai-data-platform --context "kind-${CLUSTER_NAME}" -o wide 2>/dev/null || {
        echo "WARNING: Namespace 'ai-data-platform' not found. Run: kubectl apply -f ${NAMESPACE_MANIFEST}"
    }
    echo ""

    echo "=== All namespaces ==="
    kubectl get namespaces --context "kind-${CLUSTER_NAME}"
    echo ""

    echo "=== Events (recent) ==="
    kubectl get events --context "kind-${CLUSTER_NAME}" --sort-by='.lastTimestamp' -A 2>/dev/null | tail -10 || true
}

cmd_load() {
    check_prerequisites

    if [[ $# -eq 0 ]]; then
        echo "ERROR: No images specified." >&2
        echo "Usage: $0 load IMAGE [IMAGE ...]" >&2
        exit 1
    fi

    if ! kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
        echo "ERROR: Cluster '${CLUSTER_NAME}' does not exist. Run: $0 create" >&2
        exit 1
    fi

    if ! command -v docker &>/dev/null; then
        echo "ERROR: docker is required for image loading." >&2
        exit 1
    fi

    for image in "$@"; do
        echo "Loading '${image}' into kind cluster '${CLUSTER_NAME}'..."
        kind load docker-image "${image}" --name "${CLUSTER_NAME}"
    done

    echo "All images loaded."
}

# --- Main ---

if [[ $# -lt 1 ]]; then
    usage
fi

command="$1"
shift

case "${command}" in
    create)   cmd_create ;;
    delete)   cmd_delete ;;
    recreate) cmd_recreate ;;
    verify)   cmd_verify ;;
    load)     cmd_load "$@" ;;
    *)        usage ;;
esac
