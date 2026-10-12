"""Guard the dependency boundary exercised by the offline image build smoke."""
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
IMAGE = ROOT / "images" / "llm-huggingface"


class HuggingFaceDependenciesTest(unittest.TestCase):
    def test_interdependent_runtime_packages_are_exactly_pinned(self):
        lines = (IMAGE / "requirements.txt").read_text().splitlines()
        requirements = [line for line in lines if line and not line.startswith("#")]
        pins = dict(line.split("==") for line in requirements)
        self.assertEqual(set(pins), {"transformers", "peft", "trl", "accelerate", "bitsandbytes"})
        for package, version in pins.items():
            with self.subTest(package=package):
                self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        self.assertEqual(pins["transformers"], "5.18.0")

    def test_application_install_cannot_replace_the_cuda_pinned_torch(self):
        text = (IMAGE / "Dockerfile").read_text().replace("\\\n", " ")
        installs = [line for line in text.splitlines() if line.startswith("RUN uv pip install")]
        self.assertEqual(len(installs), 2)
        self.assertIn('"torch==${TORCH_VERSION}+${TORCH_CUDA}"', installs[1])
        self.assertIn('-r /tmp/huggingface-requirements.txt', installs[1])
        self.assertNotRegex(installs[1], r"\s(?:transformers|peft|trl|accelerate|bitsandbytes)\s")

    def test_image_build_checks_real_generation_and_training_offline(self):
        text = (IMAGE / "Dockerfile").read_text().replace("\\\n", " ")
        self.assertIn('COPY runtime-smoke.py /usr/local/lib/labpod/huggingface-smoke.py', text)
        self.assertIn('HF_HUB_OFFLINE=1', text)
        self.assertIn('EXPECTED_TORCH_VERSION="${TORCH_VERSION}"', text)
        self.assertIn('EXPECTED_TORCH_CUDA="${TORCH_CUDA}"', text)
        self.assertIn('python /usr/local/lib/labpod/huggingface-smoke.py', text)


if __name__ == "__main__":
    unittest.main()
