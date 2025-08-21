"""Tests for src.auth module."""

import base64
from unittest.mock import Mock, patch

import jwt
import kubernetes
import pytest
import requests_mock

from src.auth.providers.sso import SSOServiceAccountAuthProvider
from src.auth.providers import AuthProvider, AuthenticationError, OpenShiftAuthProvider
from src.auth.providers.openshift import (
    ClusterIDNotFoundError,
    ClusterPullSecretNotFoundError,
)


class TestAuthProvider:
    """Test cases for the base AuthProvider class."""

    def test_base_provider_not_implemented(self):
        """Test that base AuthProvider methods raise NotImplementedError."""
        provider = AuthProvider()

        with pytest.raises(NotImplementedError):
            provider.get_auth_token()

        with pytest.raises(NotImplementedError):
            provider.get_identity_id()

    def test_get_credentials_returns_tuple(self):
        """Test that get_credentials returns a tuple of token and identity."""
        provider = AuthProvider()

        # Mock the individual methods
        provider.get_auth_token = Mock(return_value="test-token")
        provider.get_identity_id = Mock(return_value="test-identity")

        token, identity = provider.get_credentials()

        assert token == "test-token"
        assert identity == "test-identity"
        provider.get_auth_token.assert_called_once()
        provider.get_identity_id.assert_called_once()


class TestOpenShiftAuthProvider:
    """Test cases for OpenShiftAuthProvider."""

    @patch("src.auth.providers.openshift.kubernetes.config.load_incluster_config")
    @patch("src.auth.providers.openshift.kubernetes.client.CoreV1Api")
    def test_successful_initialization(self, mock_core_v1, mock_load_config):
        """Test successful initialization in OpenShift cluster."""
        mock_client = Mock()
        mock_core_v1.return_value = mock_client

        provider = OpenShiftAuthProvider()

        mock_load_config.assert_called_once()
        mock_core_v1.assert_called_once()
        assert provider._k8s_client == mock_client

    @patch("src.auth.providers.openshift.kubernetes.config.load_incluster_config")
    def test_initialization_fails_outside_cluster(self, mock_load_config):
        """Test initialization fails when not in OpenShift cluster."""
        mock_load_config.side_effect = kubernetes.config.ConfigException(
            "Not in cluster"
        )

        with pytest.raises(AuthenticationError) as exc_info:
            OpenShiftAuthProvider()

        assert "Not running in OpenShift cluster" in str(exc_info.value)

    @patch("src.auth.providers.openshift.kubernetes.config.load_incluster_config")
    @patch("src.auth.providers.openshift.kubernetes.client.CoreV1Api")
    @patch("src.auth.providers.openshift.kubernetes.client.CustomObjectsApi")
    def test_get_identity_id_success(
        self, mock_custom_api, mock_core_v1, mock_load_config
    ):
        """Test successful cluster ID retrieval."""
        # Setup mocks
        mock_core_v1.return_value = Mock()
        mock_custom_client = Mock()
        mock_custom_api.return_value = mock_custom_client

        # Mock cluster version response
        cluster_version = {"spec": {"clusterID": "test-cluster-id"}}
        mock_custom_client.get_cluster_custom_object.return_value = cluster_version

        provider = OpenShiftAuthProvider()
        identity = provider.get_identity_id()

        assert identity == "test-cluster-id"
        mock_custom_client.get_cluster_custom_object.assert_called_with(
            group="config.openshift.io",
            version="v1",
            plural="clusterversions",
            name="version",
        )

    @patch("src.auth.providers.openshift.kubernetes.config.load_incluster_config")
    @patch("src.auth.providers.openshift.kubernetes.client.CoreV1Api")
    def test_get_auth_token_key_error(self, mock_core_v1, mock_load_config):
        """Test get_auth_token handles KeyError when pull secret is malformed."""
        mock_client = Mock()
        mock_core_v1.return_value = mock_client

        # Mock secret with missing keys
        mock_secret = Mock()
        mock_secret.data = {}  # Missing .dockerconfigjson key
        mock_client.read_namespaced_secret.return_value = mock_secret

        provider = OpenShiftAuthProvider()

        with pytest.raises(ClusterPullSecretNotFoundError) as exc_info:
            provider.get_auth_token()

        assert "Missing required keys in pull secret" in str(exc_info.value)

    @patch("src.auth.providers.openshift.kubernetes.config.load_incluster_config")
    @patch("src.auth.providers.openshift.kubernetes.client.CoreV1Api")
    def test_get_auth_token_json_decode_error(self, mock_core_v1, mock_load_config):
        """Test get_auth_token handles JSONDecodeError when pull secret data is invalid."""
        mock_client = Mock()
        mock_core_v1.return_value = mock_client

        # Mock secret with invalid JSON
        mock_secret = Mock()
        invalid_json = base64.b64encode(b"invalid json").decode("utf-8")
        mock_secret.data = {".dockerconfigjson": invalid_json}
        mock_client.read_namespaced_secret.return_value = mock_secret

        provider = OpenShiftAuthProvider()

        with pytest.raises(ClusterPullSecretNotFoundError) as exc_info:
            provider.get_auth_token()

        assert "Invalid pull secret format" in str(exc_info.value)

    @patch("src.auth.providers.openshift.kubernetes.config.load_incluster_config")
    @patch("src.auth.providers.openshift.kubernetes.client.CoreV1Api")
    def test_get_auth_token_api_exception(self, mock_core_v1, mock_load_config):
        """Test get_auth_token handles Kubernetes API exceptions."""
        mock_client = Mock()
        mock_core_v1.return_value = mock_client

        # Mock API exception
        api_error = kubernetes.client.exceptions.ApiException(
            status=404, reason="Not Found"
        )
        api_error.body = "Secret not found"
        mock_client.read_namespaced_secret.side_effect = api_error

        provider = OpenShiftAuthProvider()

        with pytest.raises(ClusterPullSecretNotFoundError) as exc_info:
            provider.get_auth_token()

        assert "Cannot access pull secret" in str(exc_info.value)

    @patch("src.auth.providers.openshift.kubernetes.config.load_incluster_config")
    @patch("src.auth.providers.openshift.kubernetes.client.CoreV1Api")
    @patch("src.auth.providers.openshift.kubernetes.client.CustomObjectsApi")
    def test_get_identity_id_key_error(
        self, mock_custom_api, mock_core_v1, mock_load_config
    ):
        """Test get_identity_id handles KeyError when cluster version is malformed."""
        mock_client = Mock()
        mock_core_v1.return_value = mock_client
        mock_custom_client = Mock()
        mock_custom_api.return_value = mock_custom_client

        # Mock cluster version response missing clusterID
        cluster_version = {"spec": {}}  # Missing clusterID
        mock_custom_client.get_cluster_custom_object.return_value = cluster_version

        provider = OpenShiftAuthProvider()

        with pytest.raises(ClusterIDNotFoundError) as exc_info:
            provider.get_identity_id()

        assert "Missing cluster ID in cluster version" in str(exc_info.value)

    @patch("src.auth.providers.openshift.kubernetes.config.load_incluster_config")
    @patch("src.auth.providers.openshift.kubernetes.client.CoreV1Api")
    @patch("src.auth.providers.openshift.kubernetes.client.CustomObjectsApi")
    def test_get_identity_id_api_exception(
        self, mock_custom_api, mock_core_v1, mock_load_config
    ):
        """Test get_identity_id handles Kubernetes API exceptions."""
        mock_client = Mock()
        mock_core_v1.return_value = mock_client
        mock_custom_client = Mock()
        mock_custom_api.return_value = mock_custom_client

        # Mock API exception
        api_error = kubernetes.client.exceptions.ApiException(
            status=403, reason="Forbidden"
        )
        api_error.body = "Access denied"
        mock_custom_client.get_cluster_custom_object.side_effect = api_error

        provider = OpenShiftAuthProvider()

        with pytest.raises(ClusterIDNotFoundError) as exc_info:
            provider.get_identity_id()

        assert "Cannot access cluster version" in str(exc_info.value)


