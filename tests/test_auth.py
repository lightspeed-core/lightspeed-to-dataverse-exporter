"""Tests for src.auth module."""

import pytest
from unittest.mock import Mock, patch
import kubernetes
import json
import base64

from src.auth import (
    AuthProvider,
    OpenShiftAuthProvider,
    ManualAuthProvider,
    AuthenticationError,
    get_auth_credentials,
    get_openshift_auth_provider,
    get_manual_auth_provider,
)
from src.auth.providers import (
    access_token_from_offline_token,
    ClusterPullSecretNotFoundError,
    ClusterIDNotFoundError,
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


class TestManualAuthProvider:
    """Test cases for ManualAuthProvider."""

    def test_successful_initialization(self):
        """Test successful initialization with valid credentials."""
        provider = ManualAuthProvider("test-token", "test-identity")

        assert provider.get_auth_token() == "test-token"
        assert provider.get_identity_id() == "test-identity"

    def test_initialization_with_empty_token(self):
        """Test initialization fails with empty auth token."""
        with pytest.raises(AuthenticationError) as exc_info:
            ManualAuthProvider("", "test-identity")

        assert "requires both auth_token and identity_id" in str(exc_info.value)

    def test_initialization_with_empty_identity(self):
        """Test initialization fails with empty identity ID."""
        with pytest.raises(AuthenticationError) as exc_info:
            ManualAuthProvider("test-token", "")

        assert "requires both auth_token and identity_id" in str(exc_info.value)

    def test_initialization_with_none_values(self):
        """Test initialization fails with None values."""
        with pytest.raises(AuthenticationError):
            ManualAuthProvider(None, "test-identity")

        with pytest.raises(AuthenticationError):
            ManualAuthProvider("test-token", None)

    def test_get_credentials(self):
        """Test get_credentials returns correct tuple."""
        provider = ManualAuthProvider("manual-token", "manual-identity")

        token, identity = provider.get_credentials()

        assert token == "manual-token"
        assert identity == "manual-identity"


class TestOpenShiftAuthProvider:
    """Test cases for OpenShiftAuthProvider."""

    @patch("src.auth.providers.kubernetes.config.load_incluster_config")
    @patch("src.auth.providers.kubernetes.client.CoreV1Api")
    def test_successful_initialization(self, mock_core_v1, mock_load_config):
        """Test successful initialization in OpenShift cluster."""
        mock_client = Mock()
        mock_core_v1.return_value = mock_client

        provider = OpenShiftAuthProvider()

        mock_load_config.assert_called_once()
        mock_core_v1.assert_called_once()
        assert provider._k8s_client == mock_client

    @patch("src.auth.providers.kubernetes.config.load_incluster_config")
    def test_initialization_fails_outside_cluster(self, mock_load_config):
        """Test initialization fails when not in OpenShift cluster."""
        mock_load_config.side_effect = kubernetes.config.ConfigException(
            "Not in cluster"
        )

        with pytest.raises(AuthenticationError) as exc_info:
            OpenShiftAuthProvider()

        assert "Not running in OpenShift cluster" in str(exc_info.value)

    @patch("src.auth.providers.kubernetes.config.load_incluster_config")
    @patch("src.auth.providers.kubernetes.client.CoreV1Api")
    @patch("src.auth.providers.kubernetes.client.CustomObjectsApi")
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

    @patch("src.auth.providers.kubernetes.config.load_incluster_config")
    @patch("src.auth.providers.kubernetes.client.CoreV1Api")
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

    @patch("src.auth.providers.kubernetes.config.load_incluster_config")
    @patch("src.auth.providers.kubernetes.client.CoreV1Api")
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

    @patch("src.auth.providers.kubernetes.config.load_incluster_config")
    @patch("src.auth.providers.kubernetes.client.CoreV1Api")
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

    @patch("src.auth.providers.kubernetes.config.load_incluster_config")
    @patch("src.auth.providers.kubernetes.client.CoreV1Api")
    @patch("src.auth.providers.kubernetes.client.CustomObjectsApi")
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

    @patch("src.auth.providers.kubernetes.config.load_incluster_config")
    @patch("src.auth.providers.kubernetes.client.CoreV1Api")
    @patch("src.auth.providers.kubernetes.client.CustomObjectsApi")
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


class TestAccessTokenFromOfflineToken:
    """Test cases for access_token_from_offline_token function."""

    @patch("src.auth.providers.requests.post")
    def test_generate_access_token_success(self, mock_post):
        """Test successful access token generation from offline token."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "test-access-token"}
        mock_post.return_value = mock_response

        result = access_token_from_offline_token("offline-token-123")

        assert result == "test-access-token"
        mock_post.assert_called_once()

        # Check the request parameters
        call_args = mock_post.call_args
        assert "sso.stage.redhat.com" in call_args[0][0]
        assert call_args[1]["data"]["grant_type"] == "refresh_token"
        assert call_args[1]["data"]["client_id"] == "rhsm-api"
        assert call_args[1]["data"]["refresh_token"] == "offline-token-123"

    @patch("src.auth.providers.requests.post")
    def test_generate_access_token_http_error(self, mock_post):
        """Test access token generation with HTTP error response."""
        # Mock error response
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": "invalid_token"}
        mock_post.return_value = mock_response

        with pytest.raises(Exception) as exc_info:
            access_token_from_offline_token("invalid-token")

        assert "Failed to generate access token" in str(exc_info.value)
        assert "invalid_token" in str(exc_info.value)

    @patch("src.auth.providers.requests.post")
    def test_generate_access_token_json_decode_error(self, mock_post):
        """Test access token generation with invalid JSON response."""
        # Mock response with invalid JSON
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        with pytest.raises(Exception) as exc_info:
            access_token_from_offline_token("offline-token-123")

        assert "Failed to generate access token. Response is not JSON" in str(
            exc_info.value
        )
        assert "Internal Server Error" in str(exc_info.value)


class TestAuthFactory:
    """Test cases for authentication factory functions."""

    def test_get_manual_auth_provider_success(self):
        """Test successful manual auth provider creation."""
        provider = get_manual_auth_provider("test-token", "test-identity")

        assert isinstance(provider, ManualAuthProvider)
        assert provider.get_auth_token() == "test-token"
        assert provider.get_identity_id() == "test-identity"

    def test_get_manual_auth_provider_missing_credentials(self):
        """Test manual auth provider creation fails with missing credentials."""
        with pytest.raises(AuthenticationError):
            get_manual_auth_provider("", "test-identity")

    @patch("src.auth.factory.OpenShiftAuthProvider")
    def test_get_openshift_auth_provider(self, mock_openshift_provider):
        """Test OpenShift auth provider creation."""
        mock_provider = Mock()
        mock_openshift_provider.return_value = mock_provider

        provider = get_openshift_auth_provider()

        assert provider == mock_provider
        mock_openshift_provider.assert_called_once()

    def test_get_auth_credentials_manual_mode(self):
        """Test get_auth_credentials with manual mode."""
        token, identity = get_auth_credentials(
            mode="manual", auth_token="manual-token", identity_id="manual-identity"
        )

        assert token == "manual-token"
        assert identity == "manual-identity"

    @patch("src.auth.factory.get_openshift_auth_provider")
    def test_get_auth_credentials_openshift_mode(self, mock_get_provider):
        """Test get_auth_credentials with OpenShift mode."""
        mock_provider = Mock()
        mock_provider.get_credentials.return_value = (
            "openshift-token",
            "openshift-identity",
        )
        mock_get_provider.return_value = mock_provider

        token, identity = get_auth_credentials(mode="openshift")

        assert token == "openshift-token"
        assert identity == "openshift-identity"
        mock_get_provider.assert_called_once()
        mock_provider.get_credentials.assert_called_once()

    def test_get_auth_credentials_invalid_mode(self):
        """Test get_auth_credentials with invalid mode."""
        with pytest.raises(ValueError) as exc_info:
            get_auth_credentials(mode="invalid-mode")

        assert "Invalid authentication mode" in str(exc_info.value)

    def test_get_auth_credentials_manual_mode_missing_token(self):
        """Test get_auth_credentials manual mode with missing auth token."""
        with pytest.raises(AuthenticationError):
            get_auth_credentials(
                mode="manual", auth_token="", identity_id="test-identity"
            )
