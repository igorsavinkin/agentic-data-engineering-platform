# AI Data Platform Helm Chart

Event-driven AI data platform — ingestion, processing, data lake, warehouse, API, and Kafka.

## Quick Start

```bash
# Local kind development (default values)
helm upgrade --install ai-platform helm/ai-data-platform/

# Local with explicit local overrides
helm upgrade --install ai-platform helm/ai-data-platform/ \
  -f helm/ai-data-platform/values.yaml \
  -f helm/ai-data-platform/values-local.yaml

# Production-like example
helm upgrade --install ai-platform helm/ai-data-platform/ \
  -f helm/ai-data-platform/values.yaml \
  -f helm/ai-data-platform/values-production.yaml \
  --set secrets.database.password="<base64>" \
  --set secrets.minio.accessKey="<base64>" \
  --set secrets.minio.secretKey="<base64>" \
  --set secrets.ingestion.bestbuyApiKey="<base64>"
```

## Environment Files

| File | Purpose | Resources |
|------|---------|-----------|
| `values.yaml` | Base defaults (local-dev oriented) | 18 |
| `values-local.yaml` | kind cluster overrides (reduced resources) | 18 |
| `values-production.yaml` | Production example (HA, Ingress, HPA, NetworkPolicy) | 21 |

## Key Differences: Local vs Production

| Setting | Local | Production |
|---------|-------|------------|
| `platform.environment` | `local` | `production` |
| Image tags | `dev` | Pinned (e.g. `1.0.0`) |
| Service replicas | 1 | 2 |
| CPU requests (processor) | 50m | 250m |
| Memory limits (processor) | 256Mi | 1Gi |
| Ingress | Disabled | Enabled (nginx) |
| HPA | Disabled | Enabled (2-10 replicas) |
| NetworkPolicy | Disabled | Enabled |

## Uninstall

```bash
helm uninstall ai-platform
```
