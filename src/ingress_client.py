"""HTTP client for uploading data to the Ingress service."""

import io
import logging
import requests

from src.constants import TARBALL_FILENAME, CONTENT_TYPE, USER_AGENT

logger = logging.getLogger(__name__)


class IngressClient:
    """HTTP client for uploading data to the Ingress service.

    This class encapsulates all HTTP communication with the ingress server,
    including authentication, request formatting, and response handling.
    """

    def __init__(
        self,
        ingress_server_url: str,
        ingress_server_auth_token: str,
        service_id: str,
        identity_id: str,
        connection_timeout: int,
    ):
        """Initialize the ingress client.

        Args:
            ingress_server_url: URL of the ingress server
            ingress_server_auth_token: Authentication token for the server
            service_id: Service identifier for content type
            identity_id: Identity identifier for user agent
            connection_timeout: HTTP request timeout in seconds
        """
        self.ingress_server_url = ingress_server_url
        self.ingress_server_auth_token = ingress_server_auth_token
        self.service_id = service_id
        self.identity_id = identity_id
        self.connection_timeout = connection_timeout

    def _upload_data_to_ingress(self, tarball: io.BytesIO) -> requests.Response:
        """Upload the tarball to the Ingress server.

        Args:
            tarball: BytesIO object representing the tarball to be uploaded.

        Returns:
            Response object from the Ingress server.
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
                timeout=self.connection_timeout,
            )

        return response

    def upload_tarball(self, tarball: io.BytesIO) -> str:
        """Upload the tarball to the Ingress server.

        Args:
            tarball: BytesIO object representing the tarball to be uploaded.

        Returns:
            request_id: The request ID returned by the server.

        Raises:
            requests.RequestException: If the upload fails.
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

        return request_id
