import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
REMOTE_ACTION = re.compile(
    r"^\s*(?:-\s*)?uses:\s*(?P<action>[^\s#]+)@(?P<ref>[^\s#]+)",
    re.MULTILINE,
)
FULL_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")


class WorkflowSecurityTest(unittest.TestCase):
    def test_remote_actions_are_pinned_to_full_commit_shas(self):
        unpinned = []
        for workflow in sorted(WORKFLOWS.glob("*.y*ml")):
            for match in REMOTE_ACTION.finditer(workflow.read_text()):
                action = match.group("action")
                if action.startswith("./"):
                    continue
                ref = match.group("ref")
                if not FULL_COMMIT_SHA.fullmatch(ref):
                    line = workflow.read_text().count("\n", 0, match.start()) + 1
                    unpinned.append(f"{workflow.relative_to(ROOT)}:{line}: {action}@{ref}")

        self.assertEqual(
            unpinned,
            [],
            "remote actions must use immutable 40-character commit SHAs:\n"
            + "\n".join(unpinned),
        )


if __name__ == "__main__":
    unittest.main()
