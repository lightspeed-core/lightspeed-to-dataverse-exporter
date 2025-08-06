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
import requests

from src.constants import DATA_COLLECTOR_RETRY_INTERVAL
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

        # Shutdown event for graceful termination
        self._shutdown_event = threading.Event()

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

    def request_shutdown(self) -> None:
        """Request graceful shutdown of the service."""
        logger.info("Shutdown requested, will perform final collection and exit")
        self._shutdown_event.set()  # Wake up any waiting threads immediately

    def _wait_or_shutdown(self, timeout: int, wait_type: str = "collection") -> bool:
        """Wait for timeout or shutdown signal, whichever comes first.

        Args:
            timeout: Number of seconds to wait
            wait_type: Type of wait for logging ("collection" or "retry")

        Returns:
            True if shutdown was requested, False if timeout elapsed normally
        """
        if self._shutdown_event.wait(timeout=timeout):
            # Event was set (shutdown requested)
            logger.debug(
                "%s sleep interrupted by shutdown request", wait_type.capitalize()
            )
            return True
        else:
            # Timeout elapsed normally (no shutdown requested)
            logger.debug("%s sleep interval completed normally", wait_type.capitalize())
            return False

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
        """Run the periodic data collection loop.

        Flow:
        1. Single-shot mode: Collect data once and exit
        2. Periodic mode: Continuous loop with the following cycle:
           a. Collect and upload data
           b. Wait for collection_interval or shutdown signal
           c. If signal received during wait: perform final collection and exit
           d. If timeout elapsed normally: continue to next cycle

        Error handling:
        - Network/IO errors: Retry after DATA_COLLECTOR_RETRY_INTERVAL
        - If signal received during retry wait: attempt final collection and exit
        - KeyboardInterrupt: Clean exit

        Signal handling:
        - SIGTERM triggers request_shutdown() which sets _shutdown_event
        - Service responds immediately by interrupting any active wait
        - Always attempts final data collection before exit for data safety

        Single-shot mode (collection_interval is 0 or None):
        - Collects data once and exits immediately
        - Used for batch processing or scheduled jobs

        Periodic mode (collection_interval > 0):
        - Runs continuously until shutdown signal or error
        - Sleeps efficiently using threading.Event.wait() with timeout
        - Responsive to shutdown signals (no polling, immediate wake-up)
        """
        logger.info("Starting data collection service")

        in_single_shot_mode = not self.collection_interval
        if in_single_shot_mode:
            logger.info(
                "Collection interval is not set, operating in single-shot mode - service will exit after one data collection cycle"
            )

        while True:
            try:
                self._process_data_collection()

                if in_single_shot_mode:
                    return

                logger.info(
                    "Waiting %d seconds before next collection",
                    self.collection_interval,
                )

                # Wait for the collection interval or shutdown signal (whichever comes first)
                if self._wait_or_shutdown(self.collection_interval, "collection"):
                    # Shutdown was requested during collection wait
                    logger.info("Shutdown requested, performing final collection...")
                    self._process_data_collection()
                    logger.info("Shutdown completed after final data collection")
                    return
                # If wait returned False, timeout elapsed normally - continue to next collection cycle

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

                logger.info("Retrying in %d seconds...", DATA_COLLECTOR_RETRY_INTERVAL)

                # Wait for retry interval or shutdown signal (whichever comes first)
                if self._wait_or_shutdown(DATA_COLLECTOR_RETRY_INTERVAL, "retry"):
                    # Shutdown was requested during retry wait - attempt final collection
                    logger.info(
                        "Shutdown requested during retry, attempting final collection..."
                    )
                    try:
                        self._process_data_collection()
                        logger.info("Final collection completed successfully")
                    except Exception as final_e:
                        logger.error(
                            "Final collection attempt failed: %s",
                            final_e,
                            exc_info=True,
                        )
                    logger.info("Shutdown completed after final collection attempt")
                    return  # Exit the service entirely
