# Code Server image

This directory builds the managed LabPod Code Server image. It runs as the
workspace owner supplied by LabPod, with code-server started on demand while
the default process remains `sleep infinity`.

LabPod selects a free image-local UID/GID at workspace start and maps it to the
workspace owner's Linux account, so base-image accounts do not need to be
removed or renumbered.

The workflow publishes Linux `amd64` to `ghcr.io/labpod/code-server:latest`.
The code-server `.deb` is version-pinned and checksum-verified in the
Dockerfile. `scripts/bump-image-pins.py` updates that pin together with the
other LabPod images that bundle code-server.

## Local build

```sh
podman build -t labpod-code-server:latest images/code-server
```
