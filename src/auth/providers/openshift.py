"""Providers for openshift auth."""

import base64
import json
import logging
import kubernetes
import kubernetes.client
import kubernetes.config

from .types import AuthProvider, AuthenticationError


logger = logging.getLogger(__name__)


class ClusterPullSecretNotFoundError(AuthenticationError):
    """Exception raised when cluster pull secret cannot be found or accessed."""


class ClusterIDNotFoundError(AuthenticationError):
    """Exception raised when cluster ID cannot be retrieved."""


class OpenShiftAuthProvider(AuthProvider):
    """Authentication provider for OpenShift environments."""

    def __init__(self):
        """Initialize the OpenShift authentication provider."""
        try:
            kubernetes.config.load_incluster_config()
            self._k8s_client = kubernetes.client.CoreV1Api()
            logger.info("Initialized OpenShift authentication provider")
        except kubernetes.config.ConfigException as e:
            logger.error("Failed to load OpenShift in-cluster config: %s", e)
            raise AuthenticationError("Not running in OpenShift cluster") from e

    def get_auth_token(self) -> str:
        """Get the pull secret token from the OpenShift cluster.

        Returns:
            str: The authentication token from cloud.openshift.com

        Raises:
            ClusterPullSecretNotFoundError: If pull secret cannot be retrieved
        """
        try:
            secret = self._k8s_client.read_namespaced_secret(
                "pull-secret", "openshift-config"
            )
            dockerconfigjson = secret.data[".dockerconfigjson"]
            dockerconfig = json.loads(
                base64.b64decode(dockerconfigjson).decode("utf-8")
            )
            return dockerconfig["auths"]["cloud.openshift.com"]["auth"]
        except KeyError as e:
            logger.error(
                "Failed to get token from cluster pull-secret, missing keys: %s", e
            )
            raise ClusterPullSecretNotFoundError(
                "Missing required keys in pull secret"
            ) from e
        except (TypeError, json.JSONDecodeError) as e:
            logger.error("Failed to parse pull-secret data: %s", e)
            raise ClusterPullSecretNotFoundError("Invalid pull secret format") from e
        except kubernetes.client.exceptions.ApiException as e:
            logger.error("Failed to get pull-secret object, body: %s", str(e.body))
            raise ClusterPullSecretNotFoundError("Cannot access pull secret") from e

    def get_identity_id(self) -> str:
        """Get the cluster ID from OpenShift.

        Returns:
            str: The cluster identifier

        Raises:
            ClusterIDNotFoundError: If cluster ID cannot be retrieved
        """
        try:
            # Get cluster version to extract cluster ID
            config_client = kubernetes.client.CustomObjectsApi()
            cluster_version = config_client.get_cluster_custom_object(
                group="config.openshift.io",
                version="v1",
                plural="clusterversions",
                name="version",
            )
            return cluster_version["spec"]["clusterID"]
        except KeyError as e:
            logger.error("Failed to get cluster ID, missing keys: %s", e)
            raise ClusterIDNotFoundError("Missing cluster ID in cluster version") from e
        except kubernetes.client.exceptions.ApiException as e:
            logger.error("Failed to get cluster version object, body: %s", str(e.body))
            raise ClusterIDNotFoundError("Cannot access cluster version") from e
