#!/usr/bin/env bash
# Build all application container images for local kind E2E testing.
#
# Usage:
#   bash scripts/build-local-images.sh              # build all images
#   bash scripts/build-local-images.sh --load        # build + load into kind
#   bash scripts/build-local-images.sh ingestion api # build only listed services
#
# Images are tagged ai-data-platform/<service>:dev and match the references
# in kubernetes/deployments/*.yaml and helm/ai-data-platform/values.yaml.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKERFILE="${REPO_ROOT}/Dockerfile"
MIGRATION_DOCKERFILE="${REPO_ROOT}/Dockerfile.migrations"
IMAGE_TAG="${IMAGE_TAG:-dev}"
IMAGE_REGISTRY="${IMAGE_REGISTRY:-ai-data-platform}"

ALL_SERVICES="ingestion processor raw-writer lake-writer warehouse-loader api warehouse-migrations"

declare -A SERVICE_MODULES=(
    [ingestion]="services.ingestion"
    [processor]="services.processor"
    [raw-writer]="services.raw-writer.consumer"
    [lake-writer]="services.lake-writer.consumer"
    [warehouse-loader]="services.warehouse-loader.runner"
    [api]="services.api"
)

LOAD_INTO_KIND=false
SELECTED_SERVICES=()

for arg in "$@"; do
    case "${arg}" in
        --load)
            LOAD_INTO_KIND=true
            ;;
        *)
            SELECTED_SERVICES+=("${arg}")
            ;;
    esac
done

if [[ ${#SELECTED_SERVICES[@]} -eq 0 ]]; then
    SELECTED_SERVICES=(${ALL_SERVICES})
fi

for name in "${SELECTED_SERVICES[@]}"; do
    if [[ "${name}" == "warehouse-migrations" ]]; then
        continue
    fi
    if [[ -z "${SERVICE_MODULES[${name}]+x}" ]]; then
        echo "ERROR: unknown service '${name}'" >&2
        echo "Available: ${ALL_SERVICES}" >&2
        exit 1
    fi
done

if [[ ! -f "${DOCKERFILE}" ]]; then
    echo "ERROR: Dockerfile not found at ${DOCKERFILE}" >&2
    exit 1
fi

FAILED=()
BUILT_IMAGES=()

for service_name in "${SELECTED_SERVICES[@]}"; do
    image="${IMAGE_REGISTRY}/${service_name}:${IMAGE_TAG}"

    if [[ "${service_name}" == "warehouse-migrations" ]]; then
        echo "==> Building ${image} (Dockerfile.migrations)"
        if docker build \
            -t "${image}" \
            -f "${MIGRATION_DOCKERFILE}" \
            "${REPO_ROOT}"; then
            echo "    OK: ${image}"
            BUILT_IMAGES+=("${image}")
        else
            echo "    FAIL: ${image}" >&2
            FAILED+=("${image}")
        fi
        continue
    fi

    module="${SERVICE_MODULES[${service_name}]}"

    echo "==> Building ${image} (module: ${module})"
    if docker build \
        --build-arg "SERVICE_MODULE=${module}" \
        -t "${image}" \
        -f "${DOCKERFILE}" \
        "${REPO_ROOT}"; then
        echo "    OK: ${image}"
        BUILT_IMAGES+=("${image}")
    else
        echo "    FAIL: ${image}" >&2
        FAILED+=("${image}")
    fi
done

echo ""
echo "=== Build summary ==="
echo "Built: ${#BUILT_IMAGES[@]}/${#SELECTED_SERVICES[@]} images"

if [[ ${#FAILED[@]} -gt 0 ]]; then
    echo "Failed:" >&2
    for img in "${FAILED[@]}"; do
        echo "  - ${img}" >&2
    done
    exit 1
fi

if [[ "${LOAD_INTO_KIND}" == "true" ]]; then
    CLUSTER_NAME="${KIND_CLUSTER_NAME:-ai-data-platform}"
    echo ""
    echo "==> Loading images into kind cluster '${CLUSTER_NAME}'..."
    bash "${REPO_ROOT}/scripts/kind-cluster.sh" load "${BUILT_IMAGES[@]}"
fi

echo ""
echo "All application images built successfully."
