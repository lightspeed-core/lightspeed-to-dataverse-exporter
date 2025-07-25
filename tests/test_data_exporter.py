"""Tests for src.data_exporter module."""

import tempfile
from pathlib import Path
from unittest.mock import patch, Mock
import io
import pytest
import requests
import tarfile
import time

from src.data_exporter import (
    filter_allowed_files, 
    collect_files, 
    DataCollectorService,
    gather_data_chunks,
    package_files_into_tarball,
    delete_data,
    ensure_data_dir_is_not_bigger_than_defined,
)
from src.constants import ALLOWED_SUBDIRS


class TestFilterAllowedFiles:
    """Test cases for filter_allowed_files function."""

    def test_filter_allowed_files_in_feedback(self):
        """Test filtering files in allowed feedback subdirectory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            feedback_dir = data_dir / "feedback"
            feedback_dir.mkdir()

            # Create test files
            feedback_file = feedback_dir / "test.json"
            feedback_file.touch()

            files = [feedback_file]
            filtered = filter_allowed_files(data_dir, files, ALLOWED_SUBDIRS)

            assert len(filtered) == 1
            assert feedback_file in filtered

    def test_filter_allowed_files_in_transcripts(self):
        """Test filtering files in allowed transcripts subdirectory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            transcripts_dir = data_dir / "transcripts"
            transcripts_dir.mkdir()

            # Create test files
            transcript_file = transcripts_dir / "conversation.json"
            transcript_file.touch()

            files = [transcript_file]
            filtered = filter_allowed_files(data_dir, files, ALLOWED_SUBDIRS)

            assert len(filtered) == 1
            assert transcript_file in filtered

    def test_filter_disallowed_files(self):
        """Test filtering out files in disallowed directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)

            # Create disallowed directory and file
            bad_dir = data_dir / "not_allowed"
            bad_dir.mkdir()
            bad_file = bad_dir / "bad.json"
            bad_file.touch()

            files = [bad_file]
            filtered = filter_allowed_files(data_dir, files, ALLOWED_SUBDIRS)

            assert len(filtered) == 0

    def test_filter_mixed_files(self):
        """Test filtering mixed allowed and disallowed files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)

            # Create allowed directories and files
            feedback_dir = data_dir / "feedback"
            feedback_dir.mkdir()
            good_file1 = feedback_dir / "good1.json"
            good_file1.touch()

            transcripts_dir = data_dir / "transcripts"
            transcripts_dir.mkdir()
            good_file2 = transcripts_dir / "good2.json"
            good_file2.touch()

            # Create disallowed directory and file
            bad_dir = data_dir / "logs"
            bad_dir.mkdir()
            bad_file = bad_dir / "bad.json"
            bad_file.touch()

            files = [good_file1, good_file2, bad_file]
            filtered = filter_allowed_files(data_dir, files, ALLOWED_SUBDIRS)

            assert len(filtered) == 2
            assert good_file1 in filtered
            assert good_file2 in filtered
            assert bad_file not in filtered

    def test_filter_files_in_root_directory(self):
        """Test filtering files directly in root data directory (should be excluded)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            root_file = data_dir / "root.json"
            root_file.touch()

            files = [root_file]
            filtered = filter_allowed_files(data_dir, files, ALLOWED_SUBDIRS)

            assert len(filtered) == 0


class TestCollectFiles:
    """Test cases for collect_files function."""

    def test_collect_json_files_only(self):
        """Test that only JSON files are collected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            feedback_dir = data_dir / "feedback"
            feedback_dir.mkdir()

            # Create JSON file
            json_file = feedback_dir / "data.json"
            json_file.write_text('{"test": "data"}')

            # Create non-JSON file
            txt_file = feedback_dir / "data.txt"
            txt_file.write_text("text data")

            files_with_sizes = collect_files(data_dir)

            assert len(files_with_sizes) == 1
            file_path, file_size = files_with_sizes[0]
            assert file_path == json_file
            assert file_size > 0

    def test_collect_files_with_sizes(self):
        """Test that file sizes are correctly calculated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            feedback_dir = data_dir / "feedback"
            feedback_dir.mkdir()

            # Create JSON file with known content
            test_content = '{"test": "data", "more": "content"}'
            json_file = feedback_dir / "test.json"
            json_file.write_text(test_content)

            files_with_sizes = collect_files(data_dir)

            assert len(files_with_sizes) == 1
            file_path, file_size = files_with_sizes[0]
            assert file_path == json_file
            assert file_size == len(test_content.encode())

    def test_collect_files_nonexistent_directory(self):
        """Test collect_files with non-existent data directory."""
        nonexistent_dir = Path("/non/existent/directory")

        files_with_sizes = collect_files(nonexistent_dir)

        assert files_with_sizes == []

    def test_collect_files_empty_directory(self):
        """Test collect_files with empty data directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)

            files_with_sizes = collect_files(data_dir)

            assert files_with_sizes == []

    def test_collect_files_nested_subdirectories(self):
        """Test that files in nested subdirectories are found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            feedback_dir = data_dir / "feedback"
            nested_dir = feedback_dir / "nested"
            nested_dir.mkdir(parents=True)

            # Create JSON file in nested directory
            json_file = nested_dir / "nested.json"
            json_file.write_text('{"nested": "data"}')

            files_with_sizes = collect_files(data_dir)

            assert len(files_with_sizes) == 1
            file_path, file_size = files_with_sizes[0]
            assert file_path == json_file


class TestDataCollectorService:
    """Test cases for DataCollectorService."""

    @patch("src.data_exporter.collect_files")
    def test_collect_and_process_no_files(self, mock_collect_files):
        """Test that service initializes correctly with all required parameters."""
        mock_collect_files.return_value = []

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


class TestGatherDataChunks:
    """Test cases for gather_data_chunks function."""

    def test_gather_data_chunks_empty_list(self):
        """Test gather_data_chunks with empty file list."""
        result = gather_data_chunks([])
        assert result == []

    def test_gather_data_chunks_single_small_file(self):
        """Test gather_data_chunks with single small file."""
        files = [(Path("/test/file1.json"), 100)]
        result = gather_data_chunks(files)
        
        assert len(result) == 1
        assert len(result[0]) == 1
        assert result[0][0] == Path("/test/file1.json")

    def test_gather_data_chunks_multiple_small_files(self):
        """Test gather_data_chunks with multiple small files that fit in one chunk."""
        files = [
            (Path("/test/file1.json"), 100),
            (Path("/test/file2.json"), 200),
            (Path("/test/file3.json"), 150),
        ]
        result = gather_data_chunks(files)
        
        assert len(result) == 1  # All files fit in one chunk
        assert len(result[0]) == 3
        assert result[0][0] == Path("/test/file1.json")
        assert result[0][1] == Path("/test/file2.json")  
        assert result[0][2] == Path("/test/file3.json")

    def test_gather_data_chunks_large_files_split(self):
        """Test gather_data_chunks with large files that need splitting."""
        # Create files that exceed the chunk size limit (100MB default)
        files = [
            (Path("/test/large1.json"), 80 * 1024 * 1024),  # 80MB
            (Path("/test/large2.json"), 80 * 1024 * 1024),  # 80MB  
            (Path("/test/small.json"), 1024),                # 1KB
        ]
        result = gather_data_chunks(files)
        
        # Should be split into multiple chunks due to size (160MB > 100MB limit)
        assert len(result) >= 2
        # First chunk should have first large file
        assert Path("/test/large1.json") in result[0]

    def test_gather_data_chunks_file_exceeds_max_size(self):
        """Test gather_data_chunks with file that exceeds maximum chunk size."""
        # File larger than max chunk size (100MB)
        files = [(Path("/test/huge.json"), 150 * 1024 * 1024)]  # 150MB
        result = gather_data_chunks(files)
        
        # Should still create a chunk even if file exceeds max size
        assert len(result) == 1
        assert len(result[0]) == 1
        assert result[0][0] == Path("/test/huge.json")


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


class TestDeleteData:
    """Test cases for delete_data function."""

    def test_delete_data_success(self):
        """Test successful file deletion."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir)
            file1 = test_dir / "delete1.json"
            file2 = test_dir / "delete2.json"
            file1.write_text('{"test": "data1"}')
            file2.write_text('{"test": "data2"}')
            
            # Verify files exist
            assert file1.exists()
            assert file2.exists()
            
            delete_data([file1, file2])
            
            # Verify files are deleted
            assert not file1.exists()
            assert not file2.exists()

    @patch("src.data_exporter.logger")
    def test_delete_data_file_removal_fails(self, mock_logger):
        """Test delete_data handles file removal failures."""
        # Create a mock file path that simulates unlink failure
        mock_file = Mock(spec=Path)
        mock_file.unlink.return_value = None  # unlink "succeeds" but file still exists
        mock_file.exists.return_value = True  # File still exists after unlink
        mock_file.__str__ = Mock(return_value="/test/stubborn_file.json")
        
        delete_data([mock_file])
        
        # Should log error when file still exists after unlink
        mock_logger.error.assert_called_with("failed to remove '%s'", mock_file)


