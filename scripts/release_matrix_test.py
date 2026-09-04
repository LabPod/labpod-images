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
        self.assertEqual(len(self.names_and_tags(scope)), 26)
        self.assertEqual(len(self.package_names(scope)), 13)

    def test_one_image_selects_only_its_variants(self):
        scope = MODULE.release_scope(["images/pytorch-jupyter/Dockerfile"])
        self.assertEqual(
            self.names_and_tags(scope),
            [
                ("pytorch-jupyter", "v2-cu121"),
                ("pytorch-jupyter", "v2-cu126"),
                ("pytorch-jupyter", "v2-cu129"),
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
            [("code-server", "v2"), ("tensorflow-jupyter", "v2-cu125")],
        )
        self.assertEqual(
            self.package_names(scope), ["code-server", "tensorflow-jupyter"]
        )

    def test_main_release_change_expands_to_the_atomic_full_catalog(self):
        scope = MODULE.release_scope(
            ["images/code-server/Dockerfile"], force_all_if_changed=True
        )
        self.assertEqual(len(self.names_and_tags(scope)), 26)
        self.assertEqual(len(self.package_names(scope)), 13)

        docs_only = MODULE.release_scope(
            ["images/code-server/README.md"], force_all_if_changed=True
        )
        self.assertEqual(docs_only["release_required"], "false")

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
                self.assertEqual(len(self.names_and_tags(scope)), 26)

    def test_catalog_not_its_generators_decides_a_release(self):
        # A generator change that moves no digest publishes nothing new, so
        # requiring a release only collides with the immutable-tag guard for tags
        # that already exist. When such a change does move a digest,
        # published_metadata_test forces the catalog to be regenerated in the
        # same commit, and the catalog is what selects the release.
        for generator in (
            "scripts/build-input-digest.py",
            "scripts/published-metadata.py",
            "scripts/release-matrix.py",
        ):
            with self.subTest(path=generator):
                scope = MODULE.release_scope([generator])
                self.assertEqual(scope["release_required"], "false")
                self.assertEqual(self.names_and_tags(scope), [])

        scope = MODULE.release_scope(["published-images.json"])
        self.assertEqual(scope["release_required"], "true")
        self.assertEqual(len(self.names_and_tags(scope)), 26)

    def test_release_tags_are_immutable_and_channels_are_explicit(self):
        scope = MODULE.release_scope(force_all=True)
        tags = self.names_and_tags(scope)
        self.assertNotIn(("code-server", "latest"), tags)
        for _, tag in tags:
            self.assertTrue(tag == "v2" or tag.startswith("v2-"), tag)

        expected_new = {
            ("miniforge-jupyterlab", "v2-cpu"),
            ("uv-jupyterlab", "v2-py312"),
            ("r-ml-jupyterlab", "v2-cpu"),
            ("rstudio-server", "v2-cpu"),
        }
        for name in (
            "llm-huggingface",
            "comfyui-stable-diffusion",
            "cuda-composite",
            "parallel-dev",
        ):
            expected_new.update(
                (name, f"v2-{channel}")
                for channel in ("cu121", "cu126", "cu129")
            )
        self.assertTrue(expected_new.issubset(set(tags)))

    def test_every_variant_exports_build_inputs_for_provenance(self):
        scope = MODULE.release_scope(force_all=True)
        for variant in scope["variant_matrix"]["include"]:
            with self.subTest(variant=variant):
                self.assertIn("build_input_args", variant)
                self.assertEqual(
                    variant["build_input_args"], variant["build_args"]
                )

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

    def test_default_tags_follow_an_advanced_release_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "matrix.json"
            source = MODULE.CATALOG.read_text().replace('"tag": "v2', '"tag": "v3')
            catalog.write_text(source)
            variants = MODULE.load_variants(catalog)
            names = list(dict.fromkeys(item["name"] for item in variants))
            for name in names:
                with self.subTest(name=name):
                    default_tag = MODULE.package_current_tag(name, variants)
                    self.assertTrue(default_tag == "v3" or default_tag.startswith("v3-"))
                    self.assertIn(
                        (name, default_tag),
                        {(item["name"], item["tag"]) for item in variants},
                    )


if __name__ == "__main__":
    unittest.main()
