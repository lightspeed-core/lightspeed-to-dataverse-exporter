"""Tests for src.settings module."""

import pytest
import tempfile
import yaml
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
        )

        assert settings.data_dir == Path("/tmp")
        assert settings.service_id == "test-service"
        assert settings.ingress_server_url == "https://example.com/api/v1/upload"
        assert settings.ingress_server_auth_token == "test-token"
        assert settings.identity_id == "test-identity"
        assert settings.collection_interval == 300
        assert settings.cleanup_after_send is True
        assert settings.ingress_connection_timeout == 30

    def test_settings_with_defaults(self):
        """Test settings creation with default values."""
        settings = DataCollectorSettings(
            data_dir=Path("/tmp"),
            service_id="test-service",
            ingress_server_url="https://example.com/api/v1/upload",
        )

        # Check defaults
        assert settings.ingress_server_auth_token is None
        assert settings.identity_id == "unknown"
        assert settings.collection_interval == 7200  # Default from constants
        assert settings.cleanup_after_send is True
        assert settings.ingress_connection_timeout == 30  # Default from constants

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

    def test_from_yaml_valid_file(self):
        """Test loading settings from a valid YAML file."""
        config_data = {
            "data_dir": "/tmp",
            "service_id": "yaml-service",
            "ingress_server_url": "https://yaml.example.com/api/v1/upload",
            "ingress_server_auth_token": "yaml-token",
            "identity_id": "yaml-identity",
            "collection_interval": 600,
            "cleanup_after_send": False,
            "ingress_connection_timeout": 60,
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_file = Path(f.name)

        try:
            settings = DataCollectorSettings.from_yaml(config_file)

            assert settings.data_dir == Path("/tmp")
            assert settings.service_id == "yaml-service"
            assert (
                settings.ingress_server_url == "https://yaml.example.com/api/v1/upload"
            )
            assert settings.ingress_server_auth_token == "yaml-token"
            assert settings.identity_id == "yaml-identity"
            assert settings.collection_interval == 600
            assert settings.cleanup_after_send is False
            assert settings.ingress_connection_timeout == 60
        finally:
            config_file.unlink()

    def test_from_yaml_file_not_found(self):
        """Test error handling when YAML file doesn't exist."""
        non_existent_file = Path("/non/existent/config.yaml")

        with pytest.raises(FileNotFoundError) as exc_info:
            DataCollectorSettings.from_yaml(non_existent_file)

        assert "Configuration file not found" in str(exc_info.value)

    def test_from_yaml_empty_file(self):
        """Test error handling for empty YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")  # Empty file
            config_file = Path(f.name)

        try:
            with pytest.raises(ValueError) as exc_info:
                DataCollectorSettings.from_yaml(config_file)

            assert "Configuration file is empty or invalid" in str(exc_info.value)
        finally:
            config_file.unlink()

    def test_from_yaml_invalid_yaml(self):
        """Test error handling for invalid YAML syntax."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content: [")  # Invalid YAML
            config_file = Path(f.name)

        try:
            with pytest.raises(yaml.YAMLError):
                DataCollectorSettings.from_yaml(config_file)
        finally:
            config_file.unlink()

    def test_from_yaml_missing_required_fields(self):
        """Test validation error when required fields are missing from YAML."""
        config_data = {
            "service_id": "incomplete-service"
            # Missing data_dir and ingress_server_url
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_file = Path(f.name)

        try:
            with pytest.raises(ValidationError) as exc_info:
                DataCollectorSettings.from_yaml(config_file)

            errors = str(exc_info.value)
            assert "data_dir" in errors
            assert "ingress_server_url" in errors
        finally:
            config_file.unlink()

    def test_from_yaml_with_optional_fields_only(self):
        """Test loading YAML with only optional auth token field."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_data = {
                "data_dir": tmpdir,
                "service_id": "minimal-service",
                "ingress_server_url": "https://minimal.example.com/api/v1/upload",
                "ingress_server_auth_token": None,  # Explicitly None
            }

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as f:
                yaml.dump(config_data, f)
                config_file = Path(f.name)

            try:
                settings = DataCollectorSettings.from_yaml(config_file)

                assert settings.ingress_server_auth_token is None
                assert settings.identity_id == "unknown"  # Default value
            finally:
                config_file.unlink()

    def test_settings_immutability(self):
        """Test that settings are immutable after creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = DataCollectorSettings(
                data_dir=Path(tmpdir),
                service_id="immutable-service",
                ingress_server_url="https://example.com/api/v1/upload",
            )

            # Pydantic models are immutable by default, test this
            with pytest.raises(ValidationError):
                settings.service_id = "modified-service"
