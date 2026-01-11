# BIOwerk Kubernetes Deployment

This directory contains production-grade Kubernetes manifests for deploying BIOwerk to Kubernetes clusters.

## Directory Structure

```
k8s/
├── namespace.yaml                 # Namespace definition
├── base/                          # Base Kustomize configuration
│   ├── kustomization.yaml        # Base kustomization file
│   ├── configmap.yaml            # Application configuration
│   ├── secrets.yaml              # Secret templates (DO NOT commit real secrets!)
│   ├── postgres-statefulset.yaml # PostgreSQL database
│   ├── mongodb-statefulset.yaml  # MongoDB database
│   ├── redis-statefulset.yaml    # Redis cache
│   ├── pgbouncer-deployment.yaml # Connection pooler
│   ├── ollama-deployment.yaml    # LLM service
│   ├── mesh-deployment.yaml      # API gateway (3 replicas)
│   ├── osteon-deployment.yaml    # Agent service (2 replicas)
│   ├── myocyte-deployment.yaml   # Agent service (2 replicas)
│   ├── synapse-deployment.yaml   # Agent service (2 replicas)
│   ├── circadian-deployment.yaml # Agent service (2 replicas)
│   ├── nucleus-deployment.yaml   # Agent service (2 replicas)
│   ├── chaperone-deployment.yaml # Agent service (2 replicas)
│   ├── gdpr-deployment.yaml      # GDPR compliance service (2 replicas)
│   ├── larry-deployment.yaml     # PHI2 coordinator
│   ├── moe-deployment.yaml       # PHI2 coordinator
│   ├── harry-deployment.yaml     # PHI2 coordinator
│   ├── observability-deployments.yaml  # Loki, Promtail, Prometheus, Alertmanager, Grafana
│   ├── monitoring-exporters.yaml # Database and system exporters
│   ├── backup-orchestrator-deployment.yaml  # Backup service
│   ├── hpa.yaml                  # Horizontal Pod Autoscalers
│   └── ingress.yaml              # Ingress with TLS and rate limiting
├── overlays/
│   ├── staging/                  # Staging environment overrides
│   │   ├── kustomization.yaml
│   │   └── patches/
│   │       ├── reduce-replicas.yaml
│   │       ├── resource-limits.yaml
│   │       └── environment-config.yaml
│   └── production/               # Production environment overrides
│       ├── kustomization.yaml
│       └── patches/
│           ├── increase-replicas.yaml
│           ├── resource-limits.yaml
│           ├── storage-class.yaml
│           └── environment-config.yaml
└── README.md                     # This file
```

## Features

### Production-Ready
- **High Availability**: Multi-replica deployments with anti-affinity
- **Auto-scaling**: HPA for all services based on CPU/memory
- **Zero-downtime**: Rolling updates with readiness probes
- **Health Checks**: Liveness, readiness, and startup probes
- **Resource Management**: Defined requests and limits
- **Persistent Storage**: StatefulSets with PVCs for databases

### Security
- **TLS/HTTPS**: Ingress with TLS termination
- **Secrets Management**: Sealed Secrets support
- **Rate Limiting**: Ingress-level rate limiting
- **Security Headers**: X-Frame-Options, CSP, HSTS
- **Network Policies**: Optional pod-to-pod isolation
- **RBAC**: Service accounts with minimal permissions

### Observability
- **Metrics**: Prometheus with custom alerts
- **Logs**: Loki + Promtail for centralized logging
- **Dashboards**: Grafana with pre-configured dashboards
- **Tracing**: Ready for OpenTelemetry integration
- **Alerting**: Alertmanager with email/Slack/PagerDuty

## Prerequisites

### Required
- Kubernetes cluster 1.24+ (tested on 1.28)
- kubectl CLI configured
- kustomize 4.5+ (or use `kubectl apply -k`)
- Container registry for images
- Persistent volume provisioner

### Optional
- Helm 3.8+ (for Helm-based deployment)
- cert-manager (for automatic TLS certificates)
- NGINX Ingress Controller (or ALB for AWS)
- metrics-server (for HPA)
- Sealed Secrets controller (for secret management)

## Quick Start

### 1. Local Testing (minikube/kind)

