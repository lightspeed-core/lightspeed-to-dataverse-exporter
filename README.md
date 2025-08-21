# Lightspeed to Dataverse Exporter

A service that exports Lightspeed data to Dataverse for analysis and storage. It periodically scans for JSON data files, packages them, and sends them to the Red Hat.

## Quick Start

### Installation

```bash
# Install dependencies
uv sync
```

### Configuration

You can either use `config.yaml` or provide values as command-line arguments.
When both are provided, command-line arguments take precedence over config.yaml values.

**Option 1: Using config.yaml**

Create a `config.yaml` file. See example: [config.yaml.example](config.yaml.example)

```yaml
data_dir: "/path/to/data"
service_id: "your-service-id"
ingress_server_url: "https://console.redhat.com/api/ingress/v1/upload"
collection_interval: 3600  # 1 hour (set to 0 for single-shot mode)
cleanup_after_send: true
```

**Option 2: Using command-line arguments only**

```bash
uv run python -m src.main \
  --data-dir /path/to/data \
  --service-id <your-service-id> \
  --ingress-server-url "https://console.redhat.com/api/ingress/v1/upload" \
  --collection-interval 3600 \
  --mode manual \
  --ingress-server-auth-token your-token \
  --identity-id your-identity
```

**Option 3: Combining both (args override config)**

```bash
# config.yaml has most settings, but override specific values
uv run python -m src.main \
  --config config.yaml \
  --log-level DEBUG \
  --collection-interval 60  # Override the config.yaml value
```

### Usage

The service supports two authentication modes and two execution modes:

## Execution Modes

**Continuous Mode** (default):
- Runs indefinitely, collecting data at regular intervals
- Set `collection_interval` to a positive number of seconds
- Suitable for daemon-style deployments
- Supports graceful shutdown (SIGTERM) with final data collection
- Responds immediately to user interrupts (Ctrl+C) without final collection

**Single-Shot Mode**:
- Performs one data collection cycle and exits
- Set `collection_interval: 0` to enable
- Ideal for Kubernetes Jobs/CronJobs or scheduled batch processing
- On error, exits with non-zero code allowing external retry logic

## Authentication Modes

The service supports two authentication modes depending on your deployment environment:

**OpenShift Mode** (recommended for cluster deployments):
```bash
uv run python -m src.main --mode openshift --config config.yaml
```
- Automatically retrieves auth token from cluster pull-secret
- Gets identity ID (cluster ID) from cluster version
- No manual token management required

**SSO Mode** (useful when cluster pull-secrets are not available or appropriate):
```bash
uv run python -m src.main --mode sso --config config.yaml --client-id my-client-id --client-secret my-client-secret
```
- Automatically retrieves auth token from cluster api endpoints using SSO credentials
- Gets identity ID from SSO token `preferred_username` or `sub` field (can also be manually provided)
- Client ID/Secret can also be provided as envvars `CLIENT_ID` and `CLIENT_SECRET`
- You can use sso.stage.redhat.com by setting the USE_SSO_STAGE envvar to any value.


**Manual Mode** (for local testing or non-OpenShift environments):
```bash
uv run python -m src.main --mode manual --config config.yaml \
  --ingress-server-auth-token YOUR_TOKEN \
  --identity-id YOUR_IDENTITY
```
- Requires explicit credentials
- The auth token can either be specified as a command arg as above or via the envvar `INGRESS_SERVER_AUTH_TOKEN`.
- Use `scripts/ingress_token_from_offline_token.py` to generate tokens for stage testing

### Common Options

```bash
# Run with debug logging
uv run python -m src.main --config config.yaml --log-level DEBUG

# Run in single-shot mode (exit after one collection cycle)
uv run python -m src.main --config config.yaml --collection-interval 0

# Keep files after sending (useful for testing)
uv run python -m src.main --config config.yaml --no-cleanup
```

## Data Format

The service scans for JSON files in these subdirectories under your configured `data_dir`:

- `feedback/` - User feedback data
- `transcripts/` - Conversation transcripts

Example structure:
```
data/
├── feedback/
│   ├── feedback1.json
│   └── feedback2.json
└── transcripts/
    ├── conversation1.json
    └── conversation2.json
```

**Note:** Files in other directories are ignored. The service recursively scans for `*.json` files only.

## Container Usage

```bash
# Build container locally
make build

# Run with mounted config and data
podman run --rm \
  -v ./config.yaml:/config/config.yaml \
  -v ./data:/data \
  lightspeed-exporter --config /config/config.yaml
```

For detailed deployment options see [DEPLOYMENT.md](DEPLOYMENT.md).

## Documentation

- **[ONBOARDING.md](ONBOARDING.md)** - Complete setup and testing guide
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System architecture and service logic flow  
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - Development workflow and local setup
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Kubernetes/OpenShift deployment patterns (Jobs, CronJobs, Sidecars)

