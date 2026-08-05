# PyTorch Demo composite image

This directory builds LabPod's PyTorch Demo image — the kitchen-sink showcase
behind the "PyTorch Demo Workspace" template (JupyterLab, TensorBoard,
code-server, ttyd terminal, MLflow, Aim). It is a long-running workspace image:
launchers start on demand while the image's default process is `sleep infinity`.

The demo notebooks are **not** in the image; LabPod seeds a guided FashionMNIST
demo into `/work/labpod-demo` on first Start of the template.

## Published variants

The GitHub Actions workflow publishes Linux `amd64` images to
`ghcr.io/labpod/pytorch-demo` using the following matrix:

| Image tag | Base | Min host driver | Python | PyTorch / torchvision | GPU architecture |
| --- | --- | --- | --- | --- | --- |
| `cpu` | Ubuntu 24.04 | none (CPU-only) | 3.12 | 2.8.0+cpu / 0.23.0+cpu | none — runs on any host |
| `cu121` | CUDA 12.1.1 on Ubuntu 22.04 | >= 530.30.02 | 3.10 | 2.5.1+cu121 / 0.20.1+cu121 | Maxwell (`sm_50`) through Hopper (`sm_90`) |
| `cu126` | CUDA 12.6.3 on Ubuntu 24.04 | >= 560.35.05 | 3.12 | 2.8.0+cu126 / 0.23.0+cu126 | Maxwell (`sm_50`) through Hopper (`sm_90`) |
| `cu129` | CUDA 12.9.1 on Ubuntu 24.04 | >= 575.57.08 | 3.12 | 2.8.0+cu129 / 0.23.0+cu129 | Volta (`sm_70`) through Blackwell (`sm_120`) |

The **`cpu`** tag is the fast, always-works demo default: no CUDA, no host-driver
requirement, runs on any host (GPU or not). Use a `cu<xx>` tag to demo GPU
allocation and GPU monitoring — pick one that matches the host driver and GPU
(same guidance as the `pytorch-jupyter` image; the `cu129` wheels drop pre-Volta,
so Maxwell/Pascal hosts use `cu121` or `cu126`). The driver column uses NVIDIA's
Linux x86_64 toolkit-release requirements; CUDA 12.x has a lower minor-version
compatibility floor (`>= 525.60.13`).

## Runtime model

- LabPod selects a free image-local UID/GID and maps it to the workspace
  owner's Linux account; existing image accounts are supported.
- The `cu<xx>` images contain CUDA user-space libraries, not an NVIDIA kernel
  driver; the host supplies a compatible driver and makes the GPU available to
  the rootless Podman container. The `cpu` image needs neither.
- Python packages live in `/opt/venv`; it is first on `PATH`.
- Published only for `linux/amd64`.
- The scientific stack, code-server, MLflow, and Aim intentionally float between
  scheduled rebuilds; the CUDA/torch versions above are pinned.

## Local build

```sh
# CPU default
podman build -t pytorch-demo:cpu images/pytorch-demo

# A CUDA variant
podman build -t pytorch-demo:cu126 \
  --build-arg CUDA_BASE_IMAGE=docker.io/nvidia/cuda:12.6.3-runtime-ubuntu24.04 \
  --build-arg TORCH_CUDA=cu126 \
  images/pytorch-demo
```

Provide `CUDA_BASE_IMAGE`, `TORCH_CUDA`, `TORCH_VERSION`, and
`TORCHVISION_VERSION` from the matrix in
`.github/workflows/images.yml`.
