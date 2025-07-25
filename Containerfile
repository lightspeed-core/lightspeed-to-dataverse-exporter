# Use official uv image with Python 3.12
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Set working directory
WORKDIR /app

# Copy project files for dependency resolution
COPY pyproject.toml uv.lock ./

# Install dependencies first (better caching)
RUN uv sync --locked --no-dev --no-install-project

# Copy source code
COPY README.md ./
COPY src/ ./src/

# Install the project itself
RUN uv sync --locked --no-dev

# Use the virtual environment directly instead of uv run
ENV PATH="/app/.venv/bin:$PATH"
