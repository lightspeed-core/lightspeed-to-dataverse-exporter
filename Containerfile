FROM registry.access.redhat.com/ubi9/python-312 AS builder

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

USER root
# Install build dependencies
RUN dnf install -y --nodocs --setopt=keepcache=0 --setopt=tsflags=nodocs rust cargo

# Add explicit files and directories
# (avoid accidental inclusion of local directories or env files or credentials)
COPY src ./src
COPY pyproject.toml LICENSE README.md requirements.*.txt ./

# this directory is checked by ecosystem-cert-preflight-checks task in Konflux
COPY LICENSE /licenses/

# install hermetic dependencies
RUN pip3.12 install --no-cache-dir hatchling==1.28.0

# Install dependencies
RUN pip3.12 install --no-cache-dir -r requirements.$(uname -m).txt

LABEL vendor="Red Hat, Inc." \
    name="lightspeed-core/dataverse-exporter-rhel9" \
    com.redhat.component="lightspeed-core/dataverse-exporter" \
    cpe="cpe:/a:redhat:lightspeed_core:0.4::el9" \
    io.k8s.display-name="Lightspeed Dataverse Exporter" \
    summary="A service that exports Lightspeed data to Dataverse for analysis and storage." \
    description="A service that exports Lightspeed data to Dataverse for analysis and storage. It periodically scans for JSON data files, packages them, and sends them to the Red Hat." \
    io.k8s.description="A service that exports Lightspeed data to Dataverse for analysis and storage. It periodically scans for JSON data files, packages them, and sends them to the Red Hat." \
    io.openshift.tags="lightspeed-core,dataverse,lightspeed"

# no-root user is checked in Konflux
USER 1001

ENTRYPOINT ["python3.12", "-m", "src.main"]
