"""Unit tests for ingress_client module."""

import io
import pytest
from pytest_mock import MockerFixture
import requests

from src.ingress_client import IngressClient


class TestIngressClient:
    """Tests for the IngressClient class."""

    @pytest.fixture
    def client(self):
        """Create an IngressClient instance for testing."""
        return IngressClient(
            ingress_server_url="https://example.com/api/v1/upload",
            ingress_server_auth_token="test-token",
            service_id="test-service",
            identity_id="test-identity",
            connection_timeout=30,
        )

    def test_upload_data_to_ingress_success(self, mocker: MockerFixture, client):
        """Test successful data upload to ingress server."""
        # Setup mock response
        mock_response = mocker.Mock()
        mock_response.status_code = 202
        mock_response.json.return_value = {"request_id": "test-123"}

        mock_session = mocker.Mock()
        mock_session.post.return_value = mock_response
        mock_session_class = mocker.patch("src.ingress_client.requests.Session")
        mock_session_class.return_value.__enter__.return_value = mock_session

        tarball = io.BytesIO(b"test data")
        response = client._upload_data_to_ingress(tarball)

        assert response.status_code == 202
        mock_session.post.assert_called_once()

        # Check that headers were set correctly
        call_args = mock_session.post.call_args
        assert call_args[1]["url"] == "https://example.com/api/v1/upload"
        assert call_args[1]["timeout"] == 30

        # Check session headers
        expected_headers = {
            "User-Agent": "openshift-lightspeed-operator/user-data-collection cluster/test-identity",
            "Authorization": "Bearer test-token",
        }
        for key, value in expected_headers.items():
            assert mock_session.headers[key] == value

    def test_upload_tarball_success(self, mocker: MockerFixture, client):
        """Test successful tarball upload."""
        # Setup mock response
        mock_response = mocker.Mock()
        mock_response.status_code = 202
        mock_response.json.return_value = {"request_id": "test-request-123"}

        mock_session = mocker.Mock()
        mock_session.post.return_value = mock_response
        mock_session_class = mocker.patch("src.ingress_client.requests.Session")
        mock_session_class.return_value.__enter__.return_value = mock_session

        tarball = io.BytesIO(b"test tarball data")
        request_id = client.upload_tarball(tarball)

        assert request_id == "test-request-123"
        mock_session.post.assert_called_once()

        # Check that tarball is closed
        assert tarball.closed

    def test_upload_tarball_failure(self, mocker: MockerFixture, client):
        """Test tarball upload failure handling."""
        # Setup mock response for failure
        mock_response = mocker.Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_session = mocker.Mock()
        mock_session.post.return_value = mock_response
        mock_session_class = mocker.patch("src.ingress_client.requests.Session")
        mock_session_class.return_value.__enter__.return_value = mock_session

        tarball = io.BytesIO(b"test tarball data")

        with pytest.raises(requests.RequestException) as exc_info:
            client.upload_tarball(tarball)

        assert "Data upload failed with response code: 500" in str(exc_info.value)
        assert "Internal Server Error" in str(exc_info.value)
        mock_session.post.assert_called_once()

    def test_upload_tarball_network_error(self, mocker: MockerFixture, client):
        """Test tarball upload with network error."""
        mock_session = mocker.Mock()
        mock_session.post.side_effect = requests.ConnectionError("Network error")
        mock_session_class = mocker.patch("src.ingress_client.requests.Session")
        mock_session_class.return_value.__enter__.return_value = mock_session

        tarball = io.BytesIO(b"test tarball data")

        with pytest.raises(requests.ConnectionError):
            client.upload_tarball(tarball)

        mock_session.post.assert_called_once()

    def test_client_initialization(self):
        """Test IngressClient initialization."""
        client = IngressClient(
            ingress_server_url="https://test.example.com",
            ingress_server_auth_token="token-123",
            service_id="service-456",
            identity_id="identity-789",
            connection_timeout=60,
        )

        assert client.ingress_server_url == "https://test.example.com"
        assert client.ingress_server_auth_token == "token-123"
        assert client.service_id == "service-456"
        assert client.identity_id == "identity-789"
        assert client.connection_timeout == 60
