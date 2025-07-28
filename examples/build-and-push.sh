#!/bin/bash
set -e

# Configuration - update these values for your environment
REGISTRY="${REGISTRY:-quay.io}"
NAMESPACE="${NAMESPACE:-your-username}"
IMAGE_NAME="${IMAGE_NAME:-lightspeed-dataverse-exporter}"
TAG="${TAG:-latest}"

# Full image name
FULL_IMAGE="${REGISTRY}/${NAMESPACE}/${IMAGE_NAME}:${TAG}"

echo "Building and pushing container image: ${FULL_IMAGE}"
echo "============================================="

# Build the image
echo "🔨 Building container image..."
podman build -t "${FULL_IMAGE}" .

# Push to registry
echo "📤 Pushing to registry..."
podman push "${FULL_IMAGE}"

echo "✅ Successfully built and pushed: ${FULL_IMAGE}"
echo ""
echo "📝 Next steps:"
echo "1. Update the image in examples/kubernetes/deployment.yaml:"
echo "   image: \"${FULL_IMAGE}\""
echo ""
echo "2. Deploy to OpenShift:"
echo "   oc apply -f examples/kubernetes/"
echo ""
echo "3. Check the logs:"
echo "   oc logs -f deployment/lightspeed-exporter" 
