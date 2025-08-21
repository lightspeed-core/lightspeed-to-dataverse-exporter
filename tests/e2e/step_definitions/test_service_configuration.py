"""Step definitions for service configuration scenarios."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pytest_bdd import given, when, then, scenarios


# Helper functions
def extract_json_from_output(stdout):
    """Extract and parse JSON from command output."""
    lines = stdout.split("\n")
    json_lines = []
    in_json = False

    for line in lines:
        if line.strip().startswith("{"):
            in_json = True
        if in_json:
            json_lines.append(line)
        if in_json and line.strip().endswith("}"):
            break

    if json_lines:
        json_text = "\n".join(json_lines)
        return json.loads(json_text)
    return None


def assert_config_value(command_result, key, expected_value):
    """Assert that config output contains the expected key-value pair."""
    try:
        config_data = extract_json_from_output(command_result["stdout"])
        if config_data is None:
            pytest.fail(f"No JSON config found in stdout: {command_result['stdout']}")

        actual_value = str(config_data.get(key, ""))
        assert actual_value == expected_value, (
            f"Expected {key}='{expected_value}', got {key}='{actual_value}'. "
            f"Full config: {config_data}"
        )
    except json.JSONDecodeError as e:
        pytest.fail(
            f"Failed to parse JSON from output: {e}. stdout: {command_result['stdout']}"
        )


def assert_log_contains(command_result, expected_text):
    """Assert that log output contains the expected text."""
    combined_output = command_result["stdout"] + command_result["stderr"]
    assert expected_text in combined_output, (
        f"Expected text '{expected_text}' not found in output. "
        f"stdout: {command_result['stdout']}, stderr: {command_result['stderr']}"
    )


# Load scenarios from the feature file
scenarios("../features/service_configuration.feature")


@pytest.fixture
def main_py_path():
    """Get the path to main.py."""
    project_root = Path(__file__).parent.parent.parent.parent
    return project_root / "src" / "main.py"


@pytest.fixture
def fixtures_dir():
    """Get the path to test fixtures directory."""
    return Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def command_result():
    """Store the result of running a command."""
    return {}


@pytest.fixture
def env_vars():
    """Store environment variables for the test."""
    return {}


@pytest.fixture
def command_args():
    """Store command arguments being built."""
    return []


@pytest.fixture
def temp_config_file():
    """Store temporary config file path and clean up after test."""
    temp_file_data = {}
    yield temp_file_data

    # Cleanup: remove temporary file if it was created
    if "path" in temp_file_data:
        import os

        try:
            os.unlink(temp_file_data["path"])
        except FileNotFoundError:
            pass  # File already deleted, no problem


# Given steps
@given('I set environment variable "{var_name}" to "{var_value}"')
def set_environment_variable(env_vars, var_name, var_value):
    """Set an environment variable for the test."""
    env_vars[var_name] = var_value


# Specific step definition for environment variable pattern with nested quotes
@given('I set environment variable "INGRESS_SERVER_AUTH_TOKEN" to "from-env"')
def set_ingress_auth_token_env(env_vars):
    """Set INGRESS_SERVER_AUTH_TOKEN environment variable to from-env."""
    env_vars["INGRESS_SERVER_AUTH_TOKEN"] = "from-env"


@given("I have a config file with content:")
def create_temp_config_file(temp_config_file, docstring):
    """Create a temporary config file with the given content."""
    import tempfile

    # Create a temporary file
    temp_file = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    temp_file.write(docstring)
    temp_file.close()

    # Store the path for cleanup and use
    temp_config_file["path"] = temp_file.name


# When steps
@when("I run main.py without any config or arguments")
def run_main_without_config(main_py_path, command_args, command_result):
    """Run main.py without any config or arguments (execute immediately since no flag needed)."""
    try:
        result = subprocess.run(
            [sys.executable, str(main_py_path)],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=main_py_path.parent.parent,
        )
        command_result["returncode"] = result.returncode
        command_result["stdout"] = result.stdout
        command_result["stderr"] = result.stderr
    except subprocess.TimeoutExpired:
        pytest.fail("Command timed out")
    except Exception as e:
        pytest.fail(f"Failed to run command: {e}")


@when('I run main.py with config file "{config_file}"')
def run_main_with_config_file(main_py_path, fixtures_dir, command_args, config_file):
    """Set up command to run main.py with a config file."""
    config_path = fixtures_dir / config_file
    command_args.clear()
    command_args.extend(
        [sys.executable, str(main_py_path), "--config", str(config_path)]
    )


@when("I run main.py with this config file")
def run_main_with_temp_config_file(main_py_path, temp_config_file, command_args):
    """Set up command to run main.py with the temporary config file."""
    config_path = temp_config_file["path"]
    command_args.clear()
    command_args.extend([sys.executable, str(main_py_path), "--config", config_path])


@when('I run main.py with config file "{config_file}" and args "{args}"')
def run_main_with_config_and_args(
    main_py_path, fixtures_dir, command_args, config_file, args
):
    """Set up command to run main.py with a config file and additional arguments."""
    config_path = fixtures_dir / config_file
    args_list = args.split() if args else []

    command_args.clear()
    command_args.extend(
        [sys.executable, str(main_py_path), "--config", str(config_path)]
    )
    command_args.extend(args_list)


# Specific step definitions for config file patterns with nested quotes
@when('I run main.py with config file "fixtures/valid_complete.yaml"')
def run_main_with_valid_complete_config(main_py_path, fixtures_dir, command_args):
    """Build command with valid complete config file."""
    config_path = fixtures_dir / "valid_complete.yaml"
    command_args.clear()
    command_args.extend(
        [sys.executable, str(main_py_path), "--config", str(config_path)]
    )


@when(
    'I run main.py with config file "fixtures/for_override.yaml" and args "--service-id from-cli"'
)
def run_main_with_override_config_and_args(main_py_path, fixtures_dir, command_args):
    """Build command with override config and CLI args."""
    config_path = fixtures_dir / "for_override.yaml"
    command_args.clear()
    command_args.extend(
        [
            sys.executable,
            str(main_py_path),
            "--config",
            str(config_path),
            "--service-id",
            "from-cli",
        ]
    )


@when('I run main.py with config file "fixtures/nonexistent.yaml"')
def run_main_with_nonexistent_config(main_py_path, fixtures_dir, command_args):
    """Build command with nonexistent config file."""
    config_path = fixtures_dir / "nonexistent.yaml"
    command_args.clear()
    command_args.extend(
        [sys.executable, str(main_py_path), "--config", str(config_path)]
    )


@when('I run main.py with config file "fixtures/for_override.yaml"')
def run_main_with_override_config(main_py_path, fixtures_dir, command_args):
    """Build command with override config file."""
    config_path = fixtures_dir / "for_override.yaml"
    command_args.clear()
    command_args.extend(
        [sys.executable, str(main_py_path), "--config", str(config_path)]
    )


@when('I run main.py with args "{args}"')
def run_main_with_args(main_py_path, command_args, args):
    """Set up command to run main.py with only command line arguments."""
    args_list = args.split() if args else []

    command_args.clear()
    command_args.extend([sys.executable, str(main_py_path)])
    command_args.extend(args_list)


# Specific step definitions for args patterns with nested quotes
@when(
    'I run main.py with args "--mode manual --data-dir /tmp/test-data --service-id test --ingress-server-url https://test.com"'
)
def run_main_with_manual_mode_args(main_py_path, command_args):
    """Build command for manual mode missing auth fields."""
    args = [
        "--mode",
        "manual",
        "--data-dir",
        "/tmp/test-data",
        "--service-id",
        "test",
        "--ingress-server-url",
        "https://test.com",
    ]
    command_args.clear()
    command_args.extend([sys.executable, str(main_py_path)])
    command_args.extend(args)


@when(
    'I run main.py with args "--mode openshift --data-dir /tmp/test-data --service-id test --ingress-server-url https://test.com --ingress-server-auth-token manual-token --identity-id manual-id"'
)
def run_main_with_openshift_mode_args(main_py_path, command_args):
    """Build command for openshift mode with manual auth fields."""
    args = [
        "--mode",
        "openshift",
        "--data-dir",
        "/tmp/test-data",
        "--service-id",
        "test",
        "--ingress-server-url",
        "https://test.com",
        "--ingress-server-auth-token",
        "manual-token",
        "--identity-id",
        "manual-id",
    ]
    command_args.clear()
    command_args.extend([sys.executable, str(main_py_path)])
    command_args.extend(args)


@when("I use the print-config-and-exit flag")
def add_print_config_and_exit_flag(
    main_py_path, command_args, command_result, env_vars
):
    """Add the print-config-and-exit flag and execute the command."""
    # Add the flag to the command
    command_args.append("--print-config-and-exit")

    # Prepare environment
    env = os.environ.copy()
    env.update(env_vars)

    # Execute the command
    try:
        result = subprocess.run(
            command_args,
            capture_output=True,
            text=True,
            timeout=10,
            cwd=main_py_path.parent.parent,
            env=env,
        )
        command_result["returncode"] = result.returncode
        command_result["stdout"] = result.stdout
        command_result["stderr"] = result.stderr
    except subprocess.TimeoutExpired:
        pytest.fail("Command timed out")
    except Exception as e:
        pytest.fail(f"Failed to run command: {e}")


# Then steps
@then("the exit code must be 0")
def check_exit_code_is_zero(command_result):
    """Check that the exit code is 0."""
    assert command_result["returncode"] == 0, (
        f"Expected exit code 0, got {command_result['returncode']}. "
        f"stdout: {command_result['stdout']}, stderr: {command_result['stderr']}"
    )


@then("the exit code must be 1")
def check_exit_code_is_one(command_result):
    """Check that the exit code is 1."""
    assert command_result["returncode"] == 1, (
        f"Expected exit code 1, got {command_result['returncode']}. "
        f"stdout: {command_result['stdout']}, stderr: {command_result['stderr']}"
    )


@then('the log must contain: "YAML parsing error"')
def check_log_contains_yaml_error(command_result):
    """Check that the log contains a YAML parsing error."""
    combined_output = command_result["stdout"] + command_result["stderr"]
    yaml_error_indicators = ["yaml", "YAML", "parsing", "syntax", "scanner", "parser"]

    found_yaml_error = any(
        indicator in combined_output for indicator in yaml_error_indicators
    )
    assert found_yaml_error, (
        f"Expected YAML parsing error in output. "
        f"stdout: {command_result['stdout']}, stderr: {command_result['stderr']}"
    )


@then('the log must contain: "file not found error"')
def check_log_contains_file_not_found(command_result):
    """Check that the log contains a file not found error."""
    combined_output = command_result["stdout"] + command_result["stderr"]
    file_error_indicators = [
        "No such file",
        "not found",
        "FileNotFoundError",
        "does not exist",
    ]

    found_file_error = any(
        indicator in combined_output for indicator in file_error_indicators
    )
    assert found_file_error, (
        f"Expected file not found error in output. "
        f"stdout: {command_result['stdout']}, stderr: {command_result['stderr']}"
    )


# Generic log checking step
@then('the log must contain: "{expected_text}"')
def check_log_contains_text(command_result, expected_text):
    """Check that the log contains the expected text."""
    assert_log_contains(command_result, expected_text)


# Specific steps for patterns with nested quotes (pytest-bdd requirement)
@then(
    'the log must contain: "Either provide --config with a YAML file or all required arguments"'
)
def check_log_contains_config_message(command_result):
    assert_log_contains(
        command_result,
        "Either provide --config with a YAML file or all required arguments",
    )


@then('the log must contain: "Missing required configuration"')
def check_log_contains_missing_config(command_result):
    assert_log_contains(command_result, "Missing required configuration")


@then('the log must contain: "data-dir"')
def check_log_contains_data_dir(command_result):
    assert_log_contains(command_result, "data-dir")


@then('the log must contain: "ingress-server-auth-token"')
def check_log_contains_auth_token(command_result):
    assert_log_contains(command_result, "ingress-server-auth-token")


@then('the log must contain: "identity-id"')
def check_log_contains_identity_id(command_result):
    assert_log_contains(command_result, "identity-id")


@then('the log must contain: "Printing resolved configuration"')
def check_log_contains_printing_config(command_result):
    assert_log_contains(command_result, "Printing resolved configuration")


@then('the log must contain: "Authentication failed"')
def check_log_contains_auth_failed(command_result):
    assert_log_contains(command_result, "Authentication failed")


# Generic config checking step
@then('the config output must contain: "{key}" with value "{expected_value}"')
def check_config_output_contains_key_value(command_result, key, expected_value):
    """Check that the config output contains a specific key-value pair."""
    assert_config_value(command_result, key, expected_value)


# Specific steps for patterns with nested quotes (pytest-bdd requirement)
@then('the config output must contain: "service_id" with value "test-service"')
def check_config_output_service_id_test_service(command_result):
    assert_config_value(command_result, "service_id", "test-service")


@then('the config output must contain: "data_dir" with value "/tmp/test-data"')
def check_config_output_data_dir(command_result):
    assert_config_value(command_result, "data_dir", "/tmp/test-data")


@then(
    'the config output must contain: "ingress_server_auth_token" with value "from-env"'
)
def check_config_output_auth_token_from_env(command_result):
    assert_config_value(command_result, "ingress_server_auth_token", "from-env")


@then('the config output must contain: "service_id" with value "from-cli"')
def check_config_output_service_id_from_cli(command_result):
    assert_config_value(command_result, "service_id", "from-cli")
