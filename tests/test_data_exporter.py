"""Tests for src.data_exporter module."""

import tempfile
from pathlib import Path
from unittest.mock import patch, Mock
import io
import pytest
import requests
import tarfile

from src.data_exporter import (
    DataCollectorService,
    package_files_into_tarball,
)


# Note: FilterAllowedFiles and CollectFiles tests moved to test_file_handler.py
# since these functions are now part of the FileHandler class


class TestDataCollectorService:
    """Test cases for DataCollectorService."""

    def test_collect_and_process_no_files(self):
        """Test that service initializes correctly with all required parameters."""

        with tempfile.TemporaryDirectory() as tmpdir:
            service = DataCollectorService(
                data_dir=Path(tmpdir),
                service_id="test-service",
                ingress_server_url="https://example.com/api/v1/upload",
                ingress_server_auth_token="test-token",
                identity_id="test-identity",
                collection_interval=60,
                ingress_connection_timeout=30,
                cleanup_after_send=True,
            )

            # Test that service attributes are set correctly
            assert service.data_dir == Path(tmpdir)
            assert service.service_id == "test-service"
            assert service.ingress_server_url == "https://example.com/api/v1/upload"
            assert service.ingress_server_auth_token == "test-token"
            assert service.identity_id == "test-identity"
            assert service.collection_interval == 60
            assert service.ingress_connection_timeout == 30
            assert service.cleanup_after_send is True

    @patch("src.data_exporter.requests.Session")
    def test_upload_data_to_ingress_success(self, mock_session_class):
        """Test successful data upload to ingress server."""
        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.json.return_value = {"request_id": "test-123"}

        mock_session = Mock()
        mock_session.post.return_value = mock_response
        mock_session_class.return_value.__enter__.return_value = mock_session

        with tempfile.TemporaryDirectory() as tmpdir:
            service = DataCollectorService(
                data_dir=Path(tmpdir),
                service_id="test-service",
                ingress_server_url="https://example.com/api/v1/upload",
                ingress_server_auth_token="test-token",
                identity_id="test-identity",
                collection_interval=60,
                ingress_connection_timeout=30,
                cleanup_after_send=True,
            )

            tarball = io.BytesIO(b"test data")
            response = service._upload_data_to_ingress(tarball)

            assert response.status_code == 202
            mock_session.post.assert_called_once()

    @patch("src.data_exporter.requests.Session")
    def test_upload_tarball_success(self, mock_session_class):
        """Test successful tarball upload."""
        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.json.return_value = {"request_id": "test-123"}

        mock_session = Mock()
        mock_session.post.return_value = mock_response
        mock_session_class.return_value.__enter__.return_value = mock_session

        with tempfile.TemporaryDirectory() as tmpdir:
            service = DataCollectorService(
                data_dir=Path(tmpdir),
                service_id="test-service",
                ingress_server_url="https://example.com/api/v1/upload",
                ingress_server_auth_token="test-token",
                identity_id="test-identity",
                collection_interval=60,
                ingress_connection_timeout=30,
                cleanup_after_send=True,
            )

            tarball = io.BytesIO(b"test data")
            # Should not raise an exception
            service.upload_tarball(tarball)

    @patch("src.data_exporter.requests.Session")
    def test_upload_tarball_failure(self, mock_session_class):
        """Test tarball upload failure handling."""
        # Setup mock response for failure
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_session = Mock()
        mock_session.post.return_value = mock_response
        mock_session_class.return_value.__enter__.return_value = mock_session

        with tempfile.TemporaryDirectory() as tmpdir:
            service = DataCollectorService(
                data_dir=Path(tmpdir),
                service_id="test-service",
                ingress_server_url="https://example.com/api/v1/upload",
                ingress_server_auth_token="test-token",
                identity_id="test-identity",
                collection_interval=60,
                ingress_connection_timeout=30,
                cleanup_after_send=True,
            )

            tarball = io.BytesIO(b"test data")
            with pytest.raises(requests.RequestException):
                service.upload_tarball(tarball)

    def test_service_initialization(self):
        """Test DataCollectorService initialization with all parameters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service = DataCollectorService(
                data_dir=Path(tmpdir),
                service_id="test-service",
                ingress_server_url="https://example.com/api/v1/upload",
                ingress_server_auth_token="test-token",
                identity_id="cluster-123",
                collection_interval=60,
                ingress_connection_timeout=30,
                cleanup_after_send=True,
            )

            # Verify all attributes are set correctly
            assert service.data_dir == Path(tmpdir)
            assert service.service_id == "test-service"
            assert service.ingress_server_url == "https://example.com/api/v1/upload"
            assert service.ingress_server_auth_token == "test-token"
            assert service.identity_id == "cluster-123"
            assert service.collection_interval == 60
            assert service.ingress_connection_timeout == 30
            assert service.cleanup_after_send is True

    def test_service_initialization_with_different_params(self):
        """Test DataCollectorService initialization with different parameters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service = DataCollectorService(
                data_dir=Path(tmpdir),
                service_id="my-service",
                ingress_server_url="https://example.com/api/v1/upload",
                ingress_server_auth_token="test-token",
                identity_id="test-identity",
                collection_interval=120,
                ingress_connection_timeout=60,
                cleanup_after_send=False,
            )

            # Verify different parameter values
            assert service.service_id == "my-service"
            assert service.collection_interval == 120
            assert service.ingress_connection_timeout == 60
            assert service.cleanup_after_send is False

    def test_service_initialization_with_custom_allowed_subdirs(self):
        """Test DataCollectorService initialization with custom allowed_subdirs."""
        custom_subdirs = ["logs", "metrics", "traces"]

        with tempfile.TemporaryDirectory() as tmpdir:
            service = DataCollectorService(
                data_dir=Path(tmpdir),
                service_id="test-service",
                ingress_server_url="https://example.com/api/v1/upload",
                ingress_server_auth_token="test-token",
                identity_id="test-identity",
                collection_interval=60,
                ingress_connection_timeout=30,
                cleanup_after_send=True,
                allowed_subdirs=custom_subdirs,
            )

            # Verify allowed_subdirs is set correctly
            assert service.allowed_subdirs == custom_subdirs
            # Verify file_handler gets the custom subdirs
            assert service.file_handler.allowed_subdirs == custom_subdirs


