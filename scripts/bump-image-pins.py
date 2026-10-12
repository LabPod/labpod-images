#!/usr/bin/env python3
"""Bump the version pins that live in the managed-image release catalog.

Dependabot handles GitHub Actions and Dockerfile base-image tags, but it cannot
see the pip/torch/code-server versions embedded in the build matrices. This
script fetches the latest stable release of each and rewrites the pins in place,
so the scheduled bump-image-pins workflow can open a review PR. The PR-triggered
image builds validate (no publish), so a bad wheel/version combination is caught
before merge.

Handled pins:
  - torch / torchvision / torchaudio -> image-matrix.json (newest shared pin;
                             the cu121 old-driver line stays put)
  - tensorflow            -> image-matrix.json (tf_version)
  - ComfyUI               -> image-matrix.json (release tag)
  - code-server           -> every Dockerfile in CODE_SERVER_DOCKERFILES
                             (version + amd64/arm64 sha256). The pin is
                             duplicated per image because the Dockerfiles share
                             no base layer; bumping them together is what keeps
                             the sha256 guard from going stale in one of them.

No third-party imports: uses urllib + a tiny stable-version comparator so the
script runs on a bare runner.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMAGE_MATRIX = ROOT / ".github" / "image-matrix.json"
PYTORCH_WFS = [IMAGE_MATRIX]
TF_WF = IMAGE_MATRIX
CODE_SERVER_DOCKERFILES = [
    ROOT / "images" / "pytorch-demo" / "Dockerfile",
    ROOT / "images" / "pytorch-jupyter" / "Dockerfile",
    ROOT / "images" / "tensorflow-jupyter" / "Dockerfile",
    ROOT / "images" / "code-server" / "Dockerfile",
    ROOT / "images" / "llm-huggingface" / "Dockerfile",
    ROOT / "images" / "cuda-composite" / "Dockerfile",
    ROOT / "images" / "parallel-dev" / "Dockerfile",
]

_STABLE_RE = re.compile(r"^\d+(\.\d+)*$")
_RELEASE_TAG_RE = re.compile(r"v(\d+)((?:-[A-Za-z0-9_][A-Za-z0-9_.-]*)?)")


def version_key(v):
    return tuple(int(p) for p in v.split("."))


def is_stable(v):
    return bool(_STABLE_RE.match(v))


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "labpod-bump-pins"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def latest_stable_pypi(pkg):
    data = json.loads(get(f"https://pypi.org/pypi/{pkg}/json"))
    stable = [v for v in data["releases"] if is_stable(v) and data["releases"][v]]
    return max(stable, key=version_key)


def latest_code_server():
    data = json.loads(get("https://api.github.com/repos/coder/code-server/releases/latest"))
    return data["tag_name"].lstrip("v")


def latest_github_release(repository):
    data = json.loads(get(f"https://api.github.com/repos/{repository}/releases/latest"))
    return data["tag_name"]


def sha256_of(url):
    h = hashlib.sha256()
    req = urllib.request.Request(url, headers={"User-Agent": "labpod-bump-pins"})
    with urllib.request.urlopen(req, timeout=300) as r:
        for chunk in iter(lambda: r.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def newest_pinned(files, key):
    """Highest stable value of a named pin across the given catalog files."""
    found = set()
    pat = re.compile(rf'\b{re.escape(key)}"?\s*:\s*"?([0-9.]+)')
    for f in files:
        for m in pat.finditer(f.read_text()):
            if is_stable(m.group(1)):
                found.add(m.group(1))
    return max(found, key=version_key) if found else None


def replace_in(files, old_line_key, old, new, root=ROOT):
    changed = []
    for f in files:
        txt = f.read_text()
        new_txt = re.sub(
            rf'(\b{re.escape(old_line_key)}"?\s*:\s*"?){re.escape(old)}\b',
            rf"\g<1>{new}",
            txt,
        )
        if new_txt != txt:
            f.write_text(new_txt)
            changed.append(f.relative_to(root).as_posix())
    return changed


def update_code_server_dockerfile(text, version, sha_amd64, sha_arm64):
    """Return Dockerfile text with one code-server pin set updated."""
    text = re.sub(r"(CODE_SERVER_VERSION=)[0-9.]+", rf"\g<1>{version}", text)
    text = re.sub(r"(CODE_SERVER_SHA256_AMD64=)[0-9a-f]{64}", rf"\g<1>{sha_amd64}", text)
    return re.sub(r"(CODE_SERVER_SHA256_ARM64=)[0-9a-f]{64}", rf"\g<1>{sha_arm64}", text)


def release_versions(catalog):
    """Validate immutable tags and return each image family's vN version."""
    prefixes = {}
    for variant in catalog["variants"]:
        tag = variant.get("tag")
        match = _RELEASE_TAG_RE.fullmatch(tag) if isinstance(tag, str) else None
        if not match:
            raise ValueError(f"invalid immutable release tag: {tag}")
        name = variant["name"]
        prefix = match.group(1)
        if name in prefixes and prefixes[name] != prefix:
            raise ValueError(f"image family {name} must use one shared vN tag prefix")
        prefixes[name] = prefix
    if not prefixes:
        raise ValueError("release catalog must contain image variants")
    return {name: int(prefix) for name, prefix in prefixes.items()}


