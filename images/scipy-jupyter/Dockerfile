# LabPod SciPy data-science + JupyterLab composite image (public, pull-only, CPU).
#
# Built and pushed to ghcr.io/labpod/scipy-jupyter:<tag> by
# .github/workflows/images.yml. Replaces the upstream
# jovyan-based quay.io/jupyter/scipy-notebook for LabPod's default
# "Data Science JupyterLab (CPU)" template: no baked USER (runs as the
# workspace owner under rootless Podman), no /home/jovyan remnants,
# WORKDIR /work.
#
# CPU-only: there is no CUDA base and no GPU stack. The tag names the
# Python line the scientific stack is built against:
#   py312 -> Python 3.12 (Ubuntu 24.04 base)
ARG BASE_IMAGE=docker.io/ubuntu:24.04
FROM ${BASE_IMAGE}

LABEL org.opencontainers.image.description="LabPod SciPy data-science + JupyterLab workspace image (CPU) with the common scientific Python stack."

ENV DEBIAN_FRONTEND=noninteractive \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:${PATH}"

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

RUN uv pip install --no-cache \
        jupyterlab \
        ipywidgets \
        jupyter-resource-usage \
        numpy \
        scipy \
        pandas \
        scikit-learn \
        matplotlib \
        seaborn \
        bokeh

# Build-time contract checks run on pull requests. Published-image smoke tests
# additionally start JupyterLab and verify its HTTP endpoint.
RUN PYTHONDONTWRITEBYTECODE=1 python3 -c \
      'import bokeh, matplotlib, numpy, pandas, scipy, seaborn, sklearn; from scipy.linalg import solve; assert solve([[2.0]], [4.0])[0] == 2.0' \
    && jupyter lab --version

WORKDIR /work
EXPOSE 8888

# Stay-alive composite: LabPod starts JupyterLab on demand via `podman
# exec`, so PID 1 just stays alive. LabPod runs every workspace with
# `podman run --init`, so zombie reaping is handled by catatonit injected
# at runtime — the image doesn't bundle its own init.
ENTRYPOINT ["sleep", "infinity"]
