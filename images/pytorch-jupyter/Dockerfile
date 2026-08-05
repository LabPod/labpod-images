# LabPod PyTorch + JupyterLab composite image (public, pull-only).
#
# Built and pushed to ghcr.io/labpod/pytorch-jupyter:<cuda-tag> by
# .github/workflows/images.yml. Replaces the upstream
# jovyan-based quay.io/jupyter/pytorch-notebook for LabPod's default
# "PyTorch JupyterLab" template: no baked USER (runs as the workspace
# owner under rootless Podman), no /home/jovyan remnants, WORKDIR /work.
# code-server ships alongside JupyterLab so the workspace has a browser
# editor without a second image; LabPod starts it on demand like the others.
#
# CUDA/torch pairing is supplied per tag by the build matrix:
#   cu121 -> CUDA 12.1 / Ubuntu 22.04 base, torch cu121 wheels (sm_50--sm_90)
#   cu126 -> CUDA 12.6 / Ubuntu 24.04 base, torch cu126 wheels (sm_50--sm_90)
#   cu129 -> CUDA 12.9 / Ubuntu 24.04 base, torch cu129 wheels (sm_70--sm_120)
# torch cu128/cu129 wheels dropped pre-Volta support; those tags need sm_70+.
# Verify the torch/torchvision pins against the wheel index the first CI
# run (older tags cap out at older torch: cu121 -> torch 2.5.1).
ARG CUDA_BASE_IMAGE=docker.io/nvidia/cuda:12.6.3-runtime-ubuntu24.04
FROM ${CUDA_BASE_IMAGE}

LABEL org.opencontainers.image.description="LabPod PyTorch + JupyterLab workspace image with CUDA, TensorBoard, code-server, and common scientific Python tools."

ENV DEBIAN_FRONTEND=noninteractive \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:${PATH}"
ARG TORCH_CUDA=cu126
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
        unzip \
        vim \
        wget \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv "$VIRTUAL_ENV" \
    && python3 -m pip install --no-cache-dir uv \
    && uv --version

# PyTorch pinned to the matching wheel index so the bundled CUDA libs
# track the image's CUDA base instead of floating with PyPI defaults.
RUN uv pip install --no-cache \
        --index-url "https://download.pytorch.org/whl/${TORCH_CUDA}" \
        "torch==${TORCH_VERSION}" \
        "torchvision==${TORCHVISION_VERSION}"

RUN uv pip install --no-cache \
        jupyterlab \
        ipywidgets \
        jupyter-resource-usage \
        tensorboard \
        numpy \
        pandas \
        scikit-learn \
        matplotlib

# code-server (browser VS Code) so the workspace has a real editor next to
# JupyterLab. The .deb bundles its own Node, so it is independent of
# /opt/venv. Pinned + sha256-verified; scripts/bump-image-pins.py rewrites
# the version and both digests across every image that carries this block.
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

# Build-time contract checks run on pull requests without requiring a GPU.
# Published-image smoke tests additionally probe every launcher over HTTP.
RUN PYTHONDONTWRITEBYTECODE=1 python3 -c \
      'import torch, torchvision; x=torch.tensor([1.0, 2.0]); assert torch.dot(x, x).item() == 5.0' \
    && jupyter lab --version \
    && tensorboard --version \
    && code-server --version

WORKDIR /work
EXPOSE 8888 6006 8080

# Stay-alive composite: LabPod starts JupyterLab / TensorBoard / code-server on demand
# via `podman exec`, so PID 1 just stays alive. LabPod runs every
# workspace with `podman run --init`, so zombie reaping is handled by
# catatonit injected at runtime — the image doesn't bundle its own init.
ENTRYPOINT ["sleep", "infinity"]
