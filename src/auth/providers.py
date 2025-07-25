"""Authentication providers for different deployment environments."""

import base64
import json
import logging
import requests
import kubernetes
import kubernetes.client
import kubernetes.config

from src import constants


logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Exception raised when authentication fails."""


class ClusterPullSecretNotFoundError(AuthenticationError):
    """Exception raised when cluster pull secret cannot be found or accessed."""


class ClusterIDNotFoundError(AuthenticationError):
    """Exception raised when cluster ID cannot be retrieved."""


class AuthProvider:
    """Base class for authentication providers."""

    def get_auth_token(self) -> str:
        """Get authentication token.

        Returns:
            str: Authentication token

        Raises:
            AuthenticationError: If token cannot be retrieved
        """
        raise NotImplementedError

    def get_identity_id(self) -> str:
        """Get identity identifier.

        Returns:
            str: Identity identifier

        Raises:
            AuthenticationError: If identity ID cannot be retrieved
        """
        raise NotImplementedError

    def get_credentials(self) -> tuple[str, str]:
        """Get both authentication token and identity ID.

        Returns:
            tuple[str, str]: Tuple of (auth_token, identity_id)

        Raises:
            AuthenticationError: If credentials cannot be retrieved
        """
        return self.get_auth_token(), self.get_identity_id()


def access_token_from_offline_token(offline_token: str) -> str:
    """Generate "access token" from the "offline token".

    Offline token can be generated at:
        prod - https://access.redhat.com/management/api
        stage - https://access.stage.redhat.com/management/api

    Args:
        offline_token: Offline token from the Customer Portal.

    Returns:
        Refresh token.
    """
    url = "https://sso.stage.redhat.com/"
    endpoint = "auth/realms/redhat-external/protocol/openid-connect/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": "rhsm-api",
        "refresh_token": offline_token,
    }

    response = requests.post(
        url + endpoint, data=data, timeout=constants.ACCESS_TOKEN_GENERATION_TIMEOUT
    )
    try:
        if response.status_code == requests.codes.ok:
            return response.json()["access_token"]
        raise Exception(f"Failed to generate access token. Response: {response.json()}")
    except json.JSONDecodeError:
        raise Exception(
            "Failed to generate access token. Response is not JSON."
            f"Response: {response.status_code}: {response.text}"
        )


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


class ManualAuthProvider(AuthProvider):
    """Authentication provider for manual environments with explicit credentials."""

    def __init__(self, auth_token: str, identity_id: str):
        """Initialize the manual authentication provider.

        Args:
            auth_token: Authentication token
            identity_id: Identity identifier
        """
        if not auth_token or not identity_id:
            raise AuthenticationError(
                "Manual authentication requires both auth_token and identity_id"
            )

        self.auth_token = auth_token
        self.identity_id = identity_id
        logger.info("Initialized manual authentication provider")

    def get_auth_token(self) -> str:
        """Get the manually provided authentication token.

        Returns:
            str: The authentication token
        """
        return self.auth_token

    def get_identity_id(self) -> str:
        """Get the manually provided identity ID.

        Returns:
            str: The identity identifier
        """
        return self.identity_id
