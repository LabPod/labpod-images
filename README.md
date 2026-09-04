# LabPod Managed Workspace Images

This repository is the public source and publishing home for LabPod's managed
workspace container images. The images are built for Podman workspaces and are
designed to run as the LabPod workspace owner without requiring a fixed runtime
user. They target the current LabPod server identity model; image mutations
kept solely for compatibility with older server releases are not retained.

## Images

Pull sizes below are approximate compressed transfer sizes for Linux amd64.
They are capacity-planning estimates for the current `v2` catalog; registry
package pages are authoritative once the workflow has published the images.

| Image | Purpose | Immutable tag(s) | Approx. pull size per tag |
|---|---|---|---|
| `code-server` | Browser-based VS Code workspace | `v2` | 180 MB |
| `pytorch-jupyter` | PyTorch, JupyterLab, TensorBoard, code-server | `v2-cu121`, `v2-cu126`, `v2-cu129` | 4.3 GB, 4.8 GB, 5.0 GB |
| `tensorflow-jupyter` | TensorFlow, JupyterLab, TensorBoard, code-server | `v2-cu125` | 4.2 GB |
| `scipy-jupyter` | CPU data-science and JupyterLab | `v2-py312` | 850 MB |
| `pytorch-demo` | LabPod demonstration workspace | `v2-cpu`, `v2-cu121`, `v2-cu126`, `v2-cu129` | 2.2 GB, 4.4 GB, 4.9 GB, 5.1 GB |
| `miniforge-jupyterlab` | conda-forge Python and JupyterLab | `v2-cpu` | 750 MB |
| `uv-jupyterlab` | Lightweight uv/Python and JupyterLab | `v2-py312` | 420 MB |
| `r-ml-jupyterlab` | R ML packages, IRkernel, and JupyterLab | `v2-cpu` | 2.4 GB |
| `rstudio-server` | Rootless, proxy-authenticated RStudio Server | `v2-cpu` | 1.8 GB |
| `llm-huggingface` | Hugging Face fine-tuning/inference stack | `v2-cu121`, `v2-cu126`, `v2-cu129` | 4.9 GB, 5.3 GB, 5.5 GB |
| `comfyui-stable-diffusion` | ComfyUI without bundled model weights | `v2-cu121`, `v2-cu126`, `v2-cu129` | 4.8 GB, 5.2 GB, 5.4 GB |
| `cuda-composite` | CUDA, JupyterLab, MLflow, Aim, code-server | `v2-cu121`, `v2-cu126`, `v2-cu129` | 2.1 GB, 2.5 GB, 2.7 GB |
| `parallel-dev` | CUDA/MPI/OpenMP toolchain and OSS code-server | `v2-cu121`, `v2-cu126`, `v2-cu129` | 5.0 GB, 5.6 GB, 5.9 GB |

Pull an image with Podman, for example:

```bash
podman pull ghcr.io/labpod/pytorch-jupyter:v2-cu126
```

## Tags and reproducibility

Release tags are immutable. The workflow refuses to overwrite an existing
`v2` tag; a source or dependency update must advance the release prefix. Tag
suffixes such as `cu121`, `cu126`, `cu129`, `cu125`, `py312`, and `cpu`
describe runtime compatibility. Weekly rebuilds publish unique, immutable
`rebuild-<date>-<run>-<attempt>-<release-tag>` audit tags and smoke those bytes
without moving the release tags consumed by LabPod.

The host supplies the NVIDIA driver for GPU images. Select a CUDA channel that
is compatible with both the host driver and GPU architecture; see each image's
README for its supported matrix.

## Building and publishing

Each image lives under `images/<name>` with its own Dockerfile and compatibility
notes. Pull requests build only the affected image's Linux `amd64` variants
without publishing them; the Dockerfiles run import and command checks as part
of those builds. Changes to the shared release catalog, workflow, or smoke
contract validate the complete matrix.

Every release-affecting push to `main` builds the complete catalog. All refs
share one immutable `vN` prefix and one generated metadata handoff, so publishing
only a subset could leave that catalog internally inconsistent after a failed
or interrupted release. Affected-only selection remains a pull-request
optimization.

