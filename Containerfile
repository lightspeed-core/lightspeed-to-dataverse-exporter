FROM registry.access.redhat.com/ubi9/ubi-minimal:latest AS builder

ARG APP_ROOT=/app-root

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONCOERCECLOCALE=0 \
    PYTHONUTF8=1 \
    PYTHONIOENCODING=UTF-8 \
    LANG=en_US.UTF-8 \
    PIP_NO_CACHE_DIR=off

WORKDIR /app-root

USER root
# Install build dependencies (rust, cargo, python3.12-devel for any compiled wheels)
RUN microdnf install -y --nodocs --setopt=keepcache=0 --setopt=tsflags=nodocs rust cargo python3.12 python3.12-devel python3.12-pip

# Add explicit files and directories
COPY src ./src
COPY pyproject.toml LICENSE README.md requirements.*.txt ./

# Install hermetic build dependency (no PIP_TARGET here to avoid conflict with Cachi2's --home)
RUN pip3.12 install --no-cache-dir hatchling==1.28.0

# Install runtime dependencies into a known location for copying to final image.
# Unset Cachi2 pip options (e.g. PIP_INSTALL_OPTIONS=--home) to avoid "Cannot set --home and --prefix together"
# when using --target; Konflux may prepend ". /cachi2/cachi2.env && " to this RUN.
RUN unset PIP_INSTALL_OPTIONS PIP_TARGET PIP_HOME PIP_PREFIX 2>/dev/null; \
    pip3.12 install --no-cache-dir --target /app-root/site-packages -r requirements.$(uname -m).txt

FROM registry.access.redhat.com/ubi9/ubi-minimal:latest

ARG APP_ROOT=/app-root
ARG NAME_LABEL=lightspeed-core/dataverse-exporter-rhel9
ARG CPE_LABEL=cpe:/a:redhat:lightspeed_core:0.4::el9

# PYTHONDONTWRITEBYTECODE 1 : disable the generation of .pyc
# PYTHONUNBUFFERED 1 : force the stdout and stderr streams to be unbuffered
# PYTHONCOERCECLOCALE 0, PYTHONUTF8 1 : skip legacy locales and use UTF-8 mode
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONCOERCECLOCALE=0 \
    PYTHONUTF8=1 \
    PYTHONIOENCODING=UTF-8 \
    LANG=en_US.UTF-8

WORKDIR /app-root

USER root
# Install only Python runtime (no -devel, no rust/cargo)
RUN microdnf install -y --nodocs --setopt=keepcache=0 --setopt=tsflags=nodocs python3.12 && \
    microdnf clean all

# Copy installed Python packages to distro Python's site-packages (UBI9 uses sys.prefix=/usr)
COPY --from=builder /app-root/site-packages /usr/lib64/python3.12/site-packages

# Copy application source
COPY --from=builder /app-root/src ./src

# This directory is checked by ecosystem-cert-preflight-checks task in Konflux
COPY --from=builder /app-root/LICENSE /licenses/LICENSE

LABEL vendor="Red Hat, Inc." \
    name="${NAME_LABEL}" \
    com.redhat.component="lightspeed-core-dataverse-exporter" \
    cpe="${CPE_LABEL}" \
    io.k8s.display-name="Lightspeed Dataverse Exporter" \
    summary="A service that exports Lightspeed data to Dataverse for analysis and storage." \
    description="A service that exports Lightspeed data to Dataverse for analysis and storage. It periodically scans for JSON data files, packages them, and sends them to the Red Hat." \
    io.k8s.description="A service that exports Lightspeed data to Dataverse for analysis and storage. It periodically scans for JSON data files, packages them, and sends them to the Red Hat." \
    io.openshift.tags="lightspeed-core,dataverse,lightspeed"

# no-root user is checked in Konflux
USER 1001

ENTRYPOINT ["python3.12", "-m", "src.main"]
