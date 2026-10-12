#!/usr/bin/env python3
"""Select the image release matrix affected by a repository change set."""

import argparse
import json
import re
import subprocess
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / ".github" / "image-matrix.json"
# Only inputs that can change what gets published belong here: the two catalogs
# that declare it, plus the workflow and smoke script that decide how an image is
# built and validated.
#
# The generators behind the catalog, and this selector itself, do not.
# published_metadata_test asserts published-images.json matches what the
# generators emit, so a change to build-input-digest.py or published-metadata.py
# that moves any digest has to regenerate the catalog in the same commit, and the
# regenerated catalog is what selects the release. A change that moves no digest
# publishes nothing new -- listing the generators here demanded a release anyway,
# for tags that already exist, which the immutable-tag guard then refused, so no
# such change could ever merge.
FULL_MATRIX_PATHS = {
    ".github/image-matrix.json",
    ".github/workflows/images.yml",
    "published-images.json",
    "scripts/smoke-image.sh",
}
PACKAGE_DEFAULT_SUFFIX = {
    "code-server": "",
    "pytorch-jupyter": "cu126",
    "tensorflow-jupyter": "cu125",
    "scipy-jupyter": "py312",
    "pytorch-demo": "cpu",
    "miniforge-jupyterlab": "cpu",
    "uv-jupyterlab": "py312",
    "r-ml-jupyterlab": "cpu",
    "rstudio-server": "cpu",
    "llm-huggingface": "cu126",
    "comfyui-stable-diffusion": "cu126",
    "cuda-composite": "cu126",
    "parallel-dev": "cu126",
}
RELEASE_TAG_RE = re.compile(r"^(v\d+)(?:-.+)?$")


def release_prefix(variants):
    prefixes = set()
    for variant in variants:
        match = RELEASE_TAG_RE.fullmatch(variant["tag"])
        if not match:
            raise ValueError(f"invalid immutable release tag: {variant['tag']}")
        prefixes.add(match.group(1))
    if len(prefixes) != 1:
        raise ValueError("image matrix must use one shared vN release prefix per family")
    return prefixes.pop()


def package_current_tag(name, variants):
    if name not in PACKAGE_DEFAULT_SUFFIX:
        raise ValueError(f"image matrix lacks default-tag metadata for: {name}")
    prefix = release_prefix([item for item in variants if item["name"] == name])
    suffix = PACKAGE_DEFAULT_SUFFIX[name]
    tag = prefix if not suffix else f"{prefix}-{suffix}"
    if not any(item["name"] == name and item["tag"] == tag for item in variants):
        raise ValueError(f"image matrix lacks default variant {name}:{tag}")
    return tag


def load_variants(catalog=CATALOG):
    variants = json.loads(catalog.read_text())["variants"]
    keys = [(variant["name"], variant["tag"]) for variant in variants]
    if len(keys) != len(set(keys)):
        raise ValueError("image matrix contains duplicate name/tag variants")
    unknown_packages = {name for name, _ in keys} - PACKAGE_DEFAULT_SUFFIX.keys()
    if unknown_packages:
        raise ValueError(
            "image matrix lacks default-tag metadata for: "
            + ", ".join(sorted(unknown_packages))
        )
    for name in dict.fromkeys(item["name"] for item in variants):
        release_prefix([item for item in variants if item["name"] == name])
    return variants


def build_args(variant):
    name = variant["name"]
    if name in {"pytorch-jupyter", "pytorch-demo"}:
        return "\n".join(
            (
                f"CUDA_BASE_IMAGE={variant['base']}",
                f"TORCH_CUDA={variant['torch_cuda']}",
                f"TORCH_VERSION={variant['torch']}",
                f"TORCHVISION_VERSION={variant['torchvision']}",
            )
        )
    if name == "tensorflow-jupyter":
        return "\n".join(
            (
                f"CUDA_BASE_IMAGE={variant['base']}",
                f"TF_VERSION={variant['tf_version']}",
                f"CUDNN_VERSION={variant['cudnn_version']}",
            )
        )
    if name == "scipy-jupyter":
        return f"BASE_IMAGE={variant['base']}"
    if name == "miniforge-jupyterlab":
        return f"BASE_IMAGE={variant['base']}"
    if name == "uv-jupyterlab":
        return f"PYTHON_BASE={variant['base']}"
    if name in {"r-ml-jupyterlab", "rstudio-server"}:
        return f"BASE_IMAGE={variant['base']}"
    if name == "llm-huggingface":
        return "\n".join(
            (
                f"CUDA_BASE_IMAGE={variant['base']}",
                f"TORCH_CUDA={variant['torch_cuda']}",
                f"TORCH_VERSION={variant['torch']}",
            )
        )
    if name == "comfyui-stable-diffusion":
        return "\n".join(
            (
                f"CUDA_BASE_IMAGE={variant['base']}",
                f"TORCH_CUDA={variant['torch_cuda']}",
                f"TORCH_VERSION={variant['torch']}",
                f"TORCHVISION_VERSION={variant['torchvision']}",
                f"TORCHAUDIO_VERSION={variant['torchaudio']}",
                f"COMFYUI_REF={variant['comfyui_ref']}",
            )
        )
    if name in {"cuda-composite", "parallel-dev"}:
        return f"CUDA_BASE_IMAGE={variant['base']}"
    return ""


