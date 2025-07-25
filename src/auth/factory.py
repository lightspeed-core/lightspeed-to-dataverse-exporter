"""Authentication provider factory."""

import logging
from typing import Literal

from .providers import OpenShiftAuthProvider, ManualAuthProvider, AuthenticationError


logger = logging.getLogger(__name__)

AuthMode = Literal["openshift", "manual"]


def get_openshift_auth_provider() -> OpenShiftAuthProvider:
    """Get an OpenShift authentication provider.

    Returns:
        OpenShiftAuthProvider: The OpenShift authentication provider

    Raises:
        AuthenticationError: If OpenShift authentication cannot be initialized
    """
    return OpenShiftAuthProvider()


def get_manual_auth_provider(auth_token: str, identity_id: str) -> ManualAuthProvider:
    """Get a manual authentication provider.

    Args:
        auth_token: Authentication token
        identity_id: Identity identifier

    Returns:
        ManualAuthProvider: The manual authentication provider

    Raises:
        AuthenticationError: If manual authentication cannot be initialized
    """
    if not auth_token or not identity_id:
        raise AuthenticationError(
            "Manual authentication requires both auth_token and identity_id"
        )

    return ManualAuthProvider(auth_token=auth_token, identity_id=identity_id)


def get_auth_credentials(
    mode: AuthMode, auth_token: str = None, identity_id: str = None
) -> tuple[str, str]:
    """Get authentication credentials based on the specified mode.

    Args:
        mode: Authentication mode (openshift, manual)
        auth_token: Manual auth token (for manual mode)
        identity_id: Manual identity ID (for manual mode)

    Returns:
        Tuple of (auth_token, identity_id)

    Raises:
        AuthenticationError: If authentication fails
    """
    if mode == "manual":
        logger.info("Using manual authentication mode")
        auth_provider = get_manual_auth_provider(auth_token, identity_id)
        return auth_provider.get_credentials()

    elif mode == "openshift":
        logger.info("Using OpenShift authentication mode")
        auth_provider = get_openshift_auth_provider()
        return auth_provider.get_credentials()

    else:
        raise ValueError(f"Invalid authentication mode: {mode}")
