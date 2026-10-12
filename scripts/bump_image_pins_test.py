import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("bump-image-pins.py")
SPEC = importlib.util.spec_from_file_location("bump_image_pins", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BumpImagePinsTest(unittest.TestCase):
    @contextlib.contextmanager
    def pin_workspace(self, variants, code_server_versions=None):
        """Run the real entry point with isolated files and no network calls."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "scripts" / "bump-image-pins.py"
            script.parent.mkdir()
            script.write_text(MODULE_PATH.read_text())
            spec = importlib.util.spec_from_file_location("isolated_bump_pins", script)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.IMAGE_MATRIX.parent.mkdir()
            module.IMAGE_MATRIX.write_text(json.dumps({"variants": variants}, indent=2) + "\n")
            code_server_versions = code_server_versions or {}
            for path in module.CODE_SERVER_DOCKERFILES:
                path.parent.mkdir(parents=True)
                version = code_server_versions.get(path.parent.name, "1.2.3")
                path.write_text(
                    f"ARG CODE_SERVER_VERSION={version}\n"
                    f"ARG CODE_SERVER_SHA256_AMD64={'a' * 64}\n"
                    f"ARG CODE_SERVER_SHA256_ARM64={'b' * 64}\n"
                )
            with (
                mock.patch.object(module, "latest_stable_pypi", return_value="1.0.0") as pypi,
                mock.patch.object(module, "latest_github_release", return_value="v0.3.51"),
                mock.patch.object(module, "latest_code_server", return_value="1.2.3"),
                mock.patch.object(module, "sha256_of", side_effect=["c" * 64, "d" * 64]),
                mock.patch.object(module.subprocess, "run") as run,
                mock.patch.dict(module.os.environ, {}, clear=True),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                yield module, root, pypi, run

    def test_main_bumps_only_families_with_material_pin_updates(self):
        variants = [
            {"name": "llm-huggingface", "tag": "v2-cu121", "torch": "2.5.1"},
            {"name": "llm-huggingface", "tag": "v2-cu126", "torch": "2.8.0"},
            {"name": "pytorch-jupyter", "tag": "v2-cu121", "torch": "2.5.1"},
            {"name": "code-server", "tag": "v2"},
        ]
        with self.pin_workspace(variants) as (module, root, pypi, run):
            pypi.side_effect = lambda package: "2.9.0" if package == "torch" else "1.0.0"
            self.assertEqual(module.main(), 0)
            updated = json.loads(module.IMAGE_MATRIX.read_text())["variants"]
            self.assertEqual(
                [item["tag"] for item in updated],
                ["v3-cu121", "v3-cu126", "v2-cu121", "v2"],
            )
            self.assertEqual(updated[0]["torch"], "2.5.1")
            self.assertEqual(updated[1]["torch"], "2.9.0")
            run.assert_called_once()

    def test_stable_versions_sort_numerically(self):
        self.assertTrue(MODULE.is_stable("12.10.3"))
        self.assertFalse(MODULE.is_stable("12.10.3rc1"))
        self.assertGreater(MODULE.version_key("12.10"), MODULE.version_key("12.9"))

    def test_newest_pinned_reads_only_the_requested_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "workflow.yml"
            path.write_text("torch: 2.8.0\ntorch: 2.10.0\ntorchvision: 99.0.0\n")
            self.assertEqual(MODULE.newest_pinned([path], "torch"), "2.10.0")

    def test_replace_in_updates_matching_pins_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "workflow.yml"
            path.write_text("torch: 2.8.0\ntorchvision: 0.23.0\n")
            changed = MODULE.replace_in(
                [path], "torch", "2.8.0", "2.9.0", root=Path(directory)
            )
            self.assertEqual(changed, ["workflow.yml"])
            self.assertEqual(path.read_text(), "torch: 2.9.0\ntorchvision: 0.23.0\n")

    def test_catalog_pin_helpers_support_quoted_json_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "matrix.json"
            path.write_text('{"torch": "2.8.0", "torchvision": "0.23.0"}\n')
            self.assertEqual(MODULE.newest_pinned([path], "torch"), "2.8.0")
            MODULE.replace_in(
                [path], "torch", "2.8.0", "2.9.0", root=Path(directory)
            )
            self.assertIn('"torch": "2.9.0"', path.read_text())

    def test_code_server_update_changes_version_and_both_digests(self):
        old_amd64 = "a" * 64
        old_arm64 = "b" * 64
        new_amd64 = "c" * 64
        new_arm64 = "d" * 64
        source = (
            "ARG CODE_SERVER_VERSION=1.2.3\n"
            f"ARG CODE_SERVER_SHA256_AMD64={old_amd64}\n"
            f"ARG CODE_SERVER_SHA256_ARM64={old_arm64}\n"
        )
        updated = MODULE.update_code_server_dockerfile(
            source, "2.0.0", new_amd64, new_arm64
        )
        self.assertIn("CODE_SERVER_VERSION=2.0.0", updated)
        self.assertIn(f"CODE_SERVER_SHA256_AMD64={new_amd64}", updated)
        self.assertIn(f"CODE_SERVER_SHA256_ARM64={new_arm64}", updated)
        self.assertNotIn(old_amd64, updated)
        self.assertNotIn(old_arm64, updated)

    def test_release_tag_prefix_advances_without_changing_channels(self):
        source = json.dumps({"variants": [
            {"name": "code-server", "tag": "v2"},
            {"name": "llm-huggingface", "tag": "v3-cu121"},
            {"name": "llm-huggingface", "tag": "v3-cu126"},
        ]})
        updated, releases = MODULE.advance_release_tags(source, {"llm-huggingface"})
        self.assertEqual(releases, {"llm-huggingface": (3, 4)})
        self.assertEqual(
            [item["tag"] for item in json.loads(updated)["variants"]],
            ["v2", "v4-cu121", "v4-cu126"],
        )

    def test_selected_families_advance_from_their_own_versions(self):
        source = json.dumps({"variants": [
            {"name": "code-server", "tag": "v2"},
            {"name": "llm-huggingface", "tag": "v9-cu126"},
        ]})
        updated, releases = MODULE.advance_release_tags(
            source, {"llm-huggingface", "code-server"}
        )
        self.assertEqual(releases, {"code-server": (2, 3), "llm-huggingface": (9, 10)})
        self.assertEqual(
            [item["tag"] for item in json.loads(updated)["variants"]],
            ["v3", "v10-cu126"],
        )

    def test_mixed_prefixes_within_any_family_are_rejected(self):
        source = json.dumps({"variants": [
            {"name": "code-server", "tag": "v2"},
            {"name": "llm-huggingface", "tag": "v2-cu121"},
            {"name": "llm-huggingface", "tag": "v3-cu126"},
        ]})
        with self.assertRaisesRegex(ValueError, "llm-huggingface.*one.*vN"):
            MODULE.advance_release_tags(source, {"code-server"})

    def test_invalid_release_tags_are_rejected_even_for_unchanged_families(self):
        for tag in ("latest", "v2-", "v2-cu 121", "v2-cu121\n", None):
            with self.subTest(tag=tag):
                source = json.dumps({"variants": [
                    {"name": "code-server", "tag": "v2"},
                    {"name": "llm-huggingface", "tag": tag},
                ]})
                with self.assertRaisesRegex(ValueError, "invalid immutable release tag"):
                    MODULE.advance_release_tags(source, {"code-server"})

    def test_unknown_changed_family_is_rejected(self):
        source = '{"variants":[{"name":"code-server","tag":"v2"}]}'
        with self.assertRaisesRegex(ValueError, "missing-image"):
            MODULE.advance_release_tags(source, {"missing-image"})

    def test_finalizing_pin_changes_regenerates_published_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            matrix = root / ".github" / "image-matrix.json"
            matrix.parent.mkdir(parents=True)
            matrix.write_text(json.dumps({"variants": [
                {"name": "llm-huggingface", "tag": "v3-cu121", "torch": "2.5.1"},
                {"name": "llm-huggingface", "tag": "v3-cu126", "torch": "2.8.0"},
                {"name": "code-server", "tag": "v2"},
            ]}))
            before = MODULE.snapshot_pin_inputs(matrix, [], root)
            matrix.write_text(matrix.read_text().replace('"2.8.0"', '"2.9.0"'))
            changes = ["torch 1.0 -> 2.0"]
            with mock.patch.object(MODULE.subprocess, "run") as run:
                MODULE.finalize_pin_changes(
                    changes, before, image_matrix=matrix, dockerfiles=[], root=root
                )
            self.assertEqual(
                [item["tag"] for item in json.loads(matrix.read_text())["variants"]],
                ["v4-cu121", "v4-cu126", "v2"],
            )
            run.assert_called_once_with(
                [
                    sys.executable,
                    str(root / "scripts" / "published-metadata.py"),
                    "--write",
                ],
                cwd=root,
                check=True,
            )
            self.assertIn(
                "llm-huggingface release tags v3 -> v4 (.github/image-matrix.json)", changes
            )
            self.assertIn("regenerated published-images.json", changes)

    def test_main_bumps_only_the_dockerfile_carriers_actually_updated(self):
        variants = [
            {"name": "llm-huggingface", "tag": "v3-cu121"},
            {"name": "llm-huggingface", "tag": "v3-cu126"},
            {"name": "code-server", "tag": "v2"},
        ]
        with self.pin_workspace(variants, {"llm-huggingface": "1.0.0"}) as (
            module, root, pypi, run
        ):
            self.assertEqual(module.main(), 0)
            self.assertEqual(
                [item["tag"] for item in json.loads(module.IMAGE_MATRIX.read_text())["variants"]],
                ["v4-cu121", "v4-cu126", "v2"],
            )
            run.assert_called_once()

    def test_main_no_op_keeps_mixed_family_tags_and_skips_metadata(self):
        variants = [
            {"name": "llm-huggingface", "tag": "v3-cu121"},
            {"name": "code-server", "tag": "v2"},
        ]
        with self.pin_workspace(variants) as (module, root, pypi, run):
            before = module.IMAGE_MATRIX.read_bytes()
            self.assertEqual(module.main(), 0)
            self.assertEqual(module.IMAGE_MATRIX.read_bytes(), before)
            run.assert_not_called()

    def test_main_multiple_pin_updates_bump_each_affected_family_once(self):
        variants = [
            {"name": "llm-huggingface", "tag": "v3-cu126", "torch": "2.8.0"},
            {
                "name": "pytorch-jupyter", "tag": "v2-cu126",
                "torch": "2.8.0", "torchvision": "0.23.0",
            },
            {
                "name": "comfyui-stable-diffusion", "tag": "v2-cu126",
                "torch": "2.8.0", "torchvision": "0.23.0",
                "torchaudio": "2.8.0", "comfyui_ref": "v0.3.50",
            },
            {"name": "tensorflow-jupyter", "tag": "v7-cu125", "tf_version": "2.21.0"},
            {"name": "code-server", "tag": "v2"},
        ]
        with self.pin_workspace(variants) as (module, root, pypi, run):
            pypi.side_effect = {
                "torch": "2.9.0", "torchvision": "0.24.0",
                "torchaudio": "2.9.0", "tensorflow": "2.22.0",
            }.__getitem__
            self.assertEqual(module.main(), 0)
            updated = json.loads(module.IMAGE_MATRIX.read_text())["variants"]
            self.assertEqual(
                [item["tag"] for item in updated],
                ["v4-cu126", "v3-cu126", "v3-cu126", "v8-cu125", "v2"],
            )
            self.assertEqual(updated[2]["comfyui_ref"], "v0.3.51")
            self.assertEqual(updated[2]["torchaudio"], "2.9.0")
            self.assertEqual(updated[3]["tf_version"], "2.22.0")
            run.assert_called_once()

    def test_main_rejects_invalid_family_versions_before_editing_pins(self):
        variants = [
            {"name": "llm-huggingface", "tag": "v2-cu121", "torch": "2.5.1"},
            {"name": "llm-huggingface", "tag": "v3-cu126", "torch": "2.8.0"},
        ]
        with self.pin_workspace(variants) as (module, root, pypi, run):
            original = module.IMAGE_MATRIX.read_bytes()
            with self.assertRaisesRegex(ValueError, "llm-huggingface.*one.*vN"):
                module.main()
            self.assertEqual(module.IMAGE_MATRIX.read_bytes(), original)
            pypi.assert_not_called()
            run.assert_not_called()

    def test_summary_alone_does_not_cause_a_release_bump(self):
        variants = [{"name": "code-server", "tag": "v2"}]
        with self.pin_workspace(variants) as (module, root, pypi, run):
            before = module.snapshot_pin_inputs()
            original = module.IMAGE_MATRIX.read_bytes()
            changes = ["a reported change without any material input changes"]
            module.finalize_pin_changes(changes, before)
            self.assertEqual(module.IMAGE_MATRIX.read_bytes(), original)
            self.assertEqual(len(changes), 1)
            run.assert_not_called()

    def test_all_code_server_carriers_share_one_complete_pin(self):
        pins = set()
        for path in MODULE.CODE_SERVER_DOCKERFILES:
            text = path.read_text()
            version = MODULE.re.search(r"CODE_SERVER_VERSION=([0-9.]+)", text)
            amd64 = MODULE.re.search(r"CODE_SERVER_SHA256_AMD64=([0-9a-f]{64})", text)
            arm64 = MODULE.re.search(r"CODE_SERVER_SHA256_ARM64=([0-9a-f]{64})", text)
            self.assertIsNotNone(version, path)
            self.assertIsNotNone(amd64, path)
            self.assertIsNotNone(arm64, path)
            pins.add((version.group(1), amd64.group(1), arm64.group(1)))
        self.assertEqual(len(pins), 1)

    def test_new_images_are_covered_by_pin_automation(self):
        dependabot = (MODULE.ROOT / ".github" / "dependabot.yml").read_text()
        for name in (
            "miniforge-jupyterlab",
            "uv-jupyterlab",
            "r-ml-jupyterlab",
            "rstudio-server",
            "llm-huggingface",
            "comfyui-stable-diffusion",
            "cuda-composite",
            "parallel-dev",
        ):
            self.assertIn(f"/images/{name}", dependabot)
        self.assertIn("torchaudio", MODULE.IMAGE_MATRIX.read_text())
        self.assertIn("comfyui_ref", MODULE.IMAGE_MATRIX.read_text())


if __name__ == "__main__":
    unittest.main()
