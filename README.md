# LabPod Managed Workspace Images

This repository is the public source and publishing home for LabPod's managed
workspace container images. The images are built for Podman workspaces and are
designed to run as the LabPod workspace owner without requiring a fixed runtime
user. They target the current LabPod server identity model; image mutations
kept solely for compatibility with older server releases are not retained.

## Images

| Image | Purpose | Example |
|---|---|---|
| [`code-server`](https://github.com/orgs/LabPod/packages/container/package/code-server) | Browser-based VS Code workspace | `ghcr.io/labpod/code-server:latest` |
| [`pytorch-jupyter`](https://github.com/orgs/LabPod/packages/container/package/pytorch-jupyter) | PyTorch, JupyterLab, TensorBoard, and code-server | `ghcr.io/labpod/pytorch-jupyter:cu126` |
| [`tensorflow-jupyter`](https://github.com/orgs/LabPod/packages/container/package/tensorflow-jupyter) | TensorFlow, JupyterLab, TensorBoard, and code-server | `ghcr.io/labpod/tensorflow-jupyter:cu125` |
| [`scipy-jupyter`](https://github.com/orgs/LabPod/packages/container/package/scipy-jupyter) | CPU data-science and JupyterLab environment | `ghcr.io/labpod/scipy-jupyter:py312` |
| [`pytorch-demo`](https://github.com/orgs/LabPod/packages/container/package/pytorch-demo) | LabPod demonstration workspace | `ghcr.io/labpod/pytorch-demo:cpu` |

Pull an image with Podman, for example:

```bash
podman pull ghcr.io/labpod/pytorch-jupyter:cu126
```

## Tags and reproducibility

Tags such as `cu121`, `cu126`, `cu129`, `cu125`, `py312`, and `cpu` describe
runtime compatibility channels. They may be rebuilt to pick up security and
dependency updates. Pin an image digest when an exact, reproducible image is
required.

The host supplies the NVIDIA driver for GPU images. Select a CUDA channel that
is compatible with both the host driver and GPU architecture; see each image's
README for its supported matrix.

## Building and publishing

Each image lives under `images/<name>` with its own Dockerfile and compatibility
notes. Pull requests build the complete Linux `amd64` matrix without publishing
it; the Dockerfiles run import and command checks as part of those builds.

Changes on `main` and the weekly schedule first publish commit-specific
`candidate-<sha>-<tag>` tags. CI then pulls every candidate anonymously, checks
the runtime image contract, exercises the installed Python stack, and probes
the JupyterLab, TensorBoard, code-server, and ttyd HTTP launchers that apply to
that image. Stable tags are promoted only after the complete candidate matrix
passes. CI pulls and smokes every promoted stable tag again without registry
credentials.

Candidate tags are retained as an audit trail for the bytes promoted by a
given source commit. CUDA execution and driver/GPU-architecture compatibility
still require a real NVIDIA host; hosted CI validates CPU execution and the
packaged CUDA/Python dependency graph, not a real GPU kernel.

The package namespace and pull URLs did not change when image source moved to
this repository. Existing LabPod installations continue to use the same
`ghcr.io/labpod/<image>:<tag>` references.

Maintainers must grant this repository Actions access to each existing GHCR
package, connect each package to this source repository, and keep package
visibility **Public** so LabPod hosts can pull without registry credentials.

Version pins embedded in the build matrix are handled by the `bump-image-pins`
workflow. It is optional and no-ops unless the repository secret
`BUMP_PIN_TOKEN` has contents, pull-request, and workflow write access to this
repository. Dependabot continues to maintain action and base-image pins without
that secret.

## Relationship to LabPod

These packages are maintained independently from the LabPod server release
channel. LabPod server releases, portable CLI binaries, and the matching agent
skill are published at [LabPod releases](https://github.com/LabPod/labpod/releases).
Product documentation is available at [docs.labpod.ai](https://docs.labpod.ai).
