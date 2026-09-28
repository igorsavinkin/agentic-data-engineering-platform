#!/usr/bin/env bash
# deploy-eks.sh — End-to-end AWS EKS deployment for the AI Data Platform.
#
# Usage:
#   ./scripts/deploy-eks.sh [command]
#
# Commands:
#   plan        Run terraform plan (default)
#   apply       Apply terraform, push images, deploy Helm release
#   images      Build and push container images to ECR only
#   helm        Deploy/update the Helm release only (requires prior apply)
#   destroy     Tear down the Helm release and terraform resources
#   status      Show deployment status
#
# Prerequisites:
#   - AWS CLI configured with appropriate credentials
#   - Terraform >= 1.5.0
#   - kubectl configured for the EKS cluster
#   - Helm 3.x
#   - Docker (for image builds)
#
# Environment variables:
#   TF_ENV       — Terraform environment (default: dev)
#   TF_VAR_rds_password — RDS master password (required for apply)
#   IMAGE_TAG    — Docker image tag (default: latest)
#   SKIP_TERRAFORM — Skip terraform steps (default: false)
#   SKIP_IMAGES  — Skip image build/push (default: false)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TERRAFORM_DIR="$REPO_ROOT/terraform"
HELM_DIR="$REPO_ROOT/helm/ai-data-platform"

TF_ENV="${TF_ENV:-dev}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
SKIP_TERRAFORM="${SKIP_TERRAFORM:-false}"
SKIP_IMAGES="${SKIP_IMAGES:-false}"
RELEASE_NAME="ai-platform"
NAMESPACE="ai-data-platform"
STRIMZI_VERSION="0.45.0"

SERVICES=(ingestion processor raw-writer lake-writer warehouse-loader api agent)

log() { echo "[$(date +'%H:%M:%S')] $*"; }
err() { echo "[ERROR] $*" >&2; }
die() { err "$@"; exit 1; }

check_prereqs() {
    local missing=()
    for cmd in aws terraform kubectl helm docker; do
        command -v "$cmd" &>/dev/null || missing+=("$cmd")
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
        die "Missing prerequisites: ${missing[*]}"
    fi
    if [[ -z "${TF_VAR_rds_password:-}" ]] && [[ "$1" == "apply" ]]; then
        die "TF_VAR_rds_password is required for apply"
    fi
}

# ---------------------------------------------------------------------------
# Terraform
# ---------------------------------------------------------------------------

terraform_init() {
    log "Initializing Terraform (env=$TF_ENV)..."
    cd "$TERRAFORM_DIR"

    if [[ ! -f "backend.tf" ]]; then
        die "backend.tf not found — run terraform/bootstrap first"
    fi

    terraform init \
        -backend-config="bucket=ai-data-platform-tfstate" \
        -backend-config="key=envs/${TF_ENV}/terraform.tfstate" \
        -backend-config="region=eu-north-1" \
        -backend-config="dynamodb_table=ai-data-platform-tf-locks" \
        -reconfigure
}

terraform_plan() {
    terraform_init
    log "Running terraform plan..."
    terraform plan \
        -var-file="envs/${TF_ENV}.tfvars" \
        -out=tfplan
    log "Plan saved to terraform/tfplan"
}

terraform_apply() {
    terraform_init
    log "Applying terraform..."
    terraform apply \
        -var-file="envs/${TF_ENV}.tfvars" \
        -auto-approve
}