class TestEnsureDataDirSize:
    """Test cases for ensure_data_dir_is_not_bigger_than_defined function."""

    @patch("src.data_exporter.delete_data")
    @patch("src.data_exporter.logger")
    def test_ensure_data_dir_within_limit(self, mock_logger, mock_delete):
        """Test when data directory is within size limit."""
        files = [
            (Path("/test/file1.json"), 1000),
            (Path("/test/file2.json"), 2000),
        ]
        
        ensure_data_dir_is_not_bigger_than_defined(files)
        
        # Should not delete any files or log errors
        mock_delete.assert_not_called()
        mock_logger.error.assert_not_called()

    @patch("src.data_exporter.delete_data")
    @patch("src.data_exporter.logger")
    def test_ensure_data_dir_exceeds_limit(self, mock_logger, mock_delete):
        """Test when data directory exceeds size limit."""
        # Create files that exceed the maximum size limit
        large_size = 60 * 1024 * 1024  # 60MB (exceeds 50MB limit)
        files = [
            (Path("/test/large1.json"), large_size),
            (Path("/test/large2.json"), large_size),
        ]
        
        ensure_data_dir_is_not_bigger_than_defined(files)
        
        # Should log error about size limit
        mock_logger.error.assert_called()
        error_call = mock_logger.error.call_args[0]
        assert "Data folder size is bigger than the maximum allowed size" in error_call[0]
        
        # Should log info about removing files
        mock_logger.info.assert_called_with("Removing files to fit the data into the limit...")
        
        # Should delete files to bring size within limit
        mock_delete.assert_called()


