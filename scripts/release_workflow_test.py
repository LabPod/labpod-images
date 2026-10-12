import json
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "images.yml"
MATRIX = ROOT / ".github" / "image-matrix.json"
EXPECTED_VARIANTS = {
    ("code-server", "v2"),
    ("pytorch-jupyter", "v2-cu121"),
    ("pytorch-jupyter", "v2-cu126"),
    ("pytorch-jupyter", "v2-cu129"),
    ("tensorflow-jupyter", "v2-cu125"),
    ("scipy-jupyter", "v2-py312"),
    ("pytorch-demo", "v2-cpu"),
    ("pytorch-demo", "v2-cu121"),
    ("pytorch-demo", "v2-cu126"),
    ("pytorch-demo", "v2-cu129"),
}
EXPECTED_NEW_IMAGES = {
    "miniforge-jupyterlab",
    "uv-jupyterlab",
    "r-ml-jupyterlab",
    "rstudio-server",
    "llm-huggingface",
    "comfyui-stable-diffusion",
    "cuda-composite",
    "parallel-dev",
}
EXPECTED_VARIANTS.update(
    {
        ("miniforge-jupyterlab", "v2-cpu"),
        ("uv-jupyterlab", "v2-py312"),
        ("r-ml-jupyterlab", "v2-cpu"),
        ("rstudio-server", "v2-cpu"),
    }
)
EXPECTED_VARIANTS.update(
    (name, f"{'v3' if name == 'llm-huggingface' else 'v2'}-{channel}")
    for name in (
        "llm-huggingface",
        "comfyui-stable-diffusion",
        "cuda-composite",
        "parallel-dev",
    )
    for channel in ("cu121", "cu126", "cu129")
)


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
            3,
        )
        self.assertIn(
            "fromJSON(needs.changes.outputs.package_matrix)", self.workflow
        )
        self.assertIn('scripts/release-matrix.py --publish-changes-from "$base_sha"', self.workflow)
        self.assertNotIn("--all-if-paths-file", self.workflow)
        self.assertIn("scripts/release-matrix.py --all", self.workflow)
        for old_name in (
            "build-code-server-image.yml",
            "build-pytorch-demo-images.yml",
            "build-pytorch-images.yml",
            "build-scipy-images.yml",
            "build-tensorflow-images.yml",
        ):
            self.assertFalse((WORKFLOW.parent / old_name).exists(), old_name)

    def test_pr_and_push_select_the_same_changed_release_families(self):
        changes = self.workflow.split("\n  changes:\n", 1)[1].split("\n  package-access:\n", 1)[0]
        self.assertNotIn("--paths-file", changes)
        self.assertEqual(changes.count('--publish-changes-from "$base_sha"'), 1)
        self.assertIn('base_sha=$PR_BASE_SHA', changes)

    def test_promotion_waits_for_complete_validation(self):
        self.assertIn("needs: [changes, validate_release]", self.promote_section)
        self.assertIn("needs.validate_release.result == 'success'", self.promote_section)
        self.assertIn("docker buildx imagetools create --tag", self.promote_section)
        self.assertIn("stable_digest", self.promote_section)
        self.assertIn("candidate_digest", self.promote_section)

    def test_promotion_compares_raw_manifest_digests(self):
        self.assertEqual(
            self.promote_section.count(
                'docker buildx imagetools inspect --raw "$CANDIDATE_REF"'
            ),
            1,
        )
        self.assertEqual(
            self.promote_section.count(
                'docker buildx imagetools inspect --raw "$STABLE_REF"'
            ),
            2,
        )
        self.assertIn(
            'candidate_digest=$(docker buildx imagetools inspect --raw "$CANDIDATE_REF"',
            self.promote_section,
        )
        self.assertIn(
            'stable_digest=$(docker buildx imagetools inspect --raw "$STABLE_REF"',
            self.promote_section,
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
        self.assertIn('docker buildx build --file - --tag "$PROBE_REF" --push .', self.workflow)
        self.assertNotIn(
            'docker buildx build --file - --tag "$PROBE_REF" --push -',
            self.workflow,
        )

    def test_package_access_proves_anonymous_pull_before_expensive_builds(self):
        package_access = self.workflow.split("\n  package-access:\n", 1)[1].split(
            "\n  validate_pr:\n", 1
        )[0]
        self.assertIn("docker logout ghcr.io", package_access)
        self.assertIn('docker pull "$PROBE_REF"', package_access)

    def test_candidates_and_stable_tags_are_anonymously_smoked(self):
        self.assertGreaterEqual(self.workflow.count("docker logout ghcr.io"), 2)
        self.assertIn('docker pull "$CANDIDATE_REF"', self.workflow)
        self.assertIn('docker pull "$STABLE_REF"', self.workflow)
        self.assertGreaterEqual(self.workflow.count("scripts/smoke-image.sh"), 2)

    def test_release_gate_always_reports(self):
        self.assertRegex(self.workflow, r"\n  gate:\n(?:.*\n)*?    if: always\(\)")
        self.assertIn("name: release gate", self.workflow)
        self.assertIn('[[ "$VALIDATE_PR_RESULT" == success ]]', self.workflow)
        self.assertIn('[[ "$VALIDATE_RELEASE_RESULT" == success ]]', self.workflow)
        self.assertIn('[[ "$PROMOTE_RESULT" == success ]]', self.workflow)

    def test_images_are_linked_to_the_source_repository(self):
        self.assertIn(
            "org.opencontainers.image.source=${{ github.server_url }}/${{ github.repository }}",
            self.workflow,
        )

    def test_build_input_digest_is_computed_labeled_and_smoked(self):
        self.assertIn("scripts/build-input-digest.py", self.validate_section)
        self.assertIn("matrix.build_input_args", self.validate_section)
        self.assertIn(
            "ai.labpod.image.build-input-digest=${{ steps.build_input.outputs.digest }}",
            self.validate_section,
        )
        self.assertIn("EXPECTED_BUILD_INPUT_DIGEST", self.workflow)
        self.assertIn("ai.labpod.image.build-input-digest", self.workflow)

    def test_release_tags_are_never_overwritten_with_different_bytes(self):
        self.assertIn("Check release tag availability", self.validate_section)
        self.assertIn("release tag already exists; advance the vN prefix", self.validate_section)
        self.assertIn("docker buildx imagetools inspect \"$STABLE_REF\"", self.promote_section)
        self.assertIn("points at different bytes; bump the release tag", self.promote_section)

    def test_promotion_retry_accepts_the_same_validated_bytes(self):
        self.assertIn(
            'if [[ "$stable_digest" == "$candidate_digest" ]]',
            self.promote_section,
        )
        self.assertIn(
            "already points at the validated candidate; promotion is complete",
            self.promote_section,
        )

    def test_weekly_rebuilds_use_unique_audit_tags(self):
        self.assertIn("REBUILD_REF", self.workflow)
        self.assertIn("rebuild-${REBUILD_DATE}-${RUN_ID}-${RUN_ATTEMPT}", self.workflow)

    def test_manual_stable_promotion_is_an_explicit_recovery_mode(self):
        self.assertIn("promote_stable:", self.workflow)
        self.assertIn("type: boolean", self.workflow)
        self.assertIn("default: false", self.workflow)
        self.assertIn("PROMOTE_STABLE: ${{ inputs.promote_stable }}", self.workflow)
        self.assertIn(
            "github.event_name == 'workflow_dispatch' && inputs.promote_stable",
            self.promote_section,
        )
        self.assertIn(
            "github.event_name == 'workflow_dispatch' && inputs.promote_stable",
            self.workflow.split("\n  gate:\n", 1)[1],
        )

    def test_all_new_image_sources_have_smoke_contracts(self):
        matrix_names = {item["name"] for item in self.catalog["variants"]}
        self.assertTrue(EXPECTED_NEW_IMAGES.issubset(matrix_names))
        smoke = (ROOT / "scripts" / "smoke-image.sh").read_text()
        for name in EXPECTED_NEW_IMAGES:
            with self.subTest(name=name):
                self.assertTrue((ROOT / "images" / name / "Dockerfile").is_file())
                self.assertIn(name, smoke)

    def test_runtime_smoke_uses_an_unprivileged_workspace_identity(self):
        smoke = (ROOT / "scripts" / "smoke-image.sh").read_text()
        self.assertIn("runtime_uid=${SMOKE_UID:-65534}", smoke)
        self.assertIn("runtime_gid=${SMOKE_GID:-65534}", smoke)
        self.assertIn('--user "$runtime_uid:$runtime_gid"', smoke)
        self.assertIn('-e USER=nobody -e HOME=/tmp', smoke)
        self.assertIn('--tmpfs /work:rw,mode=1777', smoke)
        self.assertIn('test -w "$HOME" && test -w /work', smoke)

    def test_runtime_smoke_rejects_retired_ttyd_binary(self):
        smoke = (ROOT / "scripts" / "smoke-image.sh").read_text()
        self.assertIn("command -v ttyd", smoke)
        self.assertIn("image still ships ttyd", smoke)

    def test_parallel_dev_uses_redistributable_code_server(self):
        dockerfile = (ROOT / "images" / "parallel-dev" / "Dockerfile").read_text()
        self.assertIn("code-server", dockerfile)
        self.assertNotIn("update.code.visualstudio.com", dockerfile)

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