def advance_release_tags(text, changed_families):
    """Advance only changed families' immutable vN prefixes; retain channels."""
    catalog = json.loads(text)
    versions = release_versions(catalog)
    changed_families = set(changed_families)
    unknown = changed_families - versions.keys()
    if unknown:
        raise ValueError("changed image families absent from catalog: " + ", ".join(sorted(unknown)))
    releases = {
        name: (version, version + 1)
        for name, version in versions.items()
        if name in changed_families
    }
    if not releases:
        return text, releases
    for variant in catalog["variants"]:
        if variant["name"] in releases:
            suffix = _RELEASE_TAG_RE.fullmatch(variant["tag"]).group(2)
            variant["tag"] = f"v{releases[variant['name']][1]}{suffix}"
    return json.dumps(catalog, indent=2) + "\n", releases


def snapshot_pin_inputs(
    image_matrix=IMAGE_MATRIX, dockerfiles=CODE_SERVER_DOCKERFILES, root=ROOT
):
    """Capture the inputs this tool can change, grouped by image family.

    Snapshot the working files rather than a Git revision so unrelated existing
    edits cannot cause a release bump. Tags themselves are not build inputs.
    """
    catalog = json.loads(image_matrix.read_text())
    release_versions(catalog)
    inputs = {}
    for variant in catalog["variants"]:
        family = inputs.setdefault(variant["name"], {"variants": [], "dockerfiles": {}})
        family["variants"].append({key: value for key, value in variant.items() if key != "tag"})
    for path in dockerfiles:
        family = inputs.setdefault(path.parent.name, {"variants": [], "dockerfiles": {}})
        family["dockerfiles"][path.relative_to(root).as_posix()] = path.read_bytes()
    return inputs


def finalize_pin_changes(
    changes, before, image_matrix=IMAGE_MATRIX, dockerfiles=CODE_SERVER_DOCKERFILES, root=ROOT
):
    """Advance materially changed families and refresh the bundle handoff."""
    after = snapshot_pin_inputs(image_matrix, dockerfiles, root)
    changed_families = {
        name for name in before.keys() | after.keys() if before.get(name) != after.get(name)
    }
    if not changed_families:
        return
    matrix, releases = advance_release_tags(image_matrix.read_text(), changed_families)
    image_matrix.write_text(matrix)
    for name, (old_release, new_release) in releases.items():
        changes.append(
            f"{name} release tags v{old_release} -> v{new_release} "
            f"({image_matrix.relative_to(root).as_posix()})"
        )
    subprocess.run(
        [sys.executable, str(root / "scripts" / "published-metadata.py"), "--write"],
        cwd=root,
        check=True,
    )
    changes.append("regenerated published-images.json")


