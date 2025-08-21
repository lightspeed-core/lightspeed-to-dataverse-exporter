Feature: Service configuration and validation
  As a user of the lightspeed-to-dataverse-exporter
  I want comprehensive configuration handling
  So that I can properly configure the service and debug configuration issues

  # Basic configuration scenarios
  Scenario: Running without any configuration
    When I run main.py without any config or arguments
    Then the exit code must be 1
    And the log must contain: "Invalid config"
    And the log must contain: "data_dir: Input is not a valid path"
    And the log must contain: "service_id: Input should be a valid string (got None)"
    And the log must contain: "ingress_server_url: Input should be a valid string (got None)"
    And the log must contain: "ingress_server_auth_token: Input should be a valid string (got None)"

  Scenario: Valid config file with missing required fields
    Given I have a config file with content:
      """
      service_id: "test-service"
      # Missing required fields: data_dir, ingress_server_url, ingress_server_auth_token, identity_id
      collection_interval: 60
      cleanup_after_send: false
      """
    When I run main.py with this config file
    And I use the print-config-and-exit flag
    Then the exit code must be 1
    And the log must contain: "Invalid config"
    And the log must contain: "data_dir: Input is not a valid path"
    And the log must contain: "ingress_server_url: Input should be a valid string (got None)"
    And the log must contain: "ingress_server_auth_token: Input should be a valid string (got None)"

  Scenario: Manual mode missing auth fields
    When I run main.py with args "--mode manual --data-dir /tmp --service-id test --ingress-server-url https://test.com"
    And I use the print-config-and-exit flag
    Then the exit code must be 1
    And the log must contain: "Invalid config"
    And the log must contain: "ingress_server_auth_token: Input should be a valid string (got None)"

  # Configuration inspection scenarios
  Scenario: Valid complete config file inspection
    When I run main.py with config file "fixtures/valid_complete.yaml"
    And I use the print-config-and-exit flag
    Then the exit code must be 0
    And the log must contain: "Printing resolved configuration"
    And the config output must contain: "service_id" with value "test-service"
    And the config output must contain: "data_dir" with value "/tmp"

  Scenario: OpenShift mode with manual auth fields
    When I run main.py with args "--mode openshift --data-dir /tmp --service-id test --ingress-server-url https://test.com --ingress-server-auth-token manual-token --identity-id manual-id"
    And I use the print-config-and-exit flag
    Then the exit code must be 1
    And the log must contain: "Authentication failed"

  # Configuration precedence scenarios
  Scenario: CLI args override config file values
    When I run main.py with config file "fixtures/for_override.yaml" and args "--service-id from-cli"
    And I use the print-config-and-exit flag
    Then the exit code must be 0
    And the log must contain: "Printing resolved configuration"
    And the config output must contain: "service_id" with value "from-cli"
    And the config output must contain: "data_dir" with value "/tmp"

  Scenario: Environment variable precedence for auth token
    Given I set environment variable "INGRESS_SERVER_AUTH_TOKEN" to "from-env"
    When I run main.py with config file "fixtures/for_override.yaml"
    And I use the print-config-and-exit flag
    Then the exit code must be 0
    And the log must contain: "Printing resolved configuration"
    And the config output must contain: "ingress_server_auth_token" with value "from-env"

  # Configuration error handling scenarios
  Scenario: Invalid YAML config file
    Given I have a config file with content:
      """
      # Invalid YAML - missing closing bracket
      service_id: "test-service"
      data_dir: "/tmp/test-data"
      ingress_server_url: "https://test.example.com"
      nested:
        key: "value"
        invalid: [unclosed, list
      """
    When I run main.py with this config file
    And I use the print-config-and-exit flag
    Then the exit code must be 1
    And the log must contain: "ParserError"

  Scenario: Non-existent config file
    When I run main.py with config file "fixtures/nonexistent.yaml"
    And I use the print-config-and-exit flag
    Then the exit code must be 1
    And the log must contain: "FileNotFoundError"
