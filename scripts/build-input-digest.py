#!/usr/bin/env python3
"""Compute LabPod's offline-reproducible build-input digest (v1)."""

import argparse
import hashlib
import json
import os
import re
import struct
from pathlib import Path


MAGIC = b"labpod.build-input.v1\0"
VARIABLE = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")


def parse_build_args(value):
    result = {}
    for line in value.splitlines():
        line = line.strip()
        if not line:
            continue
        if "=" not in line:
            raise ValueError(f"build argument has no '=': {line}")
        name, item = line.split("=", 1)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError(f"invalid build argument name: {name}")
        result[name] = item
    return dict(sorted(result.items()))


def frame(kind, key, value):
    fields = (kind.encode(), key.encode(), value)
    return b"".join(struct.pack(">Q", len(field)) + field for field in fields)


def dockerfile_raw_words(line):
    # Keep quotes and escapes: a literal "<<EOF" is not a heredoc operand.
    words = []
    start = index = 0
    quote = ""
    while index < len(line):
        char = line[index]
        if char == "\\" and quote != "'" and index + 1 < len(line):
            index += 1
        elif quote:
            if char == quote:
                quote = ""
        elif char in "'\"":
            quote = char
        elif char in " \t\r\n\v\f":
            if start < index:
                words.append(line[start:index])
            start = index + 1
        index += 1
    if quote:
        raise ValueError("unterminated quote in Dockerfile instruction")
    if start < len(line):
        words.append(line[start:])
    return words


def dockerfile_heredocs(line):
    if "<<" not in line:
        return []
    words = dockerfile_raw_words(line)
    if len(words) > 1 and words[0].upper() == "ONBUILD":
        words = words[1:]
    if len(words) < 2 or words[0].upper() not in {"RUN", "COPY", "ADD"}:
        return []
    args = words[1:]
    while args and args[0].startswith("--"):
        args = args[1:]
    try:
        json_args = json.loads(" ".join(args))
    except ValueError:
        pass
    else:
        if json_args is None or (
            isinstance(json_args, list) and all(isinstance(arg, str) for arg in json_args)
        ):
            return []
    docs = []
    for word in args:
        match = re.fullmatch(r"[0-9]*<<(-?)([^<]+)", word)
        if not match:
            continue
        raw = match[2]
        delimiter = ""
        quote = ""
        index = 0
        # Heredoc operands use shell backslash quoting even with # escape=`.
        while index < len(raw):
            char = raw[index]
            if char == "\\" and quote != "'" and index + 1 < len(raw):
                following = raw[index + 1]
                if quote == '"' and following not in '"$\\':
                    delimiter += char
                    index += 1
                    continue
                index += 1
                delimiter += following
            elif quote:
                if char == quote:
                    quote = ""
                else:
                    delimiter += char
            elif char in "'\"":
                quote = char
            else:
                delimiter += char
            index += 1
        docs.append((delimiter, match[1] == "-"))
    return docs


def logical_lines(text):
    physical = iter(text.replace("\r\n", "\n").removesuffix("\n").split("\n"))
    current = ""
    escape = "\\"
    continued = False
    directives = True
    for raw in physical:
        trimmed = raw.strip()
        if not continued and directives:
            key, separator, value = trimmed.removeprefix("#").strip().partition("=")
            key, value = key.strip().lower(), value.strip()
            if trimmed.startswith("#") and separator and key in {"escape", "syntax", "check"}:
                if key == "escape":
                    if value not in {"\\", "`"}:
                        raise ValueError(f"unsupported Dockerfile escape directive: {value!r}")
                    escape = value
                elif key == "syntax" and not value:
                    raise ValueError("dockerfile syntax directive missing image reference")
                continue
            directives = False
        if trimmed.startswith("#") or (continued and not trimmed):
            continue
        segment = raw.rstrip(" \t\r")
        continued = segment.endswith(escape)
        current += segment[:-1] if continued else raw
        if continued:
            continue
        logical = current.strip()
        current = ""
        yield logical
        for delimiter, strip_tabs in dockerfile_heredocs(logical):
            for candidate in physical:
                if strip_tabs:
                    candidate = candidate.lstrip("\t")
                if candidate == delimiter:
                    break
            else:
                raise ValueError(f"unterminated Dockerfile heredoc {delimiter!r}")
    if continued:
        raise ValueError("dockerfile has dangling line continuation")