def main():
    changes = []
    before = snapshot_pin_inputs()

    # torch / torchvision (newest shared pin only; cu121 stays put).
    cur_torch = newest_pinned(PYTORCH_WFS, "torch")
    cur_tv = newest_pinned(PYTORCH_WFS, "torchvision")
    cur_audio = newest_pinned(PYTORCH_WFS, "torchaudio")
    new_torch = latest_stable_pypi("torch")
    new_tv = latest_stable_pypi("torchvision")
    new_audio = latest_stable_pypi("torchaudio")
    if cur_torch and version_key(new_torch) > version_key(cur_torch):
        files = replace_in(PYTORCH_WFS, "torch", cur_torch, new_torch)
        if files:
            changes.append(f"torch {cur_torch} -> {new_torch} ({', '.join(files)})")
    if cur_tv and version_key(new_tv) > version_key(cur_tv):
        files = replace_in(PYTORCH_WFS, "torchvision", cur_tv, new_tv)
        if files:
            changes.append(f"torchvision {cur_tv} -> {new_tv} ({', '.join(files)})")
    if cur_audio and version_key(new_audio) > version_key(cur_audio):
        files = replace_in(PYTORCH_WFS, "torchaudio", cur_audio, new_audio)
        if files:
            changes.append(f"torchaudio {cur_audio} -> {new_audio} ({', '.join(files)})")

    # TensorFlow (single matrix value).
    cur_tf = newest_pinned([TF_WF], "tf_version")
    new_tf = latest_stable_pypi("tensorflow")
    if cur_tf and version_key(new_tf) > version_key(cur_tf):
        files = replace_in([TF_WF], "tf_version", cur_tf, new_tf)
        if files:
            changes.append(f"tensorflow {cur_tf} -> {new_tf} ({', '.join(files)})")

    # ComfyUI's source checkout is a release tag rather than a Python package.
    current_comfy = re.findall(r'"comfyui_ref": "([^"]+)"', IMAGE_MATRIX.read_text())
    new_comfy = latest_github_release("Comfy-Org/ComfyUI")
    if current_comfy and any(tag != new_comfy for tag in current_comfy):
        text = IMAGE_MATRIX.read_text()
        text = re.sub(r'("comfyui_ref": ")[^"]+(")', rf"\g<1>{new_comfy}\g<2>", text)
        IMAGE_MATRIX.write_text(text)
        changes.append(
            f"ComfyUI {current_comfy[0]} -> {new_comfy} "
            f"({IMAGE_MATRIX.relative_to(ROOT).as_posix()})"
        )

    # code-server (Dockerfile ARG version + both arch sha256). Every carrying
    # Dockerfile is rewritten in one pass: a partial bump would leave a stale
    # sha256 that only fails much later, at the next build of that one image.
    new_cs = latest_code_server()
    if is_stable(new_cs):
        stale = []
        for path in CODE_SERVER_DOCKERFILES:
            m = re.search(r"CODE_SERVER_VERSION=([0-9.]+)", path.read_text())
            if not m:
                raise SystemExit(f"no CODE_SERVER_VERSION pin in {path}")
            if version_key(new_cs) > version_key(m.group(1)):
                stale.append((path, m.group(1)))
        if stale:
            base = f"https://github.com/coder/code-server/releases/download/v{new_cs}"
            sha_amd64 = sha256_of(f"{base}/code-server_{new_cs}_amd64.deb")
            sha_arm64 = sha256_of(f"{base}/code-server_{new_cs}_arm64.deb")
            for path, cur_cs in stale:
                df = path.read_text()
                df = update_code_server_dockerfile(df, new_cs, sha_amd64, sha_arm64)
                path.write_text(df)
                rel = path.relative_to(ROOT).as_posix()
                changes.append(f"code-server {cur_cs} -> {new_cs} ({rel}, sha256 recomputed)")

    # A pin update changes build bytes. Advance only the affected families'
    # immutable release prefixes and regenerate the bundle handoff in this PR.
    finalize_pin_changes(changes, before)

    summary = "\n".join(f"- {c}" for c in changes)
    print(summary if changes else "No pin updates available.")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write(f"changed={'true' if changes else 'false'}\n")
            fh.write("summary<<EOF\n" + (summary or "No pin updates available.") + "\nEOF\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
