FROM registry.access.redhat.com/ubi9/python-312-minimal AS builder

ARG APP_ROOT=/app-root

# UV_PYTHON_DOWNLOADS=0 : Disable Python interpreter downloads and use the system interpreter.
ENV UV_COMPILE_BYTECODE=0 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

# Create app directory with proper permissions
USER root
RUN mkdir -p /app-root && chown -R 1001:1001 /app-root
USER 1001

WORKDIR /app-root

# Install uv package manager
RUN pip3.12 install uv

# Add explicit files and directories
# (avoid accidental inclusion of local directories or env files or credentials)
COPY src ./src
COPY pyproject.toml LICENSE README.md uv.lock ./

RUN uv sync --locked --no-dev

# Final image without uv package manager
FROM registry.access.redhat.com/ubi9/python-312-minimal
ARG APP_ROOT=/app-root
WORKDIR /app-root

# PYTHONDONTWRITEBYTECODE 1 : disable the generation of .pyc
# PYTHONUNBUFFERED 1 : force the stdout and stderr streams to be unbuffered
# PYTHONCOERCECLOCALE 0, PYTHONUTF8 1 : skip legacy locales and use UTF-8 mode
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONCOERCECLOCALE=0 \
    PYTHONUTF8=1 \
    PYTHONIOENCODING=UTF-8 \
    LANG=en_US.UTF-8

COPY --from=builder --chown=1001:1001 /app-root /app-root

# this directory is checked by ecosystem-cert-preflight-checks task in Konflux
COPY --from=builder /app-root/LICENSE /licenses/

# Add executables from .venv to system PATH
ENV PATH="/app-root/.venv/bin:$PATH"

LABEL vendor="Red Hat, Inc."

# no-root user is checked in Konflux
USER 1001

ENTRYPOINT ["python", "-m", "src.main"]
