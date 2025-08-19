"""Tests for src.main module."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, mock_open

from src.main import parse_args, main, configure_logging
from src.settings import DataCollectorSettings


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
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data="data_dir: /tmp\nservice_id: config-service\ningress_server_url: https://config.example.com\nidentity_id: config-identity\ncollection_interval: 300\ningress_connection_timeout: 30\ncleanup_after_send: true",
    )
    @patch("src.main.OpenShiftAuthProvider")
    @patch("src.main.DataCollectorService")
    def test_main_with_config_file_openshift_mode(
        self,
        mock_service_class,
        mock_auth_provider,
        mock_open_file,
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
        mock_args.allowed_subdirs = None
        mock_args.retry_interval = None
        mock_parse_args.return_value = mock_args

        mock_provider = Mock()
        mock_auth_provider.return_value = mock_provider
        mock_provider.get_credentials.return_value = (
            "openshift-token",
            "openshift-identity",
        )

        mock_service = Mock()
        mock_service_class.return_value = mock_service

        result = main()

        assert result == 0
        mock_configure_logging.assert_called_once_with("INFO", mock_args.rich_logs)
        mock_open_file.assert_called_once_with(
            Path("/config.yaml"), "r", encoding="utf-8"
        )
        mock_provider.get_credentials.assert_called_once()
        mock_service.run.assert_called_once()

        # Verify DataCollectorService was called with DataCollectorSettings
        mock_service_class.assert_called_once()
        created_settings = mock_service_class.call_args[0][0]
        assert isinstance(created_settings, DataCollectorSettings)
        assert created_settings.data_dir == Path("/tmp")
        assert created_settings.service_id == "config-service"
        assert created_settings.ingress_server_url == "https://config.example.com"

    @patch("src.main.parse_args")
    @patch("src.main.configure_logging")
    @patch("src.main.DataCollectorService")
    def test_main_without_config_manual_mode(
        self, mock_service_class, mock_configure_logging, mock_parse_args
    ):
        """Test main function without config file in manual mode."""
        # Setup mocks
        mock_args = Mock()
        mock_args.mode = "manual"
        mock_args.config = None
        mock_args.log_level = "DEBUG"
        mock_args.data_dir = Path("/tmp")
        mock_args.service_id = "test-service"
        mock_args.ingress_server_url = "https://test.example.com"
        mock_args.ingress_server_auth_token = "test-token"
        mock_args.identity_id = "test-identity"
        mock_args.collection_interval = 600
        mock_args.ingress_connection_timeout = 60
        mock_args.no_cleanup = True
        mock_args.rich_logs = False
        mock_args.allowed_subdirs = None
        mock_args.retry_interval = None
        mock_parse_args.return_value = mock_args

        mock_service = Mock()
        mock_service_class.return_value = mock_service

        result = main()

        assert result == 0

        # Verify DataCollectorService was called with proper config
        mock_service_class.assert_called_once()
        created_settings = mock_service_class.call_args[0][0]
        assert isinstance(created_settings, DataCollectorSettings)
        mock_configure_logging.assert_called_once_with("DEBUG", mock_args.rich_logs)
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
        mock_args.collection_interval = None
        mock_args.ingress_connection_timeout = None
        mock_args.no_cleanup = False
        mock_args.rich_logs = False
        mock_args.allowed_subdirs = None
        mock_args.retry_interval = None
        mock_parse_args.return_value = mock_args

        code = main()

        assert code == 1

    @patch("src.main.parse_args")
    @patch("src.main.configure_logging")
    @patch("src.main.OpenShiftAuthProvider")
    def test_main_authentication_error(
        self, mock_auth_provider, mock_configure_logging, mock_parse_args
    ):
        """Test main function with authentication error."""
        mock_args = Mock()
        mock_args.mode = "openshift"
        mock_args.config = None
        mock_args.log_level = "INFO"
        mock_args.data_dir = Path("/tmp")
        mock_args.service_id = "test-service"
        mock_args.ingress_server_url = "https://test.example.com"
        mock_args.ingress_server_auth_token = None
        mock_args.identity_id = None
        mock_args.collection_interval = None
        mock_args.ingress_connection_timeout = None
        mock_args.no_cleanup = False
        mock_args.rich_logs = False
        mock_args.allowed_subdirs = None
        mock_args.retry_interval = None
        mock_parse_args.return_value = mock_args

        from src.auth.providers import AuthenticationError

        mock_auth_provider.get_credentials.side_effect = AuthenticationError(
            "Auth failed"
        )

        result = main()

        assert result == 1  # Error exit code

    @patch("src.main.parse_args")
    @patch("src.main.configure_logging")
    @patch("src.main.DataCollectorService")
    def test_main_keyboard_interrupt(
        self, mock_service_class, mock_configure_logging, mock_parse_args
    ):
        """Test main function handles KeyboardInterrupt gracefully."""
        mock_args = Mock()
        mock_args.mode = "manual"
        mock_args.config = None
        mock_args.log_level = "INFO"
        mock_args.data_dir = Path("/tmp")
        mock_args.service_id = "test-service"
        mock_args.ingress_server_url = "https://test.example.com"
        mock_args.ingress_server_auth_token = "test-token"
        mock_args.identity_id = "test-identity"
        mock_args.collection_interval = None
        mock_args.ingress_connection_timeout = None
        mock_args.no_cleanup = False
        mock_args.rich_logs = False
        mock_args.allowed_subdirs = None
        mock_args.retry_interval = None
        mock_parse_args.return_value = mock_args

        mock_service = Mock()
        mock_service.run.side_effect = KeyboardInterrupt()
        mock_service_class.return_value = mock_service

        result = main()

        assert result == 0  # Graceful exit

    @patch("src.main.parse_args")
    @patch("src.main.configure_logging")
    @patch("src.main.DataCollectorService")
    def test_main_unexpected_exception(
        self, mock_service_class, mock_configure_logging, mock_parse_args
    ):
        """Test main function handles unexpected exceptions."""
        mock_args = Mock()
        mock_args.mode = "manual"
        mock_args.config = None
        mock_args.log_level = "INFO"
        mock_args.data_dir = Path("/tmp")
        mock_args.service_id = "test-service"
        mock_args.ingress_server_url = "https://test.example.com"
        mock_args.ingress_server_auth_token = "test-token"
        mock_args.identity_id = "test-identity"
        mock_args.collection_interval = None
        mock_args.ingress_connection_timeout = None
        mock_args.no_cleanup = False
        mock_args.rich_logs = False
        mock_args.allowed_subdirs = None
        mock_args.retry_interval = None
        mock_parse_args.return_value = mock_args

        mock_service = Mock()
        mock_service.run.side_effect = Exception("Unexpected error")
        mock_service_class.return_value = mock_service

        result = main()

        assert result == 1  # Error exit code

    def _create_minimal_args(self, **overrides):
        """Helper to create minimal mock args with only required fields and test-specific overrides."""
        mock_args = Mock()
        # Required fields for manual mode
        mock_args.mode = "manual"
        mock_args.config = None
        mock_args.log_level = "INFO"
        mock_args.data_dir = Path("/tmp")
        mock_args.service_id = "test-service"
        mock_args.ingress_server_url = "https://test.example.com"
        mock_args.identity_id = "test-identity"
        # Minimal optional fields
        mock_args.ingress_server_auth_token = None
        mock_args.collection_interval = None
        mock_args.ingress_connection_timeout = None
        mock_args.no_cleanup = False
        mock_args.rich_logs = False
        mock_args.allowed_subdirs = None
        mock_args.retry_interval = None

        # Apply any test-specific overrides
        for key, value in overrides.items():
            setattr(mock_args, key, value)

        return mock_args

    @patch("src.main.parse_args")
    @patch("src.main.configure_logging")
    @patch("src.main.DataCollectorSettings")
    @patch("src.main.DataCollectorService")
    @patch.dict("os.environ", {"INGRESS_SERVER_AUTH_TOKEN": "env-token"})
    def test_main_ingress_token_precedence_cli_over_env(
        self,
        mock_service_class,
        mock_settings_class,
        mock_configure_logging,
        mock_parse_args,
    ):
        """Test that CLI arg takes precedence over environment variable for auth token."""
        mock_args = self._create_minimal_args(ingress_server_auth_token="cli-token")
        mock_parse_args.return_value = mock_args

        mock_service = Mock()
        mock_service_class.return_value = mock_service

        result = main()

        assert result == 0

        # Verify CLI token was passed to DataCollectorSettings, not env token
        mock_settings_class.assert_called_once()
        call_kwargs = mock_settings_class.call_args[1]
        assert call_kwargs["ingress_server_auth_token"] == "cli-token"

    @patch("src.main.parse_args")
    @patch("src.main.configure_logging")
    @patch("src.main.DataCollectorSettings")
    @patch("src.main.DataCollectorService")
    @patch.dict("os.environ", {"INGRESS_SERVER_AUTH_TOKEN": "env-token"})
    def test_main_ingress_token_precedence_env_fallback(
        self,
        mock_service_class,
        mock_settings_class,
        mock_configure_logging,
        mock_parse_args,
    ):
        """Test that environment variable is used when CLI arg not provided."""
        mock_args = (
            self._create_minimal_args()
        )  # ingress_server_auth_token defaults to None
        mock_parse_args.return_value = mock_args

        mock_service = Mock()
        mock_service_class.return_value = mock_service

        result = main()

        assert result == 0

        # Verify env token was passed to DataCollectorSettings
        mock_settings_class.assert_called_once()
        call_kwargs = mock_settings_class.call_args[1]
        assert call_kwargs["ingress_server_auth_token"] == "env-token"

    @patch("src.main.parse_args")
    @patch("src.main.configure_logging")
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data="data_dir: /tmp\nservice_id: config-service\ningress_server_url: https://config.example.com\ningress_server_auth_token: config-token\nidentity_id: config-identity\ncollection_interval: 300",
    )
    @patch("src.main.DataCollectorSettings")
    @patch("src.main.DataCollectorService")
    @patch.dict("os.environ", {"INGRESS_SERVER_AUTH_TOKEN": "env-token"})
    def test_main_ingress_token_precedence_env_over_config(
        self,
        mock_service_class,
        mock_settings_class,
        mock_open_file,
        mock_configure_logging,
        mock_parse_args,
    ):
        """Test that environment variable takes precedence over config file."""
        mock_args = self._create_minimal_args(
            config=Path("/config.yaml"),
            data_dir=None,  # Let config provide this
            service_id=None,  # Let config provide this
            ingress_server_url=None,  # Let config provide this
        )
        mock_parse_args.return_value = mock_args

        mock_service = Mock()
        mock_service_class.return_value = mock_service

        result = main()

        assert result == 0

        # Verify env token was passed to DataCollectorSettings, not config token
        mock_settings_class.assert_called_once()
        call_kwargs = mock_settings_class.call_args[1]
        assert call_kwargs["ingress_server_auth_token"] == "env-token"

    @patch("src.main.parse_args")
    @patch("src.main.configure_logging")
    @patch("src.main.DataCollectorService")
    @patch.dict("os.environ", {"INGRESS_SERVER_AUTH_TOKEN": "env-token"})
    def test_main_config_defaults(
        self,
        mock_service_class,
        mock_configure_logging,
        mock_parse_args,
    ):
        """Test that environment variable takes precedence over config file."""
        mock_args = Mock()
        # Required fields for manual mode
        mock_args.mode = "manual"
        mock_args.config = None
        mock_args.log_level = "INFO"
        mock_args.data_dir = Path("/tmp")
        mock_args.service_id = "test-service"
        mock_args.ingress_server_url = "https://test.example.com"
        # Minimal optional fields
        mock_args.identity_id = None
        mock_args.ingress_server_auth_token = "test-token"
        mock_args.collection_interval = None
        mock_args.ingress_connection_timeout = None
        mock_args.no_cleanup = False
        mock_args.rich_logs = False
        mock_args.allowed_subdirs = None
        mock_args.retry_interval = None
        mock_parse_args.return_value = mock_args

        mock_service = Mock()
        mock_service_class.return_value = mock_service

        result = main()

        assert result == 0

        mock_service_class.assert_called_once()
        settings = mock_service_class.call_args[0][0]

        # Check defaults
        assert settings.identity_id == "lightspeed-exporter"
        assert settings.collection_interval == 7200  # Default from constants
        assert settings.cleanup_after_send is True
        assert settings.ingress_connection_timeout == 30  # Default from constants
        assert settings.retry_interval == 300  # Default from constants
        assert settings.allowed_subdirs == []  # Default: collect everything