```bash
# Start minikube with sufficient resources
minikube start --cpus=8 --memory=16384 --disk-size=100g

# Enable addons
minikube addons enable ingress
minikube addons enable metrics-server
minikube addons enable storage-provisioner

# Create namespace
kubectl apply -f k8s/namespace.yaml

# Deploy with Kustomize
kubectl apply -k k8s/base

# Check deployment
kubectl get pods -n biowerk
kubectl get svc -n biowerk

# Access via port-forward
kubectl port-forward -n biowerk svc/mesh 8080:80

# Open browser to http://localhost:8080
```

### 2. Staging Deployment

```bash
# Update secrets first!
cp k8s/base/secrets.yaml k8s/overlays/staging/secrets.yaml
# Edit secrets.yaml with actual values

# Deploy staging
kubectl apply -k k8s/overlays/staging

# Monitor rollout
kubectl rollout status deployment -n biowerk-staging mesh-staging
kubectl get pods -n biowerk-staging

# Check logs
kubectl logs -f -n biowerk-staging -l app=mesh
```

### 3. Production Deployment

```bash
# CRITICAL: Update all secrets with production values
# Use sealed-secrets or external secret manager

# Build and push images with version tags
docker build -t myregistry.com/biowerk-mesh:v1.0.0 ./mesh
docker push myregistry.com/biowerk-mesh:v1.0.0

# Update image tags in kustomization.yaml
export VERSION=1.0.0
export REGISTRY=myregistry.com

# Deploy production
kubectl apply -k k8s/overlays/production

# Monitor deployment
kubectl get pods -n biowerk -w
kubectl rollout status deployment -n biowerk mesh

# Verify services
kubectl get svc,ingress -n biowerk
```

## Configuration

### Environment-Specific Configuration

Each environment has its own configuration in `k8s/overlays/{env}/`:

**Staging:**
- Reduced replicas (1-2)
- Lower resource limits
- Reduced PVC sizes
- Relaxed rate limits

**Production:**
- High replica counts (3-5)
- Production resource limits
- Large PVC sizes
- Strict rate limits
- High-performance storage classes

### Secrets Management

#### Option 1: Sealed Secrets (Recommended)

```bash
# Install sealed-secrets controller
kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.24.0/controller.yaml

# Install kubeseal CLI
brew install kubeseal

# Create and seal a secret
echo -n "my-secret-password" | kubectl create secret generic postgres-secret \
  --dry-run=client --from-file=password=/dev/stdin -o yaml | \
  kubeseal -o yaml > k8s/base/postgres-sealed-secret.yaml

# Apply sealed secret
kubectl apply -f k8s/base/postgres-sealed-secret.yaml
```

#### Option 2: External Secrets Operator

```bash
# Install External Secrets Operator
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets -n external-secrets-system --create-namespace

# Configure SecretStore (example for AWS Secrets Manager)
kubectl apply -f - <<EOF
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: aws-secrets
  namespace: biowerk
spec:
  provider:
    aws:
      service: SecretsManager
      region: us-east-1
      auth:
        jwt:
          serviceAccountRef:
            name: biowerk
EOF

# Create ExternalSecret
kubectl apply -f - <<EOF
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: postgres-secret
  namespace: biowerk
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secrets
    kind: SecretStore
  target:
    name: postgres-secret
    creationPolicy: Owner
  data:
  - secretKey: password
    remoteRef:
      key: biowerk/postgres/password
EOF
```

### TLS Certificates

#### Option 1: cert-manager + Let's Encrypt

```bash
# Install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# Create ClusterIssuer
kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@biowerk.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
EOF

# cert-manager will automatically create TLS certificates based on ingress annotations
```

#### Option 2: Manual Certificate

```bash
# Create TLS secret manually
kubectl create secret tls biowerk-tls-cert \
  --cert=path/to/tls.crt \
  --key=path/to/tls.key \
  -n biowerk
```

### Resource Scaling

#### Horizontal Pod Autoscaling

HPAs are configured for all application services. They scale based on CPU and memory:

```bash
# View HPA status
kubectl get hpa -n biowerk

# Manually scale (temporary, HPA will override)
kubectl scale deployment mesh -n biowerk --replicas=10

# Update HPA limits
kubectl edit hpa mesh-hpa -n biowerk
```

#### Vertical Pod Autoscaling (Optional)

