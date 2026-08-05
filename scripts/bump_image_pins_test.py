import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("bump-image-pins.py")
SPEC = importlib.util.spec_from_file_location("bump_image_pins", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BumpImagePinsTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