class TestSSOServiceAccountAuthProvider:
    def test_sso_auth(self, requests_mock: requests_mock.Mocker):
        client_id = "test-client-id"
        client_secret = "test-client_secret"
        expected_token = "token123"

        sso_token = jwt.encode({"preferred_username": "test-user"}, key="test")

        requests_mock.post(
            "https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token",
            json={"access_token": sso_token},
            additional_matcher=(
                lambda req: client_id in req.text
                and client_secret in req.text
                and "client_credentials" in req.text
            ),
        )

        requests_mock.post(
            "https://api.openshift.com/api/accounts_mgmt/v1/access_token",
            headers={"Authorization": f"Bearer {sso_token}"},
            json={
                "auths": {
                    "cloud.openshift.com": {
                        "auth": expected_token,
                    }
                }
            },
        )

        provider = SSOServiceAccountAuthProvider(
            client_id=client_id, client_secret=client_secret
        )

        actual_token, actual_identity_id = provider.get_credentials()
        assert actual_token == expected_token
        assert actual_identity_id == "test-user"

    def test_bad_sso_credentials(self, requests_mock: requests_mock.Mocker):
        client_id = "test-client-id"
        client_secret = "test-client_secret"

        requests_mock.post(
            "https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token",
            status_code=401,
        )

        provider = SSOServiceAccountAuthProvider(
            client_id=client_id, client_secret=client_secret
        )

        with pytest.raises(AuthenticationError):
            _, _ = provider.get_credentials()

    def test_bad_api_credentials(self, requests_mock: requests_mock.Mocker):
        client_id = "test-client-id"
        client_secret = "test-client_secret"

        sso_token = jwt.encode({"preferred_username": "test-user"}, key="test")

        requests_mock.post(
            "https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token",
            json={"access_token": sso_token},
            additional_matcher=(
                lambda req: client_id in req.text
                and client_secret in req.text
                and "client_credentials" in req.text
            ),
        )

        requests_mock.post(
            "https://api.openshift.com/api/accounts_mgmt/v1/access_token",
            status_code=403,
        )

        provider = SSOServiceAccountAuthProvider(
            client_id=client_id, client_secret=client_secret
        )

        with pytest.raises(AuthenticationError):
            _, _ = provider.get_credentials()