extract_outputs() {
    log "Extracting Terraform outputs..."
    cd "$TERRAFORM_DIR"

    EKS_CLUSTER_NAME=$(terraform output -raw eks_cluster_name)
    EKS_CLUSTER_ENDPOINT=$(terraform output -raw eks_cluster_endpoint)
    RDS_ENDPOINT=$(terraform output -raw rds_endpoint)
    S3_BUCKET=$(terraform output -raw s3_data_bucket)
    ECR_INGESTION=$(terraform output -raw ecr_repositories | python3 -c "import sys,json; print(json.load(sys.stdin)['ingestion'])")
    ECR_PROCESSOR=$(terraform output -raw ecr_repositories | python3 -c "import sys,json; print(json.load(sys.stdin)['processor'])")
    ECR_RAW_WRITER=$(terraform output -raw ecr_repositories | python3 -c "import sys,json; print(json.load(sys.stdin)['raw-writer'])")
    ECR_LAKE_WRITER=$(terraform output -raw ecr_repositories | python3 -c "import sys,json; print(json.load(sys.stdin)['lake-writer'])")
    ECR_WAREHOUSE_LOADER=$(terraform output -raw ecr_repositories | python3 -c "import sys,json; print(json.load(sys.stdin)['warehouse-loader'])")
    ECR_API=$(terraform output -raw ecr_repositories | python3 -c "import sys,json; print(json.load(sys.stdin)['api'])")

    AWS_REGION=$(terraform output -raw aws_region)

    IAM_ROLES=$(terraform output -json iam_service_role_arns)
    IAM_ROLE_INGESTION=$(echo "$IAM_ROLES" | python3 -c "import sys,json; print(json.load(sys.stdin)['ingestion'])")
    IAM_ROLE_PROCESSOR=$(echo "$IAM_ROLES" | python3 -c "import sys,json; print(json.load(sys.stdin)['processor'])")
    IAM_ROLE_RAW_WRITER=$(echo "$IAM_ROLES" | python3 -c "import sys,json; print(json.load(sys.stdin)['raw-writer'])")
    IAM_ROLE_LAKE_WRITER=$(echo "$IAM_ROLES" | python3 -c "import sys,json; print(json.load(sys.stdin)['lake-writer'])")
    IAM_ROLE_WAREHOUSE_LOADER=$(echo "$IAM_ROLES" | python3 -c "import sys,json; print(json.load(sys.stdin)['warehouse-loader'])")
    IAM_ROLE_API=$(echo "$IAM_ROLES" | python3 -c "import sys,json; print(json.load(sys.stdin)['api'])")
    IAM_ROLE_AGENT=$(echo "$IAM_ROLES" | python3 -c "import sys,json; print(json.load(sys.stdin)['agent'])")

    log "Cluster: $EKS_CLUSTER_NAME"
    log "RDS:     $RDS_ENDPOINT"
    log "S3:      $S3_BUCKET"
}

# ---------------------------------------------------------------------------
# ECR image build and push
# ---------------------------------------------------------------------------

ecr_login() {
    log "Logging in to ECR..."
    aws ecr get-login-password --region "$AWS_REGION" | \
        docker login --username AWS --password-stdin "$(echo "$ECR_INGESTION" | cut -d/ -f1)"
}

build_and_push_images() {
    log "Building and pushing images (tag=$IMAGE_TAG)..."
    cd "$REPO_ROOT"

    for svc in "${SERVICES[@]}"; do
        local ecr_url
        case "$svc" in
            ingestion)      ecr_url="$ECR_INGESTION" ;;
            processor)      ecr_url="$ECR_PROCESSOR" ;;
            raw-writer)     ecr_url="$ECR_RAW_WRITER" ;;
            lake-writer)    ecr_url="$ECR_LAKE_WRITER" ;;
            warehouse-loader) ecr_url="$ECR_WAREHOUSE_LOADER" ;;
            api)            ecr_url="$ECR_API" ;;
            agent)          continue ;;
        esac

        log "  Building $svc..."
        docker build \
            --build-arg "SERVICE_MODULE=$svc" \
            -t "$ecr_url:$IMAGE_TAG" \
            -f Dockerfile .

        log "  Pushing $svc..."
        docker push "$ecr_url:$IMAGE_TAG"
    done

    local migration_ecr="$ECR_WAREHOUSE_LOADER"
    log "  Building warehouse-migrations..."
    docker build -t "$migration_ecr:migrations-$IMAGE_TAG" -f Dockerfile.migrations .
    log "  Pushing warehouse-migrations..."
    docker push "$migration_ecr:migrations-$IMAGE_TAG"

    log "All images pushed."
}

# ---------------------------------------------------------------------------
# Kubernetes / EKS
# ---------------------------------------------------------------------------

configure_kubectl() {
    log "Configuring kubectl for EKS cluster: $EKS_CLUSTER_NAME"
    aws eks update-kubeconfig \
        --name "$EKS_CLUSTER_NAME" \
        --region "$AWS_REGION"
    kubectl cluster-info
}

