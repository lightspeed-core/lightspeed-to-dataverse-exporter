"""Collect insights and upload it to the Ingress service.

It waits `INITIAL_WAIT` min after startup before collects the data. Then
it collects data after specified interval.

When `cp_offline_token` is provided via config (either for prod or stage),
it is used for ingress authentication instead of cluster pull-secret.
"""

import io
import pathlib
import tarfile
from pathlib import Path
import logging
import threading
import time
import requests

from src.file_handler import FileHandler
from src.ingress_client import IngressClient

from src.settings import DataCollectorSettings

logger = logging.getLogger(__name__)


def package_files_into_tarball(
    file_paths: list[pathlib.Path], path_to_strip: str
) -> io.BytesIO:
    """Package specified directory into a tarball.

    Args:
        file_paths: List of paths to the files to be packaged.
        path_to_strip: Path to be stripped from the file paths (not
            included in the archive).

    Returns:
        BytesIO object representing the tarball.
    """
    tarball_io = io.BytesIO()
    with tarfile.open(fileobj=tarball_io, mode="w:gz") as tar:
        # arcname parameter is set to a stripped path to avoid including
        # the full path of the root dir
        for file_path in file_paths:
            # skip symlinks as those are a potential security risk
            if not file_path.is_symlink():
                tar.add(
                    file_path, arcname=file_path.as_posix().replace(path_to_strip, "")
                )

    tarball_io.seek(0)

    return tarball_io


class DataCollectorService:
    """Service for collecting and sending user data to ingress server.

    This service handles the periodic collection and transmission of user data
    including feedback and transcripts to the configured ingress server.
    """

    shutdown_event: threading.Event

    def __init__(self, config: DataCollectorSettings) -> None:
        """Initialize the data collector service.

        Args:
            config: Configuration settings containing all service parameters
        """
        self.config = config

        # Store frequently accessed config values as instance attributes for convenience
        self.data_dir = config.data_dir
        self.collection_interval = config.collection_interval
        self.cleanup_after_send = config.cleanup_after_send
        self.retry_interval = config.retry_interval

        # Initialize file handler for this service
        self.file_handler = FileHandler(
            config.data_dir, allowed_subdirs=config.allowed_subdirs
        )

        # Initialize ingress client for uploads
        self.ingress_client = IngressClient(
            ingress_server_url=config.ingress_server_url,
            ingress_server_auth_token=config.ingress_server_auth_token,
            service_id=config.service_id,
            identity_id=config.identity_id,
            connection_timeout=config.ingress_connection_timeout,
        )

        self.shutdown_event = threading.Event()

    def _process_data_collection(self) -> None:
        """Process a single data collection cycle."""
        collected_files = self.file_handler.collect_files()
        data_chunks = self.file_handler.gather_data_chunks(collected_files)

        if data_chunks:
            self._handle_upload_batch(data_chunks, collected_files)
        else:
            logger.info("No data marked for collection in '%s'", self.data_dir)

    def _handle_upload_batch(
        self, data_chunks: list[list[Path]], collected_files: list[tuple[Path, int]]
    ) -> None:
        """Handle uploading a batch of data chunks.

        Args:
            data_chunks: List of data chunks to upload
            collected_files: Original collected files for cleanup
        """
        for i, data_chunk in enumerate(data_chunks):
            logger.info("Uploading data chunk %d/%d", i + 1, len(data_chunks))
            self._upload_single_chunk(data_chunk)

        # Perform final cleanup after all chunks are uploaded
        if self.cleanup_after_send:
            self.file_handler.ensure_size_limit(collected_files)

    def _upload_single_chunk(self, data_chunk: list[Path]) -> None:
        """Upload a single data chunk.

        Args:
            data_chunk: List of file paths to upload in this chunk
        """
        tarball = package_files_into_tarball(
            data_chunk, path_to_strip=self.data_dir.as_posix()
        )
        logger.debug("Successfully packed data chunk into tarball")
        self.ingress_client.upload_tarball(tarball)

        # Clean up chunk files after successful upload
        if self.cleanup_after_send:
            self.file_handler.delete_collected_files(data_chunk)

    def run(self) -> None:
        """Run the periodic data collection loop."""
        logger.info("Starting data collection service")

        in_single_shot_mode = not self.collection_interval
        if in_single_shot_mode:
            logger.info(
                "Collection interval is not set, operating in single-shot mode - service will exit after one data collection cycle"
            )

        while not self.shutdown_event.is_set():
            try:
                next_collection = time.time() + self.collection_interval

                self._process_data_collection()

                if in_single_shot_mode:
                    return

                logger.info(
                    "Waiting %d seconds before next collection",
                    self.collection_interval,
                )

                time_to_wait = next_collection - time.time()
                if time_to_wait > 0:
                    _ = self.shutdown_event.wait(time_to_wait)
            except KeyboardInterrupt:
                logger.info("Data collection service stopped by user")
                break
            except (OSError, requests.RequestException) as e:
                logger.error("Error during collection process: %s", e, exc_info=True)

                if in_single_shot_mode:
                    # Let the exception cause the service to quit with a non-zero exit code. This
                    # will indicate to the external job runner that the run failed and it can choose
                    # whatever retry policy it wants.
                    raise e

                if not self.shutdown_event.is_set():
                    logger.info("Retrying in %d seconds...", self.retry_interval)
                    _ = self.shutdown_event.wait(self.retry_interval)

        logger.info("Doing one final collection before shutdown")
        # Exceptions (other than KeyboardInterrupt) here should bubble up because they indicate
        # there is data that potentially will not be sent before the process terminates.
        try:
            self._process_data_collection()
        except KeyboardInterrupt:
            pass

    def shutdown(self) -> None:
        self.shutdown_event.set()