def expand(value, variables):
    current = value
    for _ in range(len(variables) + 1):
        missing = []

        def replacement(match):
            name = match.group(1) or match.group(2)
            if name not in variables:
                missing.append(name)
                return match.group(0)
            return variables[name]

        following = VARIABLE.sub(replacement, current)
        if missing:
            raise ValueError(f"unresolved build argument in FROM: {missing[0]}")
        if following == current:
            match = VARIABLE.search(following)
            if match:
                raise ValueError(
                    f"cyclic build argument in FROM: {match.group(1) or match.group(2)}"
                )
            return following
        current = following
    raise ValueError("cyclic build argument expansion in FROM")


def normalize_image_ref(value):
    value = value.strip()
    if not value or any(character.isspace() for character in value):
        raise ValueError(f"invalid base image reference: {value!r}")
    if value.lower() == "scratch":
        return "scratch"
    name, suffix = value, ""
    if "@" in value:
        name, digest = value.rsplit("@", 1)
        suffix = "@" + digest
    else:
        slash = value.rfind("/")
        colon = value.rfind(":")
        if colon > slash:
            name, tag = value[:colon], value[colon + 1 :]
            suffix = ":" + tag
        else:
            suffix = ":latest"
    first = name.split("/", 1)[0]
    if "." not in first and ":" not in first and first != "localhost":
        name = "docker.io/" + (name if "/" in name else "library/" + name)
    return name + suffix


def base_images(dockerfile, build_args):
    variables = {}
    stages = set()
    bases = []
    saw_from = False
    for line in logical_lines(dockerfile.decode("utf-8")):
        fields = line.split(maxsplit=1)
        if not fields:
            continue
        instruction = fields[0].upper()
        body = fields[1].strip() if len(fields) > 1 else ""
        if instruction == "ARG" and not saw_from:
            name, _, default = body.partition("=")
            name = name.strip()
            variables[name] = build_args.get(name, default.strip())
            continue
        if instruction != "FROM":
            continue
        saw_from = True
        parts = body.split()
        while parts and parts[0].startswith("--"):
            parts.pop(0)
        if not parts:
            raise ValueError("FROM has no image reference")
        reference = expand(parts[0], variables)
        if reference.lower() not in stages:
            bases.append(normalize_image_ref(reference))
        if len(parts) >= 3 and parts[1].upper() == "AS":
            stages.add(parts[2].lower())
    if not bases:
        raise ValueError("Dockerfile has no external base image")
    return bases


def build_input_digest(context, dockerfile, build_args):
    context = Path(context).resolve()
    dockerfile = Path(dockerfile).resolve()
    try:
        dockerfile.relative_to(context)
    except ValueError as error:
        raise ValueError("Dockerfile must be inside build context") from error

    dockerfile_bytes = dockerfile.read_bytes()
    digest = hashlib.sha256()
    digest.update(MAGIC)
    digest.update(frame("dockerfile", "Dockerfile", dockerfile_bytes))

    entries = sorted(context.rglob("*"), key=lambda item: item.relative_to(context).as_posix())
    for entry in entries:
        if entry.is_symlink():
            raise ValueError(f"build context contains unsupported symlink: {entry}")
        if entry.is_dir():
            continue
        if not entry.is_file():
            raise ValueError(f"build context contains unsupported entry: {entry}")
        if entry == dockerfile:
            continue
        digest.update(frame("context", entry.relative_to(context).as_posix(), entry.read_bytes()))

    for name, value in sorted(build_args.items()):
        digest.update(frame("build-arg", name, value.encode()))
    for index, reference in enumerate(base_images(dockerfile_bytes, build_args)):
        digest.update(frame("base-image", str(index), reference.encode()))
    return "sha256:" + digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--dockerfile", type=Path, required=True)
    parser.add_argument("--build-args", default="")
    args = parser.parse_args()
    value = build_input_digest(
        args.context, args.dockerfile, parse_build_args(args.build_args)
    )
    print(value)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(f"digest={value}\n")


if __name__ == "__main__":
    main()
