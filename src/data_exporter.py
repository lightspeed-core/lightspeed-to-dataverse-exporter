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
import time
import requests

from src.constants import DATA_COLLECTOR_RETRY_INTERVAL
from src.file_handler import FileHandler
from src.ingress_client import IngressClient

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

    def __init__(
        self,
        data_dir: Path,
        collection_interval: int,
        ingress_server_url: str,
        ingress_server_auth_token: str,
        service_id: str,
        identity_id: str,
        ingress_connection_timeout: int,
        cleanup_after_send: bool,
        allowed_subdirs: list[str] | None = None,
    ) -> None:
        """Initialize the data collector service."""
        self.data_dir = data_dir
        self.collection_interval = collection_interval
        self.ingress_server_url = ingress_server_url
        self.ingress_server_auth_token = ingress_server_auth_token
        self.service_id = service_id
        self.identity_id = identity_id
        self.ingress_connection_timeout = ingress_connection_timeout
        self.cleanup_after_send = cleanup_after_send
        self.allowed_subdirs = allowed_subdirs or []

        # Initialize file handler for this service
        self.file_handler = FileHandler(data_dir, allowed_subdirs=allowed_subdirs)

        # Initialize ingress client for uploads
        self.ingress_client = IngressClient(
            ingress_server_url=ingress_server_url,
            ingress_server_auth_token=ingress_server_auth_token,
            service_id=service_id,
            identity_id=identity_id,
            connection_timeout=ingress_connection_timeout,
        )

    def run(self) -> None:
        """Run the periodic data collection loop."""
        logger.info("Starting data collection service")

        while True:
            try:
                collected_files = self.file_handler.collect_files()
                data_chunks = self.file_handler.gather_data_chunks(collected_files)

                if data_chunks:
                    for i, data_chunk in enumerate(data_chunks):
                        logger.info(
                            "Uploading data chunk %d/%d", i + 1, len(data_chunks)
                        )
                        tarball = package_files_into_tarball(
                            data_chunk, path_to_strip=self.data_dir.as_posix()
                        )
                        logger.debug("Successfully packed data chunk into tarball")
                        self.ingress_client.upload_tarball(tarball)
                        if self.cleanup_after_send:
                            self.file_handler.delete_collected_files(data_chunk)
                    if self.cleanup_after_send:
                        self.file_handler.ensure_size_limit(collected_files)
                else:
                    logger.info("No data marked for collection in '%s'", self.data_dir)
                logger.info(
                    "Waiting %d seconds before next collection",
                    self.collection_interval,
                )
                time.sleep(self.collection_interval)
            except KeyboardInterrupt:
                logger.info("Data collection service stopped by user")
                break
            except (OSError, requests.RequestException) as e:
                logger.error("Error during collection process: %s", e, exc_info=True)
                logger.info("Retrying in %d seconds...", self.collection_interval)
                time.sleep(DATA_COLLECTOR_RETRY_INTERVAL)
