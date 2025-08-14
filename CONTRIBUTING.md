# Contributing to Lightspeed to Dataverse Exporter

Thank you for your interest in contributing to the Lightspeed to Dataverse Exporter project! This document provides information about our development workflow.

## Container Image Build Process

Our project uses automated GitHub Actions workflows to build and push container images to Quay.io registry. The build process varies depending on the type of change being made:

### Image Registry

All images are pushed to: `quay.io/lightspeed-core/lightspeed-to-dataverse-exporter`

### Build Triggers and Tagging Strategy

#### 1. Pull Request Builds (`.github/workflows/build_and_push_pr.yaml`)

**Trigger:** When a pull request is opened or updated

**Process:**
- Builds multi-architecture images (amd64, arm64) for validation
- Uses Buildah for container builds
- **Does NOT push to registry** (security best practice)
- Validates that the Containerfile builds successfully
- Ensures PR changes don't break the build process

**Security Note:** PR builds only validate the container build process and do not push images to the registry to prevent potential security risks from untrusted code.

#### 2. Main Branch Builds (`.github/workflows/build_and_push_main.yaml`)

**Trigger:** When code is pushed to the `main` branch (typically after PR merge)

**Tags:**
- `dev-latest` (latest stable development version)
- `dev-YYYYMMDD-<git-short-hash>` (timestamped development version)

**Image Locations:**
- `quay.io/lightspeed-core/lightspeed-to-dataverse-exporter:dev-latest`
- `quay.io/lightspeed-core/lightspeed-to-dataverse-exporter:dev-YYYYMMDD-<hash>`

#### 3. Release Builds (`.github/workflows/build_and_push_release.yaml`)

**Trigger:** When a git tag is pushed (any tag pattern)

**Tags:**
- `<tag-name>` (the actual git tag)
- `latest` (latest stable release)

**Image Locations:**
- `quay.io/lightspeed-core/lightspeed-to-dataverse-exporter:latest`
- `quay.io/lightspeed-core/lightspeed-to-dataverse-exporter:<tag-name>`

### Multi-Architecture Support

All builds support both `amd64` and `arm64` architectures.

## Development Workflow

1. **Feature Development:**
   - Create a feature branch from `main`
   - Make your changes
   - Open a pull request
   - PR build validates that the container builds successfully (no image is pushed)

2. **Testing:**
   - Build and test the container locally (see Local Development section below)
   - Ensure all tests pass and code quality checks succeed

3. **Merge to Main:**
   - After PR approval and merge
   - Main build creates `dev-latest` and timestamped development images

4. **Release:**
   - Create and push a git tag
   - Release build creates versioned and `latest` images

## Local Development

### Prerequisites

```bash
# Install dependencies
uv sync --group dev
```

### Running Locally

**Option 1: Direct Python execution**
```bash
# Create config from example
cp config.yaml.example config.yaml
# Edit config.yaml with your settings

# Run in single-shot mode
uv run python -m src.main --config config.yaml --collection-interval 0

# Run with debug logging
uv run python -m src.main --config config.yaml --log-level DEBUG
```

**Option 2: Container execution**
```bash
# Build the container image
make build

# Run the container locally (requires configuration)
# First, create a config file based on the example:
cp config.yaml.example config.yaml
# Edit config.yaml with your settings, then:
podman run --rm -v $(PWD):/config lightspeed-exporter --config /config/config.yaml
```

**Known Issue - WSL2/Podman Permission Error:** If you encounter permission errors when building with Podman (particularly in WSL2 environments), you can use Docker instead:

```bash
# Alternative build command using Docker
docker build -f Containerfile -t lightspeed-exporter .

# Alternative run command using Docker
docker run --rm -v $(PWD):/config lightspeed-exporter --config /config/config.yaml
```

This is a known issue with certain local environments and the UBI9 Python minimal base image. The GitHub Actions workflows use Buildah and work correctly in the CI environment.

### Authentication for Local Testing

**Manual Mode** (for local development):
```bash
uv run python -m src.main --mode manual --config config.yaml \
  --ingress-server-auth-token YOUR_TOKEN \
  --identity-id YOUR_IDENTITY
```

Use `scripts/ingress_token_from_offline_token.py` to generate tokens for stage testing:
```bash
python scripts/ingress_token_from_offline_token.py --offline-token <offline-token> --env stage
```

## Code Quality

Before contributing, ensure your code meets our quality standards:

```bash
# Install development dependencies
make install-dev

# Run all quality checks and tests
make check

# Individual commands:
make format  # Format code
make lint    # Run linting
make test    # Run tests
make test-cov # Run tests with coverage
```

## Questions?

If you have questions about the build process or contributing guidelines, please open an issue or reach out to the maintainers.
