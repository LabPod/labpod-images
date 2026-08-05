import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("release-matrix.py")
SPEC = importlib.util.spec_from_file_location("release_matrix", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ReleaseMatrixTest(unittest.TestCase):
    def names_and_tags(self, scope):
        return [
            (variant["name"], variant["tag"])
            for variant in scope["variant_matrix"]["include"]
        ]

    def package_names(self, scope):
        return [item["name"] for item in scope["package_matrix"]["include"]]

    def test_full_scope_selects_all_variants_and_packages(self):
        scope = MODULE.release_scope(force_all=True)
        self.assertEqual(scope["release_required"], "true")
        self.assertEqual(len(self.names_and_tags(scope)), 10)
        self.assertEqual(len(self.package_names(scope)), 5)

    def test_one_image_selects_only_its_variants(self):
        scope = MODULE.release_scope(["images/pytorch-jupyter/Dockerfile"])
        self.assertEqual(
            self.names_and_tags(scope),
            [
                ("pytorch-jupyter", "cu121"),
                ("pytorch-jupyter", "cu126"),
                ("pytorch-jupyter", "cu129"),
            ],
        )
        self.assertEqual(self.package_names(scope), ["pytorch-jupyter"])

    def test_multiple_images_select_union_in_catalog_order(self):
        scope = MODULE.release_scope(
            [
                "images/code-server/Dockerfile",
                "images/tensorflow-jupyter/Dockerfile",
            ]
        )
        self.assertEqual(
            self.names_and_tags(scope),
            [("code-server", "latest"), ("tensorflow-jupyter", "cu125")],
        )
        self.assertEqual(
            self.package_names(scope), ["code-server", "tensorflow-jupyter"]
        )

    def test_docs_and_test_changes_select_nothing(self):
        scope = MODULE.release_scope(
            [
                "README.md",
                "images/code-server/README.md",
                "scripts/release_workflow_test.py",
                ".github/dependabot.yml",
            ]
        )
        self.assertEqual(scope["release_required"], "false")
        self.assertEqual(self.names_and_tags(scope), [])
        self.assertEqual(self.package_names(scope), [])

    def test_shared_release_contract_selects_all(self):
        for path in MODULE.FULL_MATRIX_PATHS:
            with self.subTest(path=path):
                scope = MODULE.release_scope([path])
                self.assertEqual(len(self.names_and_tags(scope)), 10)

    def test_unknown_image_path_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "no release-matrix entry"):
            MODULE.release_scope(["images/new-image/Dockerfile"])

    def test_duplicate_catalog_variant_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "matrix.json"
            variant = {"name": "code-server", "tag": "latest"}
            catalog.write_text(json.dumps({"variants": [variant, variant]}))
            with self.assertRaisesRegex(ValueError, "duplicate"):
                MODULE.load_variants(catalog)


if __name__ == "__main__":
    unittest.main()
