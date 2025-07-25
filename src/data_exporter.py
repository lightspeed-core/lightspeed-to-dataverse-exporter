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
    ALLOWED_SUBDIRS,
    DATA_MAX_SIZE,
    CONTENT_TYPE,
    USER_AGENT,
    DATA_COLLECTOR_RETRY_INTERVAL,
)

logger = logging.getLogger(__name__)


def filter_allowed_files(
    data_dir: Path, files: list[Path], allowed_subdirs: list[str]
) -> list[Path]:
    """Filter files to only include allowed subdirectories."""
    filtered_files: list[Path] = []
    for file in files:
        # Strip the data_dir prefix and get the first directory component
        relative_path = file.relative_to(data_dir)
        first_dir = relative_path.parts[0] if relative_path.parts else None
        if first_dir in allowed_subdirs:
            filtered_files.append(file)
    logger.warning("Found %s unknown files", len(files) - len(filtered_files))
    return filtered_files


def collect_files(data_dir: Path) -> list[tuple[Path, int]]:
    """Perform a single collection operation.

    Returns:
        List of tuples containing (file_path, file_size_bytes).
    """
    if not data_dir.exists():
        logger.warning("Data directory %s does not exist", data_dir)
        return []

    # Collect all files to be packed into tarball
    all_files = list(data_dir.rglob("*.json"))
    all_files = filter_allowed_files(data_dir, all_files, ALLOWED_SUBDIRS)

    logger.debug("Collected %d files from '%s'", len(all_files), data_dir)

    if not all_files:
        return []

    # Collect file sizes along with paths
    files_with_sizes = [
        (file_path, file_path.stat().st_size) for file_path in all_files
    ]

    return files_with_sizes


def chunk_data(
    data: list[tuple[pathlib.Path, int]], chunk_max_size: int = DATA_MAX_SIZE
) -> list[list[pathlib.Path]]:
    """Chunk the data into smaller parts.

    Args:
        data: List of tuples containing (file_path, file_size_bytes).
        chunk_max_size: Maximum size of a chunk.

    Returns:
        List of lists of paths to the chunked files.
    """
    # if file is bigger than DATA_MAX_SIZE, it will be in a chunk by itself
    chunk_size = 0
    chunks: list[list[pathlib.Path]] = []
    chunk: list[pathlib.Path] = []
    for file_path, file_size in data:
        if chunk_max_size < chunk_size + file_size or file_size > chunk_max_size:
            if chunk:
                chunks.append(chunk)
            chunk = []
            chunk_size = 0
        chunk.append(file_path)
        chunk_size += file_size
    if chunk:
        chunks.append(chunk)
    return chunks


def gather_data_chunks(
    collected_files: list[tuple[Path, int]],
) -> list[list[pathlib.Path]]:
    """Gather data chunks from the data directory."""
    data_chunks = chunk_data(collected_files)
    if any(data_chunks):
        logger.info(
            "Collected %d files (split to %d chunks)",
            len(collected_files),
            len(data_chunks),
        )
    return data_chunks


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


def delete_data(file_paths: list[pathlib.Path]) -> None:
    """Delete files from the provided paths.

    Args:
        file_paths: List of paths to the files to be deleted.
    """
    for file_path in file_paths:
        logger.debug("Removing '%s'", file_path)
        file_path.unlink()
        if file_path.exists():
            logger.error("failed to remove '%s'", file_path)


def ensure_data_dir_is_not_bigger_than_defined(
    collected_files: list[tuple[Path, int]],
    max_size: int = DATA_MAX_SIZE,
) -> None:
    """Ensure that the data dir is not bigger than it should be.

    Args:
        collected_files: List of tuples containing (file_path, file_size_bytes).
        max_size: Maximum size of the directory.
    """
    data_size = sum(file_size for _, file_size in collected_files)
    if data_size > max_size:
        logger.error(
            "Data folder size is bigger than the maximum allowed size: %d > %d",
            data_size,
            max_size,
        )
        logger.info("Removing files to fit the data into the limit...")
        extra_size = data_size - max_size
        for file_path, file_size in collected_files:
            extra_size -= file_size
            delete_data([file_path])
            if extra_size < 0:
                break


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
                collected_files = collect_files(self.data_dir)
                data_chunks = gather_data_chunks(collected_files)

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
                            delete_data(data_chunk)
                    if self.cleanup_after_send:
                        ensure_data_dir_is_not_bigger_than_defined(collected_files)
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
