class AuthenticationError(Exception):
    """Exception raised when authentication fails."""


class AuthProvider:
    """Base class for authentication providers."""

    def get_auth_token(self) -> str:
        """Get authentication token.

        Returns:
            str: Authentication token

        Raises:
            AuthenticationError: If token cannot be retrieved
        """
        raise NotImplementedError

    def get_identity_id(self) -> str:
        """Get identity identifier.

        Returns:
            str: Identity identifier

        Raises:
            AuthenticationError: If identity ID cannot be retrieved
        """
        raise NotImplementedError

    def get_credentials(self) -> tuple[str, str]:
        """Get both authentication token and identity ID.

        Returns:
            tuple[str, str]: Tuple of (auth_token, identity_id)

        Raises:
            AuthenticationError: If credentials cannot be retrieved
        """
        return self.get_auth_token(), self.get_identity_id()
