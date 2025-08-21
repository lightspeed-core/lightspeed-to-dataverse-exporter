#!/usr/bin/env python3
"""Main entrypoint for the Lightspeed to Dataverse exporter."""

import argparse
import logging
import signal
import sys
import yaml
import json
from os import environ
from pathlib import Path
from typing import TypeVar, cast, get_args

from pydantic import ValidationError

from src import constants
from src.auth import AuthMode
from src.auth.providers import OpenShiftAuthProvider, SSOServiceAccountAuthProvider
from src.settings import DataCollectorSettings
from src.data_exporter import DataCollectorService
from src.auth.providers import AuthenticationError


class Args(argparse.Namespace):
    mode: AuthMode
    config: Path | None
    data_dir: Path | None
    service_id: str | None
    ingress_server_url: str | None
    ingress_server_auth_token: str | None
    identity_id: str | None
    collection_interval: int | None
    ingress_connection_timeout: int | None
    retry_interval: int | None
    no_cleanup: bool
    allowed_subdirs: list[str] | None
    log_level: str
    rich_logs: bool
    client_id: str | None
    client_secret: str | None


logger = logging.getLogger(__name__)


def parse_args() -> Args:
    """Parse command line arguments with environment selection."""
    parser = argparse.ArgumentParser(
        description="Lightspeed to Dataverse data exporter",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--mode",
        choices=get_args(AuthMode),
        default="manual",
        help="Authentication mode: 'openshift' (OpenShift cluster auth), 'sso' (RedHat SSO auth), 'manual' (explicit credentials)",
    )

    parser.add_argument(
        "--config",
        type=Path,
        help="Path to YAML configuration file",
    )

    # Configuration overrides (optional when using config file)
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="Directory containing data to export",
    )

    parser.add_argument(
        "--service-id",
        help="Service identifier for the data export",
    )

    parser.add_argument(
        "--ingress-server-url",
        help="URL of the ingress server to send data to",
    )

    parser.add_argument(
        "--ingress-server-auth-token",
        help="Authentication token for the ingress server (required for manual mode or non-OpenShift environments)",
    )

    parser.add_argument(
        "--identity-id",
        help="Identity identifier for the data export (required for manual mode or non-OpenShift environments)",
    )

    parser.add_argument(
        "--collection-interval",
        type=int,
        help="Collection interval in seconds",
    )

    parser.add_argument(
        "--ingress-connection-timeout",
        type=int,
        help="Connection timeout for ingress server in seconds",
    )

    parser.add_argument(
        "--retry-interval",
        type=int,
        help="Retry interval in seconds when collection fails",
    )

    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Do not clean up files after successful send",
    )

    parser.add_argument(
        "--allowed-subdirs",
        nargs="*",
        help="List of allowed subdirectories to collect from (space-separated). If not specified, uses default subdirs from config.",
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Set the logging level",
    )

    parser.add_argument(
        "--rich-logs",
        action="store_true",
        help="Enable rich colored logging output",
    )

    parser.add_argument(
        "--client-id",
        help="SSO Client ID (only when using 'sso' auth). Also accepted in the CLIENT_ID envvar.",
    )

    parser.add_argument(
        "--client-secret",
        help="SSO Client secret value (only when using 'sso' auth). Also accepted in the CLIENT_SECRET envvar.",
    )

    parser.add_argument(
        "--print-config-and-exit",
        action="store_true",
        help="Print the resolved configuration as JSON and exit without running the service",
    )

    return cast(Args, parser.parse_args())


def configure_logging(log_level: str, use_rich: bool = False) -> None:
    """Configure logging with optional rich formatting.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        use_rich: Whether to use rich colored logging
    """
    if use_rich:
        try:
            from rich.logging import RichHandler
            from rich.console import Console

            # Create console with color detection
            console = Console()

            # Configure rich logging
            logging.basicConfig(
                level=getattr(logging, log_level),
                format="%(message)s",
                datefmt="[%X]",
                handlers=[
                    RichHandler(
                        console=console,
                        show_path=True,
                        show_time=True,
                        show_level=True,
                        markup=True,
                        rich_tracebacks=True,
                    )
                ],
            )
        except ImportError:
            # Fall back to standard logging if rich is not available
            logging.basicConfig(
                level=getattr(logging, log_level),
                format="%(asctime)s [%(name)s:%(filename)s:%(lineno)d] %(levelname)s: %(message)s",
            )
    else:
        logging.basicConfig(
            level=getattr(logging, log_level),
            format="%(asctime)s [%(name)s:%(filename)s:%(lineno)d] %(levelname)s: %(message)s",
        )

    # silence libs logging
    # - urllib3 - we don't care about those debug posts
    # - kubernetes - prints resources content when debug
    logging.getLogger("kubernetes").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


