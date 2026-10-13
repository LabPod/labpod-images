import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('buildx_smoke', ROOT / 'scripts/buildx-smoke.py')
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class BuildxSmokeTest(unittest.TestCase):
    def test_builder_must_be_running_and_support_amd64(self):
        nodes = [{'status': 'running', 'platforms': 'linux/amd64,linux/arm64'}]
        smoke.verify_builder('builder-test', 'docker-container', 'linux/amd64', nodes)
        for changes in [('', 'docker-container', 'linux/amd64', nodes),
                        ('builder-test', 'docker', 'linux/amd64', nodes),
                        ('builder-test', 'docker-container', 'linux/arm64', nodes),
                        ('builder-test', 'docker-container', 'linux/amd64', []),
                        ('builder-test', 'docker-container', 'linux/amd64', [{'status': 'stopped'}])]:
            with self.assertRaises(ValueError):
                smoke.verify_builder(*changes)

    def test_metadata_matches_loaded_image_and_action_outputs(self):
        image_id = 'sha256:' + 'a' * 64
        digest = 'sha256:' + 'b' * 64
        metadata = {'containerimage.config.digest': image_id, 'containerimage.digest': digest}
        smoke.verify_image(image_id, digest, metadata, image_id)
        for args in [(image_id, digest, {}, image_id),
                     (image_id, digest, metadata, digest),
                     ('bad-id', digest, metadata, image_id),
                     (image_id, image_id, metadata, image_id)]:
            with self.assertRaises(ValueError):
                smoke.verify_image(*args)

    def test_one_off_workflow_is_no_publish_and_uses_production_pins(self):
        workflow = (ROOT / '.github/workflows/pr19-buildx-smoke.yml').read_text()
        production = (ROOT / '.github/workflows/images.yml').read_text()
        self.assertIn("github.event_name == 'pull_request' && github.event.pull_request.number == 19", workflow)
        self.assertIn('contents: read', workflow)
        self.assertIn('persist-credentials: false', workflow)
        self.assertIn('push: false', workflow)
        self.assertIn('load: true', workflow)
        self.assertIn('network: none', workflow)
        self.assertIn('docker run --pull never --network none --rm', workflow)
        self.assertNotIn('packages: write', workflow)
        self.assertNotIn('docker/login-action', workflow)
        self.assertNotIn('workflow_dispatch', workflow)
        self.assertNotIn('schedule:', workflow)
        self.assertNotIn('cleanup: false', workflow)
        for line in workflow.splitlines():
            if 'uses: docker/' in line:
                self.assertIn(line.strip(), production)


if __name__ == '__main__':
    unittest.main()
