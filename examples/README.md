# OpenShift Deployment Examples

This directory contains Kubernetes/OpenShift manifests and scripts for deploying the Lightspeed to Dataverse exporter as Jobs in a cluster. The provided manifests are designed for single-shot mode execution, ideal for periodic data collection via CronJobs.

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

Edit `examples/kubernetes/deployment.yaml` and `examples/kubernetes/job.yaml` to use your image:

```yaml
image: "quay.io/your-username/lightspeed-exporter:v1.0.0"
```

### 3. Configure Ingress URL

Edit `examples/kubernetes/configmap-<stage|prod>.yaml`:

When using stage, you need to obtain offline token through https://access.redhat.com/management/api and use it as
```bash
python scripts/ingress_token_from_offline_token.py --offline-token <offline-token> --env stage
```
to obtain the auth token you can set in the `configmap-stage.yaml`.

### 4. Deploy to Cluster

```bash
make deploy-stage
```

This deploys a Kubernetes Job that runs once in single-shot mode and exits (configured with `collection_interval: 0`).

> **Note**: For continuous mode deployments (daemon-style), you would need to create a Deployment manifest with `collection_interval` set to a positive number. The provided examples focus on single-shot mode which is more efficient for periodic data collection in Kubernetes environments.

### Creating a CronJob for Periodic Execution

To run the job on a schedule, create a CronJob manifest:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: lightspeed-exporter-cron
  namespace: lsdv-exporter
spec:
  schedule: "0 */2 * * *"  # Every 2 hours
  jobTemplate:
    spec:
      template:
        # Use the same spec as job-stage.yaml
```

## RBAC Permissions

The deployment requires these permissions:

1. **Read pull-secret**: Access to `pull-secret` in `openshift-config` namespace
2. **Read cluster version**: Access to `clusterversions.config.openshift.io`

These are configured in `examples/kubernetes/rbac.yaml`.

## Cleanup

Remove all resources:
```bash
make clean-stage
``` 