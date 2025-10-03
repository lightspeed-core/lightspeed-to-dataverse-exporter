FROM registry.access.redhat.com/ubi9/python-312-minimal AS builder

ARG APP_ROOT=/app-root

# PYTHONDONTWRITEBYTECODE 1 : disable the generation of .pyc
# PYTHONUNBUFFERED 1 : force the stdout and stderr streams to be unbuffered
# PYTHONCOERCECLOCALE 0, PYTHONUTF8 1 : skip legacy locales and use UTF-8 mode
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONCOERCECLOCALE=0 \
    PYTHONUTF8=1 \
    PYTHONIOENCODING=UTF-8 \
    LANG=en_US.UTF-8 \
    PIP_NO_CACHE_DIR=off

WORKDIR /app-root

# Add explicit files and directories
# (avoid accidental inclusion of local directories or env files or credentials)
COPY src ./src
COPY pyproject.toml LICENSE README.md requirements.txt ./

# Install dependencies
RUN pip3.12 install --no-cache-dir -r requirements.txt

LABEL vendor="Red Hat, Inc."

# no-root user is checked in Konflux
USER 1001

ENTRYPOINT ["python3.12", "-m", "src.main"]
