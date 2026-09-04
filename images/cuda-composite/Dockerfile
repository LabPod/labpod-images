ARG CUDA_BASE_IMAGE=docker.io/nvidia/cuda:12.1.1-runtime-ubuntu22.04
FROM ${CUDA_BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:${PATH}
ARG CODE_SERVER_VERSION=4.118.0
ARG CODE_SERVER_SHA256_AMD64=fe2988f313c9047c1e1ccccee10ad8ccf2813b66a02c146e7d4fd2a3f7e2dc81
ARG CODE_SERVER_SHA256_ARM64=81fa5486a674428507cfb68025764646bdb99c345b8ca798fd94a13ea056eeb3

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash ca-certificates curl git htop iproute2 jq less nano openssh-client \
        python3 python3-pip python3-venv rsync tmux tree unzip vim wget \
    && (apt-get install -y --no-install-recommends btop || true) \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv "$VIRTUAL_ENV" \
    && "$VIRTUAL_ENV/bin/python" -m pip install --no-cache-dir uv \
    && uv_path="$(command -v uv)" \
    && test "$uv_path" = "$VIRTUAL_ENV/bin/uv" \
    && uv --version

RUN uv pip install --python "$VIRTUAL_ENV/bin/python" --no-cache \
        jupyterlab ipywidgets jupyter-resource-usage tensorboard mlflow aim \
        numpy scipy scikit-learn pandas matplotlib seaborn transformers \
        datasets accelerate peft safetensors streamlit gradio

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
EXPOSE 8888 6006 8080 5000 43800
ENTRYPOINT ["sleep", "infinity"]
