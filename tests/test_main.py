"""Tests for src.main module."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from src.main import parse_args, main, configure_logging


class TestParseArgs:
    """Test cases for argument parsing."""

    def test_parse_args_minimal_manual_mode(self):
        """Test parsing minimal arguments for manual mode."""
        test_args = [
            "--data-dir",
            "/tmp",
            "--service-id",
            "test-service",
            "--ingress-server-url",
            "https://example.com",
            "--ingress-server-auth-token",
            "test-token",
            "--identity-id",
            "test-identity",
        ]

        with patch("sys.argv", ["main.py"] + test_args):
            args = parse_args()

            assert args.mode == "manual"  # Default
            assert args.data_dir == Path("/tmp")
            assert args.service_id == "test-service"
            assert args.ingress_server_url == "https://example.com"
            assert args.ingress_server_auth_token == "test-token"
            assert args.identity_id == "test-identity"
            assert args.log_level == "INFO"  # Default

    def test_parse_args_openshift_mode(self):
        """Test parsing arguments for OpenShift mode."""
        test_args = [
            "--mode",
            "openshift",
            "--data-dir",
            "/tmp",
            "--service-id",
            "test-service",
            "--ingress-server-url",
            "https://example.com",
        ]

        with patch("sys.argv", ["main.py"] + test_args):
            args = parse_args()

            assert args.mode == "openshift"
            assert args.data_dir == Path("/tmp")
            assert args.service_id == "test-service"
            assert args.ingress_server_url == "https://example.com"

    def test_parse_args_with_config_file(self):
        """Test parsing arguments with config file."""
        test_args = ["--config", "/path/to/config.yaml", "--log-level", "DEBUG"]

        with patch("sys.argv", ["main.py"] + test_args):
            args = parse_args()

            assert args.config == Path("/path/to/config.yaml")
            assert args.log_level == "DEBUG"

    def test_parse_args_all_options(self):
        """Test parsing all possible arguments."""
        test_args = [
            "--mode",
            "manual",
            "--config",
            "/path/to/config.yaml",
            "--data-dir",
            "/data",
            "--service-id",
            "full-service",
            "--ingress-server-url",
            "https://full.example.com",
            "--ingress-server-auth-token",
            "full-token",
            "--identity-id",
            "full-identity",
            "--collection-interval",
            "600",
            "--ingress-connection-timeout",
            "60",
            "--no-cleanup",
            "--log-level",
            "WARNING",
        ]

        with patch("sys.argv", ["main.py"] + test_args):
            args = parse_args()

            assert args.mode == "manual"
            assert args.config == Path("/path/to/config.yaml")
            assert args.data_dir == Path("/data")
            assert args.service_id == "full-service"
            assert args.ingress_server_url == "https://full.example.com"
            assert args.ingress_server_auth_token == "full-token"
            assert args.identity_id == "full-identity"
            assert args.collection_interval == 600
            assert args.ingress_connection_timeout == 60
            assert args.no_cleanup is True
            assert args.log_level == "WARNING"

    def test_parse_args_invalid_mode(self):
        """Test parsing with invalid authentication mode."""
        test_args = ["--mode", "invalid-mode"]

        with patch("sys.argv", ["main.py"] + test_args):
            with pytest.raises(SystemExit):
                parse_args()

    def test_parse_args_invalid_log_level(self):
        """Test parsing with invalid log level."""
        test_args = ["--log-level", "INVALID"]

        with patch("sys.argv", ["main.py"] + test_args):
            with pytest.raises(SystemExit):
                parse_args()


class TestConfigureLogging:
    """Test cases for logging configuration."""

    @patch("src.main.logging.basicConfig")
    @patch("src.main.logging.getLogger")
    def test_configure_logging_info_level(self, mock_get_logger, mock_basic_config):
        """Test logging configuration with INFO level."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        configure_logging("INFO")

        mock_basic_config.assert_called_once()
        call_args = mock_basic_config.call_args
        assert call_args[1]["level"] == 20  # logging.INFO
        assert "%(asctime)s" in call_args[1]["format"]

        # Check that specific loggers are silenced
        mock_get_logger.assert_any_call("kubernetes")
        mock_get_logger.assert_any_call("urllib3")

    @patch("src.main.logging.basicConfig")
    @patch("src.main.logging.getLogger")
    def test_configure_logging_debug_level(self, mock_get_logger, mock_basic_config):
        """Test logging configuration with DEBUG level."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        configure_logging("DEBUG")

        mock_basic_config.assert_called_once()
        call_args = mock_basic_config.call_args
        assert call_args[1]["level"] == 10  # logging.DEBUG


class TestMain:
    """Test cases for main function."""

    @patch("src.main.parse_args")
    @patch("src.main.configure_logging")
    @patch("src.main.DataCollectorSettings.from_yaml")
    @patch("src.main.get_auth_credentials")
    @patch("src.main.DataCollectorService")
    def test_main_with_config_file_openshift_mode(
        self,
        mock_service_class,
        mock_get_auth,
        mock_from_yaml,
        mock_configure_logging,
        mock_parse_args,
    ):
        """Test main function with config file in OpenShift mode."""
        # Setup mocks
        mock_args = Mock()
        mock_args.mode = "openshift"
        mock_args.config = Path("/config.yaml")
        mock_args.log_level = "INFO"
        mock_args.data_dir = None
        mock_args.service_id = None
        mock_args.ingress_server_url = None
        mock_args.ingress_server_auth_token = None
        mock_args.identity_id = None
        mock_args.collection_interval = None
        mock_args.ingress_connection_timeout = None
        mock_args.no_cleanup = False
        mock_args.rich_logs = False
        mock_parse_args.return_value = mock_args

        mock_settings = Mock()
        mock_settings.data_dir = Path("/data")
        mock_settings.service_id = "config-service"
        mock_settings.ingress_server_url = "https://config.example.com"
        mock_settings.ingress_server_auth_token = None
        mock_settings.identity_id = "config-identity"
        mock_settings.collection_interval = 300
        mock_settings.ingress_connection_timeout = 30
        mock_settings.cleanup_after_send = True
        mock_from_yaml.return_value = mock_settings

        mock_get_auth.return_value = ("openshift-token", "openshift-identity")

        mock_service = Mock()
        mock_service_class.return_value = mock_service

        result = main()

        assert result == 0
        mock_configure_logging.assert_called_once_with("INFO", mock_args.rich_logs)
        mock_from_yaml.assert_called_once_with(Path("/config.yaml"))
        mock_get_auth.assert_called_once_with(
            mode="openshift", auth_token=None, identity_id="config-identity"
        )
        mock_service.run.assert_called_once()

    @patch("src.main.parse_args")
    @patch("src.main.configure_logging")
    @patch("src.main.get_auth_credentials")
    @patch("src.main.DataCollectorService")
    def test_main_without_config_manual_mode(
        self, mock_service_class, mock_get_auth, mock_configure_logging, mock_parse_args
    ):
        """Test main function without config file in manual mode."""
        # Setup mocks
        mock_args = Mock()
        mock_args.mode = "manual"
        mock_args.config = None
        mock_args.log_level = "DEBUG"
        mock_args.data_dir = Path("/test-data")
        mock_args.service_id = "test-service"
        mock_args.ingress_server_url = "https://test.example.com"
        mock_args.ingress_server_auth_token = "test-token"
        mock_args.identity_id = "test-identity"
        mock_args.collection_interval = 600
        mock_args.ingress_connection_timeout = 60
        mock_args.no_cleanup = True
        mock_args.rich_logs = False
        mock_parse_args.return_value = mock_args

        mock_get_auth.return_value = ("test-token", "test-identity")

        mock_service = Mock()
        mock_service_class.return_value = mock_service

        result = main()

        assert result == 0
        mock_configure_logging.assert_called_once_with("DEBUG", mock_args.rich_logs)
        mock_get_auth.assert_called_once_with(
            mode="manual", auth_token="test-token", identity_id="test-identity"
        )
        mock_service.run.assert_called_once()

    @patch("src.main.parse_args")
    @patch("src.main.configure_logging")
    def test_main_missing_required_args_manual_mode(
        self, mock_configure_logging, mock_parse_args
    ):
        """Test main function with missing required arguments in manual mode."""
        mock_args = Mock()
        mock_args.mode = "manual"
        mock_args.config = None
        mock_args.log_level = "INFO"
        mock_args.data_dir = None  # Missing required arg
        mock_args.service_id = "test-service"
        mock_args.ingress_server_url = "https://test.example.com"
        mock_args.ingress_server_auth_token = "test-token"
        mock_args.identity_id = "test-identity"
        mock_parse_args.return_value = mock_args

        result = main()

        assert result == 1  # Error exit code

    @patch("src.main.parse_args")
    @patch("src.main.configure_logging")
    @patch("src.main.get_auth_credentials")
    def test_main_authentication_error(
        self, mock_get_auth, mock_configure_logging, mock_parse_args
    ):
        """Test main function with authentication error."""
        mock_args = Mock()
        mock_args.mode = "openshift"
        mock_args.config = None
        mock_args.log_level = "INFO"
        mock_args.data_dir = Path("/test-data")
        mock_args.service_id = "test-service"
        mock_args.ingress_server_url = "https://test.example.com"
        mock_args.ingress_server_auth_token = None
        mock_args.identity_id = None
        mock_parse_args.return_value = mock_args

        from src.auth import AuthenticationError

        mock_get_auth.side_effect = AuthenticationError("Auth failed")

        result = main()

        assert result == 1  # Error exit code

    @patch("src.main.parse_args")
    @patch("src.main.configure_logging")
    @patch("src.main.get_auth_credentials")
    @patch("src.main.DataCollectorService")
    def test_main_keyboard_interrupt(
        self, mock_service_class, mock_get_auth, mock_configure_logging, mock_parse_args
    ):
        """Test main function handles KeyboardInterrupt gracefully."""
        mock_args = Mock()
        mock_args.mode = "manual"
        mock_args.config = None
        mock_args.log_level = "INFO"
        mock_args.data_dir = Path("/test-data")
        mock_args.service_id = "test-service"
        mock_args.ingress_server_url = "https://test.example.com"
        mock_args.ingress_server_auth_token = "test-token"
        mock_args.identity_id = "test-identity"
        mock_args.collection_interval = None
        mock_args.ingress_connection_timeout = None
        mock_args.no_cleanup = False
        mock_parse_args.return_value = mock_args

        mock_get_auth.return_value = ("test-token", "test-identity")

        mock_service = Mock()
        mock_service.run.side_effect = KeyboardInterrupt()
        mock_service_class.return_value = mock_service

        result = main()

        assert result == 0  # Graceful exit

    @patch("src.main.parse_args")
    @patch("src.main.configure_logging")
    @patch("src.main.get_auth_credentials")
    @patch("src.main.DataCollectorService")
    def test_main_unexpected_exception(
        self, mock_service_class, mock_get_auth, mock_configure_logging, mock_parse_args
    ):
        """Test main function handles unexpected exceptions."""
        mock_args = Mock()
        mock_args.mode = "manual"
        mock_args.config = None
        mock_args.log_level = "INFO"
        mock_args.data_dir = Path("/test-data")
        mock_args.service_id = "test-service"
        mock_args.ingress_server_url = "https://test.example.com"
        mock_args.ingress_server_auth_token = "test-token"
        mock_args.identity_id = "test-identity"
        mock_args.collection_interval = None
        mock_args.ingress_connection_timeout = None
        mock_args.no_cleanup = False
        mock_parse_args.return_value = mock_args

        mock_get_auth.return_value = ("test-token", "test-identity")

        mock_service = Mock()
        mock_service.run.side_effect = Exception("Unexpected error")
        mock_service_class.return_value = mock_service

        result = main()

        assert result == 1  # Error exit code
