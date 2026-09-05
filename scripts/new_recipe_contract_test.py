import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def dockerfile(name):
    return (ROOT / "images" / name / "Dockerfile").read_text()


class NewRecipeContractTest(unittest.TestCase):
    def test_r_ml_preserves_build_verified_runtime_contract(self):
        text = dockerfile("r-ml-jupyterlab")
        for marker in (
            "max(1L, parallel::detectCores(), na.rm = TRUE)",
            "library(p, character.only = TRUE)",
            "uv pip install --python",
            "kernelspec list --json",
            'reticulate::py_config()',
            'reticulate::import("numpy")',
            "command -v jupyter",
            "command -v tensorboard",
        ):
            self.assertIn(marker, text)

    def test_managed_recipes_do_not_ship_ttyd(self):
        for path in (ROOT / "images").glob("*/*"):
            if path.name not in {"Dockerfile", "README.md"}:
                continue
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertNotIn("ttyd", path.read_text().lower())

    def test_pytorch_demo_description_does_not_advertise_retired_terminal(self):
        text = dockerfile("pytorch-demo")
        description = next(
            line
            for line in text.splitlines()
            if "org.opencontainers.image.description" in line
        )
        self.assertNotIn("terminal", description.lower())

    def test_rstudio_installs_and_load_checks_advertised_packages(self):
        text = dockerfile("rstudio-server")
        for package in ("tidyverse", "data.table", "reticulate"):
            self.assertGreaterEqual(text.count(f'"{package}"'), 2)
        self.assertIn("library(p, character.only = TRUE)", text)
        self.assertIn("labpod-rstudio", text)

    def test_other_published_recipes_keep_existing_hardening(self):
        expected = {
            "miniforge-jupyterlab": ("conda clean -afy", "userdel ubuntu", "curl"),
            "uv-jupyterlab": ("UV_SYSTEM_PYTHON=1", "uv pip install", "curl"),
            "llm-huggingface": ("uv_path=", "--index-url", "git lfs install --system"),
            "comfyui-stable-diffusion": ("uv_path=", "COMFYUI_REF", "folder_paths"),
            "cuda-composite": ("uv_path=", "btop || true", "sha256sum -c"),
            "parallel-dev": ("cuda-nsight-systems", "mpicc", "code-server"),
        }
        for name, markers in expected.items():
            text = dockerfile(name)
            for marker in markers:
                with self.subTest(image=name, marker=marker):
                    self.assertIn(marker, text)

    def test_cuda_python_recipes_use_an_isolated_venv(self):
        for name in (
            "llm-huggingface",
            "comfyui-stable-diffusion",
            "cuda-composite",
        ):
            text = dockerfile(name)
            with self.subTest(image=name):
                self.assertIn("VIRTUAL_ENV=/opt/venv", text)
                self.assertIn("PATH=/opt/venv/bin:${PATH}", text)
                self.assertIn('python3 -m venv "$VIRTUAL_ENV"', text)
                self.assertIn('"$VIRTUAL_ENV/bin/python" -m pip install --no-cache-dir uv', text)
                self.assertIn('uv pip install --python "$VIRTUAL_ENV/bin/python"', text)
                self.assertNotIn("uv pip install --system", text)
                self.assertNotIn("--break-system-packages", text)

    def test_comfyui_launcher_creates_its_required_runtime_tree(self):
        text = dockerfile("comfyui-stable-diffusion")
        self.assertIn("mkdir -p /work/comfyui/custom_nodes", text)

    def test_comfyui_declares_and_import_checks_frontend_requests(self):
        text = dockerfile("comfyui-stable-diffusion")
        self.assertIn("/opt/ComfyUI/requirements.txt requests", text)
        self.assertIn("import app.frontend_management", text)

    def test_parallel_dev_contains_no_microsoft_browser_editor_artifact(self):
        text = dockerfile("parallel-dev")
        self.assertNotIn("update.code.visualstudio.com", text)
        self.assertNotIn("code serve-web", text)


if __name__ == "__main__":
    unittest.main()