install_strimzi() {
    log "Installing Strimzi operator..."

    kubectl create namespace strimzi --dry-run=client -o yaml | kubectl apply -f -

    if ! helm status strimzi -n strimzi &>/dev/null; then
        helm install strimzi oci://quay.io/strimzi-helm/strimzi-kafka-operator \
            --version "$STRIMZI_VERSION" \
            --namespace strimzi \
            --wait
    else
        log "Strimzi operator already installed."
    fi

    log "Waiting for Strimzi operator to be ready..."
    kubectl rollout status deployment/strimzi-cluster-operator -n strimzi --timeout=120s
}

apply_strimzi_kafka() {
    log "Applying Strimzi Kafka cluster..."
    kubectl apply -f "$REPO_ROOT/kubernetes/deployments/strimzi-kafka-eks.yaml"

    log "Waiting for Strimzi Kafka cluster (this takes several minutes)..."
    kubectl rollout status statefulset/platform-cluster-kafka -n strimzi --timeout=600s
    log "Strimzi Kafka cluster is ready."
}

create_kafka_topics() {
    log "Creating Kafka topics via Strimzi..."
    local kafka_pod
    kafka_pod=$(kubectl get pod -n strimzi -l strimzi.io/name=platform-cluster-kafka -o jsonpath='{.items[0].metadata.name}')

    local topics=(
        "products.raw.v1:3"
        "products.validated.v1:3"
        "products.invalid.v1:1"
        "pipeline.events.v1:1"
        "data-quality.events.v1:1"
    )

    for entry in "${topics[@]}"; do
        local topic="${entry%%:*}"
        local partitions="${entry##*:}"
        log "  Creating topic: $topic (partitions=$partitions)"
        kubectl exec -n strimzi "$kafka_pod" -- \
            /opt/kafka/bin/kafka-topics.sh \
            --bootstrap-server localhost:9092 \
            --create --if-not-exists \
            --topic "$topic" \
            --partitions "$partitions" \
            --replication-factor 3 \
            --config retention.ms=604800000
    done
    log "All topics created."
}

# ---------------------------------------------------------------------------
# Helm deployment
# ---------------------------------------------------------------------------

generate_helm_values() {
    log "Generating resolved Helm values..."
    local output_file="$REPO_ROOT/helm/ai-data-platform/values-eks-resolved.yaml"

    sed \
        -e "s|<ECR_INGESTION_URL>|$ECR_INGESTION|g" \
        -e "s|<ECR_PROCESSOR_URL>|$ECR_PROCESSOR|g" \
        -e "s|<ECR_RAW_WRITER_URL>|$ECR_RAW_WRITER|g" \
        -e "s|<ECR_LAKE_WRITER_URL>|$ECR_LAKE_WRITER|g" \
        -e "s|<ECR_WAREHOUSE_LOADER_URL>|$ECR_WAREHOUSE_LOADER|g" \
        -e "s|<ECR_API_URL>|$ECR_API|g" \
        -e "s|<RDS_ENDPOINT>|$RDS_ENDPOINT|g" \
        -e "s|<IAM_ROLE_INGESTION>|$IAM_ROLE_INGESTION|g" \
        -e "s|<IAM_ROLE_PROCESSOR>|$IAM_ROLE_PROCESSOR|g" \
        -e "s|<IAM_ROLE_RAW_WRITER>|$IAM_ROLE_RAW_WRITER|g" \
        -e "s|<IAM_ROLE_LAKE_WRITER>|$IAM_ROLE_LAKE_WRITER|g" \
        -e "s|<IAM_ROLE_WAREHOUSE_LOADER>|$IAM_ROLE_WAREHOUSE_LOADER|g" \
        -e "s|<IAM_ROLE_API>|$IAM_ROLE_API|g" \
        -e "s|<IAM_ROLE_AGENT>|$IAM_ROLE_AGENT|g" \
        "$HELM_DIR/values-eks.yaml" > "$output_file"

    echo "$output_file"
}

create_eks_secrets() {
    log "Creating Kubernetes secrets for EKS..."

    kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

    kubectl create secret generic database-credentials \
        --namespace "$NAMESPACE" \
        --from-literal=db-password="$TF_VAR_rds_password" \
        --dry-run=client -o yaml | kubectl apply -f -

    kubectl create secret generic minio-credentials \
        --namespace "$NAMESPACE" \
        --from-literal=minio-access-key="" \
        --from-literal=minio-secret-key="" \
        --dry-run=client -o yaml | kubectl apply -f -

    kubectl create secret generic ingestion-api-keys \
        --namespace "$NAMESPACE" \
        --from-literal=bestbuy-api-key="${BESTBUY_API_KEY:-placeholder}" \
        --dry-run=client -o yaml | kubectl apply -f -

    log "Secrets created."
}

