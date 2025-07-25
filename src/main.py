#!/usr/bin/env python3
"""Main entrypoint for the Lightspeed to Dataverse exporter."""

import argparse
import logging
import sys
from pathlib import Path
from src.settings import DataCollectorSettings
from src.data_exporter import DataCollectorService
from src.auth import get_auth_credentials, AuthenticationError
from src import constants

logger = logging.getLogger(__name__)


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
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Set the logging level",
    )

    return parser.parse_args()


def configure_logging(log_level: str) -> None:
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s [%(name)s:%(filename)s:%(lineno)d] %(levelname)s: %(message)s",
    )
    # silence libs logging
    # - urllib3 - we don't care about those debug posts
    # - kubernetes - prints resources content when debug, causing secrets leak
    logging.getLogger("kubernetes").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def main() -> int:
    """Main function."""
    args = parse_args()

    configure_logging(args.log_level)

    logger.info("Starting Lightspeed to Dataverse exporter (mode: %s)", args.mode)

    try:
        # Load settings from config file if provided
        settings = None
        if args.config:
            logger.info("Loading configuration from %s", args.config)
            settings = DataCollectorSettings.from_yaml(args.config)

        # Check for required arguments when no config is provided
        if not args.config:
            required_args = ["data_dir", "service_id", "ingress_server_url"]
            if args.mode == "manual":
                required_args.append("ingress_server_auth_token")
                required_args.append("identity_id")

            missing_args = [
                arg
                for arg in required_args
                if getattr(args, arg.replace("-", "_")) is None
            ]
            if missing_args:
                logger.error(
                    "Missing required arguments: %s",
                    ", ".join(f"--{arg}" for arg in missing_args),
                )
                logger.error(
                    "Either provide --config with a YAML file or all required arguments"
                )
                return 1

        # Get authentication credentials based on mode
        # Use CLI args first, fall back to config values
        auth_token, identity_id = get_auth_credentials(
            mode=args.mode,
            auth_token=args.ingress_server_auth_token
            or (settings.ingress_server_auth_token if settings else None),
            identity_id=args.identity_id
            or (settings.identity_id if settings else None),
        )

        # Create and run service using CLI args with config fallbacks
        service = DataCollectorService(
            data_dir=args.data_dir or (settings.data_dir if settings else None),
            service_id=args.service_id or (settings.service_id if settings else None),
            ingress_server_url=args.ingress_server_url
            or (settings.ingress_server_url if settings else None),
            ingress_server_auth_token=auth_token,
            identity_id=identity_id,
            collection_interval=args.collection_interval
            or (
                settings.collection_interval
                if settings
                else constants.DATA_COLLECTOR_COLLECTION_INTERVAL
            ),
            ingress_connection_timeout=args.ingress_connection_timeout
            or (
                settings.ingress_connection_timeout
                if settings
                else constants.DATA_COLLECTOR_CONNECTION_TIMEOUT
            ),
            cleanup_after_send=(
                False
                if args.no_cleanup
                else (settings.cleanup_after_send if settings else True)
            ),
        )

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
