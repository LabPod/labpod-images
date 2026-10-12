ARG CUDA_BASE_IMAGE=docker.io/nvidia/cuda:12.1.1-runtime-ubuntu22.04
FROM ${CUDA_BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive \
    HF_HUB_ENABLE_HF_TRANSFER=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:${PATH}
ARG TORCH_CUDA=cu121
ARG TORCH_VERSION=2.5.1
ARG CODE_SERVER_VERSION=4.118.0
ARG CODE_SERVER_SHA256_AMD64=fe2988f313c9047c1e1ccccee10ad8ccf2813b66a02c146e7d4fd2a3f7e2dc81
ARG CODE_SERVER_SHA256_ARM64=81fa5486a674428507cfb68025764646bdb99c345b8ca798fd94a13ea056eeb3

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash ca-certificates curl git git-lfs htop iproute2 jq less nano \
        openssh-client python3 python3-pip python3-venv rsync tmux tree \
        unzip vim wget \
    && (apt-get install -y --no-install-recommends btop || true) \
    && git lfs install --system \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv "$VIRTUAL_ENV" \
    && "$VIRTUAL_ENV/bin/python" -m pip install --no-cache-dir uv \
    && uv_path="$(command -v uv)" \
    && test "$uv_path" = "$VIRTUAL_ENV/bin/uv" \
    && uv --version

# Use the matching PyTorch wheel index as the sole index so a newer PyPI
# wheel cannot silently replace the CUDA-pinned build.
RUN uv pip install --python "$VIRTUAL_ENV/bin/python" --no-cache \
        --index-url "https://download.pytorch.org/whl/${TORCH_CUDA}" \
        "torch==${TORCH_VERSION}"

COPY requirements.txt /tmp/huggingface-requirements.txt
# Keep the tested HF cohort together and preserve the exact installed CUDA wheel
# during the second resolution; incompatible future requirements must fail closed.
RUN uv pip install --python "$VIRTUAL_ENV/bin/python" --no-cache \
        "torch==${TORCH_VERSION}+${TORCH_CUDA}" \
        -r /tmp/huggingface-requirements.txt \
        jupyterlab ipywidgets jupyter-resource-usage tensorboard \
        datasets sentencepiece safetensors \
        huggingface_hub hf-transfer einops evaluate numpy pandas

COPY runtime-smoke.py /usr/local/lib/labpod/huggingface-smoke.py
# Exercise lazy generation/trainer imports and a tiny model without downloading
# weights or requiring a GPU. Import failures must fail the build, not a release.
RUN HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
    EXPECTED_TORCH_VERSION="${TORCH_VERSION}" EXPECTED_TORCH_CUDA="${TORCH_CUDA}" \
    python /usr/local/lib/labpod/huggingface-smoke.py

RUN arch="$(dpkg --print-architecture)" \
    && case "$arch" in \
        amd64) expected="$CODE_SERVER_SHA256_AMD64" ;; \
        arm64) expected="$CODE_SERVER_SHA256_ARM64" ;; \
        *) echo "unsupported architecture: $arch" >&2; exit 1 ;; \
    esac \
    && artifact="code-server_${CODE_SERVER_VERSION}_${arch}.deb" \
    && curl -fsSL "https://github.com/coder/code-server/releases/download/v${CODE_SERVER_VERSION}/${artifact}" -o "/tmp/${artifact}" \
    && echo "${expected}  /tmp/${artifact}" | sha256sum -c - \
    && apt-get update \
    && apt-get install -y --no-install-recommends "/tmp/${artifact}" \
    && rm -f "/tmp/${artifact}" \
    && rm -rf /var/lib/apt/lists/* \
    && code-server --version

WORKDIR /work
EXPOSE 8888 6006 8080
ENTRYPOINT ["sleep", "infinity"]