class TestDataCollectorServiceRun:
    """Test cases for DataCollectorService.run method."""

    @patch("src.data_exporter.collect_files")
    @patch("src.data_exporter.gather_data_chunks")
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
            
            mock_collect.assert_called_with(Path(tmpdir))
            mock_gather.assert_called_with([])

    @patch("src.data_exporter.collect_files")
    @patch("src.data_exporter.gather_data_chunks")
    @patch("src.data_exporter.package_files_into_tarball")
    @patch("src.data_exporter.delete_data")
    @patch("src.data_exporter.ensure_data_dir_is_not_bigger_than_defined")
    @patch("src.data_exporter.time.sleep")
    def test_run_with_data_cleanup_enabled(self, mock_sleep, mock_ensure, mock_delete, 
                                          mock_package, mock_gather, mock_collect):
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
            
            with patch.object(service, 'upload_tarball'):
                service.run()
            
            # Verify data processing workflow
            mock_collect.assert_called()
            mock_gather.assert_called_with(mock_files)
            mock_package.assert_called()
            mock_delete.assert_called_with([Path("/test/file1.json")])
            mock_ensure.assert_called_with(mock_files)

    @patch("src.data_exporter.collect_files")
    @patch("src.data_exporter.gather_data_chunks")
    @patch("src.data_exporter.package_files_into_tarball")
    @patch("src.data_exporter.delete_data")
    @patch("src.data_exporter.ensure_data_dir_is_not_bigger_than_defined")
    @patch("src.data_exporter.time.sleep")
    def test_run_with_data_cleanup_disabled(self, mock_sleep, mock_ensure, mock_delete,
                                           mock_package, mock_gather, mock_collect):
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
            
            with patch.object(service, 'upload_tarball'):
                service.run()
            
            # Verify cleanup functions are not called
            mock_delete.assert_not_called()
            mock_ensure.assert_not_called()

    @patch("src.data_exporter.collect_files")
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

    @patch("src.data_exporter.collect_files")
    @patch("src.data_exporter.logger")
    @patch("src.data_exporter.time.sleep")
    def test_run_handles_request_exception(self, mock_sleep, mock_logger, mock_collect):
        """Test run method handles RequestException gracefully."""
        # Mock to raise RequestException first, then KeyboardInterrupt to exit
        mock_collect.side_effect = [requests.RequestException("Network error"), KeyboardInterrupt()]
        
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
