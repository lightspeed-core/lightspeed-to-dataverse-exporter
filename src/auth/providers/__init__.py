"""Authentication providers for different deployment environments."""

from .types import AuthProvider, AuthenticationError

from .openshift import OpenShiftAuthProvider
from .sso import SSOServiceAccountAuthProvider

__all__ = [
    "OpenShiftAuthProvider",
    "SSOServiceAccountAuthProvider",
    "AuthProvider",
    "AuthenticationError",
]
