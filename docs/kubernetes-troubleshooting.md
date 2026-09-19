# Kubernetes Troubleshooting Guide (TASK-079)

Diagnose and recover from common pod failure states in the `ai-data-platform` namespace. All commands target the local kind cluster.

## CrashLoopBackOff

The pod starts, crashes, and Kubernetes restarts it with exponential backoff.

**Diagnose:**

```bash
kubectl get pods -n ai-data-platform
kubectl describe pod <pod-name> -n ai-data-platform
kubectl logs <pod-name> -n ai-data-platform --previous
```

**Common causes:**

| Cause | Symptom in logs | Fix |
|-------|----------------|-----|
| Application error | Python traceback | Fix the code bug |
| Missing required env var | `KeyError` or startup failure | Check ConfigMap/Secret references |
| Dependency unreachable | Connection refused to Kafka/MinIO/PostgreSQL | Ensure infrastructure pods are Running first |
| Liveness probe too aggressive | Pod killed before startup completes | Increase `initialDelaySeconds` |

**Recovery:**

```bash
kubectl rollout restart deployment/<name> -n ai-data-platform
```

## ImagePullBackOff

Kubernetes cannot pull the container image.

**Diagnose:**

```bash
kubectl describe pod <pod-name> -n ai-data-platform
# Look for "Failed to pull image" in Events
```

**Common causes:**

| Cause | Fix |
|-------|-----|
| Image not built | Build the image: `docker build -t ai-data-platform/<service>:dev .` |
| Image not loaded into kind | Load it: `bash scripts/kind-cluster.sh load ai-data-platform/<service>:dev` |
| Wrong image name or tag | Check `image:` field in the deployment manifest |
| `imagePullPolicy: Never` with no local image | Build and load the image, or change to `IfNotPresent` |

**Recovery:**

```bash
# Rebuild and reload
docker build -t ai-data-platform/<service>:dev -f docker/Dockerfile.<service> .
bash scripts/kind-cluster.sh load ai-data-platform/<service>:dev
kubectl rollout restart deployment/<name> -n ai-data-platform
```

## Readiness Probe Failure

The pod is running but not receiving traffic because the readiness probe fails.

**Diagnose:**

```bash
kubectl get pods -n ai-data-platform
# Pod shows 0/1 READY
kubectl describe pod <pod-name> -n ai-data-platform
# Look for "Readiness probe failed" in Events
kubectl logs <pod-name> -n ai-data-platform
```

**Common causes:**

| Service | Probe type | Likely cause |
|---------|-----------|-------------|
| api | HTTP GET /api/v1/ready | PostgreSQL not reachable |
| kafka | TCP 29092 | Kafka still starting up |
| ingestion, processor, raw-writer, lake-writer | exec (Kafka TCP check) | Kafka not ready |
| warehouse-loader | exec (PostgreSQL TCP check) | PostgreSQL not ready |

**Recovery:**

```bash
# Check if the dependency is running
kubectl get pods -n ai-data-platform
# If Kafka is down:
kubectl logs deployment/kafka -n ai-data-platform
# If PostgreSQL is down, start it and wait for readiness
# The pod will recover automatically once the dependency is available
```

## OOMKilled

The container exceeded its memory limit and was killed by the kernel.

**Diagnose:**

```bash
kubectl get pods -n ai-data-platform
# Look for OOMKilled in the RESTARTS column or describe output
kubectl describe pod <pod-name> -n ai-data-platform
# Look for "OOMKilled" or "Last State: Terminated, Reason: OOMKilled"
```

**Common causes:**

| Cause | Fix |
|-------|-----|
| Memory limit too low for workload | Increase `resources.limits.memory` in the deployment |
| Memory leak in application code | Profile and fix the leak |
| Large batch processing in warehouse-loader | Reduce batch size or increase memory limit |

**Current limits (local dev):**

| Service | Memory Request | Memory Limit |
|---------|---------------|-------------|
| ingestion | 128Mi | 256Mi |
| processor | 256Mi | 512Mi |
| raw-writer | 256Mi | 512Mi |
| lake-writer | 256Mi | 512Mi |
| warehouse-loader | 256Mi | 512Mi |
| api | 256Mi | 512Mi |
| kafka | 512Mi | 1Gi |

**Recovery:**

```bash
# Temporarily increase memory limit
kubectl set resources deployment/<name> \
  -n ai-data-platform \
  --limits=memory=<new-limit>
```

## Missing ConfigMap or Secret

The pod cannot start because a referenced ConfigMap or Secret does not exist.

**Diagnose:**

```bash
kubectl describe pod <pod-name> -n ai-data-platform
# Look for "CreateContainerConfigError" in Status
# Message will name the missing ConfigMap or Secret
```

**Common causes:**

| Cause | Fix |
|-------|-----|
| ConfigMap not applied | `kubectl apply -f kubernetes/config/` |
| Secret not applied | `kubectl apply -f kubernetes/secrets/` or `bash scripts/create-local-secrets.sh` |
| Wrong key name in secretKeyRef | Check the Secret manifest for available keys |
| Secret key mismatch | Ensure `secretKeyRef.key` matches `data:` key in the Secret |

**Recovery:**

```bash
# Apply all ConfigMaps
kubectl apply -f kubernetes/config/

# Apply all Secrets (using the helper script)
bash scripts/create-local-secrets.sh

# Or apply Secret manifests directly
kubectl apply -f kubernetes/secrets/

# Restart the affected deployment
kubectl rollout restart deployment/<name> -n ai-data-platform
```

## General Diagnostic Commands

```bash
# All pods with status
kubectl get pods -n ai-data-platform -o wide

# All events sorted by time
kubectl get events -n ai-data-platform --sort-by='.lastTimestamp'

# Logs from a specific container
kubectl logs <pod-name> -n ai-data-platform -c <container-name>

# Follow logs in real time
kubectl logs -f deployment/<name> -n ai-data-platform

# Execute a command inside a running pod
kubectl exec -it <pod-name> -n ai-data-platform -- /bin/sh

# Port-forward to access a service locally
kubectl port-forward svc/api 8000:8000 -n ai-data-platform

# Check rollout status
kubectl rollout status deployment/<name> -n ai-data-platform

# View resource usage (requires metrics-server)
kubectl top pods -n ai-data-platform
```
