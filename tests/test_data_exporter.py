"""Tests for src.data_exporter module."""

import tempfile
import json
import os
from pathlib import Path
import threading
import time
from unittest.mock import patch
import io
import pytest
import requests
import tarfile

from src.data_exporter import (
    DataCollectorService,
    package_files_into_tarball,
)
from src.settings import DataCollectorSettings
from src.otel_ledger import LedgerError, OtelLedger


def create_test_config(**overrides) -> DataCollectorSettings:
    """Create a DataCollectorSettings for testing with default values.

    Args:
        **overrides: Any configuration values to override

    Returns:
        DataCollectorSettings with test defaults
    """
    defaults = {
        "data_dir": Path("/tmp/test"),
        "service_id": "test-service",
        "ingress_server_url": "https://example.com/api/v1/upload",
        "ingress_server_auth_token": "test-token",
        "identity_id": "test-identity",
        "collection_interval": 60,
        "ingress_connection_timeout": 30,
        "cleanup_after_send": True,
        "allowed_subdirs": [],
        "retry_interval": 10,
    }
    defaults.update(overrides)
    return DataCollectorSettings(**defaults)


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


def stop_service(service: DataCollectorService):
    # Small delay to allow service to process at least one iteration
    time.sleep(0.1)
    service.shutdown()


