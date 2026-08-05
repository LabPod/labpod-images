# LabPod PyTorch Demo composite image (public, pull-only).
#
# Built and pushed to ghcr.io/labpod/pytorch-demo:<tag> by
# .github/workflows/images.yml. Backs LabPod's
# "PyTorch Demo Workspace" template: a kitchen-sink showcase with
# JupyterLab, TensorBoard, code-server, ttyd terminal, MLflow, and Aim.
# No baked USER (runs as the workspace owner under rootless Podman),
# WORKDIR /work.
#
# The demo notebooks are NOT baked into the image — LabPod seeds them into
# /work/labpod-demo on first Start of the tmpl-pytorch-demo template
# (embedded in the labpod binary), so this Dockerfile has no COPY.
#
# One Dockerfile builds every tag; the base + torch wheel index are supplied
# per tag by the build matrix:
#   cpu   -> Ubuntu 24.04 base, torch cpu wheels (runs on ANY host, no driver)
#   cu121 -> CUDA 12.1 / Ubuntu 22.04 base, torch cu121 wheels (sm_50--sm_90)
#   cu126 -> CUDA 12.6 / Ubuntu 24.04 base, torch cu126 wheels (sm_50--sm_90)
#   cu129 -> CUDA 12.9 / Ubuntu 24.04 base, torch cu129 wheels (sm_70--sm_120)
# torch cu128/cu129 wheels dropped pre-Volta support; those tags need sm_70+.
ARG CUDA_BASE_IMAGE=docker.io/ubuntu:24.04
FROM ${CUDA_BASE_IMAGE}

LABEL org.opencontainers.image.description="LabPod PyTorch Demo workspace image with JupyterLab, TensorBoard, code-server, terminal, MLflow, and Aim."

ENV DEBIAN_FRONTEND=noninteractive \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:${PATH}"
ARG TORCH_CUDA=cpu
ARG TORCH_VERSION=2.8.0
ARG TORCHVISION_VERSION=0.23.0
ARG CODE_SERVER_VERSION=4.118.0
ARG CODE_SERVER_SHA256_AMD64=fe2988f313c9047c1e1ccccee10ad8ccf2813b66a02c146e7d4fd2a3f7e2dc81
ARG CODE_SERVER_SHA256_ARM64=81fa5486a674428507cfb68025764646bdb99c345b8ca798fd94a13ea056eeb3

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        htop \
        iproute2 \
        jq \
        less \
        nano \
        openssh-client \
        python3 \
        python3-venv \
        rsync \
        tmux \
        tree \
        ttyd \
        unzip \
        vim \
        wget \
    && (apt-get install -y --no-install-recommends btop || true) \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv "$VIRTUAL_ENV" \
    && python3 -m pip install --no-cache-dir uv \
    && uv --version

# PyTorch pinned to the matching wheel index (cpu or cu<xx>) so the bundled
# CUDA libs track the image's base instead of floating with PyPI defaults.
RUN uv pip install --no-cache \
        --index-url "https://download.pytorch.org/whl/${TORCH_CUDA}" \
        "torch==${TORCH_VERSION}" \
        "torchvision==${TORCHVISION_VERSION}"

RUN uv pip install --no-cache \
        jupyterlab \
        ipywidgets \
        jupyter-resource-usage \
        tensorboard \
        mlflow \
        aim \
        numpy \
        pandas \
        matplotlib \
        scikit-learn

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

# Build-time contract checks run for every CPU/CUDA matrix entry. Published
# image smoke tests additionally probe JupyterLab, TensorBoard, code-server,
# and ttyd over HTTP.
RUN PYTHONDONTWRITEBYTECODE=1 python3 -c \
      'import aim, mlflow, torch, torchvision; x=torch.tensor([1.0, 2.0]); assert torch.dot(x, x).item() == 5.0' \
    && jupyter lab --version \
    && tensorboard --version \
    && code-server --version \
    && ttyd --version

WORKDIR /work
EXPOSE 8888 6006 8080 7681 5000 43800

# Stay-alive composite: launchers start on demand via `podman exec`.
# Zombie reaping is handled by catatonit from LabPod's `podman run --init`,
# so the image doesn't bundle its own init.
ENTRYPOINT ["sleep", "infinity"]
