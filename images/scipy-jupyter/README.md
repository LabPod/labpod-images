# SciPy data-science + JupyterLab image

This directory builds LabPod's CPU-only SciPy + JupyterLab image. It is a
long-running workspace image: JupyterLab is started on demand, while the
image's default process is `sleep infinity`.

## Published variants

The GitHub Actions workflow publishes Linux `amd64` images to
`ghcr.io/labpod/scipy-jupyter` using the following matrix:

| Image tag | Base | Python | Stack |
| --- | --- | --- | --- |
| `py312` | Ubuntu 24.04 | 3.12 | JupyterLab, ipywidgets, jupyter-resource-usage, NumPy, SciPy, pandas, scikit-learn, matplotlib, seaborn, bokeh |

This is a **CPU-only** image — no CUDA base and no GPU stack — so there is no
host-driver requirement. It is the right pick for data wrangling, statistics,
plotting, and coursework that doesn't need CUDA, and it keeps GPUs free for
training workloads on the shared workstation.

## Runtime model

- LabPod selects a free image-local UID/GID and maps it to the workspace
  owner's Linux account; existing image accounts are supported.
- Python packages live in `/opt/venv`; it is first on `PATH`, so `python3`,
  `pip`, and `jupyter` use the image environment without modifying Ubuntu's
  system Python.
- The image is published only for `linux/amd64`.
- `jupyterlab` and the scientific stack intentionally float between scheduled
  rebuilds; the Python base line (`py312`) is pinned by the tag.

## Local build

Build the image with its default arguments (the `py312` variant):

```sh
podman build -t scipy-jupyter:py312 .
```

From the repository root, use this image directory as the build context:

```sh
podman build -t scipy-jupyter:py312 images/scipy-jupyter
```

To build against another base, provide `BASE_IMAGE` from the matrix in
`.github/workflows/images.yml`.
