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

from src.constants import (
    TARBALL_FILENAME,
    CONTENT_TYPE,
    USER_AGENT,
    DATA_COLLECTOR_RETRY_INTERVAL,
)
from src.file_handler import FileHandler

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

    def _upload_data_to_ingress(self, tarball: io.BytesIO) -> requests.Response:
        """Upload the tarball to a Ingress.

        Args:
            tarball: BytesIO object representing the tarball to be uploaded.

        Returns:
            Response object from the Ingress.
        """
        logger.info("Sending collected data")
        payload = {
            "file": (
                TARBALL_FILENAME,
                tarball.read(),
                CONTENT_TYPE.format(service_id=self.service_id),
            ),
        }

        headers: dict[str, str | bytes]
        headers = {
            "User-Agent": USER_AGENT.format(identity_id=self.identity_id),
            "Authorization": f"Bearer {self.ingress_server_auth_token}",
        }

        with requests.Session() as s:
            s.headers = headers
            logger.debug("Posting payload to %s", self.ingress_server_url)
            response = s.post(
                url=self.ingress_server_url,
                files=payload,
                timeout=self.ingress_connection_timeout,
            )

        return response

    def upload_tarball(self, tarball: io.BytesIO) -> None:
        """Upload the tarball to a Ingress.

        Args:
            tarball: BytesIO object representing the tarball to be uploaded.
        """
        response = self._upload_data_to_ingress(tarball)
        if response.status_code != 202:
            logger.error(
                "Posting payload failed, response: %d: %s",
                response.status_code,
                response.text,
            )
            raise requests.RequestException(
                f"Data upload failed with response code: {response.status_code}"
                f" and text: {response.text}",
            )

        request_id = response.json()["request_id"]
        logger.info("Data uploaded with request_id: '%s'", request_id)

        # close the tarball to release memory
        tarball.close()

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
                        self.upload_tarball(tarball)
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