class TestDataCollectorServiceRun:
    """Test cases for DataCollectorService.run method."""

    @patch("src.file_handler.FileHandler.collect_files")
    @patch("src.file_handler.FileHandler.gather_data_chunks")
    def test_run_no_data_found(self, mock_gather, mock_collect):
        """Test run method when no data is found."""
        mock_collect.return_value = []
        mock_gather.return_value = []

        with tempfile.TemporaryDirectory() as tmpdir:
            config = create_test_config(data_dir=Path(tmpdir))
            service = DataCollectorService(config)

            threading.Thread(target=stop_service, args=[service]).start()
            service.run()

            mock_collect.assert_called()
            mock_gather.assert_called_with([])

    @patch("src.file_handler.FileHandler.collect_files")
    @patch("src.file_handler.FileHandler.gather_data_chunks")
    def test_run_single_shot_mode(self, mock_gather, mock_collect):
        """Test run method when no data is found."""
        mock_collect.return_value = []
        mock_gather.return_value = []

        with tempfile.TemporaryDirectory() as tmpdir:
            config = create_test_config(data_dir=Path(tmpdir), collection_interval=0)
            service = DataCollectorService(config)

            service.run()

            mock_collect.assert_called()
            mock_gather.assert_called_with([])

    @patch("src.file_handler.FileHandler.collect_files")
    @patch("src.file_handler.FileHandler.gather_data_chunks")
    @patch("src.data_exporter.package_files_into_tarball")
    @patch("src.file_handler.FileHandler.delete_collected_files")
    @patch("src.file_handler.FileHandler.ensure_size_limit")
    def test_run_with_data_cleanup_enabled(
        self,
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

        with tempfile.TemporaryDirectory() as tmpdir:
            config = create_test_config(data_dir=Path(tmpdir))
            service = DataCollectorService(config)

            with patch.object(service.ingress_client, "upload_tarball"):
                threading.Thread(target=stop_service, args=[service]).start()
                service.run()

            # Verify data processing workflow
            mock_collect.assert_called()
            mock_gather.assert_called_with(mock_files)
            mock_package.assert_called()
            mock_delete.assert_called_with([Path("/test/file1.json")])
            mock_ensure.assert_called_with()

    @patch("src.file_handler.FileHandler.collect_files")
    @patch("src.file_handler.FileHandler.gather_data_chunks")
    @patch("src.data_exporter.package_files_into_tarball")
    @patch("src.file_handler.FileHandler.delete_collected_files")
    @patch("src.file_handler.FileHandler.ensure_size_limit")
    def test_run_with_data_cleanup_disabled(
        self,
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

        with tempfile.TemporaryDirectory() as tmpdir:
            config = create_test_config(data_dir=Path(tmpdir), cleanup_after_send=False)
            service = DataCollectorService(config)

            with patch.object(service.ingress_client, "upload_tarball"):
                threading.Thread(target=stop_service, args=[service]).start()
                service.run()

            # Verify cleanup functions are not called
            mock_delete.assert_not_called()
            mock_ensure.assert_not_called()

    @patch("src.file_handler.FileHandler.collect_files")
    @patch("src.data_exporter.logger")
    def test_run_handles_os_error(self, mock_logger, mock_collect):
        """Test run method handles OSError gracefully."""
        # Mock collect_files to raise OSError
        mock_collect.side_effect = [OSError("File system error"), KeyboardInterrupt()]

        with tempfile.TemporaryDirectory() as tmpdir:
            config = create_test_config(data_dir=Path(tmpdir))
            service = DataCollectorService(config)

            threading.Thread(target=stop_service, args=[service]).start()
            service.run()

            # Should log error and retry
            mock_logger.error.assert_called()
            error_call = mock_logger.error.call_args[0]
            assert "Error during data collection" in error_call[0]

    @patch("src.file_handler.FileHandler.collect_files")
    @patch("src.data_exporter.logger")
    def test_run_handles_request_exception(self, mock_logger, mock_collect):
        """Test run method handles RequestException gracefully."""
        # Mock to raise RequestException first, then KeyboardInterrupt to exit
        mock_collect.side_effect = [
            requests.RequestException("Network error"),
            KeyboardInterrupt(),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            config = create_test_config(data_dir=Path(tmpdir))
            service = DataCollectorService(config)

            threading.Thread(target=stop_service, args=[service]).start()
            service.run()

            # Should log error about the exception
            mock_logger.error.assert_called()
            error_call = mock_logger.error.call_args[0]
            assert "Error during data collection" in error_call[0]

    @patch("src.file_handler.FileHandler.collect_files")
    def test_run_handles_request_exception_in_single_shot_mode(self, mock_collect):
        """Test run method handles RequestException gracefully."""
        # Mock to raise RequestException first, then KeyboardInterrupt to exit
        mock_collect.side_effect = [
            requests.RequestException("Network error"),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            config = create_test_config(data_dir=Path(tmpdir), collection_interval=0)
            service = DataCollectorService(config)

            try:
                service.run()
            except requests.RequestException:
                pass
            else:
                assert (
                    False
                ), "service should have reraised exception when in single shot mode"

    @patch("src.file_handler.FileHandler.collect_files")
    @patch("src.data_exporter.logger")
    def test_retry_uses_correct_interval(self, mock_logger, mock_collect):
        """Test that retry logic uses configurable retry_interval."""
        # Mock collect_files to raise an exception on first call, then KeyboardInterrupt
        call_count = 0

        def mock_collect_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise requests.RequestException("Network error")
            else:
                raise KeyboardInterrupt()  # Exit the loop on subsequent calls

        mock_collect.side_effect = mock_collect_side_effect

        with tempfile.TemporaryDirectory() as tmpdir:
            # Test with a custom retry interval to ensure config is used
            custom_retry_interval = 120
            config = create_test_config(
                data_dir=Path(tmpdir), retry_interval=custom_retry_interval
            )
            service = DataCollectorService(config)

            # Mock the shutdown_event.wait method to capture the retry interval
            with patch.object(service.shutdown_event, "wait") as mock_wait:
                # First call returns False (not set), second call can return True or raise KeyboardInterrupt
                mock_wait.side_effect = [False, KeyboardInterrupt()]

                service.run()

                # Verify that wait was called with the correct retry interval
                mock_wait.assert_called_with(custom_retry_interval)

                # Verify the log message includes the correct interval
                mock_logger.info.assert_any_call(
                    "Retrying data collection in %d seconds...", custom_retry_interval
                )

    @patch("src.file_handler.FileHandler.collect_files")
    @patch("src.file_handler.FileHandler.gather_data_chunks")
    @patch("src.data_exporter.package_files_into_tarball")
    @patch("src.file_handler.FileHandler.delete_collected_files")
    @patch("src.file_handler.FileHandler.ensure_size_limit")
    def test_ensure_size_limit_called_on_upload_failure(
        self,
        mock_ensure,
        mock_delete,
        mock_package,
        mock_gather,
        mock_collect,
    ):
        """Test ensure_size_limit is called when ingress returns non-202 status."""
        mock_files = [(Path("/test/file1.json"), 100)]
        mock_collect.return_value = mock_files
        mock_gather.return_value = [[Path("/test/file1.json")]]
        mock_package.return_value = io.BytesIO(b"tarball data")

        mock_response = requests.Response()
        mock_response.status_code = 500
        mock_response._content = b'{"error": "internal server error"}'

        with tempfile.TemporaryDirectory() as tmpdir:
            config = create_test_config(data_dir=Path(tmpdir), collection_interval=0)
            service = DataCollectorService(config)

            with patch.object(
                service.ingress_client,
                "_upload_data_to_ingress",
                return_value=mock_response,
            ):
                with pytest.raises(requests.RequestException):
                    service.run()

        mock_ensure.assert_called_once_with()
        mock_delete.assert_not_called()


@pytest.fixture
def otel_service(tmp_path):
    source = tmp_path / "input"
    state = tmp_path / "state"
    source.mkdir()
    state.mkdir()
    return DataCollectorService(
        create_test_config(
            data_dir=source,
            data_mode="otel",
            ledger_file=state / "ledger.json",
            archive_path_prefix="v1/",
            collection_interval=0,
        )
    )


def write_backup(service, number, content=b'{"a":1}\n'):
    path = service.data_dir / f"traces-2026-10-03T03-04-{number:02d}.001-size.jsonl"
    path.write_bytes(content)
    return path


def capture_uploads(service, monkeypatch):
    uploads = []

    def upload(tarball):
        with tarfile.open(fileobj=tarball, mode="r:gz") as archive:
            names = archive.getnames()
            uploads.append((names, archive.extractfile(names[0]).read()))
        return f"request-{len(uploads)}"

    monkeypatch.setattr(service.ingress_client, "upload_tarball", upload)
    return uploads


def test_otel_restart_uses_filename_identity_and_prefix(otel_service, monkeypatch):
    service = otel_service
    source = write_backup(service, 1)
    uploads = capture_uploads(service, monkeypatch)
    service._process_data_collection()
    expected_upload = [(["v1/" + source.with_suffix(".json").name], b'[{"a":1}]')]
    assert uploads == expected_upload

    original_open = os.open

    def fail_if_acknowledged_source_is_opened(path, flags, *args, **kwargs):
        if Path(path) == source:
            pytest.fail("Acknowledged source was opened on rescan")
        return original_open(path, flags, *args, **kwargs)

    def fail_conversion(*args, **kwargs):
        pytest.fail("Acknowledged source was converted on rescan")

    with monkeypatch.context() as scoped:
        scoped.setattr(
            "src.data_exporter.os.open", fail_if_acknowledged_source_is_opened
        )
        scoped.setattr("src.data_exporter.package_jsonl_file", fail_conversion)
        service._process_data_collection()
        assert uploads == expected_upload

        restarted = DataCollectorService(service.config)
        restarted_uploads = capture_uploads(restarted, monkeypatch)
        restarted._process_data_collection()
        assert restarted_uploads == []

    configured = service.config.model_copy(update={"archive_path_prefix": "v2/"})
    changed_prefix = DataCollectorService(configured)
    uploads = capture_uploads(changed_prefix, monkeypatch)
    added = write_backup(changed_prefix, 2)
    changed_prefix._process_data_collection()
    assert uploads == [(["v2/" + added.with_suffix(".json").name], b'[{"a":1}]')]


def test_otel_malformed_source_does_not_block_or_delete(otel_service, monkeypatch):
    service = otel_service
    malformed = write_backup(service, 1, b'{"partial":1}\n{bad json')
    valid = write_backup(service, 2)
    active = service.data_dir / "traces.jsonl"
    active.write_bytes(b'{"live":1}')
    before = {path.name: path.read_bytes() for path in service.data_dir.iterdir()}
    uploads = capture_uploads(service, monkeypatch)
    monkeypatch.setattr(
        service.file_handler,
        "collect_files",
        lambda: pytest.fail("Classic scanner invoked"),
    )
    service._process_data_collection()
    assert uploads == [(["v1/" + valid.with_suffix(".json").name], b'[{"a":1}]')]
    assert {
        path.name: path.read_bytes() for path in service.data_dir.iterdir()
    } == before
    ledger = json.loads(service.config.ledger_file.read_text())
    assert set(ledger["files"]) == {valid.name}
    assert malformed.exists()
    assert set(service.config.ledger_file.parent.iterdir()) == {
        service.config.ledger_file
    }


def test_otel_upload_retry_preserves_earlier_acknowledgments(otel_service, monkeypatch):
    service = otel_service
    first = write_backup(service, 1)
    second = write_backup(service, 2)
    attempts = []

    def upload(tarball):
        with tarfile.open(fileobj=tarball, mode="r:gz") as archive:
            attempts.append(archive.getnames()[0])
        if len(attempts) == 2:
            raise requests.ConnectionError("unavailable")
        return "accepted"

    monkeypatch.setattr(service.ingress_client, "upload_tarball", upload)
    with pytest.raises(requests.ConnectionError):
        service.run()
    assert set(json.loads(service.config.ledger_file.read_text())["files"]) == {
        first.name
    }
    service.run()
    assert attempts == [
        "v1/" + first.with_suffix(".json").name,
        "v1/" + second.with_suffix(".json").name,
        "v1/" + second.with_suffix(".json").name,
    ]


def test_otel_incomplete_inventory_does_not_prune_or_upload(otel_service, monkeypatch):
    service = otel_service
    source = write_backup(service, 1)
    uploads = capture_uploads(service, monkeypatch)
    service._process_data_collection()
    original = service.config.ledger_file.read_bytes()
    source.unlink()
    write_backup(service, 2)
    from contextlib import contextmanager

    real_scandir = os.scandir

    @contextmanager
    def incomplete(path):
        with real_scandir(path) as entries:

            def partial():
                yield from entries
                raise OSError("partial inventory")

            yield partial()

    with monkeypatch.context() as scoped:
        scoped.setattr("src.otel_file_handler.os.scandir", incomplete)
        with pytest.raises(OSError, match="partial inventory"):
            service._process_data_collection()
    assert service.config.ledger_file.read_bytes() == original
    assert len(uploads) == 1
    for path in service.data_dir.iterdir():
        path.unlink()
    service._process_data_collection()
    assert json.loads(service.config.ledger_file.read_text())["files"] == {}
    assert len(uploads) == 1


def test_otel_ledger_save_failure_is_fatal_in_continuous_mode(
    otel_service, monkeypatch
):
    service = otel_service
    service.collection_interval = 60
    write_backup(service, 1)
    write_backup(service, 2)
    uploads = capture_uploads(service, monkeypatch)
    original = service.config.ledger_file.read_bytes()

    def fail_replace(*args, **kwargs):
        raise OSError("state disk failure")

    monkeypatch.setattr("src.otel_ledger.os.replace", fail_replace)
    monkeypatch.setattr(
        service.shutdown_event,
        "wait",
        lambda timeout: pytest.fail("Fatal ledger error retried"),
    )
    with pytest.raises(LedgerError):
        service.run()
    assert len(uploads) == 1
    assert service.config.ledger_file.read_bytes() == original
    accepted_name = uploads[0][0][0].removeprefix("v1/").replace(".json", ".jsonl")
    assert not OtelLedger(service.config.ledger_file).is_uploaded(accepted_name)


def test_otel_source_change_and_disappearance_skip_without_ack(
    otel_service, monkeypatch
):
    from src.otel_file_handler import package_jsonl_file

    service = otel_service
    changing = write_backup(service, 1)
    missing = write_backup(service, 2)
    valid = write_backup(service, 3)
    uploads = capture_uploads(service, monkeypatch)
    real_package = package_jsonl_file

    def mutate_during_conversion(stream, member):
        tarball = real_package(stream, member)
        if os.fstat(stream.fileno()).st_ino == changing.stat().st_ino:
            changing.write_bytes(b'{"changed":true}\n')
            missing.unlink()
        return tarball

    monkeypatch.setattr(
        "src.data_exporter.package_jsonl_file", mutate_during_conversion
    )
    service._process_data_collection()
    assert uploads == [(["v1/" + valid.with_suffix(".json").name], b'[{"a":1}]')]
    assert set(json.loads(service.config.ledger_file.read_text())["files"]) == {
        valid.name
    }


def test_otel_unlinked_open_source_remains_readable(otel_service, monkeypatch):
    from src.otel_file_handler import package_jsonl_file

    service = otel_service
    source = write_backup(service, 1)
    uploads = capture_uploads(service, monkeypatch)
    real_package = package_jsonl_file

    def unlink_before_conversion(stream, member):
        source.unlink()
        return real_package(stream, member)

    monkeypatch.setattr(
        "src.data_exporter.package_jsonl_file", unlink_before_conversion
    )
    service._process_data_collection()
    assert uploads == [(["v1/" + source.with_suffix(".json").name], b'[{"a":1}]')]
    assert source.name in json.loads(service.config.ledger_file.read_text())["files"]
    service._process_data_collection()
    assert json.loads(service.config.ledger_file.read_text())["files"] == {}


def test_otel_oversized_source_is_not_uploaded_or_acknowledged(
    otel_service, monkeypatch
):
    from src.otel_file_handler import package_jsonl_file

    service = otel_service
    oversized = write_backup(service, 1, b'{"long":"' + b"x" * 2000 + b'"}')
    valid = write_backup(service, 2)
    uploads = capture_uploads(service, monkeypatch)
    before = oversized.read_bytes()

    def bounded_package(stream, member):
        return package_jsonl_file(stream, member, max_payload_size=1024)

    monkeypatch.setattr("src.data_exporter.package_jsonl_file", bounded_package)
    service._process_data_collection()
    assert oversized.read_bytes() == before
    assert uploads == [(["v1/" + valid.with_suffix(".json").name], b'[{"a":1}]')]
    assert set(json.loads(service.config.ledger_file.read_text())["files"]) == {
        valid.name
    }


def test_otel_change_during_conversion_closes_archive(otel_service, monkeypatch):
    from src.otel_file_handler import package_jsonl_file

    service = otel_service
    source = write_backup(service, 1)
    uploads = capture_uploads(service, monkeypatch)
    packaged = []

    def changing_package(stream, member):
        tarball = package_jsonl_file(stream, member)
        packaged.append(tarball)
        source.write_bytes(b'{"changed":true}')
        return tarball

    monkeypatch.setattr("src.data_exporter.package_jsonl_file", changing_package)
    service._process_data_collection()
    assert uploads == []
    assert packaged[0].closed
    assert json.loads(service.config.ledger_file.read_text())["files"] == {}


def test_otel_failed_upload_closes_archive(otel_service, monkeypatch):
    service = otel_service
    write_backup(service, 1)
    buffers = []

    def fail(tarball):
        buffers.append(tarball)
        raise requests.ConnectionError("unavailable")

    monkeypatch.setattr(service.ingress_client, "upload_tarball", fail)
    with pytest.raises(requests.ConnectionError):
        service.run()
    assert buffers[0].closed
    assert json.loads(service.config.ledger_file.read_text())["files"] == {}


def test_otel_invalid_utf8_isolated_from_valid_source(otel_service, monkeypatch):
    service = otel_service
    invalid = write_backup(service, 1, b'{"value":"\xff"}\n')
    valid = write_backup(service, 2)
    uploads = capture_uploads(service, monkeypatch)
    service._process_data_collection()
    assert uploads == [(["v1/" + valid.with_suffix(".json").name], b'[{"a":1}]')]
    assert invalid.read_bytes() == b'{"value":"\xff"}\n'
    assert set(json.loads(service.config.ledger_file.read_text())["files"]) == {
        valid.name
    }
