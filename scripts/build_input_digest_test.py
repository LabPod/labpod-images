import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build-input-digest.py")
SPEC = importlib.util.spec_from_file_location("build_input_digest", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BuildInputDigestTest(unittest.TestCase):
    def make_context(self, root):
        context = Path(root)
        (context / "Dockerfile").write_bytes(
            b"ARG BASE=docker.io/library/ubuntu:24.04\n"
            b"FROM ${BASE} AS build\n"
            b"FROM build\n"
            b"COPY requirements.txt /tmp/\n"
        )
        (context / "requirements.txt").write_bytes(b"jupyterlab==4.4.0\n")
        return context

    def test_digest_is_stable_and_has_contract_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            context = self.make_context(directory)
            first = MODULE.build_input_digest(
                context, context / "Dockerfile", {"BASE": "example/base:v1"}
            )
            second = MODULE.build_input_digest(
                context, context / "Dockerfile", {"BASE": "example/base:v1"}
            )
            self.assertEqual(first, second)
            self.assertEqual(
                first,
                "sha256:b570f447a4366fd0ebea99155fea822447a5d4fc70ab18cfe097d2b673d9d9de",
            )
            self.assertRegex(first, r"^sha256:[0-9a-f]{64}$")

    def test_digest_covers_context_args_and_arg_expanded_external_bases(self):
        with tempfile.TemporaryDirectory() as directory:
            context = self.make_context(directory)
            baseline = MODULE.build_input_digest(
                context, context / "Dockerfile", {"BASE": "example/base:v1"}
            )
            (context / "requirements.txt").write_bytes(b"jupyterlab==4.4.1\n")
            changed_file = MODULE.build_input_digest(
                context, context / "Dockerfile", {"BASE": "example/base:v1"}
            )
            changed_base = MODULE.build_input_digest(
                context, context / "Dockerfile", {"BASE": "example/base:v2"}
            )
            self.assertNotEqual(baseline, changed_file)
            self.assertNotEqual(changed_file, changed_base)

    def test_context_order_does_not_change_digest_and_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            context = self.make_context(directory)
            (context / "z.txt").write_text("z")
            (context / "a.txt").write_text("a")
            digest = MODULE.build_input_digest(context, context / "Dockerfile", {})
            self.assertEqual(
                digest,
                MODULE.build_input_digest(context, context / "Dockerfile", {}),
            )
            (context / "linked").symlink_to("a.txt")
            with self.assertRaisesRegex(ValueError, "symlink"):
                MODULE.build_input_digest(context, context / "Dockerfile", {})

    def test_malformed_heredoc_instructions_do_not_produce_a_digest(self):
        for instruction, error in (
            ("RUN <<-EOF\n EOF\n", "unterminated Dockerfile heredoc"),
            ("RUN <<''\n", "unterminated Dockerfile heredoc"),
            ("RUN <<'EOF\n", "unterminated quote"),
            ("RUN <<EOF \\\n", "dangling line continuation"),
        ):
            with self.subTest(instruction=instruction), tempfile.TemporaryDirectory() as directory:
                context = Path(directory)
                (context / "Dockerfile").write_text("FROM scratch\n" + instruction)
                with self.assertRaisesRegex(ValueError, error):
                    MODULE.build_input_digest(context, context / "Dockerfile", {})

    def test_bare_global_arg_without_override_expands_to_empty(self):
        self.assertEqual(
            MODULE.base_images(b"ARG variant\nFROM alpine:3.20${variant}\n", {}),
            ["docker.io/library/alpine:3.20"],
        )

    def test_tab_delimited_global_arg_expands_in_from(self):
        self.assertEqual(
            MODULE.base_images(b"ARG\tBASE=alpine:3.20\nFROM ${BASE}\n", {}),
            ["docker.io/library/alpine:3.20"],
        )

    def test_cli_parses_multiline_build_args(self):
        self.assertEqual(
            MODULE.parse_build_args("B=two\nA=one\nEMPTY="),
            {"A": "one", "B": "two", "EMPTY": ""},
        )


if __name__ == "__main__":
    unittest.main()
