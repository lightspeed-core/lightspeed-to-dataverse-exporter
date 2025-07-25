# OpenShift Deployment Examples

This directory contains Kubernetes/OpenShift manifests and scripts for deploying the Lightspeed to Dataverse exporter in a cluster.

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