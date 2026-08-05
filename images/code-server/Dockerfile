# LabPod code-server workspace image (public, pull-only).
#
# Built and pushed to ghcr.io/labpod/code-server:latest by
# .github/workflows/images.yml. This is LabPod's managed
# Code Server template image, not coder/code-server:latest.
FROM docker.io/ubuntu:24.04

LABEL org.opencontainers.image.description="LabPod code-server workspace image that runs as the workspace owner."

ENV DEBIAN_FRONTEND=noninteractive

ARG CODE_SERVER_VERSION=4.118.0
ARG CODE_SERVER_SHA256_AMD64=fe2988f313c9047c1e1ccccee10ad8ccf2813b66a02c146e7d4fd2a3f7e2dc81
ARG CODE_SERVER_SHA256_ARM64=81fa5486a674428507cfb68025764646bdb99c345b8ca798fd94a13ea056eeb3

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

# The .deb bundles Node. Pin the version and both published architecture
# digests; scripts/bump-image-pins.py keeps this in sync with the composites.
RUN arch="$(dpkg --print-architecture)" \
    && case "$arch" in \
        amd64) code_server_sha256="$CODE_SERVER_SHA256_AMD64" ;; \
        arm64) code_server_sha256="$CODE_SERVER_SHA256_ARM64" ;; \
        *) echo "unsupported architecture: $arch" >&2; exit 1 ;; \
    esac \
    && code_server_deb="code-server_${CODE_SERVER_VERSION}_${arch}.deb" \
    && code_server_url="https://github.com/coder/code-server/releases/download/v${CODE_SERVER_VERSION}/${code_server_deb}" \
    && curl -fsSL "$code_server_url" -o "/tmp/${code_server_deb}" \
    && echo "${code_server_sha256}  /tmp/${code_server_deb}" | sha256sum -c - \
    && apt-get update \
    && apt-get install -y --no-install-recommends "/tmp/${code_server_deb}" \
    && rm -f "/tmp/${code_server_deb}" \
    && rm -rf /var/lib/apt/lists/*

# Build-time contract check. Published-image smoke tests additionally start the
# default process and probe code-server over HTTP.
RUN code-server --version

WORKDIR /work
EXPOSE 8080

# LabPod starts code-server on demand through podman exec.
ENTRYPOINT ["sleep", "infinity"]
