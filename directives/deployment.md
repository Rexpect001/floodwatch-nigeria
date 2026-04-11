# Deployment Guide

## Target Infrastructure
- **Primary:** AWS EKS on af-south-1 (Lagos region) — lowest latency to Nigerian users
- **Fallback CDN:** Azure Front Door / Azure South Africa North for static PWA assets
- **CDN:** AWS CloudFront in front of nginx for PWA (<3s load on 3G)

---

## Service Map

| Service | Image | Replicas | Notes |
|---------|-------|---------|-------|
| `climate-api` | Dockerfile.api | 3 (6 in peak) | FastAPI, HPA-managed |
| `climate-ingestion` | Dockerfile.ingestion | 1 | APScheduler, 15-min polls |
| `climate-alert-orchestrator` | Dockerfile.ingestion | 2 | Redis pub/sub consumer |
| `postgres` (PostGIS) | postgis/postgis:15-3.4 | 1 (RDS in prod) | |
| `redis` | redis:7-alpine | 1 (ElastiCache in prod) | 512MB allkeys-lru |
| `nginx` | nginx:1.25-alpine | 2 | TLS termination + PWA |

---

## Deployment Pipeline

### Step 1: Build & Push Images
```bash
docker build -t YOUR_REGISTRY/climate-api:latest -f docker/Dockerfile.api .
docker build -t YOUR_REGISTRY/climate-ingestion:latest -f docker/Dockerfile.ingestion .
docker push YOUR_REGISTRY/climate-api:latest
docker push YOUR_REGISTRY/climate-ingestion:latest
```

### Step 2: Apply K8s Manifests
```bash
kubectl create namespace climate-ews
kubectl create secret generic climate-secrets --from-env-file=.env -n climate-ews
kubectl apply -f docker/k8s/deployment.yaml -n climate-ews
```

### Step 3: Database Initialization
```bash
# Run schema on first deploy
kubectl exec -it $(kubectl get pod -l app=climate-api -n climate-ews -o name | head -1) \
  -- psql $DATABASE_URL -f /app/execution/db/schema.sql
```

### Step 4: PWA Build + CDN
```bash
cd frontend
npm run build   # builds to dist/
aws s3 sync dist/ s3://floodwatch-ng-pwa/ --delete
aws cloudfront create-invalidation --distribution-id YOUR_DIST_ID --paths "/*"
```

---

## Scaling Rules (July–September Peak Flood Season)

### HPA (Automatic)
- API pods: scale from 3 → 12 at 70% CPU or 80% memory
- Alert orchestrator: scale from 2 → 4

### Manual Pre-Season Actions
```bash
# Pre-scale before August 1 each year
kubectl scale deployment climate-api --replicas=6 -n climate-ews
kubectl scale deployment climate-alert-orchestrator --replicas=4 -n climate-ews
```

---

## Uptime Requirements
- 99.9% during July–September (allows ~8.7 hours downtime/year)
- Multi-AZ deployment in af-south-1 for database (RDS Multi-AZ)
- Redis Sentinel or ElastiCache Cluster Mode

---

## Data Failover Tiers
Ingestion service automatically steps down:
1. T1 (NIHSA/NiMet) fails → T2 (Google Flood Hub/GloFAS/OWM)
2. T2 fails → Serve cached data (72h retention in Redis)
3. All sources stale → Show "SERVICE_DEGRADED" banner with staleness timestamp
4. Network failure → PWA Service Worker serves offline cached maps (148 LGAs, 72h)

---

## Security Checklist
- [ ] API keys in K8s Secrets (never in image)
- [ ] OAuth 2.0 for NiMet data access
- [ ] GDPR-compliant location handling (hash phone numbers in community reports)
- [ ] HTTPS-only (cert-manager + Let's Encrypt)
- [ ] OWM API keys server-side only (never exposed to PWA frontend)
- [ ] Rate limiting at nginx + FastAPI middleware layers

---

## Monitoring
- **Prometheus + Grafana:** API latency, ingestion success rates, alert delivery rates
- **Key alert:** ingestion_consecutive_failures > 3 (any Tier 1 source)
- **Key alert:** sms_delivery_rate < 90% (Africa's Talking)
- **Key alert:** RED alert pending > 5 minutes (2nd source confirmation delay)

---

## SMS Load Test
```bash
# Simulate 10,000 concurrent SMS dispatches
python -m execution.alerts.load_test --count 10000 --severity RED
# Target: <5 minute wall-clock latency from alert creation to delivery
```
