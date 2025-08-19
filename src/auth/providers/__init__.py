"""Authentication providers for different deployment environments."""

from .types import AuthProvider, AuthenticationError

from .openshift import OpenShiftAuthProvider

__all__ = [
    "OpenShiftAuthProvider",
    "AuthProvider",
    "AuthenticationError",
]
