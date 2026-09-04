import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = Path(__file__).with_name("published-metadata.py")
SPEC = importlib.util.spec_from_file_location("published_metadata", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PublishedMetadataTest(unittest.TestCase):
    def test_checked_in_metadata_matches_canonical_inputs(self):
        expected = MODULE.published_metadata()
        actual = json.loads((ROOT / "published-images.json").read_text())
        self.assertEqual(actual, expected)

    def test_cuda_default_is_cu126_and_variants_omit_default(self):
        metadata = MODULE.published_metadata()
        by_name = {item["name"]: item for item in metadata["images"]}
        for name in (
            "llm-huggingface",
            "comfyui-stable-diffusion",
            "cuda-composite",
            "parallel-dev",
        ):
            published = by_name[name]["published"]
            self.assertTrue(published["ref"].endswith(":v2-cu126"))
            self.assertEqual(
                {item["ref"].rsplit(":", 1)[1] for item in published["variants"]},
                {"v2-cu121", "v2-cu129"},
            )
            for variant in published["variants"]:
                tag = variant["ref"].rsplit(":", 1)[1]
                self.assertEqual(
                    variant["build_args"], by_name[name]["variant_build_args"][tag]
                )


if __name__ == "__main__":
    unittest.main()
