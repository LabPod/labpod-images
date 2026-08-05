# LabPod TensorFlow + JupyterLab composite image (public, pull-only).
#
# Built and pushed to ghcr.io/labpod/tensorflow-jupyter:<cuda-tag> by
# .github/workflows/images.yml. Replaces the upstream
# jovyan-based quay.io/jupyter/tensorflow-notebook for LabPod's default
# "TensorFlow JupyterLab" template: no baked USER (runs as the workspace
# owner under rootless Podman), no /home/jovyan remnants, WORKDIR /work.
# code-server ships alongside JupyterLab so the workspace has a browser
# editor without a second image; LabPod starts it on demand like the others.
#
# CUDA pairing differs from the PyTorch image: tensorflow[and-cuda] bundles
# its CUDA user-space through pip nvidia-* wheels, so the effective CUDA
# runtime is pinned by the TensorFlow version, not by a per-CUDA wheel index.
# The nvidia/cuda base supplies a consistent system + forward-compat layout;
# TensorFlow loads most of its CUDA 12.x libs from the venv, but not all of
# them — cuSPARSE resolves to the base image's copy at runtime, so the base
# must stay a `-runtime` tag rather than a smaller `-base` one.
# The tag names the CUDA floor those wheels require:
#   cu125 -> TensorFlow 2.21 / and-cuda wheels (CUDA 12.5+, cuDNN 9.3), Ubuntu 24.04 base
# tensorflow[and-cuda] supports host driver >= 525.60.13 via CUDA 12 minor-
# version compatibility, so a single tag covers older driver lines (e.g. 535).
# Verify the TensorFlow pin against PyPI on the first CI run.
ARG CUDA_BASE_IMAGE=docker.io/nvidia/cuda:12.5.1-runtime-ubuntu24.04
FROM ${CUDA_BASE_IMAGE}

LABEL org.opencontainers.image.description="LabPod TensorFlow + JupyterLab workspace image with CUDA, TensorBoard, code-server, and common scientific Python tools."

ENV DEBIAN_FRONTEND=noninteractive \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:${PATH}"
ARG TF_VERSION=2.21.0
# cuDNN is pinned because tensorflow[and-cuda] only constrains it to a range
# (>=9.3.0.75,<10.0) and the newest version in that range dropped Pascal
# (compute capability 6.x). With cuDNN 9.24.0 every cuDNN op on a Pascal GPU
# fails at runtime -- conv2d, keras Conv2D and max_pool2d all raise
# "No algorithm worked! ... <unknown cudnn status: 5003>" -- while matmul,
# nvidia-smi and tf.config.list_physical_devices("GPU") all still succeed, so
# nothing short of running a real convolution detects it. Measured on an
# NVIDIA TITAN Xp (sm_61): 9.24.0.43 fails, 9.10.2.21 works. cuDNN was the
# only unpinned input in this image, which made the same Dockerfile produce a
# working image and then a broken one with no commit in between -- the weekly
# scheduled rebuild shipped the regression. See pkgpl/labpod#1171.
#
# Raise this pin only against a real pre-Volta GPU, or after deciding those
# GPUs are out of scope (which needs a second tag + an autoCudaTags entry on
# the LabPod side, not a silent bump). scripts/bump-image-pins.py deliberately
# does not know about this pin.
ARG CUDNN_VERSION=9.10.2.21
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

# TensorFlow's and-cuda extra pulls the matching nvidia-* CUDA wheels, so the
# bundled CUDA runtime tracks the TensorFlow version instead of PyPI defaults.
# The cuDNN pin goes to the resolver alongside TensorFlow rather than being
# force-installed afterwards, so a future TF whose cuDNN floor rises above the
# pin fails the build loudly instead of silently resolving past it.
RUN uv pip install --no-cache "tensorflow[and-cuda]==${TF_VERSION}" \
        "nvidia-cudnn-cu12==${CUDNN_VERSION}"

# cuDNN is the one dependency whose version silently decides whether this image
# works on Pascal, so assert the resolved version rather than trusting the
# resolver. Runs on any machine -- it reads metadata, no GPU needed -- which is
# what makes it a usable CI gate against the weekly rebuild drifting again.
RUN installed="$(python3 -c 'import importlib.metadata as m; print(m.version("nvidia-cudnn-cu12"))')" \
    && if [ "$installed" != "${CUDNN_VERSION}" ]; then \
         echo "cuDNN pin violated: wanted ${CUDNN_VERSION}, resolved $installed" >&2; \
         exit 1; \
       fi \
    && echo "cuDNN pinned at $installed"

# TensorBoard is an explicit launcher contract. TensorFlow 2.21 no longer
# installs its CLI as a transitive dependency, so keep it in the image directly.
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

# LabPod starts every workspace as its Linux owner and injects that user's
# passwd entry. Ubuntu/CUDA base images may reserve UID 1000 for `ubuntu`; an
# existing image entry wins over Podman's injection and redirects HOME. Leave
# UID 1000 unassigned in every published LabPod image.
RUN sed -i -E '/^[^:]*:[^:]*:1000:/d' /etc/passwd

# CPU execution catches broken TensorFlow installs on pull requests. Real-GPU
# cuDNN compatibility remains a hardware acceptance gate.
RUN CUDA_VISIBLE_DEVICES=-1 PYTHONDONTWRITEBYTECODE=1 python3 -c \
      'import tensorflow as tf; x=tf.ones((1, 4, 4, 1)); y=tf.keras.layers.Conv2D(1, 2)(x); assert tuple(y.shape) == (1, 3, 3, 1)' \
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