Changes on `main` first publish commit-specific `candidate-<sha>-<tag>` tags for
the affected variants. CI then pulls those candidates anonymously, checks the
runtime image contract as an unprivileged workspace identity with writable
`HOME` and `/work`, exercises the installed Python stack, and probes the
JupyterLab, TensorBoard, and code-server HTTP launchers that apply to that
image. Stable tags are promoted only after the complete affected candidate
matrix passes. CI pulls and smokes every promoted stable tag again without
registry credentials. The weekly schedule and manual dispatch run the complete
matrix to catch base-image and floating-dependency drift.

Promotion is retry-safe after a partial matrix failure: an existing stable tag
is accepted only when it already resolves to the exact validated candidate
manifest. CI still refuses to move a stable tag that points at different bytes.
Ordinary manual dispatch remains an audit rebuild and never moves stable tags.
If validation fails before any promotion can start, maintainers can rerun the
workflow with **Promote stable** enabled after merging the fix; that explicit
recovery mode rebuilds, validates, and promotes the complete catalog.

The release workflow stamps `org.opencontainers.image.source` on every image so
GHCR can associate every organization-scoped package with this repository.

Every image also carries
`ai.labpod.image.build-input-digest=sha256:<hex>`. This is the offline,
server-reproducible `labpod.build-input.v1` digest used by LabPod's published
image metadata. The SHA-256 input starts with the NUL-terminated magic string
`labpod.build-input.v1`. Each following record frames `kind`, `key`, and
`value` as an unsigned big-endian 64-bit byte length followed by those bytes.
Records are the exact Dockerfile bytes under key `Dockerfile`, regular build
context files sorted by POSIX path, explicit build arguments sorted by name,
and external `FROM` references in Dockerfile order after ARG expansion and
reference normalization. Prior build-stage aliases are skipped. Bundle
contexts reject symlinks and therefore the digest contract does too. Registry
lookups are deliberately not part of the algorithm, so an air-gapped LabPod
server can recompute it.

[`published-images.json`](published-images.json) is the generated,
machine-readable handoff for LabPod bundles: it records each canonical
Dockerfile, default and per-variant build arguments, immutable references, and
definition digests. Each non-default published variant embeds its own build
arguments so an offline server can recompute that variant rather than
accidentally using the default channel's arguments. Regenerate or verify it with
`scripts/published-metadata.py --write` or `--check`.

Candidate and weekly rebuild tags are retained as an audit trail for the bytes
built by a given source revision. CUDA execution and driver/GPU-architecture compatibility
still require a real NVIDIA host; hosted CI validates CPU execution and the
packaged CUDA/Python dependency graph, not a real GPU kernel.

The package namespace and pull URLs did not change when image source moved to
this repository. Existing LabPod installations continue to use the same
`ghcr.io/labpod/<image>:<tag>` references.

Maintainers must grant this repository Actions access to each existing GHCR
package, connect each package to this source repository, and keep package
visibility **Public** so LabPod hosts can pull without registry credentials.
The package-access job proves both authenticated write access and an anonymous
pull before any expensive image builds start. GitHub creates a new container
package as private, so the first run for a new package intentionally stops after
publishing its small `access-<sha>` probe. An organization owner must make that
package Public and rerun the workflow; only then can candidate builds proceed.

Version pins embedded in the build matrix are handled by the `bump-image-pins`
workflow. It is optional and no-ops unless the repository secret
`BUMP_PIN_TOKEN` has contents and pull-request write access to this repository.
The bump script advances the shared immutable `vN` prefix and regenerates
`published-images.json` in the same pull request.
Dependabot continues to maintain action and base-image pins without that
secret.

## Relationship to LabPod

These packages are maintained independently from the LabPod server release
channel. LabPod server releases, portable CLI binaries, and the matching agent
skill are published at [LabPod releases](https://github.com/LabPod/labpod/releases).
Product documentation is available at [docs.labpod.ai](https://docs.labpod.ai).
