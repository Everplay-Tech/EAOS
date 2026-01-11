# BIOwerk Helm Chart

This Helm chart deploys the BIOwerk application stack to Kubernetes.

## Prerequisites

- Kubernetes 1.24+
- Helm 3.8+
- PV provisioner support in the underlying infrastructure (for persistent volumes)
- Ingress controller (nginx recommended)
- cert-manager (optional, for TLS certificates)

## Installation

### Add Repository (if published)

```bash
helm repo add biowerk https://charts.biowerk.example.com
helm repo update
```

### Install from Local Chart

```bash
# Install with default values
helm install biowerk ./helm/biowerk -n biowerk --create-namespace

# Install with custom values
helm install biowerk ./helm/biowerk -n biowerk --create-namespace -f custom-values.yaml

# Install with inline value overrides
helm install biowerk ./helm/biowerk -n biowerk --create-namespace \
  --set postgresql.auth.password=mypassword \
  --set mongodb.auth.rootPassword=mypassword \
  --set grafana.admin.password=myadminpass
```

## Configuration

The following table lists the configurable parameters of the BIOwerk chart and their default values.

### Global Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `global.imageRegistry` | Global Docker image registry | `""` |
| `global.imagePullSecrets` | Global Docker registry secret names | `[]` |
| `global.storageClass` | Global storage class | `""` |
| `environment` | Environment name | `production` |

### Application Services

| Parameter | Description | Default |
|-----------|-------------|---------|
| `mesh.enabled` | Enable mesh service | `true` |
| `mesh.replicaCount` | Number of mesh replicas | `3` |
| `mesh.autoscaling.enabled` | Enable HPA for mesh | `true` |
| `mesh.autoscaling.minReplicas` | Minimum replicas | `2` |
| `mesh.autoscaling.maxReplicas` | Maximum replicas | `10` |

### Database Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `postgresql.enabled` | Enable PostgreSQL | `true` |
| `postgresql.auth.username` | PostgreSQL username | `biowerk` |
| `postgresql.auth.password` | PostgreSQL password | `""` |
| `postgresql.persistence.size` | PostgreSQL PVC size | `50Gi` |
| `mongodb.enabled` | Enable MongoDB | `true` |
| `mongodb.auth.rootUsername` | MongoDB root username | `biowerk` |
| `mongodb.auth.rootPassword` | MongoDB root password | `""` |
| `mongodb.persistence.size` | MongoDB PVC size | `50Gi` |
| `redis.enabled` | Enable Redis | `true` |
| `redis.persistence.size` | Redis PVC size | `20Gi` |

### Observability

| Parameter | Description | Default |
|-----------|-------------|---------|
| `prometheus.enabled` | Enable Prometheus | `true` |
| `grafana.enabled` | Enable Grafana | `true` |
| `loki.enabled` | Enable Loki | `true` |
| `alertmanager.enabled` | Enable Alertmanager | `true` |

### Ingress

| Parameter | Description | Default |
|-----------|-------------|---------|
| `ingress.enabled` | Enable ingress | `true` |
| `ingress.className` | Ingress class name | `nginx` |
| `ingress.hosts` | Ingress hosts | See values.yaml |
| `ingress.tls` | Ingress TLS configuration | See values.yaml |

## Upgrading

```bash
# Upgrade with default values
helm upgrade biowerk ./helm/biowerk -n biowerk

# Upgrade with custom values
helm upgrade biowerk ./helm/biowerk -n biowerk -f custom-values.yaml
```

## Uninstalling

```bash
helm uninstall biowerk -n biowerk
```

## Examples

### Production Deployment

```yaml
# production-values.yaml
environment: production

mesh:
  replicaCount: 5
  autoscaling:
    minReplicas: 3
    maxReplicas: 20

postgresql:
  auth:
    password: "CHANGE_ME"
  persistence:
    size: 200Gi
    storageClass: fast-ssd
  resources:
    requests:
      cpu: 1000m
      memory: 4Gi
    limits:
      cpu: 4000m
      memory: 16Gi

ingress:
  hosts:
    - host: biowerk.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: biowerk-prod-tls
      hosts:
        - biowerk.com
```

Deploy:
```bash
helm install biowerk ./helm/biowerk -n biowerk -f production-values.yaml
```

### Staging Deployment

```yaml
# staging-values.yaml
environment: staging

mesh:
  replicaCount: 2
  autoscaling:
    minReplicas: 1
    maxReplicas: 4
  resources:
    requests:
      cpu: 100m
      memory: 256Mi

postgresql:
  persistence:
    size: 50Gi
  resources:
    requests:
      cpu: 250m
      memory: 512Mi

ingress:
  hosts:
    - host: staging.biowerk.com
```

Deploy:
```bash
helm install biowerk-staging ./helm/biowerk -n biowerk-staging -f staging-values.yaml
```

## Troubleshooting

### Check deployment status

```bash
helm status biowerk -n biowerk
kubectl get pods -n biowerk
kubectl get svc -n biowerk
```

### View logs

```bash
kubectl logs -f -n biowerk -l app.kubernetes.io/name=biowerk
```

### Debug Helm template

```bash
helm template biowerk ./helm/biowerk -f custom-values.yaml
```

## Contributing

Please read CONTRIBUTING.md for details on our code of conduct and the process for submitting pull requests.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
