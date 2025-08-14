# Kubernetes/OpenShift Deployment Guide

This guide covers deploying the Lightspeed to Dataverse exporter in Kubernetes/OpenShift clusters. Multiple deployment patterns are supported: single-shot Jobs, scheduled CronJobs, and sidecar containers.

## Prerequisites

1. **OpenShift cluster access** with `oc` or `oc` CLI configured
2. **Container registry access** (quay.io, docker.io, or internal registry)
3. **Cluster permissions** to create ServiceAccounts, ClusterRoles, and deployments

## Quick Start

### 1. Build and Push Container Image

First, update the registry configuration and build the image:

```bash
# Set your registry details
export REGISTRY="quay.io"              # or docker.io, ghcr.io, etc.
export NAMESPACE="your-username"       # your registry namespace
export TAG="v1.0.0"                    # or latest, dev, etc. (optional)

# Build and push
./examples/build-and-push.sh
```

### 2. Update Image Reference

Edit `examples/kubernetes/deployment.yaml` to use your image:

```yaml
image: "quay.io/your-username/lightspeed-to-dataverse-exporter:v1.0.0"
```

### 3. Configure Service Settings

Edit `examples/kubernetes/configmap.yaml` to set your service configuration:

```yaml
data:
  exporter-config.yaml: |
    service_id: "<MY SERVICE ID>"  # Replace with your service ID
    ingress_server_url: "https://console.redhat.com/api/ingress/v1/upload"
    # ... other settings
```

The deployment uses OpenShift mode by default, which automatically retrieves authentication tokens from the cluster's pull-secret.

### 4. Deploy to Cluster

```bash
make deploy
```

This is equivalent to running:
```bash
# Apply the Kubernetes manifests
oc apply -f examples/kubernetes/namespace.yaml
oc apply -f examples/kubernetes/rbac.yaml  
oc apply -f examples/kubernetes/configmap.yaml
oc apply -f examples/kubernetes/deployment.yaml
```

This deploys a sidecar deployment with both the Lightspeed stack and the exporter running together. The exporter is configured with `collection_interval: 7200` (2 hours) for continuous data collection.

> **Note**: The current deployment pattern uses a sidecar approach where the exporter runs alongside the main Lightspeed application, sharing data through a mounted volume.

## Deployment Patterns

### 1. Sidecar Deployment (Current Default)

The provided manifests deploy as a sidecar container alongside the Lightspeed stack:

```bash
make deploy
```

This creates a Deployment with two containers:
- `lightspeed-stack`: The main Lightspeed application
- `lightspeed-to-dataverse-exporter`: The data exporter sidecar

Both containers share a data volume at `/tmp/data` for seamless data exchange.

### 2. Single-Shot Job (Alternative Pattern)

For one-time data collection runs, you can create a Job manifest based on the current deployment:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: lightspeed-exporter-job
  namespace: lightspeed
spec:
  template:
    metadata:
      labels:
        app: lightspeed-exporter
    spec:
      serviceAccountName: lightspeed-with-exporter
      containers:
      - name: exporter
        image: "quay.io/lightspeed-core/lightspeed-to-dataverse-exporter:dev-latest"
        args: 
        - "--mode"
        - "openshift"
        - "--config"
        - "/etc/config/config.yaml"
        - "--log-level"
        - "INFO"
        - "--data-dir"
        - "/tmp/data"
        volumeMounts:
        - name: config
          mountPath: /etc/config/config.yaml
          subPath: exporter-config.yaml
        - name: data
          mountPath: /tmp/data
      volumes:
      - name: config
        configMap:
          name: lightspeed-config
      - name: data
        emptyDir: {}
      restartPolicy: OnFailure
```

> **Note**: Set `collection_interval: 0` in the config for single-shot mode.

### 3. CronJob for Scheduled Execution

For periodic data collection, create a CronJob manifest:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: lightspeed-exporter-cron
  namespace: lightspeed
spec:
  schedule: "0 */2 * * *"  # Every 2 hours
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 1
  jobTemplate:
    spec:
      template:
        metadata:
          labels:
            app: lightspeed-exporter
        spec:
          serviceAccountName: lightspeed-with-exporter
          containers:
          - name: exporter
            image: "quay.io/lightspeed-core/lightspeed-to-dataverse-exporter:dev-latest"
            args: 
            - "--mode"
            - "openshift"
            - "--config"
            - "/etc/config/config.yaml"
            - "--log-level"
            - "INFO"
            - "--data-dir"
            - "/tmp/data"
            volumeMounts:
            - name: config
              mountPath: /etc/config/config.yaml
              subPath: exporter-config.yaml
            - name: data
              mountPath: /tmp/data
          volumes:
          - name: config
            configMap:
              name: lightspeed-config
          - name: data
            emptyDir: {}
          restartPolicy: OnFailure
```

> **⚠️ Important**: CronJobs with `emptyDir` volumes can have mounting issues in some cluster configurations. The sidecar deployment pattern is recommended for most use cases.

## Configuration Details

The current deployment uses the following key configurations:

**Namespace**: `lightspeed`
**ServiceAccount**: `lightspeed-with-exporter`
**ConfigMap**: `lightspeed-config`

**Authentication Mode**: OpenShift mode (automatic token retrieval from cluster)
**Data Directory**: `/tmp/data` (shared between containers)
**Collection Interval**: 7200 seconds (2 hours) for continuous mode

**Resource Limits** (exporter sidecar):
- Memory: 512Mi limit, 256Mi request  
- CPU: 200m limit, 100m request

## RBAC Permissions

The deployment requires these permissions:

1. **Read pull-secret**: Access to `pull-secret` in `openshift-config` namespace
2. **Read cluster version**: Access to `clusterversions.config.openshift.io`

These are configured in `examples/kubernetes/rbac.yaml` with:
- ServiceAccount: `lightspeed-with-exporter`  
- ClusterRole: `lightspeed-exporter`
- ClusterRoleBinding and RoleBinding for proper access

## Cleanup

Remove all resources:
```bash
make clean-deployment-stage
``` 