# TensorFlow + JupyterLab image

This directory builds LabPod's TensorFlow + JupyterLab image. It is a
long-running workspace image: JupyterLab, TensorBoard, and code-server are
started on demand, while the image's default process is `sleep infinity`.

## Published variants

The GitHub Actions workflow publishes Linux `amd64` images to
`ghcr.io/labpod/tensorflow-jupyter` using the following matrix:

| Image tag | CUDA runtime base | Minimum Linux host driver | Python | TensorFlow | GPU architecture |
| --- | --- | --- | --- | --- | --- |
| `cu125` | CUDA 12.5.1 on Ubuntu 24.04 | >= 525.60.13 | 3.12 | 2.21.0 (`tensorflow[and-cuda]`, CUDA 12.5+ / cuDNN 9.3) | Pascal (`sm_60`) and newer |

Unlike the PyTorch image, TensorFlow's `and-cuda` extra bundles its own CUDA
user-space through pip `nvidia-*` wheels. The effective CUDA runtime is
therefore pinned by the TensorFlow version, not by a per-CUDA wheel index, and
the driver coupling is looser: TensorFlow's CUDA 12 wheels run on any host
driver `>= 525.60.13` through CUDA minor-version compatibility. That is why a
single tag covers older driver lines (including the NVIDIA 535 series) without a
per-CUDA matrix. The `sm_*` range above is the set of compute capabilities the
tested TensorFlow wheels compile for; confirm it against the release for your
specific GPU.

## Runtime model

- LabPod selects a free image-local UID/GID and maps it to the workspace
  owner's Linux account; existing image accounts are supported.
- The image contains CUDA user-space libraries (bundled by
  `tensorflow[and-cuda]`), not an NVIDIA kernel driver. The host must provide a
  compatible NVIDIA driver and make the GPU available to the rootless Podman
  container.
- Python packages live in `/opt/venv`; it is first on `PATH`, so `python3`,
  `pip`, `jupyter`, and `tensorboard` use the image environment without
  modifying Ubuntu's system Python.
- The image is published only for `linux/amd64`. The CUDA base images may
  support other architectures, but they are not built or published by this
  workflow.
- `jupyterlab` and the scientific stack intentionally float between scheduled
  rebuilds. The TensorFlow version above is pinned; its bundled CUDA wheels are
  resolved from the `and-cuda` extra at build time.
- code-server (browser VS Code, container port `8080`) is installed from the
  upstream `.deb`, pinned by version and verified against a sha256 recorded in
  the Dockerfile. It bundles its own Node runtime and does not use `/opt/venv`.
  `scripts/bump-image-pins.py` bumps the pin here, in the PyTorch image, and in
  the demo image together. code-server writes user data (settings, installed
  extensions) under `$HOME`, so those persist only when the workspace's home
  directory is on persistent storage.
- After allocating a GPU, confirm `tf.config.list_physical_devices('GPU')` lists
  it before starting long-running training — an empty list means TensorFlow fell
  back to CPU.

For driver compatibility, consult NVIDIA's [CUDA compatibility guide](https://docs.nvidia.com/deploy/cuda-compatibility/) and the [CUDA 12.5.1 release notes](https://docs.nvidia.com/cuda/archive/12.5.1/cuda-toolkit-release-notes/index.html).
For TensorFlow's tested build configuration (CUDA / cuDNN / Python versions), see the [TensorFlow GPU install guide](https://www.tensorflow.org/install/pip) and the [tested build configurations](https://www.tensorflow.org/install/source#gpu).
For GPU compute capabilities, see NVIDIA's [CUDA GPUs reference](https://developer.nvidia.com/cuda-gpus).

## Local build

Build the image with its default arguments (the `cu125` variant):

```sh
podman build -t tensorflow-jupyter:cu125 .
```

From the repository root, use this image directory as the build context:

```sh
podman build -t tensorflow-jupyter:cu125 images/tensorflow-jupyter
```

To build another variant, provide `CUDA_BASE_IMAGE` and `TF_VERSION` from the
matrix in `.github/workflows/images.yml`.
