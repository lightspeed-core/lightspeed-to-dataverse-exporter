"""Tests for src.settings module."""

import pytest
import tempfile
from pathlib import Path
from pydantic import ValidationError

from src.settings import DataCollectorSettings


class TestDataCollectorSettings:
    """Test cases for DataCollectorSettings."""

    def test_valid_settings_creation(self):
        """Test creating settings with valid data."""
        settings = DataCollectorSettings(
            data_dir=Path("/tmp"),
            service_id="test-service",
            ingress_server_url="https://example.com/api/v1/upload",
            ingress_server_auth_token="test-token",
            identity_id="test-identity",
            collection_interval=300,
            cleanup_after_send=True,
            ingress_connection_timeout=30,
            retry_interval=120,
            allowed_subdirs=[],
        )

        assert settings.data_dir == Path("/tmp")
        assert settings.service_id == "test-service"
        assert settings.ingress_server_url == "https://example.com/api/v1/upload"
        assert settings.ingress_server_auth_token == "test-token"
        assert settings.identity_id == "test-identity"
        assert settings.collection_interval == 300
        assert settings.cleanup_after_send is True
        assert settings.ingress_connection_timeout == 30
        assert settings.retry_interval == 120

    def test_invalid_data_dir(self):
        """Test validation error for non-existent data directory."""
        with pytest.raises(ValidationError) as exc_info:
            DataCollectorSettings(
                data_dir=Path("/non/existent/path"),
                service_id="test-service",
                ingress_server_url="https://example.com/api/v1/upload",
            )

        assert "path_not_directory" in str(exc_info.value)

    def test_invalid_collection_interval(self):
        """Test validation error for negative collection interval."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValidationError) as exc_info:
                DataCollectorSettings(
                    data_dir=Path(tmpdir),
                    service_id="test-service",
                    ingress_server_url="https://example.com/api/v1/upload",
                    collection_interval=-1,
                )

            assert "greater_than" in str(exc_info.value)

    def test_zero_collection_interval(self):
        """Test validation error for negative collection interval."""
        with tempfile.TemporaryDirectory() as tmpdir:
            DataCollectorSettings(
                data_dir=Path(tmpdir),
                service_id="test-service",
                ingress_server_url="https://example.com/api/v1/upload",
                ingress_server_auth_token="test-token",
                identity_id="test-identity",
                collection_interval=0,
                cleanup_after_send=True,
                ingress_connection_timeout=30,
                retry_interval=120,
                allowed_subdirs=[],
            )

    def test_settings_immutability(self):
        """Test that settings are immutable after creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = DataCollectorSettings(
                data_dir=Path(tmpdir),
                service_id="test-service",
                ingress_server_url="https://example.com/api/v1/upload",
                ingress_server_auth_token="test-token",
                identity_id="test-identity",
                collection_interval=0,
                cleanup_after_send=True,
                ingress_connection_timeout=30,
                retry_interval=120,
                allowed_subdirs=[],
            )

            # Pydantic models are immutable by default, test this
            with pytest.raises(ValidationError):
                settings.service_id = "modified-service"