```bash
# Install VPA
git clone https://github.com/kubernetes/autoscaler.git
cd autoscaler/vertical-pod-autoscaler
./hack/vpa-up.sh

# Create VPA
kubectl apply -f - <<EOF
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: mesh-vpa
  namespace: biowerk
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: mesh
  updatePolicy:
    updateMode: "Auto"
EOF
```

### Storage Configuration

Update storage classes in overlays for your cloud provider:

**AWS EBS:**
```yaml
storageClassName: gp3
```

**GCP Persistent Disk:**
```yaml
storageClassName: pd-ssd
```

**Azure Disk:**
```yaml
storageClassName: managed-premium
```

## Monitoring & Observability

### Access Grafana

```bash
# Port-forward to Grafana
kubectl port-forward -n biowerk svc/grafana 3000:3000

# Open http://localhost:3000
# Default credentials: admin / (see secret)
```

### Access Prometheus

```bash
kubectl port-forward -n biowerk svc/prometheus 9090:9090
# Open http://localhost:9090
```

### View Logs with Loki

```bash
# Via Grafana:
# 1. Open Grafana
# 2. Go to Explore
# 3. Select Loki data source
# 4. Query: {namespace="biowerk", app="mesh"}
```

### Configure Alerts

Edit `k8s/base/configmap.yaml` to customize Prometheus alerts, then:

```bash
kubectl apply -k k8s/base
kubectl rollout restart deployment prometheus -n biowerk
```

## Backup & Disaster Recovery

### Manual Backup

```bash
# Trigger manual backup
kubectl exec -n biowerk backup-orchestrator-0 -- /app/scripts/backup.sh

# List backups
kubectl exec -n biowerk backup-orchestrator-0 -- ls -lh /var/backups/biowerk

# Download backup
kubectl cp biowerk/backup-orchestrator-0:/var/backups/biowerk/backup-20240101.tar.gz ./backup-20240101.tar.gz
```

### Restore from Backup

```bash
# Upload backup
kubectl cp ./backup-20240101.tar.gz biowerk/backup-orchestrator-0:/var/backups/biowerk/restore/

# Restore
kubectl exec -n biowerk backup-orchestrator-0 -- /app/scripts/restore.sh /var/backups/biowerk/restore/backup-20240101.tar.gz
```

### Cloud Backup (S3)

Configure in `k8s/base/backup-orchestrator-deployment.yaml`:

```yaml
env:
  - name: S3_ENABLED
    value: "true"
  - name: S3_BUCKET
    value: "biowerk-backups"
  - name: AWS_ACCESS_KEY_ID
    valueFrom:
      secretKeyRef:
        name: backup-secrets
        key: aws_access_key_id
```

## Troubleshooting

### Pods Not Starting

```bash
# Check pod status
kubectl get pods -n biowerk

# Describe pod for events
kubectl describe pod <pod-name> -n biowerk

# Check logs
kubectl logs <pod-name> -n biowerk

# Check previous logs (if crashed)
kubectl logs <pod-name> -n biowerk --previous
```

### Database Connection Issues

```bash
# Test PostgreSQL connectivity
kubectl run -it --rm debug --image=postgres:16-alpine --restart=Never -n biowerk -- \
  psql postgresql://biowerk:password@postgres.biowerk.svc.cluster.local:5432/biowerk

# Test MongoDB connectivity
kubectl run -it --rm debug --image=mongo:7.0 --restart=Never -n biowerk -- \
  mongosh mongodb://biowerk:password@mongodb.biowerk.svc.cluster.local:27017/biowerk

# Test Redis connectivity
kubectl run -it --rm debug --image=redis:7-alpine --restart=Never -n biowerk -- \
  redis-cli -h redis.biowerk.svc.cluster.local ping
```

### Ingress Not Working

```bash
# Check ingress
kubectl get ingress -n biowerk
kubectl describe ingress biowerk-ingress -n biowerk

# Check ingress controller logs
kubectl logs -n ingress-nginx -l app.kubernetes.io/component=controller

# Test service directly (bypass ingress)
kubectl port-forward -n biowerk svc/mesh 8080:80
```

### Performance Issues

```bash
# Check resource usage
kubectl top pods -n biowerk
kubectl top nodes

# View HPA metrics
kubectl get hpa -n biowerk

# Check Prometheus for detailed metrics
kubectl port-forward -n biowerk svc/prometheus 9090:9090
# Query: container_cpu_usage_seconds_total{namespace="biowerk"}
```

