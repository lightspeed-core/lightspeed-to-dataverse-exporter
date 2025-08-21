"""Authentication providers for different deployment environments."""

from typing import Literal

AuthMode = Literal["openshift", "manual", "sso"]

__all__ = [
    "AuthMode",
]
