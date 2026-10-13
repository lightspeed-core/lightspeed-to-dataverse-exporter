"""Tests for src.settings module."""

import pytest
import tempfile
from pathlib import Path
from pydantic import ValidationError

from src.settings import DataCollectorSettings


def _create_otel_settings(
    data_dir: Path, ledger_file: Path | None = None, **overrides
) -> DataCollectorSettings:
    values = {
        "data_dir": data_dir,
        "service_id": "test-service",
        "ingress_server_url": "https://example.com/api/v1/upload",
        "ingress_server_auth_token": "test-token",
        "identity_id": "test-identity",
        "collection_interval": 60,
        "cleanup_after_send": True,
        "ingress_connection_timeout": 30,
        "retry_interval": 120,
        "allowed_subdirs": [],
        "data_mode": "otel",
        "ledger_file": ledger_file,
    }
    values.update(overrides)
    return DataCollectorSettings(**values)


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
        """Test validation error for zero collection interval."""
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

    def test_otel_configuration_requires_ledger_file(self, tmp_path):
        data_dir = tmp_path / "input"
        data_dir.mkdir()

        with pytest.raises(ValidationError, match="ledger_file is required"):
            _create_otel_settings(data_dir)

    @pytest.mark.parametrize(
        ("prefix", "normalized"),
        [
            ("v1", "v1/"),
            ("v1/", "v1/"),
            ("v1///", "v1/"),
            ("agentic/v1/", "agentic/v1/"),
        ],
    )
    def test_otel_configuration_normalizes_safe_archive_prefix(
        self, tmp_path, prefix, normalized
    ):
        data_dir = tmp_path / "input"
        data_dir.mkdir()
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        settings = _create_otel_settings(
            data_dir,
            state_dir / "ledger.json",
            archive_path_prefix=prefix,
        )

        assert settings.archive_path_prefix == normalized

    @pytest.mark.parametrize(
        "prefix",
        [
            "",
            "/v1/",
            r"v1\archive",
            ".",
            "..",
            "v1/../archive",
            "v1//archive",
            "C:/v1",
            "\x00",
        ],
    )
    def test_otel_configuration_rejects_unsafe_archive_prefix(self, tmp_path, prefix):
        data_dir = tmp_path / "input"
        data_dir.mkdir()
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        with pytest.raises(ValidationError, match="archive_path_prefix"):
            _create_otel_settings(
                data_dir,
                state_dir / "ledger.json",
                archive_path_prefix=prefix,
            )

    @pytest.mark.parametrize(
        "active_file",
        [
            "",
            ".jsonl",
            "../traces.jsonl",
            r"..\traces.jsonl",
            "nested/traces.jsonl",
            "traces.txt",
            "\x00traces.jsonl",
        ],
    )
    def test_otel_active_file_must_be_a_plain_jsonl_basename(
        self, tmp_path, active_file
    ):
        data_dir = tmp_path / "input"
        data_dir.mkdir()
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        with pytest.raises(ValidationError, match="otel_active_file"):
            _create_otel_settings(
                data_dir,
                state_dir / "ledger.json",
                otel_active_file=active_file,
                archive_path_prefix="v1",
            )

    def test_otel_ledger_must_be_outside_source_tree(self, tmp_path):
        data_dir = tmp_path / "input"
        data_dir.mkdir()

        with pytest.raises(ValidationError, match="outside the data_dir source tree"):
            _create_otel_settings(data_dir, data_dir / "ledger.json")

    def test_otel_ledger_path_with_parent_segment_resolves_outside_source_tree(
        self, tmp_path
    ):
        data_dir = tmp_path / "input"
        data_dir.mkdir()
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        ledger_path = data_dir / ".." / "state" / "ledger.json"

        settings = _create_otel_settings(
            data_dir, ledger_path, archive_path_prefix="v1"
        )

        assert settings.ledger_file.resolve() == state_dir / "ledger.json"

    def test_otel_ledger_parent_is_checked_after_resolving_symlinks(self, tmp_path):
        data_dir = tmp_path / "input"
        data_dir.mkdir()
        source_alias = tmp_path / "input-alias"
        source_alias.symlink_to(data_dir, target_is_directory=True)

        with pytest.raises(ValidationError, match="outside the data_dir source tree"):
            _create_otel_settings(data_dir, source_alias / "ledger.json")

    def test_otel_ledger_parent_must_exist_without_being_created(self, tmp_path):
        data_dir = tmp_path / "input"
        data_dir.mkdir()
        missing_state_dir = tmp_path / "missing-state"

        with pytest.raises(ValidationError, match="existing directory"):
            _create_otel_settings(data_dir, missing_state_dir / "ledger.json")

        assert not missing_state_dir.exists()

    def test_otel_ledger_rejects_directory_and_symlink(self, tmp_path):
        data_dir = tmp_path / "input"
        data_dir.mkdir()
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        ledger_directory = state_dir / "ledger-directory"
        ledger_directory.mkdir()
        with pytest.raises(ValidationError, match="regular file"):
            _create_otel_settings(data_dir, ledger_directory)

        ledger_target = state_dir / "existing-ledger.json"
        ledger_target.write_text("{}", encoding="utf-8")
        ledger_symlink = state_dir / "ledger-link.json"
        ledger_symlink.symlink_to(ledger_target)
        with pytest.raises(ValidationError, match="must not be a symlink"):
            _create_otel_settings(data_dir, ledger_symlink)

    def test_otel_options_do_not_validate_classic_json_configuration(self, tmp_path):
        data_dir = tmp_path / "input"
        data_dir.mkdir()

        settings = _create_otel_settings(
            data_dir,
            data_dir / "ledger.json",
            data_mode="json",
            otel_active_file="../invalid.txt",
            archive_path_prefix="/unsafe//..",
        )

        assert settings.data_mode == "json"
        assert settings.archive_path_prefix == "/unsafe//.."
