#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 <image-ref> <image-kind>" >&2
  exit 2
}

[[ $# -eq 2 ]] || usage
image_ref=$1
image_kind=$2
engine=${CONTAINER_ENGINE:-docker}
runtime_uid=${SMOKE_UID:-65534}
runtime_gid=${SMOKE_GID:-65534}

case "$image_kind" in
  code-server|pytorch-jupyter|tensorflow-jupyter|scipy-jupyter|pytorch-demo|\
  miniforge-jupyterlab|uv-jupyterlab|r-ml-jupyterlab|rstudio-server|\
  llm-huggingface|comfyui-stable-diffusion|cuda-composite|parallel-dev) ;;
  *) usage ;;
esac

fail() {
  echo "smoke failure: $*" >&2
  exit 1
}

container_id=""
cleanup() {
  if [[ -n "$container_id" ]]; then
    "$engine" rm -f "$container_id" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

[[ $("$engine" image inspect --format '{{.Architecture}}' "$image_ref") == amd64 ]] \
  || fail "published image is not linux/amd64"
[[ -z $("$engine" image inspect --format '{{.Config.User}}' "$image_ref") ]] \
  || fail "image bakes a runtime USER"
[[ $("$engine" image inspect --format '{{.Config.WorkingDir}}' "$image_ref") == /work ]] \
  || fail "image WORKDIR is not /work"
[[ $("$engine" image inspect --format '{{json .Config.Entrypoint}}' "$image_ref") == '["sleep","infinity"]' ]] \
  || fail "image entrypoint is not sleep infinity"

build_input_digest=$("$engine" image inspect --format \
  '{{index .Config.Labels "ai.labpod.image.build-input-digest"}}' "$image_ref")
[[ "$build_input_digest" =~ ^sha256:[0-9a-f]{64}$ ]] \
  || fail "image lacks a valid build-input digest label"
if [[ -n "${EXPECTED_BUILD_INPUT_DIGEST:-}" ]]; then
  [[ "$build_input_digest" == "$EXPECTED_BUILD_INPUT_DIGEST" ]] \
    || fail "build-input digest label does not match workflow input"
fi

# LabPod supplies a passwd entry and persistent HOME for its unprivileged
# workspace identity. The standard nobody identity exercises the same privilege
# boundary in Docker/Podman smoke runs; /tmp is its writable stand-in for HOME
# and the tmpfs matches LabPod's writable /work bind mount.
container_id=$("$engine" run -d \
  --user "$runtime_uid:$runtime_gid" \
  -e USER=nobody -e HOME=/tmp \
  --tmpfs /work:rw,mode=1777 \
  "$image_ref")
for _ in $(seq 1 10); do
  [[ $("$engine" inspect --format '{{.State.Running}}' "$container_id") == true ]] && break
  sleep 1
done
[[ $("$engine" inspect --format '{{.State.Running}}' "$container_id") == true ]] \
  || fail "default container process did not stay running"
[[ $("$engine" exec "$container_id" id -u) == "$runtime_uid" ]] \
  || fail "container is not running as the smoke workspace uid"
[[ $("$engine" exec "$container_id" id -g) == "$runtime_gid" ]] \
  || fail "container is not running as the smoke workspace gid"
# shellcheck disable=SC2016 # HOME must expand inside the container.
"$engine" exec "$container_id" sh -c 'test -w "$HOME" && test -w /work' \
  || fail "workspace identity cannot write HOME and /work"

probe_http() {
  local name=$1
  local port=$2
  local path=$3
  local command=$4
  local log="/tmp/labpod-smoke-${name}.log"

  "$engine" exec "$container_id" sh -c "$command >'$log' 2>&1 &"
  for _ in $(seq 1 45); do
    if "$engine" exec "$container_id" curl -fsS "http://127.0.0.1:${port}${path}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  "$engine" exec "$container_id" sh -c "cat '$log'" >&2 || true
  fail "$name did not answer HTTP on port $port"
}

case "$image_kind" in
  code-server)
    "$engine" exec "$container_id" code-server --version
    probe_http code-server 8080 / \
      "code-server --bind-addr 127.0.0.1:8080 --auth none /work"
    ;;
  pytorch-jupyter)
    "$engine" exec "$container_id" python3 -c \
      'import torch, torchvision; x=torch.tensor([1.0, 2.0]); assert torch.dot(x, x).item() == 5.0'
    "$engine" exec "$container_id" code-server --version
    probe_http jupyter 8888 /lab \
      "jupyter lab --allow-root --no-browser --ip=127.0.0.1 --port=8888 --ServerApp.token='' --ServerApp.password=''"
    probe_http tensorboard 6006 / \
      "tensorboard --host 127.0.0.1 --port 6006 --logdir /tmp/tensorboard"
    probe_http code-server 8080 / \
      "code-server --bind-addr 127.0.0.1:8080 --auth none /work"
    ;;
  tensorflow-jupyter)
    "$engine" exec -e CUDA_VISIBLE_DEVICES=-1 "$container_id" python3 -c \
      'import tensorflow as tf; x=tf.ones((1, 4, 4, 1)); y=tf.keras.layers.Conv2D(1, 2)(x); assert tuple(y.shape) == (1, 3, 3, 1)'
    "$engine" exec "$container_id" code-server --version
    probe_http jupyter 8888 /lab \
      "jupyter lab --allow-root --no-browser --ip=127.0.0.1 --port=8888 --ServerApp.token='' --ServerApp.password=''"
    probe_http tensorboard 6006 / \
      "tensorboard --host 127.0.0.1 --port 6006 --logdir /tmp/tensorboard"
    probe_http code-server 8080 / \
      "code-server --bind-addr 127.0.0.1:8080 --auth none /work"
    ;;
  scipy-jupyter)
    "$engine" exec "$container_id" python3 -c \
      'import bokeh, matplotlib, numpy, pandas, scipy, seaborn, sklearn; from scipy.linalg import solve; assert solve([[2.0]], [4.0])[0] == 2.0'
    probe_http jupyter 8888 /lab \
      "jupyter lab --allow-root --no-browser --ip=127.0.0.1 --port=8888 --ServerApp.token='' --ServerApp.password=''"
    ;;
  pytorch-demo)
    "$engine" exec "$container_id" python3 -c \
      'import aim, mlflow, torch, torchvision; x=torch.tensor([1.0, 2.0]); assert torch.dot(x, x).item() == 5.0'
    "$engine" exec "$container_id" code-server --version
    probe_http jupyter 8888 /lab \
      "jupyter lab --allow-root --no-browser --ip=127.0.0.1 --port=8888 --ServerApp.token='' --ServerApp.password=''"
    probe_http tensorboard 6006 / \
      "tensorboard --host 127.0.0.1 --port 6006 --logdir /tmp/tensorboard"
    probe_http code-server 8080 / \
      "code-server --bind-addr 127.0.0.1:8080 --auth none /work"
    ;;
  miniforge-jupyterlab)
    "$engine" exec "$container_id" conda --version
    "$engine" exec "$container_id" python -c 'import ipywidgets, jupyterlab'
    probe_http jupyter 8888 /lab \
      "jupyter lab --allow-root --no-browser --ip=127.0.0.1 --port=8888 --ServerApp.token='' --ServerApp.password=''"
    ;;
  uv-jupyterlab)
    "$engine" exec "$container_id" uv --version
    "$engine" exec "$container_id" python3 -c 'import ipywidgets, jupyterlab'
    probe_http jupyter 8888 /lab \
      "jupyter lab --allow-root --no-browser --ip=127.0.0.1 --port=8888 --ServerApp.token='' --ServerApp.password=''"
    ;;
  r-ml-jupyterlab)
    "$engine" exec "$container_id" Rscript -e \
      'pkgs <- c("tidyverse", "tidymodels", "caret", "xgboost", "randomForest", "glmnet", "data.table", "reticulate", "IRkernel"); stopifnot(all(vapply(pkgs, function(p) { library(p, character.only=TRUE); TRUE }, logical(1))))'
    "$engine" exec "$container_id" python -c 'import jupyterlab, numpy'
    probe_http jupyter 8888 /lab \
      "jupyter lab --allow-root --no-browser --ip=127.0.0.1 --port=8888 --ServerApp.token='' --ServerApp.password=''"
    ;;
  rstudio-server)
    "$engine" exec "$container_id" R --version
    "$engine" exec "$container_id" Rscript -e \
      'pkgs <- c("tidyverse", "data.table", "reticulate"); stopifnot(all(vapply(pkgs, function(p) { library(p, character.only=TRUE); TRUE }, logical(1))))'
    probe_http rstudio 8787 / \
      "labpod-rstudio --www-port=8787"
    ;;
  llm-huggingface)
    "$engine" exec "$container_id" python3 -c \
      'import accelerate, datasets, peft, torch, transformers; assert torch.tensor([2]).item() == 2'
    "$engine" exec "$container_id" code-server --version
    probe_http jupyter 8888 /lab \
      "jupyter lab --allow-root --no-browser --ip=127.0.0.1 --port=8888 --ServerApp.token='' --ServerApp.password=''"
    probe_http code-server 8080 / \
      "code-server --bind-addr 127.0.0.1:8080 --auth none /work"
    ;;
  comfyui-stable-diffusion)
    "$engine" exec "$container_id" sh -c \
      'cd /opt/ComfyUI && python3 -c "import folder_paths, torch"'
    probe_http comfyui 8188 / \
      "comfyui --listen 127.0.0.1 --port 8188 --cpu"
    ;;
  cuda-composite)
    "$engine" exec "$container_id" python3 -c \
      'import aim, gradio, jupyterlab, mlflow, sklearn, tensorboard'
    "$engine" exec "$container_id" code-server --version
    probe_http jupyter 8888 /lab \
      "jupyter lab --allow-root --no-browser --ip=127.0.0.1 --port=8888 --ServerApp.token='' --ServerApp.password=''"
    probe_http code-server 8080 / \
      "code-server --bind-addr 127.0.0.1:8080 --auth none /work"
    ;;
  parallel-dev)
    "$engine" exec "$container_id" nvcc --version
    "$engine" exec "$container_id" mpicc --version
    "$engine" exec "$container_id" code-server --version
    probe_http code-server 8080 / \
      "code-server --bind-addr 127.0.0.1:8080 --auth none /work"
    ;;
esac

echo "smoke passed: $image_ref ($image_kind)"
