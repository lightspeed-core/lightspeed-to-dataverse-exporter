#!/usr/bin/env python3
"""Main entrypoint for the Lightspeed to Dataverse exporter."""

import argparse
import logging
import sys
from os import environ
from pathlib import Path
from src.settings import DataCollectorSettings
from src.data_exporter import DataCollectorService
from src.auth import get_auth_credentials, AuthenticationError
from src import constants

logger = logging.getLogger(__name__)


def validate_required_config(config_dict: dict, mode: str) -> None:
    """Validate that all required configuration is present.

    Args:
        config_dict: Dictionary containing configuration values
        mode: Authentication mode (openshift or manual)

    Raises:
        SystemExit: If required configuration is missing
    """
    required_fields = ["data_dir", "service_id", "ingress_server_url"]
    if mode == "manual":
        required_fields.extend(["ingress_server_auth_token", "identity_id"])

    missing_fields = [
        field
        for field in required_fields
        if field not in config_dict or config_dict[field] is None
    ]

    if missing_fields:
        logger.error(
            "Missing required configuration: %s",
            ", ".join(f"--{field.replace('_', '-')}" for field in missing_fields),
        )
        logger.error(
            "Either provide --config with a YAML file or all required arguments"
        )
        sys.exit(1)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments with environment selection."""
    parser = argparse.ArgumentParser(
        description="Lightspeed to Dataverse data exporter",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--mode",
        choices=["openshift", "manual"],
        default="manual",
        help="Authentication mode: 'openshift' (OpenShift cluster auth), 'manual' (explicit credentials)",
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

    return parser.parse_args()


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


def main() -> int:
    """Main function."""
    args = parse_args()

    configure_logging(args.log_level, args.rich_logs)

    logger.info("Starting Lightspeed to Dataverse exporter (mode: %s)", args.mode)

    try:
        # Load config as dict if provided
        config_dict = {}
        if args.config:
            logger.info("Loading configuration from %s", args.config)
            import yaml

            with open(args.config, "r", encoding="utf-8") as f:
                config_dict = yaml.safe_load(f) or {}

        # Apply CLI args to config dict (CLI args override config file values)
        if args.data_dir:
            config_dict["data_dir"] = args.data_dir
        if args.service_id:
            config_dict["service_id"] = args.service_id
        if args.ingress_server_url:
            config_dict["ingress_server_url"] = args.ingress_server_url
        if args.ingress_server_auth_token:
            config_dict["ingress_server_auth_token"] = args.ingress_server_auth_token
        elif "INGRESS_SERVER_AUTH_TOKEN" in environ:
            config_dict["ingress_server_auth_token"] = environ[
                "INGRESS_SERVER_AUTH_TOKEN"
            ]
        if args.identity_id:
            config_dict["identity_id"] = args.identity_id
        if args.collection_interval:
            config_dict["collection_interval"] = args.collection_interval
        if args.ingress_connection_timeout:
            config_dict["ingress_connection_timeout"] = args.ingress_connection_timeout
        if args.no_cleanup:
            config_dict["cleanup_after_send"] = False
        if args.allowed_subdirs:
            config_dict["allowed_subdirs"] = args.allowed_subdirs

        # Validate required configuration
        validate_required_config(config_dict, args.mode)

        # Get authentication credentials based on mode
        auth_token, identity_id = get_auth_credentials(
            mode=args.mode,
            auth_token=args.ingress_server_auth_token
            or config_dict.get("ingress_server_auth_token"),
            identity_id=args.identity_id or config_dict.get("identity_id"),
        )

        # Update config dict with resolved auth values
        config_dict["ingress_server_auth_token"] = auth_token
        config_dict["identity_id"] = identity_id

        # Set defaults for optional fields
        config_dict.setdefault(
            "collection_interval", constants.DATA_COLLECTOR_COLLECTION_INTERVAL
        )
        config_dict.setdefault(
            "ingress_connection_timeout", constants.DATA_COLLECTOR_CONNECTION_TIMEOUT
        )
        config_dict.setdefault("cleanup_after_send", True)
        config_dict.setdefault("allowed_subdirs", [])

        # Create settings from merged config
        config = DataCollectorSettings(**config_dict)
        service = DataCollectorService(config)

        service.run()

    except AuthenticationError as e:
        logger.error("Authentication failed: %s", e)
        if args.mode == "openshift":
            logger.info(
                "Ensure the application is running in an OpenShift cluster with proper permissions"
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