def workflow_variant(variant):
    name = variant["name"]
    args = build_args(variant)
    return {
        "name": name,
        "repository": f"ghcr.io/labpod/{name}",
        "tag": variant["tag"],
        "context": f"images/{name}",
        "dockerfile": f"images/{name}/Dockerfile",
        "kind": name,
        "build_args": args,
        "build_input_args": args,
    }


def select_variant_names(paths, variants, force_all=False):
    ordered_names = list(dict.fromkeys(variant["name"] for variant in variants))
    if force_all:
        return ordered_names

    normalized = set()
    for path in paths:
        path = path.strip()
        if not path:
            continue
        if path.startswith("./"):
            path = path[2:]
        normalized.add(path)
    if normalized & FULL_MATRIX_PATHS:
        return ordered_names

    known_names = set(ordered_names)
    selected = set()
    for path in normalized:
        parts = PurePosixPath(path).parts
        if len(parts) < 3 or parts[0] != "images":
            continue
        name = parts[1]
        if name not in known_names:
            raise ValueError(f"image path has no release-matrix entry: {path}")
        if parts[-1] == "README.md":
            continue
        selected.add(name)
    return [name for name in ordered_names if name in selected]


def scope_for_names(names, variants):
    selected = [variant for variant in variants if variant["name"] in names]
    variant_matrix = {"include": [workflow_variant(item) for item in selected]}
    package_matrix = {
        "include": [
            {
                "name": name,
                "repository": f"ghcr.io/labpod/{name}",
                "current_tag": package_current_tag(name, variants),
            }
            for name in names
        ]
    }
    return {
        "release_required": "true" if selected else "false",
        "variant_matrix": variant_matrix,
        "package_matrix": package_matrix,
    }


def release_scope(paths=(), force_all=False, catalog=CATALOG):
    variants = load_variants(catalog)
    names = select_variant_names(paths, variants, force_all=force_all)
    return scope_for_names(names, variants)


def metadata_by_name(metadata):
    images = metadata["images"]
    indexed = {item["name"]: item for item in images}
    if len(indexed) != len(images):
        raise ValueError("published metadata contains duplicate image families")
    return indexed


def published_refs(image):
    published = image["published"]
    return [item["ref"] for item in [published, *published.get("variants", [])]]


def publication_scope(previous_metadata, catalog=CATALOG, metadata=None):
    """Publish only changed family definitions, never overwrite an existing vN.

    The canonical metadata is checked by repository tests. Comparing its actual
    contents avoids rebuilding unrelated families when a generator or workflow
    changes, or when only one family's entries in a shared JSON file change.
    Weekly/manual audits still explicitly select --all and use unique audit tags.
    """
    variants = load_variants(catalog)
    names = list(dict.fromkeys(item["name"] for item in variants))
    if metadata is None:
        metadata = json.loads((ROOT / "published-images.json").read_text())
    current = metadata_by_name(metadata)
    previous = metadata_by_name(previous_metadata)
    if set(current) != set(names):
        raise ValueError("published metadata families do not match the image matrix")
    selected = []
    for name in names:
        expected_refs = {
            f"ghcr.io/labpod/{name}:{item['tag']}"
            for item in variants if item["name"] == name
        }
        if set(published_refs(current[name])) != expected_refs:
            raise ValueError(f"published metadata refs do not match the image matrix: {name}")
        if current[name] == previous.get(name):
            continue
        if name in previous:
            old_prefix = release_prefix([
                {"tag": ref.rsplit(":", 1)[1]} for ref in published_refs(previous[name])
            ])
            new_prefix = release_prefix([item for item in variants if item["name"] == name])
            if int(new_prefix[1:]) <= int(old_prefix[1:]):
                raise ValueError(f"advance the immutable release version for changed family: {name}")
        selected.append(name)
    return scope_for_names(selected, variants)


def base_metadata(commit):
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        raise ValueError("publication base must be a full commit SHA")
    return json.loads(subprocess.check_output(
        ["git", "show", f"{commit}:published-images.json"], cwd=ROOT, text=True
    ))


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="select every variant")
    group.add_argument("--paths-file", type=Path, help="newline-delimited changed paths")
    group.add_argument(
        "--publish-changes-from",
        help="publish only families changed since this full commit SHA",
    )
    args = parser.parse_args()

    if args.publish_changes_from:
        scope = publication_scope(base_metadata(args.publish_changes_from))
    else:
        paths = () if args.all else args.paths_file.read_text().splitlines()
        scope = release_scope(paths, force_all=args.all)
    print(f"release_required={scope['release_required']}")
    print("variant_matrix=" + json.dumps(scope["variant_matrix"], separators=(",", ":")))
    print("package_matrix=" + json.dumps(scope["package_matrix"], separators=(",", ":")))


if __name__ == "__main__":
    main()
