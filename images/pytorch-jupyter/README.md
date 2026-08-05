# PyTorch + JupyterLab image

This directory builds LabPod's PyTorch + JupyterLab image. It is a
long-running workspace image: JupyterLab, TensorBoard, and code-server are
started on demand, while the image's default process is `sleep infinity`.

## Published variants

The GitHub Actions workflow publishes Linux `amd64` images to
`ghcr.io/labpod/pytorch-jupyter` using the following matrix:

| Image tag | CUDA runtime base | Minimum Linux host driver | Python | PyTorch / torchvision | GPU architecture |
| --- | --- | --- | --- | --- | --- |
| `cu121` | CUDA 12.1.1 on Ubuntu 22.04 | >= 530.30.02 | 3.10 | 2.5.1+cu121 / 0.20.1+cu121 | Maxwell (`sm_50`) through Hopper (`sm_90`) |
| `cu126` | CUDA 12.6.3 on Ubuntu 24.04 | >= 560.35.05 | 3.12 | 2.8.0+cu126 / 0.23.0+cu126 | Maxwell (`sm_50`) through Hopper (`sm_90`) |
| `cu129` | CUDA 12.9.1 on Ubuntu 24.04 | >= 575.57.08 | 3.12 | 2.8.0+cu129 / 0.23.0+cu129 | Volta (`sm_70`) through Blackwell (`sm_120`) |

The `cu129` wheel family does not support pre-Volta GPUs, so use `cu121` or
`cu126` for Maxwell- or Pascal-class hardware. The CUDA runtime is selected to
match the PyTorch wheel index for each tag. The architecture ranges above are
the compiled CUDA flags reported by the tested torch wheels; future GPU
support can also depend on PTX forward compatibility and the host driver.

The driver column uses NVIDIA's Linux x86_64 toolkit-release driver requirements
for CUDA 12.1.1, 12.6.3, and 12.9.1. CUDA 12.x has a lower minor-version
compatibility floor (`>= 525.60.13`), but that compatibility mode has feature
restrictions; use the table values for the normal supported path.

## Runtime model

- LabPod selects a free image-local UID/GID and maps it to the workspace
  owner's Linux account; existing image accounts are supported.
- The image contains CUDA user-space libraries, not an NVIDIA kernel driver.
  The host must provide a compatible NVIDIA driver and make the GPU available
  to the rootless Podman container.
- Python packages live in `/opt/venv`; it is first on `PATH`, so `python3`,
  `pip`, `jupyter`, and `tensorboard` use the image environment without
  modifying Ubuntu's system Python.
- The image is published only for `linux/amd64`. The CUDA base images may
  support other architectures, but they are not built or published by this
  workflow.
- `jupyterlab` and the scientific stack intentionally float between scheduled
  rebuilds. The CUDA, PyTorch, and torchvision versions above are pinned.
- code-server (browser VS Code, container port `8080`) is installed from the
  upstream `.deb`, pinned by version and verified against a sha256 recorded in
  the Dockerfile. It bundles its own Node runtime and does not use `/opt/venv`.
  `scripts/bump-image-pins.py` bumps the pin here, in the TensorFlow image, and
  in the demo image together. code-server writes user data (settings, installed
  extensions) under `$HOME`, so those persist only when the workspace's home
  directory is on persistent storage.

For driver compatibility, consult NVIDIA's [CUDA compatibility guide](https://docs.nvidia.com/deploy/cuda-compatibility/) and the [CUDA 12.1.1](https://docs.nvidia.com/cuda/archive/12.1.1/cuda-toolkit-release-notes/index.html), [CUDA 12.6.3](https://docs.nvidia.com/cuda/archive/12.6.3/cuda-toolkit-release-notes/index.html), and [CUDA 12.9.1](https://docs.nvidia.com/cuda/archive/12.9.1/cuda-toolkit-release-notes/index.html) release notes.
For GPU compute capabilities, see NVIDIA's [CUDA GPUs reference](https://developer.nvidia.com/cuda-gpus).

## Local build

Build a variant by passing its matrix values as build arguments. For example,
the default arguments build the `cu126` variant:

```sh
podman build -t pytorch-jupyter:cu126 .
```

From the repository root, use this image directory as the build context:

```sh
podman build -t pytorch-jupyter:cu126 images/pytorch-jupyter
```

To build another variant, provide `CUDA_BASE_IMAGE`, `TORCH_CUDA`,
`TORCH_VERSION`, and `TORCHVISION_VERSION` from the matrix in
`.github/workflows/images.yml`.
