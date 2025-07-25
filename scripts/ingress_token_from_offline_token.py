#!/usr/bin/env python3
"""Utility to generate pull secret from offline token.

Usage:
    python scripts/ingress_token_from_offline_token.py --offline-token <offline_token> --env <prod|stage>
"""

import argparse
import sys
import requests


def get_pull_secret_url(env: str) -> str:
    """Get the pull secret URL for the given environment."""
    if env == "prod":
        return "https://api.openshift.com/api/accounts_mgmt/v1/access_token"
    elif env == "stage":
        return "https://api.stage.openshift.com/api/accounts_mgmt/v1/access_token"
    else:
        raise ValueError(f"Invalid environment: {env}")


def get_access_token_from_offline_token(offline_token: str) -> str:
    """Get access token from offline token using Red Hat SSO."""
    token_url = "https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token"
    data = {
        "client_id": "rhsm-api",
        "grant_type": "refresh_token",
        "refresh_token": offline_token,
    }
    headers = {"content-type": "application/x-www-form-urlencoded"}

    try:
        resp = requests.post(token_url, data=data, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()["access_token"]
    except requests.RequestException as e:
        raise Exception(f"Failed to get access token: {e}") from e
    except KeyError as e:
        raise Exception(
            f"Invalid response format when getting access token: {e}"
        ) from e


def get_pull_secret_token(access_token: str, env: str) -> str:
    """Get the pull secret token using the access token."""
    pull_secret_url = get_pull_secret_url(env)
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        resp = requests.post(pull_secret_url, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()["auths"]["cloud.openshift.com"]["auth"]
    except requests.RequestException as e:
        raise Exception(f"Failed to get pull secret: {e}") from e
    except KeyError as e:
        raise Exception(f"Invalid response format when getting pull secret: {e}") from e


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Generate pull secret token from offline token"
    )
    parser.add_argument(
        "--offline-token",
        required=True,
        help="Offline token from Red Hat Customer Portal",
    )
    parser.add_argument(
        "--env",
        choices=["prod", "stage"],
        required=True,
        help="Environment (prod or stage)",
    )

    args = parser.parse_args()

    try:
        print("Getting access token from offline token...", file=sys.stderr)
        access_token = get_access_token_from_offline_token(args.offline_token)

        print(f"Getting pull secret for {args.env} environment...", file=sys.stderr)
        ingress_token = get_pull_secret_token(access_token, args.env)

        # Print the token to stdout
        print(f"ingress_server_auth_token: {ingress_token}")

        print(
            f"✅ Successfully generated pull secret for {args.env} environment!",
            file=sys.stderr,
        )

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
