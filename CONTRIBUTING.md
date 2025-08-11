# Contributing to Lightspeed to Dataverse Exporter

Thank you for your interest in contributing to the Lightspeed to Dataverse Exporter project! This document provides information about our development workflow.

## Container Image Build Process

Our project uses automated GitHub Actions workflows to build and push container images to Quay.io registry. The build process varies depending on the type of change being made:

### Image Registry

All images are pushed to: `quay.io/lightspeed-core/lightspeed-to-dataverse-exporter`

### Build Triggers and Tagging Strategy

#### 1. Pull Request Builds (`.github/workflows/build_and_push_pr.yaml`)

**Trigger:** When a pull request is opened or updated

**Tags:**
- `pr-latest`

**Image Location:** `quay.io/lightspeed-core/lightspeed-to-dataverse-exporter:pr-latest`

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
   - PR build creates `pr-latest` image for testing

2. **Testing:**
   - Use the `pr-latest` image to test your changes
   - Ensure all tests pass and code quality checks succeed

3. **Merge to Main:**
   - After PR approval and merge
   - Main build creates `dev-latest` and timestamped development images

4. **Release:**
   - Create and push a git tag
   - Release build creates versioned and `latest` images

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