T = TypeVar("T")


def first_not_none(*values: list[T | None]) -> T | None:
    for v in values:
        if v is not None:
            return v
    return None


def main() -> int:
    """Main function."""
    args = parse_args()

    configure_logging(args.log_level, args.rich_logs)

    logger.info("Starting Lightspeed to Dataverse exporter (mode: %s)", args.mode)

    try:
        config_dict = {}

        auth_token: str | None = None
        identity_id: str | None = None

        if args.mode != "manual":
            if args.mode == "openshift":
                provider = OpenShiftAuthProvider()
            elif args.mode == "sso":
                client_id = args.client_id or environ.get("CLIENT_ID")
                client_secret = args.client_secret or environ.get("CLIENT_SECRET")

                if not client_id or not client_secret:
                    logging.error(
                        "Must specify client id and secret when using sso auth"
                    )
                    sys.exit(1)

                provider = SSOServiceAccountAuthProvider(
                    client_id=client_id,
                    client_secret=client_secret,
                    identity_id=args.identity_id,
                    # Just expose this via envvar since it is not really for prod use
                    env="stage" if environ.get("USE_SSO_STAGE") is not None else "prod",
                )
            else:
                logger.error(f"Invalid auth mode: {args.mode}")
                sys.exit(1)

            auth_token, identity_id = provider.get_credentials()

        if args.config:
            logger.info("Loading configuration from %s", args.config)
            with open(args.config, "r", encoding="utf-8") as f:
                config_dict = yaml.safe_load(f)

        config = DataCollectorSettings(
            data_dir=first_not_none(args.data_dir, config_dict.get("data_dir")),
            service_id=first_not_none(args.service_id, config_dict.get("service_id")),
            ingress_server_url=first_not_none(
                args.ingress_server_url, config_dict.get("ingress_server_url")
            ),
            # values from auth provider will take precedent
            ingress_server_auth_token=first_not_none(
                auth_token,
                args.ingress_server_auth_token,
                environ.get("INGRESS_SERVER_AUTH_TOKEN"),
                config_dict.get("ingress_server_auth_token"),
            ),
            identity_id=first_not_none(
                identity_id,
                args.identity_id,
                config_dict.get("identity_id"),
                "lightspeed-exporter",
            ),
            collection_interval=first_not_none(
                args.collection_interval,
                config_dict.get("collection_interval"),
                constants.DATA_COLLECTOR_COLLECTION_INTERVAL,
            ),
            ingress_connection_timeout=first_not_none(
                args.ingress_connection_timeout,
                config_dict.get("ingress_connection_timeout"),
                constants.DATA_COLLECTOR_CONNECTION_TIMEOUT,
            ),
            retry_interval=first_not_none(
                args.retry_interval,
                config_dict.get("retry_interval"),
                constants.DATA_COLLECTOR_RETRY_INTERVAL,
            ),
            cleanup_after_send=first_not_none(
                False if args.no_cleanup is True else None,
                config_dict.get("cleanup_after_send"),
                True,
            ),
            allowed_subdirs=first_not_none(
                args.allowed_subdirs, config_dict.get("allowed_subdirs"), []
            ),
        )

        # If print-config-and-exit flag is set, output config and exit
        if args.print_config_and_exit:
            logger.info("Printing resolved configuration")
            config_dict_clean = config.model_dump()
            # Convert Path objects to strings for JSON serialization
            for key, value in config_dict_clean.items():
                if hasattr(value, "__fspath__"):  # Path-like object
                    config_dict_clean[key] = str(value)
            print(json.dumps(config_dict_clean, indent=2, sort_keys=True))
            return 0

        service = DataCollectorService(config)

        _ = signal.signal(signal.SIGTERM, lambda _, _2: service.shutdown())

        service.run()

    except ValidationError as e:
        logger.error(
            "Invalid config\n"
            + "\n".join(
                [
                    f"{''.join([str(loc) for loc in err['loc']])}: {err['msg']} (got {err['input']})"
                    for err in e.errors()
                ]
            )
        )
        return 1
    except AuthenticationError as e:
        logger.error("Authentication failed: %s", e)
        if args.mode == "openshift":
            logger.info(
                "Ensure the application is running in an OpenShift cluster with proper permissions"
            )
        elif args.mode == "sso":
            logger.info(
                "Ensure CLIENT_ID and CLIENT_SECRET envvars are set to valid SSO service account credentials"
            )
        elif args.mode == "manual":
            logger.info("Provide valid --ingress-server-auth-token and --identity-id")
        return 1
    except KeyboardInterrupt:
        logger.info("Exporter stopped by user")
        return 0
    except Exception as e:
        logger.error("Error running exporter: %s", e, exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