# Note: GatherDataChunks tests moved to test_file_handler.py
# since this functionality is now part of the FileHandler class


class TestPackageFilesIntoTarball:
    """Test cases for package_files_into_tarball function."""

    def test_package_files_into_tarball_success(self):
        """Test successful tarball creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            test_dir = Path(tmpdir)
            file1 = test_dir / "test1.json"
            file2 = test_dir / "test2.json"
            file1.write_text('{"test": "data1"}')
            file2.write_text('{"test": "data2"}')

            file_paths = [file1, file2]
            result = package_files_into_tarball(file_paths, tmpdir)

            # Should return BytesIO object
            assert isinstance(result, io.BytesIO)

            # Verify tarball contents
            result.seek(0)
            with tarfile.open(fileobj=result, mode="r:gz") as tar:
                members = tar.getnames()
                assert len(members) == 2
                assert "test1.json" in members
                assert "test2.json" in members

    def test_package_files_into_tarball_with_subdirectories(self):
        """Test tarball creation with files in subdirectories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files in subdirectories
            test_dir = Path(tmpdir)
            subdir = test_dir / "subdir"
            subdir.mkdir()
            file1 = test_dir / "root.json"
            file2 = subdir / "nested.json"
            file1.write_text('{"test": "root"}')
            file2.write_text('{"test": "nested"}')

            file_paths = [file1, file2]
            result = package_files_into_tarball(file_paths, tmpdir)

            # Verify tarball contents preserve directory structure
            result.seek(0)
            with tarfile.open(fileobj=result, mode="r:gz") as tar:
                members = tar.getnames()
                assert "root.json" in members
                assert "subdir/nested.json" in members

    def test_package_files_into_tarball_skips_symlinks(self):
        """Test that symlinks are skipped during tarball creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir)
            # Create regular file
            regular_file = test_dir / "regular.json"
            regular_file.write_text('{"test": "data"}')

            # Create symlink
            symlink_file = test_dir / "symlink.json"
            symlink_file.symlink_to(regular_file)

            file_paths = [regular_file, symlink_file]
            result = package_files_into_tarball(file_paths, tmpdir)

            # Verify only regular file is included
            result.seek(0)
            with tarfile.open(fileobj=result, mode="r:gz") as tar:
                members = tar.getnames()
                assert "regular.json" in members
                assert "symlink.json" not in members  # Symlink should be skipped


# Note: DeleteData and EnsureDataDirSize tests moved to test_file_handler.py
# since these functions are now part of the FileHandler class as delete_files() and ensure_size_limit()


class TestDataCollectorServiceRun:
    """Test cases for DataCollectorService.run method."""

    @patch("src.file_handler.FileHandler.collect_files")
    @patch("src.file_handler.FileHandler.gather_data_chunks")
    @patch("src.data_exporter.time.sleep")
    def test_run_no_data_found(self, mock_sleep, mock_gather, mock_collect):
        """Test run method when no data is found."""
        mock_collect.return_value = []
        mock_gather.return_value = []

        # Mock sleep to break the loop after first iteration
        mock_sleep.side_effect = KeyboardInterrupt()

        with tempfile.TemporaryDirectory() as tmpdir:
            service = DataCollectorService(
                data_dir=Path(tmpdir),
                service_id="test-service",
                ingress_server_url="https://example.com/api/v1/upload",
                ingress_server_auth_token="test-token",
                identity_id="test-identity",
                collection_interval=60,
                ingress_connection_timeout=30,
                cleanup_after_send=True,
            )

            service.run()

            mock_collect.assert_called()
            mock_gather.assert_called_with([])

    @patch("src.file_handler.FileHandler.collect_files")
    @patch("src.file_handler.FileHandler.gather_data_chunks")
    @patch("src.data_exporter.package_files_into_tarball")
    @patch("src.file_handler.FileHandler.delete_collected_files")
    @patch("src.file_handler.FileHandler.ensure_size_limit")
    @patch("src.data_exporter.time.sleep")
    def test_run_with_data_cleanup_enabled(
        self,
        mock_sleep,
        mock_ensure,
        mock_delete,
        mock_package,
        mock_gather,
        mock_collect,
    ):
        """Test run method with data and cleanup enabled."""
        # Setup mocks
        mock_files = [(Path("/test/file1.json"), 100)]
        mock_collect.return_value = mock_files
        mock_chunks = [[Path("/test/file1.json")]]
        mock_gather.return_value = mock_chunks
        mock_package.return_value = io.BytesIO(b"tarball data")

        # Mock sleep to break the loop after first iteration
        mock_sleep.side_effect = KeyboardInterrupt()

        with tempfile.TemporaryDirectory() as tmpdir:
            service = DataCollectorService(
                data_dir=Path(tmpdir),
                service_id="test-service",
                ingress_server_url="https://example.com/api/v1/upload",
                ingress_server_auth_token="test-token",
                identity_id="test-identity",
                collection_interval=60,
                ingress_connection_timeout=30,
                cleanup_after_send=True,
            )

            with patch.object(service, "upload_tarball"):
                service.run()

            # Verify data processing workflow
            mock_collect.assert_called()
            mock_gather.assert_called_with(mock_files)
            mock_package.assert_called()
            mock_delete.assert_called_with([Path("/test/file1.json")])
            mock_ensure.assert_called_with(mock_files)

    @patch("src.file_handler.FileHandler.collect_files")
    @patch("src.file_handler.FileHandler.gather_data_chunks")
    @patch("src.data_exporter.package_files_into_tarball")
    @patch("src.file_handler.FileHandler.delete_collected_files")
    @patch("src.file_handler.FileHandler.ensure_size_limit")
    @patch("src.data_exporter.time.sleep")
    def test_run_with_data_cleanup_disabled(
        self,
        mock_sleep,
        mock_ensure,
        mock_delete,
        mock_package,
        mock_gather,
        mock_collect,
    ):
        """Test run method with data but cleanup disabled."""
        # Setup mocks
        mock_files = [(Path("/test/file1.json"), 100)]
        mock_collect.return_value = mock_files
        mock_chunks = [[Path("/test/file1.json")]]
        mock_gather.return_value = mock_chunks
        mock_package.return_value = io.BytesIO(b"tarball data")

        # Mock sleep to break the loop after first iteration
        mock_sleep.side_effect = KeyboardInterrupt()

        with tempfile.TemporaryDirectory() as tmpdir:
            service = DataCollectorService(
                data_dir=Path(tmpdir),
                service_id="test-service",
                ingress_server_url="https://example.com/api/v1/upload",
                ingress_server_auth_token="test-token",
                identity_id="test-identity",
                collection_interval=60,
                ingress_connection_timeout=30,
                cleanup_after_send=False,  # Cleanup disabled
            )

            with patch.object(service, "upload_tarball"):
                service.run()

            # Verify cleanup functions are not called
            mock_delete.assert_not_called()
            mock_ensure.assert_not_called()

    @patch("src.file_handler.FileHandler.collect_files")
    @patch("src.data_exporter.logger")
    @patch("src.data_exporter.time.sleep")
    def test_run_handles_os_error(self, mock_sleep, mock_logger, mock_collect):
        """Test run method handles OSError gracefully."""
        # Mock collect_files to raise OSError
        mock_collect.side_effect = [OSError("File system error"), KeyboardInterrupt()]

        with tempfile.TemporaryDirectory() as tmpdir:
            service = DataCollectorService(
                data_dir=Path(tmpdir),
                service_id="test-service",
                ingress_server_url="https://example.com/api/v1/upload",
                ingress_server_auth_token="test-token",
                identity_id="test-identity",
                collection_interval=60,
                ingress_connection_timeout=30,
                cleanup_after_send=True,
            )

            service.run()

            # Should log error and retry
            mock_logger.error.assert_called()
            error_call = mock_logger.error.call_args[0]
            assert "Error during collection process" in error_call[0]

    @patch("src.file_handler.FileHandler.collect_files")
    @patch("src.data_exporter.logger")
    @patch("src.data_exporter.time.sleep")
    def test_run_handles_request_exception(self, mock_sleep, mock_logger, mock_collect):
        """Test run method handles RequestException gracefully."""
        # Mock to raise RequestException first, then KeyboardInterrupt to exit
        mock_collect.side_effect = [
            requests.RequestException("Network error"),
            KeyboardInterrupt(),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            service = DataCollectorService(
                data_dir=Path(tmpdir),
                service_id="test-service",
                ingress_server_url="https://example.com/api/v1/upload",
                ingress_server_auth_token="test-token",
                identity_id="test-identity",
                collection_interval=60,
                ingress_connection_timeout=30,
                cleanup_after_send=True,
            )

            service.run()

            # Should log error about the exception
            mock_logger.error.assert_called()
            error_call = mock_logger.error.call_args[0]
            assert "Error during collection process" in error_call[0]

            # Should sleep with retry interval after exception
            mock_sleep.assert_called()
