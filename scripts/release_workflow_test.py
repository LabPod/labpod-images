import json
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "images.yml"
MATRIX = ROOT / ".github" / "image-matrix.json"
EXPECTED_VARIANTS = {
    ("code-server", "latest"),
    ("pytorch-jupyter", "cu121"),
    ("pytorch-jupyter", "cu126"),
    ("pytorch-jupyter", "cu129"),
    ("tensorflow-jupyter", "cu125"),
    ("scipy-jupyter", "py312"),
    ("pytorch-demo", "cpu"),
    ("pytorch-demo", "cu121"),
    ("pytorch-demo", "cu126"),
    ("pytorch-demo", "cu129"),
}


class ReleaseWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text()
        cls.catalog = json.loads(MATRIX.read_text())
        cls.validate_section = cls.workflow.split("\n  promote:\n", 1)[0]
        cls.promote_section = cls.workflow.split("\n  promote:\n", 1)[1]

    def test_one_workflow_owns_all_stable_variants(self):
        variants = {
            (item["name"], item["tag"]) for item in self.catalog["variants"]
        }
        self.assertEqual(variants, EXPECTED_VARIANTS)
        self.assertEqual(
            self.workflow.count(
                "fromJSON(needs.changes.outputs.variant_matrix)"
            ),
            2,
        )
        self.assertIn(
            "fromJSON(needs.changes.outputs.package_matrix)", self.workflow
        )
        self.assertIn("scripts/release-matrix.py --paths-file", self.workflow)
        self.assertIn("scripts/release-matrix.py --all", self.workflow)
        for old_name in (
            "build-code-server-image.yml",
            "build-pytorch-demo-images.yml",
            "build-pytorch-images.yml",
            "build-scipy-images.yml",
            "build-tensorflow-images.yml",
        ):
            self.assertFalse((WORKFLOW.parent / old_name).exists(), old_name)

    def test_promotion_waits_for_complete_validation(self):
        self.assertIn("needs: [changes, validate]", self.promote_section)
        self.assertIn("needs.validate.result == 'success'", self.promote_section)
        self.assertIn("docker buildx imagetools create --tag", self.promote_section)
        self.assertIn("stable_digest", self.promote_section)
        self.assertIn("candidate_digest", self.promote_section)

    def test_promotion_compares_raw_manifest_digests(self):
        self.assertEqual(
            self.promote_section.count("docker buildx imagetools inspect --raw"), 2
        )
        self.assertNotIn(
            'docker buildx imagetools inspect "$CANDIDATE_REF"',
            self.promote_section,
        )
        self.assertNotIn(
            'docker buildx imagetools inspect "$STABLE_REF"', self.promote_section
        )

    def test_images_do_not_delete_legacy_uid_1000_accounts(self):
        for dockerfile in (ROOT / "images").glob("*/Dockerfile"):
            with self.subTest(dockerfile=dockerfile):
                contents = dockerfile.read_text()
                self.assertNotIn("sed -i -E '/^[^:]*:[^:]*:1000:/d'", contents)

    def test_package_access_is_checked_before_expensive_builds(self):
        self.assertIn("name: package access (${{ matrix.name }})", self.workflow)
        self.assertIn("needs: [changes, package-access]", self.validate_section)
        self.assertIn("needs.package-access.result == 'success'", self.validate_section)
        self.assertEqual(
            self.workflow.count("docker buildx imagetools create --tag"), 2
        )

    def test_candidates_and_stable_tags_are_anonymously_smoked(self):
        self.assertGreaterEqual(self.workflow.count("docker logout ghcr.io"), 2)
        self.assertIn('docker pull "$CANDIDATE_REF"', self.workflow)
        self.assertIn('docker pull "$STABLE_REF"', self.workflow)
        self.assertGreaterEqual(self.workflow.count("scripts/smoke-image.sh"), 2)

    def test_release_gate_always_reports(self):
        self.assertRegex(self.workflow, r"\n  gate:\n(?:.*\n)*?    if: always\(\)")
        self.assertIn("name: release gate", self.workflow)
        self.assertIn('[[ "$VALIDATE_RESULT" == success ]]', self.workflow)
        self.assertIn('[[ "$PROMOTE_RESULT" == success ]]', self.workflow)

    def test_images_are_linked_to_the_source_repository(self):
        self.assertIn(
            "labels: org.opencontainers.image.source=${{ github.server_url }}/${{ github.repository }}",
            self.workflow,
        )

    def test_smoke_script_rejects_missing_arguments(self):
        result = subprocess.run(
            ["bash", str(ROOT / "scripts" / "smoke-image.sh")],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage:", result.stderr)


if __name__ == "__main__":
    unittest.main()
