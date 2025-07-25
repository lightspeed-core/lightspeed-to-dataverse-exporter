"""Authentication providers for different deployment environments."""

from .factory import (
    get_openshift_auth_provider,
    get_manual_auth_provider,
    get_auth_credentials,
    AuthMode,
)
from .providers import (
    AuthProvider,
    OpenShiftAuthProvider,
    ManualAuthProvider,
    AuthenticationError,
)

__all__ = [
    "AuthProvider",
    "OpenShiftAuthProvider",
    "ManualAuthProvider",
    "AuthenticationError",
    "AuthMode",
    "get_openshift_auth_provider",
    "get_manual_auth_provider",
    "get_auth_credentials",
]