### Debugging Pod Issues

```bash
# Get shell in running pod
kubectl exec -it <pod-name> -n biowerk -- /bin/sh

# Run ephemeral debug container
kubectl debug <pod-name> -n biowerk -it --image=busybox

# Copy files from pod
kubectl cp biowerk/<pod-name>:/app/logs/error.log ./error.log
```

## Maintenance

### Rolling Updates

```bash
# Update image
kubectl set image deployment/mesh mesh=myregistry.com/biowerk-mesh:v1.1.0 -n biowerk

# Check rollout status
kubectl rollout status deployment/mesh -n biowerk

# View rollout history
kubectl rollout history deployment/mesh -n biowerk

# Rollback if needed
kubectl rollout undo deployment/mesh -n biowerk
```

### Database Migrations

```bash
# Run migration job
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: db-migration-v1-1-0
  namespace: biowerk
spec:
  template:
    spec:
      containers:
      - name: migrate
        image: myregistry.com/biowerk-mesh:v1.1.0
        command: ["python", "manage.py", "migrate"]
        env:
        - name: POSTGRES_HOST
          value: pgbouncer.biowerk.svc.cluster.local
      restartPolicy: Never
  backoffLimit: 3
EOF

# Monitor migration
kubectl logs -f job/db-migration-v1-1-0 -n biowerk
```

### Cleaning Up

```bash
# Delete specific deployment
kubectl delete deployment mesh -n biowerk

# Delete everything in namespace
kubectl delete namespace biowerk

# Delete with Kustomize
kubectl delete -k k8s/base
```

## CI/CD Integration

### GitOps with ArgoCD

```bash
# Install ArgoCD
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Create Application
kubectl apply -f - <<EOF
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: biowerk
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/E-TECH-PLAYTECH/BIOwerk
    targetRevision: main
    path: k8s/overlays/production
  destination:
    server: https://kubernetes.default.svc
    namespace: biowerk
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
    - CreateNamespace=true
EOF
```

### GitHub Actions Example

```yaml
name: Deploy to Kubernetes
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up kubectl
        uses: azure/setup-kubectl@v3

      - name: Configure kubectl
        run: |
          echo "${{ secrets.KUBECONFIG }}" | base64 -d > kubeconfig
          export KUBECONFIG=./kubeconfig

      - name: Deploy
        run: |
          kubectl apply -k k8s/overlays/production
          kubectl rollout status deployment -n biowerk mesh
```

## Performance Tuning

### Database Optimization

**PostgreSQL:**
```yaml
# In postgres-statefulset.yaml, add args:
args:
  - -c
  - max_connections=200
  - -c
  - shared_buffers=2GB
  - -c
  - effective_cache_size=6GB
  - -c
  - work_mem=16MB
```

**MongoDB:**
```yaml
# Add to mongodb-statefulset.yaml:
args:
  - --wiredTigerCacheSizeGB=2
  - --maxConns=200
```

### Application Tuning

- Adjust HPA thresholds based on traffic patterns
- Use Pod Disruption Budgets for critical services
- Configure node affinity for database pods
- Use init containers for slow-starting services

## Security Hardening

### Pod Security Standards

```bash
# Enable Pod Security Admission
kubectl label namespace biowerk \
  pod-security.kubernetes.io/enforce=baseline \
  pod-security.kubernetes.io/audit=restricted \
  pod-security.kubernetes.io/warn=restricted
```

### Network Policies

```bash
# Enable network policies in kustomization.yaml
# Then apply:
kubectl apply -k k8s/base
```

### Image Scanning

```bash
# Scan images before deployment
trivy image myregistry.com/biowerk-mesh:v1.0.0
```

## Additional Resources

- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Kustomize Documentation](https://kustomize.io/)
- [Helm Documentation](https://helm.sh/docs/)
- [NGINX Ingress Controller](https://kubernetes.github.io/ingress-nginx/)
- [cert-manager](https://cert-manager.io/)
- [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets)

## Support

For issues and questions:
- GitHub Issues: https://github.com/E-TECH-PLAYTECH/BIOwerk/issues
- Documentation: https://docs.biowerk.com

## License

This project is licensed under the MIT License - see the LICENSE file for details.
