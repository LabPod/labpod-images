#!/usr/bin/env python3
"""Select the image release matrix affected by a repository change set."""

import argparse
import json
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / ".github" / "image-matrix.json"
FULL_MATRIX_PATHS = {
    ".github/image-matrix.json",
    ".github/workflows/images.yml",
    "scripts/release-matrix.py",
    "scripts/smoke-image.sh",
}
PACKAGE_CURRENT_TAG = {
    "code-server": "latest",
    "pytorch-jupyter": "cu126",
    "tensorflow-jupyter": "cu125",
    "scipy-jupyter": "py312",
    "pytorch-demo": "cpu",
}


def load_variants(catalog=CATALOG):
    variants = json.loads(catalog.read_text())["variants"]
    keys = [(variant["name"], variant["tag"]) for variant in variants]
    if len(keys) != len(set(keys)):
        raise ValueError("image matrix contains duplicate name/tag variants")
    unknown_packages = {name for name, _ in keys} - PACKAGE_CURRENT_TAG.keys()
    if unknown_packages:
        raise ValueError(
            "image matrix lacks package-access metadata for: "
            + ", ".join(sorted(unknown_packages))
        )
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
    return ""


def workflow_variant(variant):
    name = variant["name"]
    return {
        "name": name,
        "repository": f"ghcr.io/labpod/{name}",
        "tag": variant["tag"],
        "context": f"images/{name}",
        "dockerfile": f"images/{name}/Dockerfile",
        "kind": name,
        "build_args": build_args(variant),
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


def release_scope(paths=(), force_all=False, catalog=CATALOG):
    variants = load_variants(catalog)
    names = select_variant_names(paths, variants, force_all=force_all)
    selected = [variant for variant in variants if variant["name"] in names]
    variant_matrix = {"include": [workflow_variant(item) for item in selected]}
    package_matrix = {
        "include": [
            {
                "name": name,
                "repository": f"ghcr.io/labpod/{name}",
                "current_tag": PACKAGE_CURRENT_TAG[name],
            }
            for name in names
        ]
    }
    return {
        "release_required": "true" if selected else "false",
        "variant_matrix": variant_matrix,
        "package_matrix": package_matrix,
    }


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="select every variant")
    group.add_argument("--paths-file", type=Path, help="newline-delimited changed paths")
    args = parser.parse_args()

    paths = () if args.all else args.paths_file.read_text().splitlines()
    scope = release_scope(paths, force_all=args.all)
    print(f"release_required={scope['release_required']}")
    print("variant_matrix=" + json.dumps(scope["variant_matrix"], separators=(",", ":")))
    print("package_matrix=" + json.dumps(scope["package_matrix"], separators=(",", ":")))


if __name__ == "__main__":
    main()
