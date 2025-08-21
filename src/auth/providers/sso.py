"""Providers for RedHat SSO auth."""

import json
import logging
from typing import Literal, cast, override
import requests
import jwt

from src import constants

from src.auth.providers.types import AuthProvider, AuthenticationError


logger = logging.getLogger(__name__)

SSOEnv = Literal["prod", "stage"]


def derive_sso_id(sso_jwt: str) -> str:
    decoded = jwt.decode(sso_jwt, options={"verify_signature": False})
    return decoded.get("preferred_username") or decoded.get("sub") or "unknown"


class SSOServiceAccountAuthProvider(AuthProvider):
    """Auth provider for RedHat SSO service accounts."""

    client_id: str
    client_secret: str
    env: SSOEnv
    identity_id: str | None

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        identity_id: str | None = None,
        env: SSOEnv = "prod",
    ):
        """
        Args:
            client_id: Service account client id
            client_secret: Service account secret
            identity_id: Optional identity id to use, otherwise sso token's preferred_username or
            sub will be used
            env: Either the prod or stage environment for SSO/api.
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.env = env
        self.identity_id = identity_id

    def get_sso_token(self) -> str:
        """Generate "access token" from the "offline token".

        Offline token can be generated at:
            prod - https://access.redhat.com/management/api
            stage - https://access.stage.redhat.com/management/api

        Args:
            offline_token: Offline token from the Customer Portal.

        Returns:
            Refresh token.
        """
        endpoint = f"https://{'sso' if self.env == 'prod' else 'sso.stage'}.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "api.console",
        }

        response = requests.post(
            endpoint, data=data, timeout=constants.ACCESS_TOKEN_GENERATION_TIMEOUT
        )
        try:
            if response.status_code == requests.codes.ok:
                return response.json()["access_token"]
            else:
                raise AuthenticationError(
                    f"Got {response.status_code} response from SSO: {response.text}"
                )
        except json.JSONDecodeError:
            raise AuthenticationError(
                "SSO response is not JSON. "
                f"Response: {response.status_code}: {response.text}"
            )

    @override
    def get_credentials(self) -> tuple[str, str]:
        """Get authentication token.

        Returns:
            str: Authentication token

        Raises:
            AuthenticationError: If token cannot be retrieved
        """
        sso_access_token = self.get_sso_token()

        identity_id = self.identity_id
        if not identity_id:
            identity_id = derive_sso_id(sso_access_token)

        endpoint = f"https://{'api' if self.env == 'prod' else 'api.stage'}.openshift.com/api/accounts_mgmt/v1/access_token"
        response = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {sso_access_token}",
            },
            timeout=constants.ACCESS_TOKEN_GENERATION_TIMEOUT,
        )

        if response.status_code != requests.codes.ok:
            raise AuthenticationError(
                f"Failed to access api access_token endpoint to get ingress token, got {response.status_code} response: {response.text}"
            )

        try:
            return (
                cast(str, response.json()["auths"]["cloud.openshift.com"]["auth"]),
                identity_id,
            )
        except KeyError:
            raise AuthenticationError(
                f"Request for API access token was malformed, got {response.text}"
            )
        except json.JSONDecodeError:
            raise AuthenticationError(
                f"Response for API access token was not valid JSON, got {response.text}"
            )