helm_deploy() {
    local resolved_values="$1"
    log "Deploying Helm release..."

    helm upgrade --install "$RELEASE_NAME" "$HELM_DIR" \
        --namespace "$NAMESPACE" \
        --create-namespace \
        -f "$HELM_DIR/values.yaml" \
        -f "$resolved_values" \
        --set images.warehouseMigration.tag="migrations-$IMAGE_TAG" \
        --wait \
        --timeout 600s

    log "Helm release deployed."
}

# ---------------------------------------------------------------------------
# Status and teardown
# ---------------------------------------------------------------------------

show_status() {
    configure_kubectl
    log "=== Pods ==="
    kubectl get pods -n "$NAMESPACE" -o wide
    log "=== Services ==="
    kubectl get svc -n "$NAMESPACE"
    log "=== Strimzi ==="
    kubectl get pods -n strimzi
    log "=== Kafka Topics ==="
    local kafka_pod
    kafka_pod=$(kubectl get pod -n strimzi -l strimzi.io/name=platform-cluster-kafka -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [[ -n "$kafka_pod" ]]; then
        kubectl exec -n strimzi "$kafka_pod" -- \
            /opt/kafka/bin/kafka-topics.sh \
            --bootstrap-server localhost:9092 --list 2>/dev/null || true
    fi
}

destroy_all() {
    log "WARNING: This will destroy all AWS resources!"
    read -rp "Type 'yes' to confirm: " confirm
    if [[ "$confirm" != "yes" ]]; then
        log "Aborted."
        return
    fi

    configure_kubectl

    log "Uninstalling Helm release..."
    helm uninstall "$RELEASE_NAME" --namespace "$NAMESPACE" 2>/dev/null || true

    log "Deleting Strimzi Kafka cluster..."
    kubectl delete -f "$REPO_ROOT/kubernetes/deployments/strimzi-kafka-eks.yaml" 2>/dev/null || true
    helm uninstall strimzi --namespace strimzi 2>/dev/null || true
    kubectl delete namespace strimzi 2>/dev/null || true

    log "Destroying Terraform resources..."
    cd "$TERRAFORM_DIR"
    terraform init \
        -backend-config="bucket=ai-data-platform-tfstate" \
        -backend-config="key=envs/${TF_ENV}/terraform.tfstate" \
        -backend-config="region=eu-north-1" \
        -backend-config="dynamodb_table=ai-data-platform-tf-locks" \
        -reconfigure
    terraform destroy \
        -var-file="envs/${TF_ENV}.tfvars" \
        -auto-approve

    log "All resources destroyed."
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

cmd="${1:-plan}"

case "$cmd" in
    plan)
        check_prereqs plan
        terraform_plan
        ;;
    apply)
        check_prereqs apply
        terraform_apply
        extract_outputs
        configure_kubectl

        if [[ "$SKIP_IMAGES" != "true" ]]; then
            ecr_login
            build_and_push_images
        fi

        install_strimzi
        apply_strimzi_kafka
        create_kafka_topics

        create_eks_secrets
        resolved=$(generate_helm_values)
        helm_deploy "$resolved"

        log "=== Deployment complete ==="
        log "API endpoint: kubectl get svc api -n $NAMESPACE"
        log "Grafana:      kubectl port-forward svc/grafana 3000:3000 -n $NAMESPACE"
        ;;
    images)
        check_prereqs apply
        extract_outputs
        ecr_login
        build_and_push_images
        ;;
    helm)
        check_prereqs apply
        extract_outputs
        configure_kubectl
        create_eks_secrets
        resolved=$(generate_helm_values)
        helm_deploy "$resolved"
        ;;
    destroy)
        check_prereqs plan
        destroy_all
        ;;
    status)
        check_prereqs plan
        show_status
        ;;
    *)
        echo "Usage: $0 {plan|apply|images|helm|destroy|status}"
        exit 1
        ;;
esac
